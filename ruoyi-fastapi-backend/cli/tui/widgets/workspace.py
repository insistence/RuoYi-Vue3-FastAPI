from dataclasses import dataclass
from datetime import datetime
from math import sin
from time import monotonic

from rich.text import Text
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static

from cli.tui.adapters.models import BrowserRecordSnapshot, DetailSectionSnapshot
from cli.tui.copy import TUI_COPY
from cli.tui.keymaps import TUI_KEYMAP_REGISTRY
from cli.tui.search import TUI_SEARCH_HIGHLIGHTER


class WorkspaceRenderingSupport:
    """
    工作台组件渲染支持对象。

    该对象负责状态徽标、状态类名、结构化文本渲染和预览提取，
    供工作台中的导航项、详情视图和摘要视图复用。
    """

    @staticmethod
    def highlight_search_text(text: str, query: str) -> str:
        """
        对工作台文本执行搜索高亮。

        :param text: 原始文本
        :param query: 搜索词
        :return: 高亮后的文本
        """
        return TUI_SEARCH_HIGHLIGHTER.highlight(text, query)

    @staticmethod
    def render_status_badge(status: str) -> str:
        """
        将状态值转换为紧凑徽标文本。

        :param status: 原始状态值
        :return: 徽标文本
        """
        return f'[{TUI_COPY.render_status_code(status)}]'

    @staticmethod
    def resolve_status_class(status: str) -> str:
        """
        根据状态值解析统一样式类。

        :param status: 原始状态值
        :return: 状态样式类名
        """
        normalized_status = str(status).strip().lower()
        if normalized_status in {'ok', 'success', 'healthy'}:
            return 'is-ok'
        if normalized_status in {'fail', 'error'}:
            return 'is-fail'
        if normalized_status in {'warn', 'warning'}:
            return 'is-warn'
        return 'is-info'

    @staticmethod
    def strip_line_markup(line: str) -> str:
        """
        去除内部展示标记，便于提取预览文本。

        :param line: 原始文本行
        :return: 纯文本内容
        """
        stripped = line.strip()
        if stripped.startswith('## '):
            return stripped[3:].strip()
        if stripped.startswith('> '):
            return stripped[2:].strip()
        return stripped

    def build_preview_line(self, lines: list[str], fallback: str) -> str:
        """
        从结构化文本中提取首条适合作为预览的内容。

        :param lines: 原始文本行列表
        :param fallback: 兜底文本
        :return: 预览文本
        """
        for line in lines:
            preview = self.strip_line_markup(line)
            if preview:
                return preview
        return fallback

    def render_structured_lines(self, lines: list[str], empty_text: str) -> str:
        """
        将结构化文本行渲染为适合终端展示的块文本。

        支持以下轻量约定：
        - `## ` 开头：区块标题
        - `> ` 开头：说明或子项
        - 空字符串：保留空行

        :param lines: 原始文本行列表
        :param empty_text: 空态提示文本
        :return: 渲染后的文本块
        """
        rendered_lines: list[str] = []
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                if rendered_lines and rendered_lines[-1] != '':
                    rendered_lines.append('')
                continue
            if stripped.startswith('## '):
                title = stripped[3:].strip()
                if rendered_lines and rendered_lines[-1] != '':
                    rendered_lines.append('')
                rendered_lines.append(f'【{title}】')
                rendered_lines.append('─' * max(10, min(len(title) * 2, 30)))
                continue
            if stripped.startswith('> '):
                rendered_lines.append(f'│ {stripped[2:].strip()}')
                continue
            rendered_lines.append(f'• {stripped}')

        while rendered_lines and rendered_lines[0] == '':
            rendered_lines.pop(0)
        while rendered_lines and rendered_lines[-1] == '':
            rendered_lines.pop()

        if not rendered_lines:
            return f'- {empty_text}'
        return '\n'.join(rendered_lines)


WORKSPACE_RENDERING = WorkspaceRenderingSupport()


@dataclass(frozen=True)
class NavigationItem:
    """
    工作台导航项定义。

    :param view_key: 视图唯一标识
    :param label: 导航显示名称
    :param shortcut: 快捷键
    :param description: 导航说明
    """

    view_key: str
    label: str
    shortcut: str
    description: str


class NavigationListItem(ListItem):
    """
    工作台导航列表项。

    :param item: 导航项定义
    """

    DEFAULT_CSS = """
    NavigationListItem {
        padding: 0 1;
        margin-bottom: 1;
        border: round #18425d;
        background: #07131f;
        color: #89b9c9;
        height: auto;
    }

    NavigationListItem Label {
        width: 1fr;
    }

    NavigationListItem.is-active {
        border: round #38d8ff;
        background: #0a1e2d;
        color: #e4fbff;
    }

    NavigationListItem.is-active Label {
        text-style: bold;
    }

    NavigationListItem.-highlight {
        border: heavy #6df7ff;
        background: #10364b;
        color: #ffffff;
        text-style: bold;
        padding-left: 2;
    }
    """

    def __init__(self, item: NavigationItem, index: int, *, active: bool = False) -> None:
        """
        初始化导航列表项。

        :param item: 导航项定义
        :return: None
        """
        self.item = item
        super().__init__(
            Label(
                '\n'.join(TUI_COPY.build_navigation_item_lines(index, item.label, item.shortcut, item.description)),
                markup=False,
            )
        )
        if active:
            self.add_class('is-active')


class WorkspaceSidebar(ListView):
    """
    工作台左侧导航组件。

    :param env: 当前运行环境
    :param items: 导航项列表
    :param active_view: 当前激活视图
    """

    DEFAULT_CSS = """
    WorkspaceSidebar {
        width: 34;
        min-width: 34;
        padding: 1;
        margin: 1 0 1 1;
        border: double #18425d;
        background: #06111b;
    }

    WorkspaceSidebar:focus {
        border: heavy #6df7ff;
    }
    """

    def __init__(self, env: str, items: list[NavigationItem], active_view: str) -> None:
        """
        初始化工作台导航组件。

        :param env: 当前运行环境
        :param items: 导航项列表
        :param active_view: 当前激活视图
        :return: None
        """
        self.env = env
        self.items = items
        self.active_view = active_view
        initial_index = self._resolve_initial_index()
        children = [
            NavigationListItem(item, index, active=item.view_key == self.active_view)
            for index, item in enumerate(self.items)
        ]
        super().__init__(*children, initial_index=initial_index, id='workspace-sidebar')

    def _resolve_initial_index(self) -> int:
        """
        解析当前激活视图对应的导航索引。

        :return: 初始高亮索引
        """
        for index, item in enumerate(self.items):
            if item.view_key == self.active_view:
                return index
        return 0


class WorkspaceHero(Static):
    """
    工作台顶部摘要组件。

    :param title: 页面标题
    :param subtitle: 页面副标题
    :param env: 当前运行环境
    :param active_view: 当前激活视图
    :param summary: 状态摘要文本
    :param refreshed_at: 本次刷新时间
    """

    DEFAULT_CSS = """
    WorkspaceHero {
        border: double #38d8ff;
        padding: 1 2;
        margin-bottom: 1;
        min-height: 11;
        background: #081827;
        color: #e9fcff;
    }
    """
    _BORDER_PHASES = ('#2fb8df', '#38d8ff', '#62ecff', '#38d8ff')
    _TITLE_GLOW_PALETTE = ('#7be8ff', '#b4f6ff', '#e9fdff', '#b4f6ff')

    def __init__(
        self,
        title: str,
        subtitle: str,
        env: str,
        active_view: str,
        summary: str,
        refreshed_at: str,
    ) -> None:
        """
        初始化工作台顶部摘要组件。

        :param title: 页面标题
        :param subtitle: 页面副标题
        :param active_view: 当前激活视图
        :param summary: 状态摘要文本
        :param refreshed_at: 本次刷新时间
        :return: None
        """
        self.title = title
        self.subtitle = subtitle
        self.env = env
        self.active_view = active_view
        self.summary = summary
        self.refreshed_at = refreshed_at
        super().__init__(self._build_render_text(), id='workspace-hero', markup=False)

    def on_mount(self) -> None:
        """
        在组件挂载后启动低频边框呼吸动效。

        :return: None
        """
        self.set_interval(0.9, self._pulse_border, name='pulse workspace hero border')

    def _pulse_border(self) -> None:
        """
        以低频节奏切换 Hero 边框颜色。

        :return: None
        """
        phase_index = int(monotonic() * 1.1) % len(self._BORDER_PHASES)
        self.styles.border = ('double', self._BORDER_PHASES[phase_index])

    @classmethod
    def _build_title_text(cls, title: str) -> Text:
        """
        构建 Hero 标题渐变文本。

        :param title: 标题文本
        :return: 富文本标题
        """
        rendered = Text()
        palette_size = len(cls._TITLE_GLOW_PALETTE)
        for index, char in enumerate(title):
            rendered.append(char, style=f'bold {cls._TITLE_GLOW_PALETTE[index % palette_size]}')
        return rendered

    def _build_render_text(self) -> Text:
        """
        构建顶部摘要文本。

        :return: 渲染富文本
        """
        lines = TUI_COPY.build_workspace_hero_lines(
            view_label=TUI_COPY.render_view_label(self.active_view),
            title=self.title,
            subtitle=self.subtitle,
            env=self.env,
            summary=self.summary,
            refreshed_at=self.refreshed_at,
            shortcut_hint=TUI_KEYMAP_REGISTRY.hero_shortcut_hint,
        )
        rendered = Text()
        for index, line in enumerate(lines):
            if index:
                rendered.append('\n')
            if line.startswith('标题 · '):
                rendered.append('标题 · ', style='bold #8fd9e8')
                rendered.append_text(self._build_title_text(line.removeprefix('标题 · ')))
                continue
            rendered.append(line, style='bold #e9fcff' if index == 0 else '#d7f7ff')
        return rendered


class WorkspaceHeader(Static):
    """
    工作台顶部状态栏。

    :param env: 当前运行环境
    :param active_view: 当前激活视图
    """

    DEFAULT_CSS = """
    WorkspaceHeader {
        height: 2;
        padding: 0 2;
        background: #060d16;
        color: #c7f6ff;
        border-bottom: heavy #163c57;
        content-align: left middle;
        text-style: bold;
    }
    """
    _HEADER_LINE_COUNT = 2
    _SCANLINE_WIDTH = 16
    _HEADER_HORIZONTAL_PADDING = 4
    _HEADER_FALLBACK_WIDTH = 108
    _SCANLINE_BASE_STYLE = '#1c5368'
    _SCANLINE_GLOW_STYLES = {
        '·': '#8ef7ff',
        '░': '#62ecff',
        '▒': '#4ee4ff',
        '▓': '#2cc9ff',
        '█': '#dffcff',
    }

    @classmethod
    def build_scanline_text(cls, phase: float, width: int) -> Text:
        """
        构建页眉扫描线文本。

        通过单个高亮扫描头和两侧衰减尾迹，营造简洁的霓虹扫线效果。

        :param phase: 当前动画相位
        :param width: 扫描线宽度
        :return: 带颜色层次的扫描线文本
        """
        cells = ['─'] * width
        head_position = int(((sin(phase * 0.82) + 1) / 2) * (width - 1))
        for offset, symbol in ((-2, '·'), (-1, '░'), (0, '█'), (1, '▓'), (2, '▒')):
            position = head_position + offset
            if 0 <= position < width:
                cells[position] = symbol
        rendered = Text()
        for symbol in cells:
            rendered.append(symbol, style=cls._SCANLINE_GLOW_STYLES.get(symbol, cls._SCANLINE_BASE_STYLE))
        return rendered

    def __init__(self, env: str, active_view: str) -> None:
        """
        初始化工作台顶部状态栏。

        :param env: 当前运行环境
        :param active_view: 当前激活视图
        :return: None
        """
        self.env = env
        self.active_view = active_view
        super().__init__(id='workspace-header', markup=False)

    def on_mount(self) -> None:
        """
        在组件挂载后启动时钟刷新。

        :return: None
        """
        self.set_interval(0.18, self.refresh, name='update workspace header')

    def build_scanline_text_label(self) -> Text:
        """
        构建扫描线文本。

        :return: 扫描线文本
        """
        phase = monotonic() * 2.1
        return self.build_scanline_text(phase, self._SCANLINE_WIDTH)

    def build_symmetric_effects(self) -> tuple[Text, Text]:
        """
        构建标题两侧的对称动效文本。

        左右两侧都使用固定宽度，确保标题中心点稳定，不随动效变化漂移。

        :return: 左右动效文本
        """
        left_effect = self.build_scanline_text_label()
        right_effect = Text()
        for span_symbol in reversed(left_effect.plain):
            right_effect.append(
                span_symbol,
                style=self._SCANLINE_GLOW_STYLES.get(span_symbol, self._SCANLINE_BASE_STYLE),
            )
        return left_effect, right_effect

    def build_centered_title_line(self, title_text: str) -> Text:
        """
        构建居中的标题装饰行。

        标题左右分别放置镜像扫描线动效，中间保留标题主体。

        :param title_text: 标题主体文本
        :return: 居中后的富文本标题行
        """
        left_effect, right_effect = self.build_symmetric_effects()
        decorated_title = Text()
        decorated_title.append_text(left_effect)
        decorated_title.append('  ')
        decorated_title.append(title_text, style='bold #e8fdff')
        decorated_title.append('  ')
        decorated_title.append_text(right_effect)
        available_width = self.size.width - self._HEADER_HORIZONTAL_PADDING
        if available_width <= 0:
            available_width = self._HEADER_FALLBACK_WIDTH
        centered = Text(
            ' ' * max((max(available_width, len(decorated_title.plain)) - len(decorated_title.plain)) // 2, 0)
        )
        centered.append_text(decorated_title)
        return centered

    def render(self) -> Text:
        """
        渲染顶部状态栏文本。

        :return: 渲染富文本
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        lines = TUI_COPY.build_workspace_header_lines(
            env=self.env,
            view_label=TUI_COPY.render_view_label(self.active_view),
            timestamp=timestamp,
            shortcut_hint=TUI_KEYMAP_REGISTRY.global_shortcut_hint,
        )
        rendered = Text()
        if len(lines) >= self._HEADER_LINE_COUNT:
            rendered.append_text(self.build_centered_title_line(lines[0]))
            rendered.append('\n')
            rendered.append(lines[1], style='bold #c7f6ff')
            return rendered
        rendered.append('\n'.join(lines), style='bold #c7f6ff')
        return rendered


class SectionListItem(ListItem):
    """
    详情页分区导航列表项。

    :param section: 分区快照
    :param index: 分区索引
    """

    DEFAULT_CSS = """
    SectionListItem {
        padding: 0 1;
        margin-bottom: 1;
        border: round #123148;
        background: #07131f;
        color: #a3c8d2;
        height: auto;
    }

    SectionListItem Label {
        width: 1fr;
    }

    SectionListItem.is-ok {
        border: round #22c983;
        background: #081b17;
    }

    SectionListItem.is-fail {
        border: round #ff6b7a;
        background: #241118;
    }

    SectionListItem.is-warn {
        border: round #f2b84b;
        background: #261d0f;
    }

    SectionListItem.is-info {
        border: round #38d8ff;
        background: #081825;
    }

    SectionListItem.-highlight {
        border: heavy #6df7ff;
        background: #10364b;
        color: #ffffff;
        text-style: bold;
        padding-left: 2;
    }
    """

    def __init__(
        self,
        section: DetailSectionSnapshot,
        index: int,
        query: str = '',
        rendering: WorkspaceRenderingSupport | None = None,
    ) -> None:
        """
        初始化详情页分区导航项。

        :param section: 分区快照
        :param index: 分区索引
        :param rendering: 工作台组件渲染支持对象
        :return: None
        """
        self.section = section
        self.index = index
        self.search_query = query
        self.rendering = rendering or WORKSPACE_RENDERING
        preview_line = self.rendering.build_preview_line(section.lines, TUI_COPY.build_workspace_empty_text('detail'))
        super().__init__(
            Label(
                '\n'.join(
                    TUI_COPY.build_section_item_lines(
                        index,
                        self.rendering.highlight_search_text(section.title, query),
                        self.rendering.render_status_badge(section.status),
                        self.rendering.highlight_search_text(preview_line, query),
                    )
                ),
                markup=False,
            )
        )
        self.add_class(self.rendering.resolve_status_class(section.status))


class SectionNavigator(ListView):
    """
    详情页分区导航组件。

    :param sections: 分区快照列表
    :param initial_index: 初始高亮索引
    """

    DEFAULT_CSS = """
    SectionNavigator {
        width: 30;
        min-width: 30;
        border: double #18425d;
        padding: 1;
        margin-right: 1;
        background: #06111b;
    }

    SectionNavigator:focus {
        border: heavy #6df7ff;
    }
    """

    class Changed(Message):
        """
        分区导航高亮变更消息。
        """

        def __init__(self, navigator: 'SectionNavigator', index: int, item: SectionListItem) -> None:
            super().__init__()
            self.navigator = navigator
            self.index = index
            self.item = item

        @property
        def control(self) -> 'SectionNavigator':
            return self.navigator

    def __init__(
        self,
        sections: list[DetailSectionSnapshot],
        initial_index: int = 0,
        query: str = '',
        rendering: WorkspaceRenderingSupport | None = None,
    ) -> None:
        """
        初始化详情页分区导航。

        :param sections: 分区快照列表
        :param initial_index: 初始高亮索引
        :param rendering: 工作台组件渲染支持对象
        :return: None
        """
        self.sections = sections
        self.search_query = query
        self.rendering = rendering or WORKSPACE_RENDERING
        children = [
            SectionListItem(section, index, query=query, rendering=self.rendering)
            for index, section in enumerate(sections)
        ]
        super().__init__(*children, initial_index=initial_index)

    def watch_index(self, old_index: int | None, new_index: int | None) -> None:
        """
        在高亮变化后向父级发送明确的分区切换消息。

        :param old_index: 旧索引
        :param new_index: 新索引
        :return: None
        """
        super().watch_index(old_index, new_index)
        if new_index is None or not 0 <= new_index < len(self._nodes):
            return
        item = self._nodes[new_index]
        if isinstance(item, SectionListItem):
            self.post_message(self.Changed(self, new_index, item))

    async def show_sections(
        self, sections: list[DetailSectionSnapshot], initial_index: int = 0, query: str = ''
    ) -> None:
        """
        刷新分区导航内容并恢复高亮位置。

        :param sections: 最新分区快照列表
        :param initial_index: 目标高亮索引
        :return: None
        """
        self.sections = sections
        self.search_query = query
        await self.clear()
        children = [
            SectionListItem(section, index, query=query, rendering=self.rendering)
            for index, section in enumerate(sections)
        ]
        if not children:
            self.index = None
            return
        await self.extend(children)
        self.index = max(0, min(initial_index, len(children) - 1))


class SectionDetailView(Static):
    """
    详情页分区内容展示组件。

    :param section: 当前展示的分区快照
    """

    DEFAULT_CSS = """
    SectionDetailView {
        border: double #245874;
        padding: 1 2;
        background: #08131f;
        color: #ddf8ff;
        width: 1fr;
        min-height: 18;
        overflow-x: auto;
        overflow-y: auto;
    }

    SectionDetailView.is-ok {
        border: double #22c983;
        background: #081b17;
    }

    SectionDetailView.is-fail {
        border: double #ff6b7a;
        background: #241118;
    }

    SectionDetailView.is-warn {
        border: double #f2b84b;
        background: #261d0f;
    }

    SectionDetailView.is-info {
        border: double #38d8ff;
        background: #081825;
    }

    SectionDetailView:focus {
        border: heavy #6df7ff;
        background: #10364b;
    }
    """

    def __init__(
        self,
        section: DetailSectionSnapshot,
        query: str = '',
        rendering: WorkspaceRenderingSupport | None = None,
    ) -> None:
        """
        初始化详情页分区内容展示组件。

        :param section: 当前展示的分区快照
        :param rendering: 工作台组件渲染支持对象
        :return: None
        """
        self.section = section
        self.search_query = query
        self.rendering = rendering or WORKSPACE_RENDERING
        super().__init__(markup=False)
        self.can_focus = True
        self._render_section()

    def show_section(self, section: DetailSectionSnapshot, query: str = '') -> None:
        """
        切换并渲染当前展示的分区内容。

        :param section: 待展示的分区快照
        :return: None
        """
        self.section = section
        self.search_query = query
        self._render_section()

    def _render_section(self) -> None:
        """
        渲染当前分区内容。

        :return: None
        """
        self.remove_class('is-ok', 'is-fail', 'is-warn', 'is-info')
        self.add_class(self.rendering.resolve_status_class(self.section.status))
        highlighted_lines = [
            self.rendering.highlight_search_text(line, self.search_query) for line in self.section.lines
        ]
        body = self.rendering.render_structured_lines(
            highlighted_lines,
            TUI_COPY.build_workspace_empty_text('detail'),
        )
        self.update(
            '\n'.join(
                TUI_COPY.build_section_detail_lines(
                    self.rendering.highlight_search_text(self.section.title, self.search_query),
                    TUI_COPY.render_status_label(self.section.status),
                    self.rendering.render_status_badge(self.section.status),
                    body,
                )
            )
        )


class RecordListItem(ListItem):
    """
    浏览页记录导航列表项。

    :param record: 记录快照
    :param index: 记录索引
    """

    DEFAULT_CSS = """
    RecordListItem {
        padding: 0 1;
        margin-bottom: 1;
        border: round #123148;
        background: #07131f;
        color: #a3c8d2;
        height: auto;
    }

    RecordListItem Label {
        width: 1fr;
    }

    RecordListItem.is-ok {
        border: round #22c983;
        background: #081b17;
    }

    RecordListItem.is-fail {
        border: round #ff6b7a;
        background: #241118;
    }

    RecordListItem.is-warn {
        border: round #f2b84b;
        background: #261d0f;
    }

    RecordListItem.is-info {
        border: round #38d8ff;
        background: #081825;
    }

    RecordListItem.-highlight {
        border: heavy #6df7ff;
        background: #10364b;
        color: #ffffff;
        text-style: bold;
        padding-left: 2;
    }
    """

    def __init__(
        self,
        record: BrowserRecordSnapshot,
        index: int,
        query: str = '',
        rendering: WorkspaceRenderingSupport | None = None,
    ) -> None:
        """
        初始化浏览页记录导航项。

        :param record: 记录快照
        :param index: 记录索引
        :param rendering: 工作台组件渲染支持对象
        :return: None
        """
        self.record = record
        self.index = index
        self.search_query = query
        self.rendering = rendering or WORKSPACE_RENDERING
        super().__init__(
            Label(
                '\n'.join(
                    TUI_COPY.build_record_item_lines(
                        index,
                        self.rendering.highlight_search_text(record.title, query),
                        self.rendering.render_status_badge(record.status),
                        self.rendering.highlight_search_text(record.summary, query),
                    )
                ),
                markup=False,
            )
        )
        self.add_class(self.rendering.resolve_status_class(record.status))


class RecordNavigator(ListView):
    """
    浏览页记录导航组件。

    :param records: 记录快照列表
    :param initial_index: 初始高亮索引
    """

    DEFAULT_CSS = """
    RecordNavigator {
        width: 34;
        min-width: 34;
        border: double #18425d;
        padding: 1;
        margin-right: 1;
        background: #06111b;
    }

    RecordNavigator:focus {
        border: heavy #6df7ff;
    }
    """

    class Changed(Message):
        """
        记录导航高亮变更消息。
        """

        def __init__(self, navigator: 'RecordNavigator', index: int, item: RecordListItem) -> None:
            super().__init__()
            self.navigator = navigator
            self.index = index
            self.item = item

        @property
        def control(self) -> 'RecordNavigator':
            return self.navigator

    def __init__(
        self,
        records: list[BrowserRecordSnapshot],
        initial_index: int = 0,
        query: str = '',
        rendering: WorkspaceRenderingSupport | None = None,
    ) -> None:
        """
        初始化浏览页记录导航。

        :param records: 记录快照列表
        :param initial_index: 初始高亮索引
        :param rendering: 工作台组件渲染支持对象
        :return: None
        """
        self.records = records
        self.search_query = query
        self.rendering = rendering or WORKSPACE_RENDERING
        children = [
            RecordListItem(record, index, query=query, rendering=self.rendering) for index, record in enumerate(records)
        ]
        super().__init__(*children, initial_index=initial_index, id='record-navigator')

    def watch_index(self, old_index: int | None, new_index: int | None) -> None:
        """
        在高亮变化后向父级发送明确的记录切换消息。

        :param old_index: 旧索引
        :param new_index: 新索引
        :return: None
        """
        super().watch_index(old_index, new_index)
        if new_index is None or not 0 <= new_index < len(self._nodes):
            return
        item = self._nodes[new_index]
        if isinstance(item, RecordListItem):
            self.post_message(self.Changed(self, new_index, item))


class RecordDetailView(Static):
    """
    浏览页记录详情展示组件。

    :param record: 当前展示的记录快照
    :param shared_sections: 页面共享分区列表
    """

    DEFAULT_CSS = """
    RecordDetailView {
        border: double #245874;
        padding: 1 2;
        background: #08131f;
        color: #ddf8ff;
        width: 1fr;
        min-height: 18;
        overflow-x: auto;
        overflow-y: auto;
    }

    RecordDetailView.is-ok {
        border: double #22c983;
    }

    RecordDetailView.is-fail {
        border: double #ff6b7a;
    }

    RecordDetailView.is-warn {
        border: double #f2b84b;
    }

    RecordDetailView.is-info {
        border: double #38d8ff;
    }

    RecordDetailView:focus {
        border: heavy #6df7ff;
        background: #10364b;
    }
    """

    def __init__(
        self,
        record: BrowserRecordSnapshot,
        shared_sections: list[DetailSectionSnapshot],
        query: str = '',
        rendering: WorkspaceRenderingSupport | None = None,
    ) -> None:
        """
        初始化浏览页记录详情展示组件。

        :param record: 当前展示的记录快照
        :param shared_sections: 页面共享分区列表
        :param rendering: 工作台组件渲染支持对象
        :return: None
        """
        self.record = record
        self.shared_sections = shared_sections
        self.search_query = query
        self.rendering = rendering or WORKSPACE_RENDERING
        super().__init__(id='record-detail-view', markup=False)
        self.can_focus = True
        self._render_record()

    def show_record(
        self,
        record: BrowserRecordSnapshot,
        shared_sections: list[DetailSectionSnapshot],
        query: str = '',
    ) -> None:
        """
        切换并渲染当前展示的记录内容。

        :param record: 待展示的记录快照
        :param shared_sections: 页面共享分区列表
        :return: None
        """
        self.record = record
        self.shared_sections = shared_sections
        self.search_query = query
        self._render_record()

    def _render_record(self) -> None:
        """
        渲染当前记录内容。

        :return: None
        """
        self.remove_class('is-ok', 'is-fail', 'is-warn', 'is-info')
        self.add_class(self.rendering.resolve_status_class(self.record.status))
        lines = [
            (
                f'{self.rendering.render_status_badge(self.record.status)} '
                f'{self.rendering.highlight_search_text(self.record.title, self.search_query)}'
            ),
            f'{TUI_COPY.build_workspace_label("overview")} · {self.rendering.highlight_search_text(self.record.summary, self.search_query)}',
            '',
        ]
        if self.record.metadata_lines:
            lines.append(TUI_COPY.build_workspace_title('key_info'))
            lines.append('────────────────')
            lines.append(
                self.rendering.render_structured_lines(
                    [
                        self.rendering.highlight_search_text(line, self.search_query)
                        for line in self.record.metadata_lines
                    ],
                    TUI_COPY.build_workspace_empty_text('key_info'),
                )
            )
            lines.append('')

        combined_sections = [*self.record.detail_sections, *self.shared_sections]
        if not combined_sections:
            lines.append(TUI_COPY.build_workspace_title('detail_content'))
            lines.append('========')
            lines.append(f'- {TUI_COPY.build_workspace_empty_text("detail")}')
        else:
            for section in combined_sections:
                lines.append('-' * 44)
                lines.append(
                    f'{self.rendering.render_status_badge(section.status)} '
                    f'{self.rendering.highlight_search_text(section.title, self.search_query)}'
                )
                lines.append(
                    self.rendering.render_structured_lines(
                        [self.rendering.highlight_search_text(line, self.search_query) for line in section.lines],
                        TUI_COPY.build_workspace_empty_text('detail'),
                    )
                )
                lines.append('')
        self.update('\n'.join(lines).strip())


class RecordSummaryView(Static):
    """
    浏览页记录摘要展示组件。

    :param record: 当前展示的记录快照
    """

    DEFAULT_CSS = """
    RecordSummaryView {
        border: double #38d8ff;
        padding: 1 2;
        margin-bottom: 1;
        background: #081827;
        color: #e9fcff;
        overflow-x: auto;
        overflow-y: auto;
    }

    RecordSummaryView.is-ok {
        border: double #22c983;
        background: #081b17;
    }

    RecordSummaryView.is-fail {
        border: double #ff6b7a;
        background: #241118;
    }

    RecordSummaryView.is-warn {
        border: double #f2b84b;
        background: #261d0f;
    }

    RecordSummaryView.is-info {
        border: double #38d8ff;
        background: #081825;
    }

    RecordSummaryView.section-ok {
        border-left: heavy #22c983;
    }

    RecordSummaryView.section-fail {
        border-left: heavy #ff6b7a;
    }

    RecordSummaryView.section-warn {
        border-left: heavy #f2b84b;
    }

    RecordSummaryView.section-info {
        border-left: heavy #38d8ff;
    }

    RecordSummaryView:focus {
        border: heavy #6df7ff;
        background: #10364b;
    }
    """

    def __init__(
        self,
        record: BrowserRecordSnapshot,
        rendering: WorkspaceRenderingSupport | None = None,
    ) -> None:
        """
        初始化浏览页记录摘要展示组件。

        :param record: 当前展示的记录快照
        :param rendering: 工作台组件渲染支持对象
        :return: None
        """
        self.record = record
        self.section: DetailSectionSnapshot | None = None
        self.action_lines: list[str] = []
        self.search_query = ''
        self.rendering = rendering or WORKSPACE_RENDERING
        super().__init__(id='record-summary-view', markup=False)
        self.can_focus = True
        self._render_record()

    def show_record(
        self,
        record: BrowserRecordSnapshot,
        selected_section: DetailSectionSnapshot | None = None,
        action_lines: list[str] | None = None,
        query: str = '',
    ) -> None:
        """
        更新当前展示的记录摘要。

        :param record: 待展示的记录快照
        :param selected_section: 当前联动分区
        :param action_lines: 动作摘要文本
        :return: None
        """
        self.record = record
        self.section = selected_section
        self.action_lines = list(action_lines or [])
        self.search_query = query
        self._render_record()

    def _render_record(self) -> None:
        """
        渲染当前记录摘要。

        :return: None
        """
        self.remove_class('is-ok', 'is-fail', 'is-warn', 'is-info')
        self.remove_class('section-ok', 'section-fail', 'section-warn', 'section-info')
        self.add_class(self.rendering.resolve_status_class(self.record.status))
        if self.section is not None:
            self.add_class(
                f'section-{self.section.status if self.section.status in {"ok", "fail", "warn"} else "info"}'
            )
        lines = [
            (
                f'{self.rendering.render_status_badge(self.record.status)} '
                f'{self.rendering.highlight_search_text(self.record.title, self.search_query)}'
            ),
            f'{TUI_COPY.build_workspace_label("overview")} · {self.rendering.highlight_search_text(self.record.summary, self.search_query)}',
        ]
        if self.section is not None:
            lines.append(
                f'{TUI_COPY.build_workspace_label("current_section")} · {self.rendering.highlight_search_text(self.section.title, self.search_query)} / {TUI_COPY.render_status_label(self.section.status)}'
            )
        if self.record.metadata_lines:
            lines.append('')
            lines.append(TUI_COPY.build_workspace_title('key_fields'))
            lines.append('────────────────')
            lines.append(
                self.rendering.render_structured_lines(
                    [
                        self.rendering.highlight_search_text(line, self.search_query)
                        for line in self.record.metadata_lines
                    ],
                    TUI_COPY.build_workspace_empty_text('key_info'),
                )
            )
        if self.action_lines:
            lines.append('')
            lines.append(TUI_COPY.build_workspace_title('action_feedback'))
            lines.append('────────────────')
            lines.append(
                self.rendering.render_structured_lines(
                    [self.rendering.highlight_search_text(line, self.search_query) for line in self.action_lines],
                    TUI_COPY.build_workspace_empty_text('actions'),
                )
            )
        self.update('\n'.join(lines))
