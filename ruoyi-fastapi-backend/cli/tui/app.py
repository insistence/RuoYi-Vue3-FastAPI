from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from textual.app import App
from textual.css.query import NoMatches

from cli.tui.adapters import (
    TUI_SNAPSHOT_COLLECTOR_REGISTRY,
    BrowserPageSnapshot,
    DashboardSnapshot,
    DetailPageSnapshot,
)
from cli.tui.copy import TUI_COPY
from cli.tui.keymaps import TUI_KEYMAP_REGISTRY
from cli.tui.screens import BrowserScreen, DashboardScreen, DetailScreen
from cli.tui.widgets import NavigationItem, WorkspaceSidebar

SnapshotCollector = Callable[['RuoyiTuiApp'], BrowserPageSnapshot | DashboardSnapshot | DetailPageSnapshot]


@dataclass(frozen=True)
class TuiViewSpec:
    """
    TUI 视图规格定义。

    :param view_key: 视图标识
    :param include_query: 是否注入搜索词
    :param include_filter: 是否注入筛选键
    """

    view_key: str
    include_query: bool = False
    include_filter: bool = False


@dataclass(frozen=True)
class TuiViewDefinition:
    """
    TUI 视图定义。

    :param view_key: 视图标识
    :param collector: 页面快照采集器
    """

    view_key: str
    collector: SnapshotCollector


@dataclass(frozen=True)
class TuiViewRegistry:
    """
    TUI 视图注册表。

    该对象集中维护视图打开、刷新与顺序导航所需的元数据，
    避免 `RuoyiTuiApp` 内继续手工维护多份视图映射。

    :param definitions: 视图定义映射
    :param navigation_items: 导航项列表
    """

    definitions: dict[str, TuiViewDefinition]
    navigation_items: list[NavigationItem]

    @staticmethod
    def normalize_view_key(view_key: str) -> str:
        """
        规范化视图标识。

        :param view_key: 原始视图标识
        :return: 规范化后的视图标识
        """
        return str(view_key).strip().lower()

    def resolve_view_key(self, view_key: str) -> str:
        """
        解析可用视图标识，不存在时回退到 dashboard。

        :param view_key: 原始视图标识
        :return: 可用视图标识
        """
        normalized_view_key = self.normalize_view_key(view_key)
        if normalized_view_key in self.definitions:
            return normalized_view_key
        return 'dashboard'

    def collect_snapshot(
        self, app: 'RuoyiTuiApp', view_key: str
    ) -> BrowserPageSnapshot | DashboardSnapshot | DetailPageSnapshot:
        """
        采集指定视图的页面快照。

        :param app: 当前 TUI 应用实例
        :param view_key: 目标视图标识
        :return: 页面快照
        """
        resolved_view_key = self.resolve_view_key(view_key)
        return self.definitions[resolved_view_key].collector(app)

    def get_navigation_index(self, view_key: str) -> int:
        """
        获取视图在导航列表中的索引。

        :param view_key: 目标视图标识
        :return: 导航索引
        """
        resolved_view_key = self.resolve_view_key(view_key)
        return next(
            (index for index, item in enumerate(self.navigation_items) if item.view_key == resolved_view_key),
            0,
        )

    def get_relative_view_key(self, view_key: str, offset: int) -> str:
        """
        获取相对当前视图偏移后的目标视图标识。

        :param view_key: 当前视图标识
        :param offset: 偏移量
        :return: 目标视图标识
        """
        current_index = self.get_navigation_index(view_key)
        target_index = (current_index + offset) % len(self.navigation_items)
        return self.navigation_items[target_index].view_key


_TUI_VIEW_SPECS: tuple[TuiViewSpec, ...] = (
    TuiViewSpec('dashboard'),
    TuiViewSpec('app', include_query=True),
    TuiViewSpec('ops', include_query=True),
    TuiViewSpec('database', include_query=True),
    TuiViewSpec('cache', include_query=True),
    TuiViewSpec('jobs', include_query=True, include_filter=True),
    TuiViewSpec('gen', include_query=True),
    TuiViewSpec('configs', include_query=True, include_filter=True),
    TuiViewSpec('crypto', include_query=True),
)

_TUI_APP_CSS = """
Screen {
    layout: vertical;
    background: #04080f;
    color: #d8f7ff;
    scrollbar-size-horizontal: 1;
    scrollbar-size-vertical: 1;
    scrollbar-background: #06111b;
    scrollbar-background-hover: #0a1723;
    scrollbar-background-active: #0d1f2d;
    scrollbar-color: #1f6f8d;
    scrollbar-color-hover: #38d8ff;
    scrollbar-color-active: #6df7ff;
}

Widget {
    scrollbar-size-horizontal: 1;
    scrollbar-size-vertical: 1;
    scrollbar-background: #06111b;
    scrollbar-background-hover: #0a1723;
    scrollbar-background-active: #0d1f2d;
    scrollbar-color: #1f6f8d;
    scrollbar-color-hover: #38d8ff;
    scrollbar-color-active: #6df7ff;
}

#workspace-shell {
    height: 1fr;
    background: #050c15;
}

#workspace-main {
    padding: 1 2 1 1;
    background: #050c15;
    border: round #18425d;
    margin: 1 1 1 0;
    overflow-x: auto;
    overflow-y: auto;
    scrollbar-size-horizontal: 1;
    scrollbar-size-vertical: 1;
    scrollbar-background: #06111b;
    scrollbar-background-hover: #0a1723;
    scrollbar-background-active: #0d1f2d;
    scrollbar-color: #1f6f8d;
    scrollbar-color-hover: #38d8ff;
    scrollbar-color-active: #6df7ff;
}

#workspace-main:focus {
    border: heavy #6df7ff;
    background: #071320;
}

#detail-body {
    height: auto;
    margin-top: 1;
    border: double #18425d;
    background: #06111b;
    padding: 1;
    overflow-x: auto;
    overflow-y: auto;
}

#browser-body {
    height: auto;
    margin-top: 1;
    border: double #18425d;
    background: #06111b;
    padding: 1;
    overflow-x: auto;
    overflow-y: auto;
}

#browser-filter-bar {
    border: round #163c57;
    padding: 1 2;
    margin-bottom: 1;
    background: #07131f;
    color: #d9fbff;
}

#browser-detail-pane {
    width: 1fr;
    min-width: 48;
    border: round #163c57;
    padding: 1;
    background: #07131f;
    overflow-x: auto;
    overflow-y: auto;
}

#browser-detail-pane.is-ok {
    border: round #22c983;
}

#browser-detail-pane.is-fail {
    border: round #ff6b7a;
    background: #190d12;
}

#browser-detail-pane.is-warn {
    border: round #f2b84b;
    background: #171108;
}

#browser-detail-pane.is-info {
    border: round #38d8ff;
}

#browser-section-body {
    height: auto;
    border-top: solid #163c57;
    padding-top: 1;
    background: #06111b;
    overflow-x: auto;
    overflow-y: auto;
}

#dashboard-metrics {
    grid-size: 4;
    grid-gutter: 1 2;
    grid-columns: 1fr 1fr 1fr 1fr;
    height: auto;
    margin-top: 1;
    margin-bottom: 1;
    padding: 1 0;
}

#dashboard-grid, #detail-grid {
    grid-size: 2;
    grid-gutter: 1 2;
    grid-columns: 1fr 1fr;
    height: auto;
    margin-top: 1;
}

#detail-grid {
    margin-bottom: 1;
}

Footer {
    background: #060d16;
    color: #b6efff;
    border-top: heavy #163c57;
}

FooterKey {
    background: #0b2130;
    color: #ecfcff;
}
"""


@dataclass(frozen=True)
class TuiBindingSpec:
    """
    TUI 快捷键绑定定义。

    :param key: 快捷键
    :param action: 动作名称
    :param label: 展示标签
    """

    key: str
    action: str
    label: str


class TuiBindingBuilder:
    """
    TUI 快捷键绑定构建器。

    该对象负责统一装配应用级固定绑定和视图跳转绑定，避免 `RuoyiTuiApp`
    继续手工维护重复的绑定元组列表。
    """

    def build_base_bindings(self) -> list[TuiBindingSpec]:
        """
        构建应用级固定绑定。

        :return: 绑定定义列表
        """
        return [
            TuiBindingSpec('q', 'quit', TUI_COPY.build_app_binding_label('quit')),
            TuiBindingSpec('s', 'focus_sidebar', TUI_COPY.build_app_binding_label('sidebar')),
            TuiBindingSpec('[', 'show_previous_view', TUI_COPY.build_app_binding_label('previous')),
            TuiBindingSpec(']', 'show_next_view', TUI_COPY.build_app_binding_label('next')),
            TuiBindingSpec('r', 'refresh_current_view', TUI_COPY.build_app_binding_label('refresh')),
        ]

    def build_navigation_bindings(self) -> list[TuiBindingSpec]:
        """
        构建页面导航绑定。

        :return: 绑定定义列表
        """
        return [
            TuiBindingSpec(
                TUI_KEYMAP_REGISTRY.get_navigation_shortcut(spec.view_key),
                f'show_{spec.view_key}',
                TUI_COPY.render_view_label(spec.view_key),
            )
            for spec in _TUI_VIEW_SPECS
        ]

    def build(self) -> list[tuple[str, str, str]]:
        """
        构建 Textual 所需的绑定元组列表。

        :return: 绑定元组列表
        """
        return [
            (binding.key, binding.action, binding.label)
            for binding in [*self.build_base_bindings(), *self.build_navigation_bindings()]
        ]


TUI_APP_BINDINGS = TuiBindingBuilder().build()


@dataclass(frozen=True)
class TuiViewRegistryBuilder:
    """
    TUI 视图注册表构建器。

    该对象负责根据统一规格构建导航项和快照采集定义，避免模块内
    继续维护重复的 `lambda collect(...)` 配置块。
    """

    def build_navigation_items(self) -> list[NavigationItem]:
        """
        构建工作台导航项列表。

        :return: 导航项列表
        """
        return [
            NavigationItem(
                view_key,
                TUI_COPY.render_view_label(view_key),
                shortcut,
                TUI_COPY.render_navigation_description(view_key),
            )
            for view_key, shortcut in TUI_KEYMAP_REGISTRY.navigation_shortcuts.items()
        ]

    def build_collector(self, spec: TuiViewSpec) -> SnapshotCollector:
        """
        根据视图规格构建页面快照采集器。

        :param spec: 视图规格
        :return: 页面快照采集器
        """

        def collect(app: 'RuoyiTuiApp') -> BrowserPageSnapshot | DashboardSnapshot | DetailPageSnapshot:
            collect_kwargs: dict[str, str] = {}
            if spec.include_filter:
                collect_kwargs['filter_key'] = app.get_browser_filter(spec.view_key)
            if spec.include_query:
                collect_kwargs['query'] = app.get_browser_query(spec.view_key)
            return TUI_SNAPSHOT_COLLECTOR_REGISTRY.collect(spec.view_key, app.env, **collect_kwargs)

        return collect

    def build_definitions(self) -> dict[str, TuiViewDefinition]:
        """
        构建视图定义映射。

        :return: 视图定义映射
        """
        return {spec.view_key: TuiViewDefinition(spec.view_key, self.build_collector(spec)) for spec in _TUI_VIEW_SPECS}

    def build(self) -> TuiViewRegistry:
        """
        构建 TUI 视图注册表。

        :return: 视图注册表
        """
        return TuiViewRegistry(
            definitions=self.build_definitions(),
            navigation_items=self.build_navigation_items(),
        )


@dataclass
class TuiViewStateStore:
    """
    TUI 视图状态存储。

    该对象集中维护页面级动作反馈、浏览页筛选键和搜索词，避免
    `RuoyiTuiApp` 本体继续直接操作多份同类字典状态。

    :param action_feedback_by_view: 动作反馈映射
    :param browser_filter_by_view: 浏览页筛选映射
    :param browser_query_by_view: 浏览页搜索词映射
    """

    action_feedback_by_view: dict[str, list[str]]
    browser_filter_by_view: dict[str, str]
    browser_query_by_view: dict[str, str]

    @classmethod
    def create_default(cls) -> 'TuiViewStateStore':
        """
        创建默认视图状态存储。

        :return: 视图状态存储
        """
        return cls(
            action_feedback_by_view={},
            browser_filter_by_view={'jobs': 'all', 'configs': 'all'},
            browser_query_by_view={},
        )

    def remember_action_feedback(self, view_key: str, lines: list[str]) -> None:
        """
        记录指定页面最近一次动作反馈。

        :param view_key: 页面视图标识
        :param lines: 反馈文本行
        :return: None
        """
        self.action_feedback_by_view[view_key] = list(lines)

    def get_action_feedback_lines(self, view_key: str) -> list[str]:
        """
        读取指定页面最近一次动作反馈。

        :param view_key: 页面视图标识
        :return: 反馈文本行
        """
        return list(self.action_feedback_by_view.get(view_key, []))

    def remember_browser_filter(self, view_key: str, filter_key: str) -> None:
        """
        记录指定浏览页当前筛选键。

        :param view_key: 页面视图标识
        :param filter_key: 当前筛选键
        :return: None
        """
        self.browser_filter_by_view[view_key] = filter_key

    def get_browser_filter(self, view_key: str, default: str = 'all') -> str:
        """
        读取指定浏览页当前筛选键。

        :param view_key: 页面视图标识
        :param default: 默认筛选键
        :return: 当前筛选键
        """
        return str(self.browser_filter_by_view.get(view_key, default) or default)

    def remember_browser_query(self, view_key: str, query: str) -> None:
        """
        记录指定浏览页当前搜索词。

        :param view_key: 页面视图标识
        :param query: 当前搜索词
        :return: None
        """
        normalized_query = str(query or '').strip()
        if normalized_query:
            self.browser_query_by_view[view_key] = normalized_query
            return
        self.browser_query_by_view.pop(view_key, None)

    def get_browser_query(self, view_key: str, default: str = '') -> str:
        """
        读取指定浏览页当前搜索词。

        :param view_key: 页面视图标识
        :param default: 默认搜索词
        :return: 当前搜索词
        """
        return str(self.browser_query_by_view.get(view_key, default) or default)


TUI_VIEW_REGISTRY = TuiViewRegistryBuilder().build()
NAVIGATION_ITEMS = TUI_VIEW_REGISTRY.navigation_items


@dataclass(frozen=True)
class TuiScreenFactory:
    """
    TUI 工作台页面工厂。

    该对象负责把页面快照转换为具体 screen 实例，避免 `RuoyiTuiApp`
    同时承担状态协调和 screen 构建职责。
    """

    @staticmethod
    def build_refresh_timestamp() -> str:
        """
        构建当前页面刷新时间文本。

        :return: 格式化后的刷新时间
        """
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def build(
        self,
        *,
        snapshot: BrowserPageSnapshot | DashboardSnapshot | DetailPageSnapshot,
        env: str,
        active_view: str,
        navigation_items: list[NavigationItem],
        action_feedback_lines: list[str],
    ) -> BrowserScreen | DashboardScreen | DetailScreen:
        """
        根据快照类型构建对应的工作台页面。

        :param snapshot: 页面快照
        :param env: 当前运行环境
        :param active_view: 当前激活视图
        :param navigation_items: 导航项列表
        :param action_feedback_lines: 当前视图动作反馈
        :return: 对应的页面对象
        """
        refreshed_at = self.build_refresh_timestamp()
        if isinstance(snapshot, DashboardSnapshot):
            return DashboardScreen(
                snapshot,
                env=env,
                active_view=active_view,
                navigation_items=navigation_items,
                refreshed_at=refreshed_at,
            )
        if isinstance(snapshot, BrowserPageSnapshot):
            return BrowserScreen(
                snapshot,
                env=env,
                active_view=active_view,
                navigation_items=navigation_items,
                refreshed_at=refreshed_at,
                action_feedback_lines=action_feedback_lines,
            )
        return DetailScreen(
            snapshot,
            env=env,
            active_view=active_view,
            navigation_items=navigation_items,
            refreshed_at=refreshed_at,
        )


@dataclass
class TuiScreenNavigator:
    """
    TUI 工作台页面导航器。

    该对象负责处理首屏展示与后续切屏差异，让应用壳更专注于状态切换。

    :param app: 当前 TUI 应用实例
    :param initialized: 工作台屏幕是否已初始化
    """

    app: 'RuoyiTuiApp'
    initialized: bool = False

    def show(self, screen: BrowserScreen | DashboardScreen | DetailScreen) -> None:
        """
        显示工作台页面，并兼容首屏初始化与后续切屏。

        Textual 在默认根屏阶段直接调用 `switch_screen()` 会触发内部回调栈异常，
        因此首次展示页面需要使用 `push_screen()` 建立活动屏，后续再改用
        `switch_screen()` 做同层页面替换。

        :param screen: 待显示的页面对象
        :return: None
        """
        if not self.initialized:
            self.app.push_screen(screen)
            self.initialized = True
            return
        self.app.switch_screen(screen)


@dataclass(frozen=True)
class TuiViewOpeningCoordinator:
    """
    TUI 视图打开协调器。

    该对象负责串联视图解析、快照采集、screen 构建与切屏展示，
    让 `RuoyiTuiApp` 更专注于状态暴露与 Textual action 桥接。

    :param view_registry: 视图注册表
    :param screen_factory: 工作台页面工厂
    :param navigation_items: 导航项列表
    """

    view_registry: TuiViewRegistry
    screen_factory: TuiScreenFactory
    navigation_items: list[NavigationItem]

    def show(self, app: 'RuoyiTuiApp', view_key: str) -> None:
        """
        切换并展示指定视图。

        :param app: 当前 TUI 应用实例
        :param view_key: 目标视图标识
        :return: None
        """
        resolved_view_key = self.view_registry.resolve_view_key(view_key)
        app.current_view = resolved_view_key
        snapshot = self.view_registry.collect_snapshot(app, resolved_view_key)
        screen = self.screen_factory.build(
            snapshot=snapshot,
            env=app.env,
            active_view=app.current_view,
            navigation_items=self.navigation_items,
            action_feedback_lines=app.get_action_feedback_lines(app.current_view),
        )
        app.screen_navigator.show(screen)


class RuoyiTuiApp(App[None]):
    """
    RuoYi CLI Textual 应用。

    :param env: 当前运行环境
    """

    CSS = _TUI_APP_CSS
    BINDINGS = TUI_APP_BINDINGS

    def __init__(self, env: str) -> None:
        """
        初始化 TUI 应用实例。

        :param env: 当前运行环境
        :return: None
        """
        self.env = env
        self.current_view = 'dashboard'
        self.view_state_store = TuiViewStateStore.create_default()
        self.screen_factory = TuiScreenFactory()
        self.screen_navigator = TuiScreenNavigator(self)
        self.view_opening_coordinator = TuiViewOpeningCoordinator(
            view_registry=TUI_VIEW_REGISTRY,
            screen_factory=self.screen_factory,
            navigation_items=NAVIGATION_ITEMS,
        )
        super().__init__()

    def show_view(self, view_key: str) -> None:
        """
        切换并展示指定视图。

        :param view_key: 目标视图标识
        :return: None
        """
        self.view_opening_coordinator.show(self, view_key)

    def remember_action_feedback(self, view_key: str, lines: list[str]) -> None:
        """
        记录指定页面最近一次动作反馈。

        :param view_key: 页面视图标识
        :param lines: 反馈文本行
        :return: None
        """
        self.view_state_store.remember_action_feedback(view_key, lines)

    def get_action_feedback_lines(self, view_key: str) -> list[str]:
        """
        读取指定页面最近一次动作反馈。

        :param view_key: 页面视图标识
        :return: 反馈文本行
        """
        return self.view_state_store.get_action_feedback_lines(view_key)

    def remember_browser_filter(self, view_key: str, filter_key: str) -> None:
        """
        记录指定浏览页当前筛选键。

        :param view_key: 页面视图标识
        :param filter_key: 当前筛选键
        :return: None
        """
        self.view_state_store.remember_browser_filter(view_key, filter_key)

    def get_browser_filter(self, view_key: str, default: str = 'all') -> str:
        """
        读取指定浏览页当前筛选键。

        :param view_key: 页面视图标识
        :param default: 默认筛选键
        :return: 当前筛选键
        """
        return self.view_state_store.get_browser_filter(view_key, default)

    def remember_browser_query(self, view_key: str, query: str) -> None:
        """
        记录指定浏览页当前搜索词。

        :param view_key: 页面视图标识
        :param query: 当前搜索词
        :return: None
        """
        self.view_state_store.remember_browser_query(view_key, query)

    def get_browser_query(self, view_key: str, default: str = '') -> str:
        """
        读取指定浏览页当前搜索词。

        :param view_key: 页面视图标识
        :param default: 默认搜索词
        :return: 当前搜索词
        """
        return self.view_state_store.get_browser_query(view_key, default)

    def on_mount(self) -> None:
        """
        在应用启动时载入首页。

        :return: None
        """
        self.show_view('dashboard')

    def open_view(self, view_key: str) -> None:
        """
        按视图标识打开对应页面。

        :param view_key: 视图标识
        :return: None
        """
        self.show_view(view_key)

    def action_focus_sidebar(self) -> None:
        """
        将焦点切换到左侧导航栏。

        :return: None
        """
        try:
            self.screen.query_one(WorkspaceSidebar).focus()
        except NoMatches:
            return

    def action_show_previous_view(self) -> None:
        """
        切换到前一个工作台视图。

        :return: None
        """
        self.open_view(TUI_VIEW_REGISTRY.get_relative_view_key(self.current_view, -1))

    def action_show_next_view(self) -> None:
        """
        切换到后一个工作台视图。

        :return: None
        """
        self.open_view(TUI_VIEW_REGISTRY.get_relative_view_key(self.current_view, 1))

    def action_refresh_current_view(self) -> None:
        """
        刷新当前视图数据。

        :return: None
        """
        self.show_view(self.current_view)

    def action_show_dashboard(self) -> None:
        """
        切换到首页视图。

        :return: None
        """
        self.open_view('dashboard')

    def action_show_app(self) -> None:
        """
        切换到应用详情视图。

        :return: None
        """
        self.open_view('app')

    def action_show_ops(self) -> None:
        """
        切换到运维详情视图。

        :return: None
        """
        self.open_view('ops')

    def action_show_database(self) -> None:
        """
        切换到数据库详情视图。

        :return: None
        """
        self.open_view('database')

    def action_show_cache(self) -> None:
        """
        切换到缓存浏览视图。

        :return: None
        """
        self.open_view('cache')

    def action_show_jobs(self) -> None:
        """
        切换到任务浏览视图。

        :return: None
        """
        self.open_view('jobs')

    def action_show_gen(self) -> None:
        """
        切换到代码生成浏览视图。

        :return: None
        """
        self.open_view('gen')

    def action_show_configs(self) -> None:
        """
        切换到配置浏览视图。

        :return: None
        """
        self.open_view('configs')

    def action_show_crypto(self) -> None:
        """
        切换到传输加密详情视图。

        :return: None
        """
        self.open_view('crypto')


@dataclass(frozen=True)
class TuiAppRunner:
    """
    TUI 应用启动器。

    该对象负责按环境创建并运行 Textual 应用实例，使命令入口不再依赖
    模块级启动函数。

    :param app_factory: TUI 应用工厂
    """

    app_factory: Callable[[str], RuoyiTuiApp]

    def run(self, env: str) -> None:
        """
        启动 TUI 应用。

        :param env: 当前运行环境
        :return: None
        """
        self.app_factory(env).run()


TUI_APP_RUNNER = TuiAppRunner(RuoyiTuiApp)
