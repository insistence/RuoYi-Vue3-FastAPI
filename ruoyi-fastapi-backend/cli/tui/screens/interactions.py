import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from textual.app import SuspendNotSupported

from cli.tui.actions import (
    TUI_ACTION_EXECUTION_SERVICE,
    TUI_ACTION_PRESENTATION_SERVICE,
    TuiActionResult,
    TuiActionSpec,
)
from cli.tui.copy import TUI_COPY
from cli.tui.screens.confirm import ActionConfirmScreen
from cli.tui.screens.search import SearchInputScreen
from cli.tui.search import PageSearchContext
from cli.tui.widgets import WorkspaceSidebar


class TuiScreenInteractionService:
    """
    TUI 屏幕交互服务。

    该服务负责搜索弹窗、搜索状态写回、动作确认弹窗和动作执行通知等
    屏幕级交互流程，减少浏览页与详情页之间的重复控制逻辑。
    """

    @staticmethod
    def open_search_dialog(
        screen: Any,
        search_context: PageSearchContext | None,
        callback: Callable[[str | None], None],
    ) -> None:
        """
        打开搜索输入弹窗。

        :param screen: 当前屏幕对象
        :param search_context: 搜索上下文
        :param callback: 提交搜索词后的回调
        :return: None
        """
        if search_context is None:
            return
        screen.app.push_screen(
            SearchInputScreen(
                '页内搜索',
                search_context.placeholder,
                search_context.query,
                search_context.suggestions,
            ),
            callback=callback,
        )

    @staticmethod
    def remember_query_and_refresh(screen: Any, active_view: str, query: str | None) -> None:
        """
        记录当前页面搜索词并刷新页面。

        :param screen: 当前屏幕对象
        :param active_view: 当前页面视图标识
        :param query: 搜索词
        :return: None
        """
        if query is None:
            return
        remember_query = getattr(screen.app, 'remember_browser_query', None)
        if callable(remember_query):
            remember_query(active_view, query)
        screen.app.action_refresh_current_view()

    def clear_query_and_refresh(self, screen: Any, active_view: str, current_query: str) -> None:
        """
        清空当前页面搜索词并刷新页面。

        :param screen: 当前屏幕对象
        :param active_view: 当前页面视图标识
        :param current_query: 当前搜索词
        :return: None
        """
        if not current_query:
            return
        self.remember_query_and_refresh(screen, active_view, '')

    @staticmethod
    def open_action_confirm(
        screen: Any,
        action: TuiActionSpec | None,
        callback: Callable[[bool | None, TuiActionSpec], None],
    ) -> None:
        """
        打开动作确认弹窗。

        :param screen: 当前屏幕对象
        :param action: 待执行动作
        :param callback: 确认回调
        :return: None
        """
        if action is None:
            screen.notify(
                TUI_COPY.build_action_unavailable_message(),
                title=TUI_COPY.build_action_notification_title(),
                severity='warning',
            )
            return
        screen.app.push_screen(
            ActionConfirmScreen(action.preview_title, action.preview_lines, action.label),
            callback=lambda confirmed, action=action: callback(confirmed, action),
        )

    @staticmethod
    def schedule_action_task(
        existing_task: asyncio.Task[None] | None,
        action: TuiActionSpec,
        execute_callback: Callable[[TuiActionSpec], Awaitable[None]],
    ) -> asyncio.Task[None]:
        """
        安排动作执行任务，并在必要时取消旧任务。

        :param existing_task: 现有动作任务
        :param action: 待执行动作
        :param execute_callback: 动作执行协程工厂
        :return: 新建任务
        """
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()
        return asyncio.create_task(execute_callback(action))

    def confirm_and_schedule_action(
        self,
        screen: Any,
        action: TuiActionSpec | None,
        existing_task: asyncio.Task[None] | None,
        execute_callback: Callable[[TuiActionSpec], Awaitable[None]],
    ) -> asyncio.Task[None] | None:
        """
        统一处理动作确认结果，并在确认后调度后台执行任务。

        :param screen: 当前屏幕对象
        :param action: 待执行动作
        :param existing_task: 当前已有动作任务
        :param execute_callback: 动作执行协程工厂
        :return: 新建任务或原任务
        """
        if action is None:
            self.open_action_confirm(screen, action, lambda confirmed, action_spec: None)
            return existing_task

        scheduled_task = existing_task

        def _handle_confirmed(confirmed: bool | None, action_spec: TuiActionSpec) -> None:
            nonlocal scheduled_task
            if not confirmed:
                return
            scheduled_task = self.schedule_action_task(
                scheduled_task,
                action_spec,
                execute_callback,
            )

        self.open_action_confirm(screen, action, _handle_confirmed)
        return scheduled_task

    async def execute_action(
        self,
        screen: Any,
        action: TuiActionSpec,
        env: str,
        active_view: str,
        *,
        on_result: Callable[[TuiActionResult, list[str]], Any] | None = None,
    ) -> TuiActionResult:
        """
        执行屏幕动作并统一处理通知、反馈持久化与刷新。

        :param screen: 当前屏幕对象
        :param action: 动作定义
        :param env: 当前运行环境
        :param active_view: 当前页面视图标识
        :param on_result: 动作结果回调
        :return: 动作结果
        """
        screen.notify(
            TUI_COPY.build_action_running_message(action.label),
            title=TUI_COPY.build_action_notification_title(),
        )
        if action.execution_mode == 'external':
            try:
                with screen.app.suspend():
                    result = TUI_ACTION_EXECUTION_SERVICE.execute_external(action)
            except SuspendNotSupported:
                result = TuiActionResult(
                    spec=action,
                    external_exit_code=1,
                    external_message='当前终端不支持挂起 TUI，无法打开外部交互向导',
                )
        else:
            result = await asyncio.to_thread(TUI_ACTION_EXECUTION_SERVICE.execute, action, env)

        feedback_lines = TUI_ACTION_EXECUTION_SERVICE.build_result_lines(result)
        remember_feedback = getattr(screen.app, 'remember_action_feedback', None)
        if callable(remember_feedback):
            remember_feedback(active_view, feedback_lines)
        if on_result is not None:
            maybe_result = on_result(result, feedback_lines)
            if inspect.isawaitable(maybe_result):
                await maybe_result
        screen.notify(
            TUI_ACTION_PRESENTATION_SERVICE.build_action_result_message(result),
            title=TUI_COPY.build_action_notification_title(),
            severity='information' if result.ok else 'error',
        )
        if result.ok and action.refresh_view:
            screen.app.action_refresh_current_view()
        return result

    async def execute_action_with_feedback(
        self,
        screen: Any,
        action: TuiActionSpec,
        env: str,
        active_view: str,
        feedback_callback: Callable[[TuiActionResult, list[str]], Any],
    ) -> TuiActionResult:
        """
        执行动作并将统一反馈回调注入结果收口流程。

        :param screen: 当前屏幕对象
        :param action: 动作定义
        :param env: 当前运行环境
        :param active_view: 当前页面视图标识
        :param feedback_callback: 反馈写回回调
        :return: 动作结果
        """
        return await self.execute_action(
            screen,
            action,
            env,
            active_view,
            on_result=feedback_callback,
        )


class ScreenInteractionActionsMixin:
    """
    屏幕交互动作混入。

    该混入负责把搜索、动作确认和侧栏切屏这类重复桥接 action 收口为
    通用 Screen 方法，具体页面只需实现对应的私有协作方法。
    """

    def _open_search(self) -> None:
        """
        打开当前页面搜索输入弹窗。

        :return: None
        """

    def _clear_search(self) -> None:
        """
        清空当前页面搜索词。

        :return: None
        """

    def _open_action_confirm(self, slot: str) -> None:
        """
        打开指定槽位动作的确认弹窗。

        :param slot: 动作槽位
        :return: None
        """

    def _open_sidebar_item(self, event: WorkspaceSidebar.Highlighted | WorkspaceSidebar.Selected) -> None:
        """
        根据侧栏事件打开对应视图。

        :param event: 侧栏事件
        :return: None
        """

    def action_open_search(self) -> None:
        """
        打开当前页面搜索输入。

        :return: None
        """
        self._open_search()

    def action_clear_search(self) -> None:
        """
        清空当前页面搜索词。

        :return: None
        """
        self._clear_search()

    def action_trigger_primary_action(self) -> None:
        """
        触发当前页面主动作。

        :return: None
        """
        self._open_action_confirm('primary')

    def action_trigger_secondary_action(self) -> None:
        """
        触发当前页面次动作。

        :return: None
        """
        self._open_action_confirm('secondary')

    def action_trigger_global_action(self) -> None:
        """
        触发当前页面全局动作。

        :return: None
        """
        self._open_action_confirm('global')

    def action_trigger_utility_action(self) -> None:
        """
        触发当前页面工具动作。

        :return: None
        """
        self._open_action_confirm('utility')


TUI_SCREEN_INTERACTION_SERVICE = TuiScreenInteractionService()
