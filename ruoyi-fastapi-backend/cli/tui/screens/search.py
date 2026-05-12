from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from cli.tui.copy import TUI_COPY


class SearchInputScreen(ModalScreen[str | None]):
    """
    通用搜索输入弹窗。

    :param title: 弹窗标题
    :param placeholder: 输入框提示
    :param value: 当前搜索词
    :param suggestions: 候选建议
    """

    CSS = """
    SearchInputScreen {
        align: center middle;
    }

    #search-dialog {
        width: 88;
        max-width: 88;
        border: heavy #38d8ff;
        background: #06111b;
        padding: 1 2;
    }

    #search-title {
        text-style: bold;
        color: #e9fcff;
        margin-bottom: 1;
    }

    #search-input {
        margin-bottom: 1;
    }

    #search-suggestions {
        color: #8fc6d6;
    }
    """

    BINDINGS = [
        Binding('escape', 'cancel', TUI_COPY.build_confirm_binding_label('cancel'), show=False),
        Binding('enter', 'submit', TUI_COPY.build_confirm_binding_label('submit'), show=False),
    ]

    def __init__(self, title: str, placeholder: str, value: str, suggestions: list[str]) -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._value = value
        self._suggestions = suggestions

    def compose(self) -> ComposeResult:
        with Vertical(id='search-dialog'):
            yield Static(self._title, id='search-title', markup=False)
            yield Input(value=self._value, placeholder=self._placeholder, id='search-input')
            suggestion_text = '候选建议 · ' + ('  '.join(self._suggestions[:6]) if self._suggestions else '暂无建议')
            yield Static(suggestion_text, id='search-suggestions', markup=False)

    def on_mount(self) -> None:
        self.call_after_refresh(self.query_one('#search-input', Input).focus)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        input_widget = self.query_one('#search-input', Input)
        self.dismiss(str(input_widget.value or '').strip())

    @on(Input.Submitted, '#search-input')
    def on_input_submitted(self) -> None:
        self.action_submit()
