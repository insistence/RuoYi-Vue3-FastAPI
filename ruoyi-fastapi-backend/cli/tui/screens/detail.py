import asyncio

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Footer

from cli.tui.actions import (
    TUI_ACTION_PRESENTATION_SERVICE,
    TUI_ACTION_REGISTRY,
    TuiActionResult,
    TuiActionSpec,
)
from cli.tui.adapters import DetailPageSnapshot, DetailSectionSnapshot
from cli.tui.adapters.models import TUI_ADAPTER_MODEL_RENDERER
from cli.tui.copy import TUI_COPY
from cli.tui.screens.focus import BaseScreenFocusService, ScreenFocusActionsMixin
from cli.tui.screens.interactions import TUI_SCREEN_INTERACTION_SERVICE, ScreenInteractionActionsMixin
from cli.tui.screens.summary import STATUS_SUMMARY_BUILDER
from cli.tui.widgets import (
    NavigationItem,
    SectionDetailView,
    SectionNavigator,
    WorkspaceHeader,
    WorkspaceHero,
    WorkspaceSidebar,
)


class DetailScreenSupport:
    """
    详情页屏幕支持对象。

    该对象负责详情页摘要、搜索词、动作解析与空态分区构建，
    使 `DetailScreen` 本体主要保留 Textual 事件桥接。
    """

    @staticmethod
    def build_empty_section() -> DetailSectionSnapshot:
        """
        构建详情页空态兜底分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title=TUI_COPY.build_detail_empty_section_copy('title'),
            status='info',
            lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                empty_label=TUI_COPY.build_detail_empty_section_copy('label'),
                empty_value=TUI_COPY.build_detail_empty_section_copy('value'),
                detail=TUI_COPY.build_detail_empty_section_copy('detail_page'),
            ),
        )

    @staticmethod
    def build_summary_text(snapshot: DetailPageSnapshot, active_view: str) -> str:
        """
        构建详情页摘要文本。

        :param snapshot: 页面快照
        :param active_view: 当前激活视图
        :return: 摘要文本
        """
        summary = STATUS_SUMMARY_BUILDER.build(snapshot.sections)
        return (
            TUI_COPY.build_detail_summary_text(
                total_count=summary.total_count,
                ok_count=summary.ok_count,
                warn_count=summary.warn_count,
                fail_count=summary.fail_count,
            )
            + f' {TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint(active_view)}'
        )

    @staticmethod
    def current_search_query(snapshot: DetailPageSnapshot) -> str:
        """
        读取当前详情页搜索词。

        :param snapshot: 页面快照
        :return: 搜索词
        """
        search_context = snapshot.search
        return search_context.query if search_context is not None else ''

    @staticmethod
    def resolve_action(*, active_view: str, slot: str, env: str) -> TuiActionSpec | None:
        """
        解析当前详情页指定槽位对应的动作。

        :param active_view: 当前激活视图
        :param slot: 动作槽位
        :param env: 当前运行环境
        :return: 动作定义
        """
        return TUI_ACTION_REGISTRY.resolve_detail_action(
            view_key=active_view,
            slot=slot,  # type: ignore[arg-type]
            env=env,
        )


class DetailScreenFocusService(BaseScreenFocusService):
    """
    详情页焦点服务。

    该对象负责定义详情页可聚焦组件顺序，以及按左右键和滚动键解析
    当前目标区域。
    """

    def get_focus_order(self, screen: 'DetailScreen') -> list[WorkspaceSidebar | SectionNavigator | SectionDetailView]:
        """
        定义详情页可通过左右键切换的焦点顺序。

        :param screen: 当前详情页屏幕
        :return: 焦点顺序列表
        """
        return [
            screen.query_one(WorkspaceSidebar),
            screen.query_one(SectionNavigator),
            screen.query_one(SectionDetailView),
        ]

    def get_default_scroll_target(
        self,
        screen: 'DetailScreen',
    ) -> ScrollableContainer:
        """
        返回详情页默认滚动容器。

        :param screen: 当前详情页屏幕
        :return: 主工作区滚动容器
        """
        return screen.query_one('#workspace-main', ScrollableContainer)


class DetailScreen(ScreenInteractionActionsMixin, ScreenFocusActionsMixin, Screen[None]):
    """
    TUI 通用详情屏幕。

    :param snapshot: 页面快照
    """

    BINDINGS = [
        Binding('left', 'focus_left', TUI_COPY.build_internal_binding_label('focus_left'), show=False),
        Binding('right', 'focus_right', TUI_COPY.build_internal_binding_label('focus_right'), show=False),
        Binding('j', 'scroll_focus_down', TUI_COPY.build_internal_binding_label('scroll_down'), show=False),
        Binding('k', 'scroll_focus_up', TUI_COPY.build_internal_binding_label('scroll_up'), show=False),
        Binding('pagedown', 'scroll_focus_page_down', TUI_COPY.build_internal_binding_label('page_down'), show=False),
        Binding('pageup', 'scroll_focus_page_up', TUI_COPY.build_internal_binding_label('page_up'), show=False),
        Binding('home', 'scroll_focus_home', TUI_COPY.build_internal_binding_label('home'), show=False),
        Binding('end', 'scroll_focus_end', TUI_COPY.build_internal_binding_label('end'), show=False),
        Binding('x', 'trigger_primary_action', TUI_COPY.build_internal_binding_label('action_primary'), show=False),
        Binding('z', 'trigger_secondary_action', TUI_COPY.build_internal_binding_label('action_secondary'), show=False),
        Binding('y', 'trigger_global_action', TUI_COPY.build_internal_binding_label('action_global'), show=False),
        Binding('w', 'trigger_utility_action', TUI_COPY.build_internal_binding_label('action_utility'), show=False),
        Binding('/', 'open_search', TUI_COPY.build_internal_binding_label('search'), show=False),
        Binding('backspace', 'clear_search', TUI_COPY.build_internal_binding_label('clear_search'), show=False),
    ]

    def __init__(
        self,
        snapshot: DetailPageSnapshot,
        env: str,
        active_view: str,
        navigation_items: list[NavigationItem],
        refreshed_at: str,
        support: DetailScreenSupport | None = None,
        focus_service: DetailScreenFocusService | None = None,
    ) -> None:
        """
        初始化通用详情屏幕。

        :param snapshot: 页面快照
        :param env: 当前运行环境
        :param active_view: 当前激活视图
        :param navigation_items: 导航项列表
        :param refreshed_at: 本次刷新时间
        :param support: 详情页屏幕支持对象
        :param focus_service: 详情页焦点服务
        :return: None
        """
        self.snapshot = snapshot
        self.env = env
        self.active_view = active_view
        self.navigation_items = navigation_items
        self.refreshed_at = refreshed_at
        self.selected_section_index = 0
        self._last_action_result: TuiActionResult | None = None
        self._action_feedback_lines: list[str] = []
        self._action_task: asyncio.Task[None] | None = None
        self.support = support or DetailScreenSupport()
        self.focus_service = focus_service or DetailScreenFocusService()
        super().__init__()

    @staticmethod
    def _cancel_task(task: asyncio.Task[None] | None) -> None:
        """
        取消指定后台任务。

        :param task: 待取消任务
        :return: None
        """
        if task is None or task.done():
            return
        task.cancel()

    def _get_section_or_fallback(self, index: int) -> DetailSectionSnapshot:
        """
        获取指定索引的分区快照，缺失时返回兜底分区。

        :param index: 分区索引
        :return: 分区快照
        """
        if 0 <= index < len(self.snapshot.sections):
            return self.snapshot.sections[index]
        return self.support.build_empty_section()

    def _build_summary_text(self) -> str:
        """
        构建详情页摘要文本。

        :return: 摘要文本
        """
        return self.support.build_summary_text(self.snapshot, self.active_view)

    def _current_search_query(self) -> str:
        return self.support.current_search_query(self.snapshot)

    def _open_search(self) -> None:
        """
        打开当前详情页搜索输入弹窗。

        :return: None
        """
        TUI_SCREEN_INTERACTION_SERVICE.open_search_dialog(
            self,
            self.snapshot.search,
            self._handle_search_submitted,
        )

    def _handle_search_submitted(self, query: str | None) -> None:
        """
        处理详情页搜索输入结果。

        :param query: 搜索词
        :return: None
        """
        TUI_SCREEN_INTERACTION_SERVICE.remember_query_and_refresh(self, self.active_view, query)

    def _clear_search(self) -> None:
        """
        清空当前详情页搜索词。

        :return: None
        """
        TUI_SCREEN_INTERACTION_SERVICE.clear_query_and_refresh(
            self,
            self.active_view,
            self._current_search_query(),
        )

    def _resolve_action(self, slot: str) -> TuiActionSpec | None:
        """
        解析当前详情页指定槽位对应的动作。

        :param slot: 动作槽位
        :return: 动作定义
        """
        return self.support.resolve_action(active_view=self.active_view, slot=slot, env=self.env)

    def _open_action_confirm(self, slot: str) -> None:
        """
        打开指定槽位动作的确认弹窗。

        :param slot: 动作槽位
        :return: None
        """
        self._action_task = TUI_SCREEN_INTERACTION_SERVICE.confirm_and_schedule_action(
            self,
            self._resolve_action(slot),
            self._action_task,
            self._execute_action,
        )

    async def _execute_action(self, action: TuiActionSpec) -> None:
        """
        执行详情页动作。

        :param action: 动作定义
        :return: None
        """

        def _handle_result(result: TuiActionResult, feedback_lines: list[str]) -> None:
            self._last_action_result = result
            self._action_feedback_lines = feedback_lines

        await TUI_SCREEN_INTERACTION_SERVICE.execute_action_with_feedback(
            self,
            action,
            self.env,
            self.active_view,
            _handle_result,
        )

    def _update_selected_section(self, index: int) -> None:
        """
        更新当前选中分区，并同步右侧详情视图。

        :param index: 待选中的分区索引
        :return: None
        """
        if not self.snapshot.sections:
            detail_view = self.query_one(SectionDetailView)
            detail_view.show_section(self._get_section_or_fallback(index), query=self._current_search_query())
            return
        if not 0 <= index < len(self.snapshot.sections):
            return
        self.selected_section_index = index
        detail_view = self.query_one(SectionDetailView)
        detail_view.show_section(self.snapshot.sections[index], query=self._current_search_query())

    def compose(self) -> ComposeResult:
        """
        构建详情页界面结构。

        :return: Textual 组件结果
        """
        yield WorkspaceHeader(self.env, self.active_view)
        with Horizontal(id='workspace-shell'):
            yield WorkspaceSidebar(self.env, self.navigation_items, self.active_view)
            with ScrollableContainer(id='workspace-main'):
                yield WorkspaceHero(
                    title=self.snapshot.title,
                    subtitle=self.snapshot.subtitle,
                    env=self.env,
                    active_view=self.active_view,
                    summary=self._build_summary_text(),
                    refreshed_at=self.refreshed_at,
                )
                with Horizontal(id='detail-body'):
                    yield SectionNavigator(
                        self.snapshot.sections,
                        initial_index=self.selected_section_index,
                        query=self._current_search_query(),
                    )
                    yield SectionDetailView(
                        self._get_section_or_fallback(self.selected_section_index),
                        query=self._current_search_query(),
                    )
        yield Footer()

    def on_mount(self) -> None:
        """
        详情页挂载后默认将焦点停留在左侧导航。

        :return: None
        """
        self.call_after_refresh(self.query_one(WorkspaceSidebar).focus)

    def on_unmount(self) -> None:
        """
        详情页卸载时取消尚未完成的后台任务。

        :return: None
        """
        self._cancel_task(self._action_task)

    def _open_sidebar_item(self, event: WorkspaceSidebar.Highlighted | WorkspaceSidebar.Selected) -> None:
        """
        根据侧边栏事件打开对应视图，并避免重复打开当前页面。

        :param event: 侧边栏高亮或选中事件
        :return: None
        """
        item = getattr(event.item, 'item', None)
        if not isinstance(item, NavigationItem):
            return
        if item.view_key == self.active_view:
            return
        self.app.open_view(item.view_key)

    @on(WorkspaceSidebar.Selected)
    def on_sidebar_selected(self, event: WorkspaceSidebar.Selected) -> None:
        """
        响应左侧导航选中事件并切换视图。

        :param event: 导航选中事件
        :return: None
        """
        self._open_sidebar_item(event)

    @on(WorkspaceSidebar.Highlighted)
    def on_sidebar_highlighted(self, event: WorkspaceSidebar.Highlighted) -> None:
        """
        响应左侧导航高亮变更并立即切换视图。

        :param event: 导航高亮事件
        :return: None
        """
        self._open_sidebar_item(event)

    @on(SectionNavigator.Changed)
    def on_section_changed(self, event: SectionNavigator.Changed) -> None:
        """
        响应分区导航高亮变更并更新详情内容。

        :param event: 分区导航高亮事件
        :return: None
        """
        self._update_selected_section(event.index)
