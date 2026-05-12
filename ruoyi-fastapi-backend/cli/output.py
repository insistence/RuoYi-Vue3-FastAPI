import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

import typer

from cli.context import CliContext


@dataclass
class OutputSettings:
    """
    输出渲染配置。

    :param color_mode: 颜色模式
    :param icon_mode: 图标模式
    """

    color_mode: str = 'always'
    icon_mode: str = 'emoji'


@dataclass(frozen=True)
class StatusTokenDefinition:
    """
    状态标签定义。

    :param emoji: emoji 模式文案
    :param ascii: ASCII 模式文案
    :param none: 无图标模式文案
    :param color: 默认前景色
    """

    emoji: str
    ascii: str
    none: str
    color: str


@dataclass
class CommandResult:
    """
    统一命令执行结果。

    :param data: 命令结果负载
    :param exit_code: 命令退出码
    :param already_printed: 是否已由上层提前输出
    """

    data: Any = None
    exit_code: int = 0
    already_printed: bool = False


class OutputStatusStyler:
    """
    统一负责状态标签与单行文本样式。

    :param settings: 输出配置
    """

    _STATUS_DEFINITIONS = {
        'ok': StatusTokenDefinition(emoji='✅ OK', ascii='[OK]', none='OK', color='green'),
        'fail': StatusTokenDefinition(emoji='❌ FAIL', ascii='[FAIL]', none='FAIL', color='red'),
        'warn': StatusTokenDefinition(emoji='💡 HINT', ascii='[HINT]', none='HINT', color='yellow'),
        'error': StatusTokenDefinition(emoji='🚨 ERROR', ascii='[ERROR]', none='ERROR', color='red'),
        'info': StatusTokenDefinition(emoji='💬 INFO', ascii='[INFO]', none='INFO', color='blue'),
    }
    _STATUS_FIELD_KIND_MAPPING = {
        'message': 'info',
        'info': 'info',
        'hint': 'warn',
        'warn': 'warn',
        'warning': 'warn',
        'error': 'error',
    }

    def __init__(self, settings: OutputSettings) -> None:
        """
        初始化状态样式器。

        :param settings: 输出配置
        :return: None
        """
        self.settings = settings

    def supports_color(self, stream: Any) -> bool:
        """
        判断当前输出流是否应启用颜色。

        :param stream: 输出流对象
        :return: 是否启用颜色
        """
        if self.settings.color_mode == 'always':
            return True
        if self.settings.color_mode == 'never':
            return False
        if os.environ.get('NO_COLOR'):
            return False
        if os.environ.get('TERM') == 'dumb':
            return False
        return bool(getattr(stream, 'isatty', lambda: False)())

    @staticmethod
    def style_text(text: str, *, fg: str | None = None, bold: bool = False, dim: bool = False) -> str:
        """
        为文本附加终端样式。

        :param text: 原始文本
        :param fg: 前景色
        :param bold: 是否加粗
        :param dim: 是否弱化显示
        :return: 样式化后的文本
        """
        return typer.style(text, fg=fg, bold=bold, dim=dim)

    def get_status_definition(self, kind: str) -> StatusTokenDefinition:
        """
        获取状态标签定义。

        :param kind: 状态类型
        :return: 状态标签定义
        """
        return self._STATUS_DEFINITIONS.get(kind, self._STATUS_DEFINITIONS['info'])

    def build_status_token(self, kind: str) -> str:
        """
        根据当前图标模式构建状态标签文本。

        :param kind: 标签类型
        :return: 标签文本
        """
        definition = self.get_status_definition(kind)
        return getattr(definition, self.settings.icon_mode, definition.none)

    def style_status_token(self, kind: str, *, fg: str | None = None) -> str:
        """
        将状态标签渲染为高亮样式。

        :param kind: 标签类型
        :param fg: 前景色
        :return: 样式化后的标签文本
        """
        definition = self.get_status_definition(kind)
        return self.style_text(self.build_status_token(kind), fg=fg or definition.color, bold=True)

    def style_status_message(self, kind: str, text: str) -> str:
        """
        使用统一状态图标和颜色渲染消息文本。

        :param kind: 状态类型
        :param text: 原始消息文本
        :return: 样式化后的消息文本
        """
        color = self.get_status_definition(kind).color
        return f'{self.style_status_token(kind, fg=color)} {self.style_text(text, fg=color, bold=kind == "error")}'

    def build_result_header(self, is_ok: bool) -> str:
        """
        构建统一的结果头部文本。

        :param is_ok: 是否成功
        :return: 结果头部文本
        """
        if is_ok:
            return f'{self.build_status_token("ok")} SUCCESS'
        return f'{self.build_status_token("fail")} FAILED'

    def style_scalar_text(self, value: str) -> str:
        """
        为标量文本值应用颜色样式。

        :param value: 原始标量文本
        :return: 样式化后的文本
        """
        normalized_value = value.strip().lower()
        if normalized_value == 'true':
            return self.style_text(value, fg='green', bold=True)
        if normalized_value == 'false':
            return self.style_text(value, fg='red', bold=True)
        if normalized_value in {'null', 'none', '-'}:
            return self.style_text(value, fg='bright_black')
        return value

    def style_inline_status_segment(self, segment: str) -> str:
        """
        为行内状态片段应用样式。

        :param segment: 原始片段文本
        :return: 样式化后的片段文本
        """
        normalized_segment = segment.strip().lower()
        if normalized_segment == 'true':
            return self.style_status_token('ok', fg='green')
        if normalized_segment == 'false':
            return self.style_status_token('fail', fg='red')
        for prefix, kind in self._STATUS_FIELD_KIND_MAPPING.items():
            if normalized_segment.startswith(f'{prefix}:'):
                status_message = segment.split(':', 1)[1].strip()
                return self.style_status_message(kind, status_message)
        if ': ' in segment:
            segment_key, segment_value = segment.split(': ', 1)
            styled_segment_value = self.style_inline_status_value(segment_value)
            if styled_segment_value != segment_value:
                return f'{segment_key}: {styled_segment_value}'
        return segment

    def style_inline_status_value(self, value: str) -> str:
        """
        为带分隔符的行内状态值应用样式。

        :param value: 原始字段值
        :return: 样式化后的字段值
        """
        if ' | ' not in value:
            styled_value = self.style_inline_status_segment(value)
            if styled_value != value:
                return styled_value
            return self.style_scalar_text(value)
        return ' | '.join(self.style_inline_status_segment(segment) for segment in value.split(' | '))

    def style_named_value(self, key: str, value: str) -> str:
        """
        按字段语义为值应用样式。

        :param key: 字段名
        :param value: 原始字段值
        :return: 样式化后的字段值
        """
        normalized_key = key.strip().lower()
        normalized_value = value.strip().lower()

        if normalized_key == 'ok':
            if normalized_value == 'true':
                return self.style_status_token('ok', fg='green')
            if normalized_value == 'false':
                return self.style_status_token('fail', fg='red')

        status_kind = self._STATUS_FIELD_KIND_MAPPING.get(normalized_key)
        if status_kind:
            return self.style_status_message(status_kind, value)

        return self.style_inline_status_value(value)

    def style_line(self, line: str) -> str:
        """
        对单行文本输出应用可读性增强样式。

        :param line: 原始输出行
        :return: 样式化后的输出行
        """
        if not line.strip():
            return line

        leading_spaces = len(line) - len(line.lstrip(' '))
        indent = line[:leading_spaces]
        content = line[leading_spaces:]

        if content == self.build_result_header(True):
            return (
                f'{indent}{self.style_status_token("ok", fg="green")} '
                f'{self.style_text("SUCCESS", fg="green", bold=True)}'
            )
        if content == self.build_result_header(False):
            return (
                f'{indent}{self.style_status_token("fail", fg="red")} {self.style_text("FAILED", fg="red", bold=True)}'
            )

        if content.startswith('- '):
            return (
                f'{indent}{self.style_text("-", fg="bright_black", bold=True)} '
                f'{self.style_inline_status_value(content[2:])}'
            )

        if ': ' in content:
            key, value = content.split(': ', 1)
            styled_key = self.style_text(f'{key}:', fg='cyan', bold=leading_spaces == 0)
            return f'{indent}{styled_key} {self.style_named_value(key, value)}'

        if content.endswith(':'):
            return f'{indent}{self.style_text(content, fg="blue", bold=True)}'

        if content == '|':
            return f'{indent}{self.style_text(content, fg="bright_black")}'

        return line

    def render_error_text(self, message: str, exit_code: int, stream: Any) -> str:
        """
        渲染标准错误输出文本。

        :param message: 错误消息
        :param exit_code: 退出码
        :param stream: 输出流对象
        :return: 渲染后的错误文本
        """
        error_prefix = f'{self.build_status_token("error")}[{exit_code}]:'
        if not self.supports_color(stream):
            return f'{error_prefix} {message}'
        return (
            f'{self.style_status_token("error", fg="red")}[{exit_code}]: '
            f'{self.style_text(message, fg="red", bold=True)}'
        )


class StructuredTextRenderer:
    """
    负责结构化数据到文本的转换与装饰。

    :param status_styler: 状态样式器
    """

    _SNAKE_CASE_BOUNDARY_PATTERN = re.compile(r'(?<!^)(?=[A-Z])')

    def __init__(self, status_styler: OutputStatusStyler) -> None:
        """
        初始化结构化文本渲染器。

        :param status_styler: 状态样式器
        :return: None
        """
        self.status_styler = status_styler

    def render_text_output(self, data: Any) -> str:
        """
        将任意数据渲染为纯文本输出。

        :param data: 待渲染数据
        :return: 文本输出结果
        """
        if isinstance(data, str):
            return data
        return '\n'.join(self.render_text_lines(data))

    def colorize_text_output(self, text: str, stream: Any) -> str:
        """
        按终端能力为文本输出增加颜色。

        :param text: 原始文本输出
        :param stream: 输出流对象
        :return: 样式化后的文本输出
        """
        if not self.status_styler.supports_color(stream):
            return text
        return '\n'.join(self.status_styler.style_line(line) for line in text.splitlines())

    def decorate_text_output(self, text: str) -> str:
        """
        对文本输出进行结构化装饰。

        :param text: 原始文本输出
        :return: 装饰后的文本输出
        """
        lines = text.splitlines()
        if not lines:
            return text

        first_non_empty_index = next((index for index, line in enumerate(lines) if line.strip()), None)
        if first_non_empty_index is None:
            return text

        first_line = lines[first_non_empty_index].strip().lower()
        if first_line == 'ok: true':
            decorated_lines = list(lines)
            decorated_lines[first_non_empty_index] = self.status_styler.build_result_header(True)
            return '\n'.join(decorated_lines)
        if first_line == 'ok: false':
            decorated_lines = list(lines)
            decorated_lines[first_non_empty_index] = self.status_styler.build_result_header(False)
            return '\n'.join(decorated_lines)
        return text

    @staticmethod
    def format_scalar(value: Any) -> str:
        """
        将标量值格式化为文本输出。

        :param value: 待格式化的值
        :return: 文本格式化结果
        """
        if value is None:
            return 'null'
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return str(value)

    @classmethod
    def format_field_name(cls, key: object) -> str:
        """
        将字段名标准化为文本输出使用的 `snake_case` 形式。

        :param key: 原始字段名
        :return: 标准化后的字段名
        """
        text = str(key).strip()
        if not text:
            return ''
        normalized_text = text.replace('-', '_').replace(' ', '_')
        return cls._SNAKE_CASE_BOUNDARY_PATTERN.sub('_', normalized_text).lower()

    def append_multiline_text(self, lines: list[str], prefix: str, value: str, indent: str) -> None:
        """
        将多行文本追加到输出行列表中。

        :param lines: 输出行列表
        :param prefix: 当前字段前缀
        :param value: 多行文本内容
        :param indent: 子级缩进
        :return: None
        """
        lines.append(f'{prefix} |')
        lines.extend(f'{indent}{line}' for line in value.splitlines())

    def render_nested_lines(self, prefix: str, nested_data: dict[str, Any] | list[Any], indent_level: int) -> list[str]:
        """
        渲染嵌套字典或列表字段。

        :param prefix: 当前字段前缀
        :param nested_data: 嵌套数据
        :param indent_level: 当前缩进层级
        :return: 渲染后的文本行列表
        """
        nested_lines = self.render_text_lines(nested_data, indent_level=indent_level + 1)
        if len(nested_lines) == 1 and nested_lines[0].strip() in {'{}', '[]'}:
            return [f'{prefix} {nested_lines[0].strip()}']
        return [prefix, *nested_lines]

    def render_mapping_lines(self, data: dict[str, Any], *, indent_level: int) -> list[str]:
        """
        将字典渲染为层级化文本输出。

        :param data: 待渲染字典
        :param indent_level: 当前缩进层级
        :return: 文本输出行列表
        """
        indent = '  ' * indent_level
        child_indent = '  ' * (indent_level + 1)
        if not data:
            return [f'{indent}{{}}']

        lines: list[str] = []
        for key, value in data.items():
            field_name = self.format_field_name(key)
            prefix = f'{indent}{field_name}:'
            if isinstance(value, str) and '\n' in value:
                self.append_multiline_text(lines, prefix, value, child_indent)
                continue
            if isinstance(value, dict | list):
                lines.extend(self.render_nested_lines(prefix, value, indent_level))
                continue
            lines.append(f'{prefix} {self.format_scalar(value)}')
        return lines

    def render_list_lines(self, data: list[Any], *, indent_level: int) -> list[str]:
        """
        将列表渲染为层级化文本输出。

        :param data: 待渲染列表
        :param indent_level: 当前缩进层级
        :return: 文本输出行列表
        """
        indent = '  ' * indent_level
        child_indent = '  ' * (indent_level + 1)
        if not data:
            return [f'{indent}[]']

        lines: list[str] = []
        for item in data:
            item_prefix = f'{indent}-'
            if isinstance(item, str) and '\n' in item:
                self.append_multiline_text(lines, item_prefix, item, child_indent)
                continue
            if isinstance(item, dict | list):
                lines.extend(self.render_nested_lines(item_prefix, item, indent_level))
                continue
            lines.append(f'{item_prefix} {self.format_scalar(item)}')
        return lines

    def render_text_lines(self, data: Any, *, indent_level: int = 0) -> list[str]:
        """
        将任意数据结构渲染为层级化文本输出。

        :param data: 待渲染数据
        :param indent_level: 当前缩进层级
        :return: 文本输出行列表
        """
        if isinstance(data, dict):
            return self.render_mapping_lines(data, indent_level=indent_level)

        if isinstance(data, list):
            return self.render_list_lines(data, indent_level=indent_level)

        indent = '  ' * indent_level
        if isinstance(data, str) and '\n' in data:
            return [f'{indent}{line}' for line in data.splitlines()]

        return [f'{indent}{self.format_scalar(data)}']


class OutputEmitter:
    """
    负责标准输出、标准错误与命令退出收口。

    :param text_renderer: 结构化文本渲染器
    :param status_styler: 状态样式器
    """

    def __init__(self, text_renderer: StructuredTextRenderer, status_styler: OutputStatusStyler) -> None:
        """
        初始化输出发射器。

        :param text_renderer: 结构化文本渲染器
        :param status_styler: 状态样式器
        :return: None
        """
        self.text_renderer = text_renderer
        self.status_styler = status_styler

    def emit_output(self, data: Any, output_format: str) -> None:
        """
        输出命令结果。

        :param data: 输出数据
        :param output_format: 输出格式
        :return: None
        """
        if data is None:
            return
        if output_format == 'json':
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            return
        rendered_text = self.text_renderer.decorate_text_output(self.text_renderer.render_text_output(data))
        print(self.text_renderer.colorize_text_output(rendered_text, sys.stdout))

    def emit_error(self, message: str, output_format: str, *, exit_code: int) -> None:
        """
        输出错误信息。

        :param message: 错误消息
        :param output_format: 输出格式
        :param exit_code: 退出码
        :return: None
        """
        if output_format == 'json':
            print(
                json.dumps({'ok': False, 'error': message, 'exitCode': exit_code}, ensure_ascii=False),
                file=sys.stderr,
            )
            return
        print(self.status_styler.render_error_text(message, exit_code, sys.stderr), file=sys.stderr)

    def complete_command(self, result: CommandResult, ctx: CliContext) -> None:
        """
        输出命令结果并结束当前命令。

        :param result: 命令执行结果
        :param ctx: CLI 上下文
        :return: None
        :raises typer.Exit: 始终通过 Typer 退出并返回对应退出码
        """
        if not result.already_printed:
            self.emit_output(result.data, ctx.output)
        raise typer.Exit(code=result.exit_code)


class OutputRenderer:
    """
    CLI 输出渲染门面。

    :param color_mode: 颜色模式
    :param icon_mode: 图标模式
    """

    def __init__(self, *, color_mode: str = 'always', icon_mode: str = 'emoji') -> None:
        """
        初始化输出渲染器。

        :param color_mode: 颜色模式，支持 `auto`、`always`、`never`
        :param icon_mode: 图标模式，支持 `emoji`、`ascii`、`none`
        :return: None
        """
        self.settings = OutputSettings(color_mode=color_mode, icon_mode=icon_mode)
        self.status_styler = OutputStatusStyler(self.settings)
        self.text_renderer = StructuredTextRenderer(self.status_styler)
        self.emitter = OutputEmitter(self.text_renderer, self.status_styler)

    @property
    def color_mode(self) -> str:
        """
        返回当前颜色模式。

        :return: 颜色模式
        """
        return self.settings.color_mode

    @property
    def icon_mode(self) -> str:
        """
        返回当前图标模式。

        :return: 图标模式
        """
        return self.settings.icon_mode

    def set_color_mode(self, color_mode: str) -> None:
        """
        设置颜色模式。

        :param color_mode: 颜色模式
        :return: None
        """
        self.settings.color_mode = color_mode

    def set_icon_mode(self, icon_mode: str) -> None:
        """
        设置图标模式。

        :param icon_mode: 图标模式
        :return: None
        """
        self.settings.icon_mode = icon_mode

    def supports_color(self, stream: Any) -> bool:
        """
        判断当前输出流是否应启用颜色。

        :param stream: 输出流对象
        :return: 是否启用颜色
        """
        return self.status_styler.supports_color(stream)

    @staticmethod
    def style_text(text: str, *, fg: str | None = None, bold: bool = False, dim: bool = False) -> str:
        """
        为文本附加终端样式。

        :param text: 原始文本
        :param fg: 前景色
        :param bold: 是否加粗
        :param dim: 是否弱化显示
        :return: 样式化后的文本
        """
        return OutputStatusStyler.style_text(text, fg=fg, bold=bold, dim=dim)

    def build_status_token(self, kind: str) -> str:
        """
        根据当前图标模式构建状态标签文本。

        :param kind: 标签类型
        :return: 标签文本
        """
        return self.status_styler.build_status_token(kind)

    def style_status_token(self, kind: str, *, fg: str) -> str:
        """
        将状态标签渲染为高亮样式。

        :param kind: 标签类型
        :param fg: 前景色
        :return: 样式化后的标签文本
        """
        return self.status_styler.style_status_token(kind, fg=fg)

    def style_status_message(self, kind: str, text: str) -> str:
        """
        使用统一状态图标和颜色渲染消息文本。

        :param kind: 状态类型
        :param text: 原始消息文本
        :return: 样式化后的消息文本
        """
        return self.status_styler.style_status_message(kind, text)

    def build_result_header(self, is_ok: bool) -> str:
        """
        构建统一的结果头部文本。

        :param is_ok: 是否成功
        :return: 结果头部文本
        """
        return self.status_styler.build_result_header(is_ok)

    def style_scalar_text(self, value: str) -> str:
        """
        为标量文本值应用颜色样式。

        :param value: 原始标量文本
        :return: 样式化后的文本
        """
        return self.status_styler.style_scalar_text(value)

    def style_inline_status_segment(self, segment: str) -> str:
        """
        为行内状态片段应用样式。

        :param segment: 原始片段文本
        :return: 样式化后的片段文本
        """
        return self.status_styler.style_inline_status_segment(segment)

    def style_inline_status_value(self, value: str) -> str:
        """
        为带分隔符的行内状态值应用样式。

        :param value: 原始字段值
        :return: 样式化后的字段值
        """
        return self.status_styler.style_inline_status_value(value)

    def style_named_value(self, key: str, value: str) -> str:
        """
        按字段语义为值应用样式。

        :param key: 字段名
        :param value: 原始字段值
        :return: 样式化后的字段值
        """
        return self.status_styler.style_named_value(key, value)

    def style_line(self, line: str) -> str:
        """
        对单行文本输出应用可读性增强样式。

        :param line: 原始输出行
        :return: 样式化后的输出行
        """
        return self.status_styler.style_line(line)

    def render_text_output(self, data: Any) -> str:
        """
        将任意数据渲染为纯文本输出。

        :param data: 待渲染数据
        :return: 文本输出结果
        """
        return self.text_renderer.render_text_output(data)

    def colorize_text_output(self, text: str, stream: Any) -> str:
        """
        按终端能力为文本输出增加颜色。

        :param text: 原始文本输出
        :param stream: 输出流对象
        :return: 样式化后的文本输出
        """
        return self.text_renderer.colorize_text_output(text, stream)

    def decorate_text_output(self, text: str) -> str:
        """
        对文本输出进行结构化装饰。

        :param text: 原始文本输出
        :return: 装饰后的文本输出
        """
        return self.text_renderer.decorate_text_output(text)

    @staticmethod
    def format_scalar(value: Any) -> str:
        """
        将标量值格式化为文本输出。

        :param value: 待格式化的值
        :return: 文本格式化结果
        """
        return StructuredTextRenderer.format_scalar(value)

    @staticmethod
    def format_field_name(key: object) -> str:
        """
        将字段名标准化为文本输出使用的 `snake_case` 形式。

        :param key: 原始字段名
        :return: 标准化后的字段名
        """
        return StructuredTextRenderer.format_field_name(key)

    def append_multiline_text(self, lines: list[str], prefix: str, value: str, indent: str) -> None:
        """
        将多行文本追加到输出行列表中。

        :param lines: 输出行列表
        :param prefix: 当前字段前缀
        :param value: 多行文本内容
        :param indent: 子级缩进
        :return: None
        """
        self.text_renderer.append_multiline_text(lines, prefix, value, indent)

    def render_nested_lines(self, prefix: str, nested_data: dict[str, Any] | list[Any], indent_level: int) -> list[str]:
        """
        渲染嵌套字典或列表字段。

        :param prefix: 当前字段前缀
        :param nested_data: 嵌套数据
        :param indent_level: 当前缩进层级
        :return: 渲染后的文本行列表
        """
        return self.text_renderer.render_nested_lines(prefix, nested_data, indent_level)

    def render_mapping_lines(self, data: dict[str, Any], *, indent_level: int) -> list[str]:
        """
        将字典渲染为层级化文本输出。

        :param data: 待渲染字典
        :param indent_level: 当前缩进层级
        :return: 文本输出行列表
        """
        return self.text_renderer.render_mapping_lines(data, indent_level=indent_level)

    def render_list_lines(self, data: list[Any], *, indent_level: int) -> list[str]:
        """
        将列表渲染为层级化文本输出。

        :param data: 待渲染列表
        :param indent_level: 当前缩进层级
        :return: 文本输出行列表
        """
        return self.text_renderer.render_list_lines(data, indent_level=indent_level)

    def render_text_lines(self, data: Any, *, indent_level: int = 0) -> list[str]:
        """
        将任意数据结构渲染为层级化文本输出。

        :param data: 待渲染数据
        :param indent_level: 当前缩进层级
        :return: 文本输出行列表
        """
        return self.text_renderer.render_text_lines(data, indent_level=indent_level)

    def emit_output(self, data: Any, output_format: str) -> None:
        """
        输出命令结果。

        :param data: 输出数据
        :param output_format: 输出格式
        :return: None
        """
        self.emitter.emit_output(data, output_format)

    def render_error_text(self, message: str, exit_code: int, stream: Any) -> str:
        """
        渲染标准错误输出文本。

        :param message: 错误消息
        :param exit_code: 退出码
        :param stream: 输出流对象
        :return: 渲染后的错误文本
        """
        return self.status_styler.render_error_text(message, exit_code, stream)

    def emit_error(self, message: str, output_format: str, *, exit_code: int) -> None:
        """
        输出错误信息。

        :param message: 错误消息
        :param output_format: 输出格式
        :param exit_code: 退出码
        :return: None
        """
        self.emitter.emit_error(message, output_format, exit_code=exit_code)

    def complete_command(self, result: CommandResult, ctx: CliContext) -> None:
        """
        输出命令结果并结束当前命令。

        :param result: 命令执行结果
        :param ctx: CLI 上下文
        :return: None
        """
        self.emitter.complete_command(result, ctx)
