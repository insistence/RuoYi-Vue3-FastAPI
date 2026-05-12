from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Footer

from cli.tui.adapters import DashboardSnapshot
from cli.tui.copy import TUI_COPY
from cli.tui.keymaps import TUI_KEYMAP_REGISTRY
from cli.tui.screens.focus import BaseScreenFocusService, ScreenFocusActionsMixin
from cli.tui.screens.summary import STATUS_SUMMARY_BUILDER
from cli.tui.widgets import (
    MetricPanel,
    NavigationItem,
    SignalRail,
    StatusPanel,
    WorkspaceHeader,
    WorkspaceHero,
    WorkspaceSidebar,
)

PRIMARY_METRIC_COUNT = 2


class DashboardScreenSupport:
    """
    首页屏幕支持对象。

    该对象负责首页摘要文本、信号带文本和状态轨迹构建，
    使 `DashboardScreen` 本体主要保留 Textual 生命周期与界面编排。
    """

    @staticmethod
    def build_summary_text(snapshot: DashboardSnapshot) -> str:
        """
        构建首页摘要文本。

        :param snapshot: 首页聚合快照
        :return: 摘要文本
        """
        summary = STATUS_SUMMARY_BUILDER.build(snapshot.panels)
        return TUI_COPY.build_dashboard_summary_text(
            total_count=summary.total_count,
            ok_count=summary.ok_count,
            warn_count=summary.warn_count,
            fail_count=summary.fail_count,
        )

    @staticmethod
    def build_status_track(snapshot: DashboardSnapshot) -> str:
        """
        构建首页面板状态轨迹字符串。

        :param snapshot: 首页聚合快照
        :return: 状态轨迹
        """
        return ''.join(
            'x' if panel.status == 'fail' else '!' if panel.status == 'warn' else 'o' if panel.status == 'ok' else '-'
            for panel in snapshot.panels
        )

    def build_signal_lines(self, snapshot: DashboardSnapshot) -> list[str]:
        """
        构建首页顶部信号带文本。

        :param snapshot: 首页聚合快照
        :return: 信号文本行
        """
        summary = STATUS_SUMMARY_BUILDER.build(snapshot.panels)
        return TUI_COPY.build_dashboard_signal_lines(
            status_track=self.build_status_track(snapshot),
            fail_count=summary.fail_count,
            warn_count=summary.warn_count,
            ok_count=summary.ok_count,
            total_count=summary.total_count,
            navigation_shortcut_hint=TUI_KEYMAP_REGISTRY.navigation_shortcut_hint,
        )


class DashboardScreenFocusService(BaseScreenFocusService):
    """
    首页焦点服务。

    该对象负责定义首页可聚焦组件顺序，以及按左右键和滚动键解析
    当前目标区域。
    """

    def get_focus_order(self, screen: 'DashboardScreen') -> list[WorkspaceSidebar | ScrollableContainer]:
        """
        定义首页可通过左右键切换的焦点顺序。

        :param screen: 当前首页屏幕
        :return: 焦点顺序列表
        """
        return [
            screen.query_one(WorkspaceSidebar),
            screen.query_one('#workspace-main', ScrollableContainer),
        ]

    def get_default_scroll_target(self, screen: 'DashboardScreen') -> ScrollableContainer:
        """
        返回首页默认滚动容器。

        :param screen: 当前首页屏幕
        :return: 主工作区滚动容器
        """
        return screen.query_one('#workspace-main', ScrollableContainer)


class DashboardScreen(ScreenFocusActionsMixin, Screen[None]):
    """
    TUI 首页巡检屏幕。

    :param snapshot: 首页聚合快照
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
    ]

    def __init__(
        self,
        snapshot: DashboardSnapshot,
        env: str,
        active_view: str,
        navigation_items: list[NavigationItem],
        refreshed_at: str,
        support: DashboardScreenSupport | None = None,
        focus_service: DashboardScreenFocusService | None = None,
    ) -> None:
        """
        初始化首页巡检屏幕。

        :param snapshot: 首页聚合快照
        :param env: 当前运行环境
        :param active_view: 当前激活视图
        :param navigation_items: 导航项列表
        :param refreshed_at: 本次刷新时间
        :param support: 首页屏幕支持对象
        :param focus_service: 首页焦点服务
        :return: None
        """
        self.snapshot = snapshot
        self.env = env
        self.active_view = active_view
        self.navigation_items = navigation_items
        self.refreshed_at = refreshed_at
        self.support = support or DashboardScreenSupport()
        self.focus_service = focus_service or DashboardScreenFocusService()
        super().__init__()

    def _build_summary_text(self) -> str:
        """
        构建首页摘要文本。

        :return: 摘要文本
        """
        return self.support.build_summary_text(self.snapshot)

    def _build_signal_lines(self) -> list[str]:
        """
        构建首页顶部信号带文本。

        :return: 信号文本行
        """
        return self.support.build_signal_lines(self.snapshot)

    def compose(self) -> ComposeResult:
        """
        构建首页界面结构。

        :return: Textual 组件结果
        """
        yield WorkspaceHeader(self.env, self.active_view)
        with Horizontal(id='workspace-shell'):
            yield WorkspaceSidebar(self.env, self.navigation_items, self.active_view)
            with ScrollableContainer(id='workspace-main'):
                yield WorkspaceHero(
                    title=TUI_COPY.build_dashboard_hero_title(),
                    subtitle=TUI_COPY.build_dashboard_hero_subtitle(),
                    env=self.env,
                    active_view=self.active_view,
                    summary=self._build_summary_text(),
                    refreshed_at=self.refreshed_at,
                )
                yield SignalRail(self._build_signal_lines())
                with Grid(id='dashboard-metrics'):
                    for index, metric in enumerate(self.snapshot.metrics):
                        yield MetricPanel(
                            title=metric.title,
                            value=metric.value,
                            status=metric.status,
                            hint=metric.hint,
                            accent=index < PRIMARY_METRIC_COUNT,
                        )
                with Grid(id='dashboard-grid'):
                    for panel in self.snapshot.panels:
                        yield StatusPanel(
                            title=panel.title,
                            status=panel.status,
                            body='\n'.join(panel.lines),
                        )
        yield Footer()

    def on_mount(self) -> None:
        """
        首页挂载后默认将焦点停留在左侧导航。

        :return: None
        """
        self.call_after_refresh(self.query_one(WorkspaceSidebar).focus)

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
