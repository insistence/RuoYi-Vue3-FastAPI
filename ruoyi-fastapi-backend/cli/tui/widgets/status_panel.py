from textual.widgets import Static

from cli.tui.copy import TUI_COPY


class StatusPanelRenderingSupport:
    """
    状态面板渲染支持对象。

    该对象负责状态类名解析、结构化正文渲染和信号带脉冲文本构建，
    供状态面板、指标卡与信号带组件复用。
    """

    PULSE_FRAMES = ['·', '•', '◉', '•']

    @staticmethod
    def resolve_status_class(status: str) -> str:
        """
        根据状态值解析样式类。

        :param status: 面板状态
        :return: 状态样式类名
        """
        normalized_status = str(status).strip().lower()
        if normalized_status in {'ok', 'success', 'healthy'}:
            return 'is-ok'
        if normalized_status in {'fail', 'error', 'down'}:
            return 'is-fail'
        if normalized_status in {'warn', 'warning', 'degraded'}:
            return 'is-warn'
        return 'is-info'

    def render_structured_body(self, body: str) -> str:
        """
        将结构化正文文本渲染为更有层次的终端块内容。

        支持以下约定：
        - `## ` 开头：分组标题
        - `> ` 开头：说明或子项
        - 空字符串：保留空行

        :param body: 原始正文文本
        :return: 渲染后的正文文本
        """
        rendered_lines: list[str] = []
        for raw_line in body.splitlines():
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
                rendered_lines.append('─' * max(10, min(len(title) * 2, 28)))
                continue
            if stripped.startswith('> '):
                rendered_lines.append(f'│ {stripped[2:].strip()}')
                continue
            rendered_lines.append(f'• {stripped}')

        while rendered_lines and rendered_lines[0] == '':
            rendered_lines.pop(0)
        while rendered_lines and rendered_lines[-1] == '':
            rendered_lines.pop()
        return '\n'.join(rendered_lines) if rendered_lines else f'- {TUI_COPY.build_status_panel_empty_text()}'

    def build_signal_rail_text(self, lines: list[str], pulse_index: int) -> str:
        """
        构建信号带渲染文本。

        :param lines: 信号文本行
        :param pulse_index: 当前脉冲帧索引
        :return: 渲染文本
        """
        pulse = self.PULSE_FRAMES[pulse_index % len(self.PULSE_FRAMES)]
        body = '\n'.join(line for line in lines if line.strip())
        return TUI_COPY.build_signal_rail_text(pulse, body or TUI_COPY.build_signal_rail_empty_text())


STATUS_PANEL_RENDERING = StatusPanelRenderingSupport()


class StatusPanel(Static):
    """
    TUI 状态面板组件。

    :param title: 面板标题
    :param status: 面板状态
    :param body: 面板正文
    """

    DEFAULT_CSS = """
    StatusPanel {
        border: double #245874;
        padding: 1 2;
        margin: 0;
        height: 17;
        min-height: 17;
        background: #08131f;
        color: #def8ff;
    }

    StatusPanel.is-ok {
        border: double #22c983;
        background: #081b17;
    }

    StatusPanel.is-fail {
        border: double #ff6b7a;
        background: #241118;
    }

    StatusPanel.is-warn {
        border: double #f2b84b;
        background: #261d0f;
    }

    StatusPanel.is-info {
        border: double #38d8ff;
        background: #081825;
    }

    StatusPanel:focus {
        border: heavy #6df7ff;
        background: #10364b;
    }
    """

    def __init__(
        self,
        title: str,
        status: str,
        body: str,
        rendering: StatusPanelRenderingSupport | None = None,
    ) -> None:
        """
        初始化状态面板。

        :param title: 面板标题
        :param status: 面板状态
        :param body: 面板正文
        :param rendering: 状态面板渲染支持对象
        :return: None
        """
        self.title = title
        self.status = status
        self.body = body
        self.rendering = rendering or STATUS_PANEL_RENDERING
        super().__init__(self._build_render_text(), markup=False)
        self.can_focus = True
        self.add_class(self.rendering.resolve_status_class(self.status))

    def _build_render_text(self) -> str:
        """
        构建面板渲染文本。

        :return: 渲染文本
        """
        rendered_body = self.rendering.render_structured_body(self.body)
        normalized_status = TUI_COPY.render_status_label(self.status)
        return TUI_COPY.build_status_panel_text(
            self.title,
            TUI_COPY.render_status_code(self.status),
            normalized_status,
            rendered_body,
        )


class MetricPanel(Static):
    """
    TUI 首页驾驶舱指标卡组件。

    :param title: 指标标题
    :param value: 指标主值
    :param status: 指标状态
    :param hint: 指标补充说明
    """

    DEFAULT_CSS = """
    MetricPanel {
        border: double #245874;
        padding: 1 2;
        height: 12;
        min-height: 12;
        background: #08131f;
        color: #effcff;
    }

    MetricPanel.is-primary {
        border: heavy #6df7ff;
        height: 12;
        min-height: 12;
        background: #0a1725;
        text-style: bold;
    }

    MetricPanel.is-ok {
        border: double #22c983;
        background: #081b17;
    }

    MetricPanel.is-fail {
        border: double #ff6b7a;
        background: #241118;
    }

    MetricPanel.is-warn {
        border: double #f2b84b;
        background: #261d0f;
    }

    MetricPanel.is-info {
        border: double #38d8ff;
        background: #081825;
    }
    """

    def __init__(
        self,
        title: str,
        value: str,
        status: str,
        hint: str,
        *,
        accent: bool = False,
        rendering: StatusPanelRenderingSupport | None = None,
    ) -> None:
        """
        初始化指标卡。

        :param title: 指标标题
        :param value: 指标主值
        :param status: 指标状态
        :param hint: 指标补充说明
        :param accent: 是否作为主指标高亮展示
        :param rendering: 状态面板渲染支持对象
        :return: None
        """
        self.title = title
        self.value = value
        self.status = status
        self.hint = hint
        self.rendering = rendering or STATUS_PANEL_RENDERING
        super().__init__(self._build_render_text(), markup=False)
        self.add_class(self.rendering.resolve_status_class(self.status))
        if accent:
            self.add_class('is-primary')

    def _build_render_text(self) -> str:
        """
        构建指标卡渲染文本。

        :return: 渲染文本
        """
        normalized_status = TUI_COPY.render_status_label(self.status)
        return TUI_COPY.build_metric_panel_text(
            self.title,
            self.value,
            TUI_COPY.render_status_code(self.status),
            normalized_status,
            self.hint,
        )


class SignalRail(Static):
    """
    首页信号带组件，用于展示简洁的系统态势条目。

    :param lines: 信号文本行
    """

    DEFAULT_CSS = """
    SignalRail {
        border: double #1db9d1;
        padding: 1 2;
        margin-top: 1;
        margin-bottom: 1;
        min-height: 6;
        background: #06111b;
        color: #e9fdff;
    }
    """

    def __init__(self, lines: list[str], rendering: StatusPanelRenderingSupport | None = None) -> None:
        """
        初始化首页信号带。

        :param lines: 信号文本行
        :param rendering: 状态面板渲染支持对象
        :return: None
        """
        self.lines = lines
        self._pulse_index = 0
        self.rendering = rendering or STATUS_PANEL_RENDERING
        super().__init__(self._build_render_text(), markup=False)

    def on_mount(self) -> None:
        """
        挂载后启动轻量脉冲刷新。

        :return: None
        """
        self.set_interval(0.8, self._advance_pulse, name='signal rail pulse')

    def _advance_pulse(self) -> None:
        """
        推进信号带脉冲状态。

        :return: None
        """
        self._pulse_index = (self._pulse_index + 1) % 4
        self.update(self._build_render_text())

    def _build_render_text(self) -> str:
        """
        构建信号带渲染文本。

        :return: 渲染文本
        """
        return self.rendering.build_signal_rail_text(self.lines, self._pulse_index)
