import asyncio

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from cli.tui.actions import (
    TUI_ACTION_PRESENTATION_SERVICE,
    TUI_ACTION_REGISTRY,
    TuiActionResult,
    TuiActionSpec,
)
from cli.tui.adapters import BrowserPageSnapshot, BrowserRecordSnapshot, DetailSectionSnapshot
from cli.tui.adapters.models import TUI_ADAPTER_MODEL_RENDERER
from cli.tui.copy import TUI_COPY
from cli.tui.screens.focus import BaseScreenFocusService, ScreenFocusActionsMixin
from cli.tui.screens.interactions import TUI_SCREEN_INTERACTION_SERVICE, ScreenInteractionActionsMixin
from cli.tui.screens.summary import STATUS_SUMMARY_BUILDER
from cli.tui.search import TUI_SEARCH_SERVICE
from cli.tui.widgets import (
    NavigationItem,
    RecordNavigator,
    RecordSummaryView,
    SectionDetailView,
    SectionNavigator,
    WorkspaceHeader,
    WorkspaceHero,
    WorkspaceSidebar,
)


class BrowserScreenSupport:
    """
    浏览页屏幕支持对象。

    该对象负责浏览页摘要、搜索词、动作解析、空态/加载态分区构建和
    焦点顺序编排，使 `BrowserScreen` 本体主要保留 Textual 事件桥接。
    """

    @staticmethod
    def build_summary_text(snapshot: BrowserPageSnapshot, active_view: str) -> str:
        """
        构建浏览页摘要文本。

        :param snapshot: 浏览页快照
        :param active_view: 当前激活视图
        :return: 摘要文本
        """
        summary = STATUS_SUMMARY_BUILDER.build(snapshot.records)
        return TUI_COPY.build_browser_summary_text(
            total_count=summary.total_count,
            ok_count=summary.ok_count,
            warn_count=summary.warn_count,
            fail_count=summary.fail_count,
            action_hint=TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint(active_view),
        )

    @staticmethod
    def build_filter_bar_text(snapshot: BrowserPageSnapshot) -> str:
        """
        构建当前浏览页筛选条文本。

        :param snapshot: 浏览页快照
        :return: 筛选条文本
        """
        search_context = snapshot.search
        return TUI_SEARCH_SERVICE.build_filter_bar_text(
            snapshot.filters,
            snapshot.active_filter_key,
            search_query=search_context.query if search_context is not None else '',
            search_placeholder=search_context.placeholder if search_context is not None else '',
            search_suggestions=search_context.suggestions if search_context is not None else [],
        )

    @staticmethod
    def current_search_query(snapshot: BrowserPageSnapshot) -> str:
        """
        读取当前浏览页搜索词。

        :param snapshot: 浏览页快照
        :return: 搜索词
        """
        search_context = snapshot.search
        return search_context.query if search_context is not None else ''

    @staticmethod
    def resolve_action(
        *,
        active_view: str,
        slot: str,
        record: BrowserRecordSnapshot,
        env: str,
    ) -> TuiActionSpec | None:
        """
        解析当前页面指定槽位对应的动作。

        :param active_view: 当前激活视图
        :param slot: 动作槽位
        :param record: 当前选中记录
        :param env: 当前运行环境
        :return: 动作定义
        """
        return TUI_ACTION_REGISTRY.resolve_browser_action(
            view_key=active_view,
            slot=slot,  # type: ignore[arg-type]
            record=record,
            env=env,
        )

    @staticmethod
    def build_record_action_lines(
        *,
        active_view: str,
        record: BrowserRecordSnapshot,
        env: str,
        feedback_lines: list[str],
    ) -> list[str]:
        """
        构建当前记录动作面板文本。

        :param active_view: 当前激活视图
        :param record: 当前记录
        :param env: 当前运行环境
        :param feedback_lines: 最近动作反馈文本
        :return: 动作面板文本
        """
        action_lines = TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_lines(
            view_key=active_view,
            record=record,
            env=env,
        )
        return TUI_COPY.build_browser_action_panel_lines(action_lines, feedback_lines)

    @staticmethod
    def build_empty_record() -> BrowserRecordSnapshot:
        """
        构建浏览页空态兜底记录。

        :return: 记录快照
        """
        return BrowserRecordSnapshot(
            key='empty',
            title=TUI_COPY.build_browser_empty_record_copy('title'),
            status='info',
            summary=TUI_COPY.build_browser_empty_record_copy('summary'),
            metadata_lines=[],
            detail_sections=[
                DetailSectionSnapshot(
                    title=TUI_COPY.build_browser_empty_record_copy('title'),
                    status='info',
                    lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                        empty_label=TUI_COPY.build_browser_empty_record_copy('label'),
                        empty_value=TUI_COPY.build_browser_empty_record_copy('value'),
                        detail=TUI_COPY.build_browser_empty_record_copy('detail'),
                    ),
                )
            ],
        )

    @staticmethod
    def build_loading_section() -> DetailSectionSnapshot:
        """
        构建详情加载中的占位分区。

        :return: 占位分区
        """
        return DetailSectionSnapshot(
            title=TUI_COPY.build_browser_loading_copy('title'),
            status='info',
            lines=TUI_ADAPTER_MODEL_RENDERER.build_loading_lines(
                loading_label=TUI_COPY.build_browser_loading_copy('label'),
                loading_value=TUI_COPY.build_browser_loading_copy('value'),
                detail=TUI_COPY.build_browser_loading_copy('detail'),
            ),
        )

    @staticmethod
    def build_detail_load_failure_sections(error: Exception, resource_name: str) -> list[DetailSectionSnapshot]:
        """
        构建详情加载失败时的兜底分区。

        :param error: 后台加载异常
        :param resource_name: 资源名称
        :return: 失败分区列表
        """
        return [
            DetailSectionSnapshot(
                title=TUI_COPY.build_load_failure_section_title(resource_name),
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    {
                        'message': '后台详情加载失败',
                        'error': str(error) or error.__class__.__name__,
                        'hint': '可按 [R] 刷新当前页面，或切换记录后重试',
                    },
                    empty_label='详情状态',
                    empty_value='不可用',
                ),
            )
        ]

    @staticmethod
    def build_empty_section() -> DetailSectionSnapshot:
        """
        构建浏览页详情空态兜底分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title=TUI_COPY.build_detail_empty_section_copy('title'),
            status='info',
            lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                empty_label=TUI_COPY.build_detail_empty_section_copy('label'),
                empty_value=TUI_COPY.build_detail_empty_section_copy('value'),
                detail=TUI_COPY.build_detail_empty_section_copy('detail_record'),
            ),
        )


class BrowserScreenFocusService(BaseScreenFocusService):
    """
    浏览页焦点服务。

    该对象负责定义浏览页可聚焦组件顺序，以及按左右键和滚动键解析
    当前目标区域。
    """

    def get_focus_order(
        self,
        screen: 'BrowserScreen',
    ) -> list[WorkspaceSidebar | RecordNavigator | SectionNavigator | RecordSummaryView | SectionDetailView]:
        """
        定义浏览页可通过左右键切换的焦点顺序。

        :param screen: 当前浏览页屏幕
        :return: 焦点顺序列表
        """
        return [
            screen.query_one(WorkspaceSidebar),
            screen.query_one(RecordNavigator),
            screen.query_one(SectionNavigator),
            screen.query_one(RecordSummaryView),
            screen.query_one(SectionDetailView),
        ]

    def get_default_scroll_target(
        self,
        screen: 'BrowserScreen',
    ) -> ScrollableContainer:
        """
        返回浏览页默认滚动容器。

        :param screen: 当前浏览页屏幕
        :return: 主工作区滚动容器
        """
        return screen.query_one('#workspace-main', ScrollableContainer)


class BrowserScreen(ScreenInteractionActionsMixin, ScreenFocusActionsMixin, Screen[None]):
    """
    TUI 浏览型页面。

    :param snapshot: 浏览页快照
    :param env: 当前运行环境
    :param active_view: 当前激活视图
    :param navigation_items: 导航项列表
    :param refreshed_at: 本次刷新时间
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
        Binding('1', 'apply_filter_1', TUI_COPY.build_internal_binding_label('filter_1'), show=False),
        Binding('2', 'apply_filter_2', TUI_COPY.build_internal_binding_label('filter_2'), show=False),
        Binding('3', 'apply_filter_3', TUI_COPY.build_internal_binding_label('filter_3'), show=False),
        Binding('4', 'apply_filter_4', TUI_COPY.build_internal_binding_label('filter_4'), show=False),
        Binding('/', 'open_search', TUI_COPY.build_internal_binding_label('search'), show=False),
        Binding('backspace', 'clear_search', TUI_COPY.build_internal_binding_label('clear_search'), show=False),
    ]

    def __init__(
        self,
        snapshot: BrowserPageSnapshot,
        env: str,
        active_view: str,
        navigation_items: list[NavigationItem],
        refreshed_at: str,
        action_feedback_lines: list[str] | None = None,
        support: BrowserScreenSupport | None = None,
        focus_service: BrowserScreenFocusService | None = None,
    ) -> None:
        """
        初始化浏览型页面。

        :param snapshot: 浏览页快照
        :param env: 当前运行环境
        :param active_view: 当前激活视图
        :param navigation_items: 导航项列表
        :param refreshed_at: 本次刷新时间
        :param action_feedback_lines: 最近动作反馈文本
        :param support: 浏览页屏幕支持对象
        :param focus_service: 浏览页焦点服务
        :return: None
        """
        self.snapshot = snapshot
        self.env = env
        self.active_view = active_view
        self.navigation_items = navigation_items
        self.refreshed_at = refreshed_at
        self.selected_record_index = 0
        self.selected_section_index = 0
        self._is_syncing_sections = False
        self._record_detail_request_id = 0
        self._record_detail_task: asyncio.Task[None] | None = None
        self._action_task: asyncio.Task[None] | None = None
        self._last_action_result: TuiActionResult | None = None
        self._action_feedback_lines = list(action_feedback_lines or [])
        self.support = support or BrowserScreenSupport()
        self.focus_service = focus_service or BrowserScreenFocusService()
        super().__init__()

    def _build_summary_text(self) -> str:
        """
        构建浏览页摘要文本。

        :return: 摘要文本
        """
        return self.support.build_summary_text(self.snapshot, self.active_view)

    def _build_filter_bar_text(self) -> str:
        """
        构建当前浏览页筛选条文本。

        :return: 筛选条文本
        """
        return self.support.build_filter_bar_text(self.snapshot)

    def _current_search_query(self) -> str:
        return self.support.current_search_query(self.snapshot)

    def _apply_filter_shortcut(self, shortcut: str) -> None:
        """
        按快捷键切换当前浏览页筛选条件。

        :param shortcut: 筛选快捷键
        :return: None
        """
        if not self.snapshot.filters:
            return
        target = next((option for option in self.snapshot.filters if option.shortcut == shortcut), None)
        if target is None or target.key == self.snapshot.active_filter_key:
            return
        remember_filter = getattr(self.app, 'remember_browser_filter', None)
        if callable(remember_filter):
            remember_filter(self.active_view, target.key)
        self.app.action_refresh_current_view()

    def _open_search(self) -> None:
        """
        打开当前浏览页搜索输入弹窗。

        :return: None
        """
        TUI_SCREEN_INTERACTION_SERVICE.open_search_dialog(
            self,
            self.snapshot.search,
            self._handle_search_submitted,
        )

    def _handle_search_submitted(self, query: str | None) -> None:
        """
        处理页内搜索输入结果。

        :param query: 搜索词
        :return: None
        """
        TUI_SCREEN_INTERACTION_SERVICE.remember_query_and_refresh(self, self.active_view, query)

    def _clear_search(self) -> None:
        """
        清空当前浏览页搜索词。

        :return: None
        """
        TUI_SCREEN_INTERACTION_SERVICE.clear_query_and_refresh(
            self,
            self.active_view,
            self._current_search_query(),
        )

    def _resolve_action(self, slot: str) -> TuiActionSpec | None:
        """
        解析当前页面指定槽位对应的动作。

        :param slot: 动作槽位
        :return: 动作定义
        """
        return self.support.resolve_action(
            active_view=self.active_view,
            slot=slot,
            record=self._get_record_or_fallback(self.selected_record_index),
            env=self.env,
        )

    def _build_record_action_lines(self, record: BrowserRecordSnapshot) -> list[str]:
        """
        构建当前记录动作面板文本。

        :param record: 当前记录
        :return: 动作面板文本
        """
        return self.support.build_record_action_lines(
            active_view=self.active_view,
            record=record,
            env=self.env,
            feedback_lines=self._action_feedback_lines,
        )

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
        执行低风险动作并在结束后通知与刷新页面。

        :param action: 动作定义
        :return: None
        """

        async def _handle_result(result: TuiActionResult, feedback_lines: list[str]) -> None:
            self._last_action_result = result
            self._action_feedback_lines = feedback_lines
            await self._render_record_detail(eager=False)

        await TUI_SCREEN_INTERACTION_SERVICE.execute_action_with_feedback(
            self,
            action,
            self.env,
            self.active_view,
            _handle_result,
        )

    def _get_record_or_fallback(self, index: int) -> BrowserRecordSnapshot:
        """
        获取指定索引的记录快照，缺失时返回兜底记录。

        :param index: 记录索引
        :return: 记录快照
        """
        if 0 <= index < len(self.snapshot.records):
            return self.snapshot.records[index]
        return self.support.build_empty_record()

    def _build_loading_section(self) -> DetailSectionSnapshot:
        """
        构建详情加载中的占位分区。

        :return: 占位分区
        """
        return self.support.build_loading_section()

    def _build_detail_load_failure_sections(self, error: Exception) -> list[DetailSectionSnapshot]:
        """
        构建详情加载失败时的兜底分区。

        :param error: 后台加载异常
        :return: 失败分区列表
        """
        resource_name = self.snapshot.title if '详情' in self.snapshot.title else f'{self.snapshot.title}详情'
        return self.support.build_detail_load_failure_sections(error, resource_name)

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

    def _cancel_background_tasks(self) -> None:
        """
        取消当前屏幕持有的后台任务。

        :return: None
        """
        self._record_detail_request_id += 1
        self._cancel_task(self._record_detail_task)
        self._cancel_task(self._action_task)

    def _get_sections_for_record(self, index: int, *, eager: bool = False) -> list[DetailSectionSnapshot]:
        """
        获取指定记录对应的详情分区列表。

        :param index: 记录索引
        :param eager: 是否立即加载按需详情
        :return: 详情分区列表
        """
        record = self._get_record_or_fallback(index)
        if eager:
            try:
                detail_sections = record.resolve_detail_sections()
            except Exception as error:
                detail_sections = self._build_detail_load_failure_sections(error)
        elif record.detail_sections:
            detail_sections = record.detail_sections
        elif record._cached_detail_sections:
            detail_sections = list(record._cached_detail_sections)
        elif record.detail_loader is not None:
            detail_sections = [self._build_loading_section()]
        else:
            detail_sections = []
        return [*detail_sections, *self.snapshot.shared_sections]

    def _get_section_or_fallback(self, record_index: int, section_index: int) -> DetailSectionSnapshot:
        """
        获取指定记录下的分区快照，缺失时返回兜底分区。

        :param record_index: 记录索引
        :param section_index: 分区索引
        :return: 分区快照
        """
        sections = self._get_sections_for_record(record_index)
        if 0 <= section_index < len(sections):
            return sections[section_index]
        return self.support.build_empty_section()

    async def _render_record_detail(self, *, eager: bool = False) -> None:
        """
        根据当前选中记录刷新右侧详情区域。

        :param eager: 是否立即解析完整详情
        :return: None
        """
        record = self._get_record_or_fallback(self.selected_record_index)
        sections = self._get_sections_for_record(self.selected_record_index, eager=eager)
        selected_section = self._get_section_or_fallback(self.selected_record_index, self.selected_section_index)
        self.query_one(RecordSummaryView).show_record(
            record,
            selected_section,
            self._build_record_action_lines(record),
            self._current_search_query(),
        )
        navigator = self.query_one(SectionNavigator)
        detail_view = self.query_one(SectionDetailView)
        self._is_syncing_sections = True
        try:
            await navigator.show_sections(
                sections,
                initial_index=self.selected_section_index,
                query=self._current_search_query(),
            )
            detail_view.show_section(selected_section, query=self._current_search_query())
            self._sync_detail_pane_state(selected_section)
        finally:
            self._is_syncing_sections = False

    def _sync_detail_pane_state(self, section: DetailSectionSnapshot) -> None:
        """
        依据当前分区状态同步右侧详情容器样式。

        :param section: 当前分区快照
        :return: None
        """
        detail_pane = self.query_one('#browser-detail-pane', Vertical)
        detail_pane.remove_class('is-ok', 'is-fail', 'is-warn', 'is-info')
        normalized = section.status if section.status in {'ok', 'fail', 'warn'} else 'info'
        detail_pane.add_class(f'is-{normalized}')

    async def _load_record_detail_async(self, index: int, request_id: int) -> None:
        """
        在后台线程中加载指定记录的详情，并在仍为当前选中记录时回填界面。

        :param index: 记录索引
        :param request_id: 当前加载请求编号
        :return: None
        """
        record = self._get_record_or_fallback(index)
        try:
            await asyncio.to_thread(record.resolve_detail_sections)
        except Exception as error:
            failure_sections = self._build_detail_load_failure_sections(error)
            object.__setattr__(record, '_cached_detail_sections', tuple(failure_sections))
        if request_id != self._record_detail_request_id:
            return
        if index != self.selected_record_index:
            return
        await self._render_record_detail(eager=False)

    def _schedule_record_detail_load(self, index: int) -> None:
        """
        为当前选中记录安排一次后台详情加载。

        :param index: 记录索引
        :return: None
        """
        record = self._get_record_or_fallback(index)
        if record.detail_loader is None:
            return
        if record._cached_detail_sections:
            return
        self._cancel_task(self._record_detail_task)
        self._record_detail_request_id += 1
        self._record_detail_task = asyncio.create_task(
            self._load_record_detail_async(index, self._record_detail_request_id)
        )

    async def _update_selected_record(self, index: int) -> None:
        """
        更新当前选中记录，并同步右侧详情视图。

        :param index: 待选中的记录索引
        :return: None
        """
        if not self.snapshot.records:
            self.selected_record_index = 0
            self.selected_section_index = 0
            await self._render_record_detail(eager=False)
            return
        if not 0 <= index < len(self.snapshot.records):
            return
        if index == self.selected_record_index:
            return
        self.selected_record_index = index
        self.selected_section_index = 0
        await self._render_record_detail(eager=False)
        self._schedule_record_detail_load(index)

    def _update_selected_section(self, index: int) -> None:
        """
        更新当前选中分区，并同步最右侧详情内容。

        :param index: 分区索引
        :return: None
        """
        if self._is_syncing_sections:
            return
        sections = self._get_sections_for_record(self.selected_record_index)
        if not sections:
            detail_view = self.query_one(SectionDetailView)
            fallback = self._get_section_or_fallback(self.selected_record_index, index)
            detail_view.show_section(fallback, query=self._current_search_query())
            record = self._get_record_or_fallback(self.selected_record_index)
            self.query_one(RecordSummaryView).show_record(
                record,
                fallback,
                self._build_record_action_lines(record),
                self._current_search_query(),
            )
            self._sync_detail_pane_state(fallback)
            return
        if not 0 <= index < len(sections):
            return
        if index == self.selected_section_index:
            return
        self.selected_section_index = index
        current_section = sections[index]
        detail_view = self.query_one(SectionDetailView)
        detail_view.show_section(current_section, query=self._current_search_query())
        record = self._get_record_or_fallback(self.selected_record_index)
        self.query_one(RecordSummaryView).show_record(
            record,
            current_section,
            self._build_record_action_lines(record),
            self._current_search_query(),
        )
        self._sync_detail_pane_state(current_section)

    def on_mount(self) -> None:
        """
        浏览页挂载后默认将焦点停留在左侧导航。

        :return: None
        """
        self.call_after_refresh(self.query_one(WorkspaceSidebar).focus)
        self._schedule_record_detail_load(self.selected_record_index)

    def on_unmount(self) -> None:
        """
        浏览页卸载时取消尚未完成的后台任务。

        :return: None
        """
        self._cancel_background_tasks()

    def action_apply_filter_1(self) -> None:
        """
        应用第一个浏览页筛选条件。

        :return: None
        """
        self._apply_filter_shortcut('1')

    def action_apply_filter_2(self) -> None:
        """
        应用第二个浏览页筛选条件。

        :return: None
        """
        self._apply_filter_shortcut('2')

    def action_apply_filter_3(self) -> None:
        """
        应用第三个浏览页筛选条件。

        :return: None
        """
        self._apply_filter_shortcut('3')

    def action_apply_filter_4(self) -> None:
        """
        应用第四个浏览页筛选条件。

        :return: None
        """
        self._apply_filter_shortcut('4')

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

    def compose(self) -> ComposeResult:
        """
        构建浏览页界面结构。

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
                if self.snapshot.filters:
                    yield Static(self._build_filter_bar_text(), id='browser-filter-bar', markup=False)
                with Horizontal(id='browser-body'):
                    yield RecordNavigator(
                        self.snapshot.records,
                        initial_index=self.selected_record_index,
                        query=self._current_search_query(),
                    )
                    with Vertical(id='browser-detail-pane'):
                        yield RecordSummaryView(self._get_record_or_fallback(self.selected_record_index))
                        with Horizontal(id='browser-section-body'):
                            yield SectionNavigator(
                                self._get_sections_for_record(self.selected_record_index, eager=False),
                                initial_index=self.selected_section_index,
                                query=self._current_search_query(),
                            )
                            yield SectionDetailView(
                                self._get_section_or_fallback(
                                    self.selected_record_index,
                                    self.selected_section_index,
                                ),
                                query=self._current_search_query(),
                            )
        yield Footer()

    @on(RecordNavigator.Changed)
    async def on_record_changed(self, event: RecordNavigator.Changed) -> None:
        """
        响应记录导航高亮变更并更新详情内容。

        :param event: 记录导航高亮事件
        :return: None
        """
        await self._update_selected_record(event.index)

    @on(SectionNavigator.Changed)
    def on_section_changed(self, event: SectionNavigator.Changed) -> None:
        """
        响应记录详情分区高亮变更并更新最右侧详情内容。

        :param event: 分区导航高亮事件
        :return: None
        """
        self._update_selected_section(event.index)
