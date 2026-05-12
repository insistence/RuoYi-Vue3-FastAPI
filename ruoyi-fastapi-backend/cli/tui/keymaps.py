from dataclasses import dataclass, field


@dataclass(frozen=True)
class TuiKeymapRegistry:
    """
    TUI 键位注册表。

    该对象集中维护页面切换快捷键和派生提示文案，避免模块级
    常量散落并在后续扩展时继续增长。

    :param navigation_shortcuts: 页面导航快捷键映射
    """

    navigation_shortcuts: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def normalize_view_key(view_key: str) -> str:
        """
        规范化页面标识。

        :param view_key: 原始页面标识
        :return: 规范化后的页面标识
        """
        return str(view_key).strip().lower()

    def get_navigation_shortcut(self, view_key: str) -> str:
        """
        获取指定页面的导航快捷键。

        :param view_key: 页面标识
        :return: 快捷键文本
        """
        normalized_view_key = self.normalize_view_key(view_key)
        return self.navigation_shortcuts.get(normalized_view_key, '')

    @property
    def navigation_shortcut_hint(self) -> str:
        """
        构建页面导航快捷键总提示。

        :return: 快捷键提示
        """
        ordered_keys = ['dashboard', 'app', 'ops', 'database', 'cache', 'jobs', 'gen', 'configs', 'crypto']
        shortcuts = [
            self.get_navigation_shortcut(view_key).upper()
            for view_key in ordered_keys
            if self.get_navigation_shortcut(view_key)
        ]
        return f'[{" / ".join(shortcuts).replace(" / ", "/")}]'

    @property
    def sidebar_shortcut_hint(self) -> str:
        """
        获取侧栏快捷键提示。

        :return: 提示文本
        """
        return '[S] 侧栏'

    @property
    def refresh_shortcut_hint(self) -> str:
        """
        获取刷新快捷键提示。

        :return: 提示文本
        """
        return '[R] 刷新'

    @property
    def quit_shortcut_hint(self) -> str:
        """
        获取退出快捷键提示。

        :return: 提示文本
        """
        return '[Q] 退出'

    @property
    def focus_shortcut_hint(self) -> str:
        """
        获取焦点切换快捷键提示。

        :return: 提示文本
        """
        return '[←/→] 切换焦点'

    @property
    def region_switch_shortcut_hint(self) -> str:
        """
        获取区域切换快捷键提示。

        :return: 提示文本
        """
        return '[←/→] 切换区域'

    @property
    def scroll_shortcut_hint(self) -> str:
        """
        获取滚动快捷键提示。

        :return: 提示文本
        """
        return '[J/K] 滚动'

    @property
    def page_scroll_shortcut_hint(self) -> str:
        """
        获取翻页快捷键提示。

        :return: 提示文本
        """
        return '[PgUp/PgDn] 翻页'

    @property
    def home_end_shortcut_hint(self) -> str:
        """
        获取首尾跳转快捷键提示。

        :return: 提示文本
        """
        return '[Home/End] 首尾'

    @property
    def browser_interaction_hint(self) -> str:
        """
        构建浏览页交互提示。

        :return: 提示文本
        """
        return (
            f'浏览键：{self.focus_shortcut_hint}  {self.scroll_shortcut_hint}  '
            f'{self.page_scroll_shortcut_hint}  {self.home_end_shortcut_hint}'
        )

    @property
    def global_shortcut_hint(self) -> str:
        """
        构建全局快捷键提示。

        :return: 提示文本
        """
        return (
            f'页面 {self.navigation_shortcut_hint}  {self.sidebar_shortcut_hint}  '
            f'{self.focus_shortcut_hint}  {self.scroll_shortcut_hint}  '
            f'{self.page_scroll_shortcut_hint}  {self.home_end_shortcut_hint}  '
            f'{self.refresh_shortcut_hint}  {self.quit_shortcut_hint}'
        )

    @property
    def hero_shortcut_hint(self) -> str:
        """
        构建首页英雄区快捷键提示。

        :return: 提示文本
        """
        return (
            f'页面 {self.navigation_shortcut_hint}  {self.sidebar_shortcut_hint}  '
            f'{self.region_switch_shortcut_hint}  {self.scroll_shortcut_hint}  '
            f'{self.page_scroll_shortcut_hint}  {self.home_end_shortcut_hint}  '
            f'{self.refresh_shortcut_hint}  {self.quit_shortcut_hint}'
        )


TUI_KEYMAP_REGISTRY = TuiKeymapRegistry(
    navigation_shortcuts={
        'dashboard': 'd',
        'app': 'a',
        'ops': 'o',
        'database': 'b',
        'cache': 'c',
        'jobs': 't',
        'gen': 'g',
        'configs': 'p',
        'crypto': 'e',
    }
)
