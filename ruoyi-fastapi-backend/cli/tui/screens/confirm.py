from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from cli.tui.copy import TUI_COPY


class ActionConfirmScreen(ModalScreen[bool]):
    """
    通用动作确认弹窗。

    :param title: 弹窗标题
    :param lines: 预览文本行
    :param confirm_label: 确认按钮文本
    """

    CSS = """
    ActionConfirmScreen {
        align: center middle;
    }

    #action-confirm-dialog {
        width: 96;
        max-width: 96;
        border: heavy #38d8ff;
        background: #06111b;
        padding: 1 2;
    }

    #action-confirm-title {
        text-style: bold;
        color: #e9fcff;
        margin-bottom: 1;
    }

    #action-confirm-body {
        border: round #18425d;
        background: #081827;
        color: #d8f7ff;
        padding: 1 2;
        margin-bottom: 1;
    }

    #action-confirm-actions {
        height: auto;
        align-horizontal: right;
    }

    #action-confirm-hint {
        color: #8fc6d6;
        margin-bottom: 1;
    }

    #action-confirm-cancel {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding('escape', 'cancel', TUI_COPY.build_confirm_binding_label('cancel'), show=False),
        Binding('enter', 'submit', TUI_COPY.build_confirm_binding_label('submit'), show=False),
    ]

    def __init__(self, title: str, lines: list[str], confirm_label: str) -> None:
        super().__init__()
        self._dialog_title = title
        self._dialog_lines = lines
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        """
        构建确认弹窗界面。

        :return: Textual 组件结果
        """
        with Vertical(id='action-confirm-dialog'):
            yield Static(self._dialog_title, id='action-confirm-title', markup=False)
            yield Static('\n'.join(self._dialog_lines), id='action-confirm-body', markup=False)
            yield Static(TUI_COPY.build_action_confirm_hint(), id='action-confirm-hint', markup=False)
            with Horizontal(id='action-confirm-actions'):
                yield Button(TUI_COPY.build_action_confirm_cancel_label(), id='action-confirm-cancel')
                yield Button(self._confirm_label, id='action-confirm-submit', variant='primary')

    def on_mount(self) -> None:
        """
        弹窗挂载后默认聚焦确认按钮。

        :return: None
        """
        self.call_after_refresh(self.query_one('#action-confirm-submit', Button).focus)

    def action_cancel(self) -> None:
        """
        取消并关闭弹窗。

        :return: None
        """
        self.dismiss(False)

    def action_submit(self) -> None:
        """
        通过键盘确认执行当前动作。

        :return: None
        """
        submit_button = self.query_one('#action-confirm-submit', Button)
        submit_button.press()

    @on(Button.Pressed, '#action-confirm-cancel')
    def on_cancel_pressed(self) -> None:
        """
        响应取消按钮。

        :return: None
        """
        self.dismiss(False)

    @on(Button.Pressed, '#action-confirm-submit')
    def on_submit_pressed(self) -> None:
        """
        响应确认按钮。

        :return: None
        """
        self.dismiss(True)
