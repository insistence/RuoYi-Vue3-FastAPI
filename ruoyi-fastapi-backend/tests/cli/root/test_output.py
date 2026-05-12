import importlib
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(BACKEND_DIR))
sys.modules.pop('cli.output', None)
sys.modules.pop('cli', None)

cli_output = importlib.import_module('cli.output')
OUTPUT_RENDERER = cli_output.OutputRenderer()

_ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')


class _FakeStream:
    """
    模拟终端输出流。

    :param is_tty: 是否模拟为 TTY
    """

    def __init__(self, *, is_tty: bool) -> None:
        self._is_tty = is_tty

    def isatty(self) -> bool:
        """
        返回是否为 TTY。

        :return: 是否为 TTY
        """
        return self._is_tty


def _strip_ansi(text: str) -> str:
    """
    移除 ANSI 转义序列，便于断言文本可视结果。

    :param text: 原始带样式文本
    :return: 去除 ANSI 后的文本
    """
    return _ANSI_ESCAPE_PATTERN.sub('', text)


def test_decorate_text_output_promotes_success_header_with_emoji_icon() -> None:
    """
    校验成功结果头在 emoji 模式下会被提升为统一状态头。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('emoji')

    rendered = OUTPUT_RENDERER.decorate_text_output('ok: true\nenv: dev')

    assert rendered == '✅ OK SUCCESS\nenv: dev'


def test_decorate_text_output_promotes_failure_header_with_emoji_icon() -> None:
    """
    校验失败结果头在 emoji 模式下会被提升为统一状态头。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('emoji')

    rendered = OUTPUT_RENDERER.decorate_text_output('ok: false\nerror: boom')

    assert rendered == '❌ FAIL FAILED\nerror: boom'


def test_colorize_text_output_renders_inline_status_segments_with_emoji_icon() -> None:
    """
    校验文本着色后会为 message、hint、error 等字段附加状态标签。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('emoji')
    OUTPUT_RENDERER.set_color_mode('always')
    decorated = OUTPUT_RENDERER.decorate_text_output('ok: false\nmessage: retry later\nhint: use --yes\nerror: boom')

    rendered = OUTPUT_RENDERER.colorize_text_output(decorated, _FakeStream(is_tty=True))

    assert '\x1b[' in rendered
    assert _strip_ansi(rendered) == (
        '❌ FAIL FAILED\nmessage: 💬 INFO retry later\nhint: 💡 HINT use --yes\nerror: 🚨 ERROR boom'
    )


def test_colorize_text_output_supports_warning_and_info_field_aliases() -> None:
    """
    校验 `warning` 与 `info` 字段也会使用统一状态图标渲染。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('emoji')
    OUTPUT_RENDERER.set_color_mode('always')
    decorated = OUTPUT_RENDERER.decorate_text_output('ok: true\nwarning: rotate key soon\ninfo: cache refreshed')

    rendered = OUTPUT_RENDERER.colorize_text_output(decorated, _FakeStream(is_tty=True))

    assert _strip_ansi(rendered) == ('✅ OK SUCCESS\nwarning: 💡 HINT rotate key soon\ninfo: 💬 INFO cache refreshed')


def test_colorize_text_output_styles_status_segments_inside_list_items() -> None:
    """
    校验列表项中的带标签状态片段也会应用统一视觉规则。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('emoji')
    OUTPUT_RENDERER.set_color_mode('always')
    rendered = OUTPUT_RENDERER.colorize_text_output(
        'results:\n  - users: true | exported\n  - roles: false | error: lock timeout',
        _FakeStream(is_tty=True),
    )

    assert _strip_ansi(rendered) == (
        'results:\n  - users: ✅ OK | exported\n  - roles: ❌ FAIL | 🚨 ERROR lock timeout'
    )


def test_colorize_text_output_supports_ascii_icon_mode() -> None:
    """
    校验 ascii 图标模式会渲染为纯 ASCII 状态标签。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('ascii')
    OUTPUT_RENDERER.set_color_mode('always')
    decorated = OUTPUT_RENDERER.decorate_text_output('ok: true\nhint: use --yes')

    rendered = OUTPUT_RENDERER.colorize_text_output(decorated, _FakeStream(is_tty=True))

    assert _strip_ansi(rendered) == '[OK] SUCCESS\nhint: [HINT] use --yes'


def test_colorize_text_output_skips_ansi_when_color_mode_is_never() -> None:
    """
    校验关闭颜色后不会输出 ANSI 转义序列。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('emoji')
    OUTPUT_RENDERER.set_color_mode('never')
    decorated = OUTPUT_RENDERER.decorate_text_output('ok: false\nhint: use --yes')

    rendered = OUTPUT_RENDERER.colorize_text_output(decorated, _FakeStream(is_tty=True))

    assert rendered == '❌ FAIL FAILED\nhint: use --yes'
    assert '\x1b[' not in rendered


def test_render_error_text_uses_status_token_in_emoji_mode() -> None:
    """
    校验标准错误输出在 emoji 模式下使用统一错误图标。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('emoji')
    OUTPUT_RENDERER.set_color_mode('never')

    rendered = OUTPUT_RENDERER.render_error_text('boom', 23, _FakeStream(is_tty=True))

    assert rendered == '🚨 ERROR[23]: boom'


def test_render_error_text_supports_ascii_mode_with_color() -> None:
    """
    校验标准错误输出在 ascii 模式下仍保持统一错误前缀与颜色。

    :return: None
    """
    OUTPUT_RENDERER.set_icon_mode('ascii')
    OUTPUT_RENDERER.set_color_mode('always')

    rendered = OUTPUT_RENDERER.render_error_text('boom', 23, _FakeStream(is_tty=True))

    assert '\x1b[' in rendered
    assert _strip_ansi(rendered) == '[ERROR][23]: boom'
