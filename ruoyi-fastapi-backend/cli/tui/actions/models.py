from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from cli.tui.adapters.models import TUI_ADAPTER_MODEL_RENDERER, BrowserRecordSnapshot

ActionSlot = Literal['primary', 'secondary', 'global', 'utility']
ActionExecutionMode = Literal['nested_json', 'external']
ActionCommandBuilder = Callable[[BrowserRecordSnapshot | None, str], tuple[str, ...] | None]
ActionSummaryBuilder = Callable[[BrowserRecordSnapshot | None, str], list[str]]
ActionTextBuilder = Callable[[BrowserRecordSnapshot | None, str], str]


@dataclass(frozen=True)
class TuiActionSpec:
    """
    TUI 低风险动作定义。

    :param action_id: 动作唯一标识
    :param label: 动作显示名称
    :param command_args: 对应 CLI 命令参数
    :param preview_title: 预览弹窗标题
    :param preview_lines: 预览摘要文本
    :param append_yes: 执行 nested JSON 动作时是否自动追加 `--yes`
    :param refresh_view: 执行完成后是否刷新当前页面
    """

    action_id: str
    label: str
    command_args: tuple[str, ...]
    preview_title: str
    preview_lines: list[str]
    execution_mode: ActionExecutionMode = 'nested_json'
    append_yes: bool = True
    refresh_view: bool = True


@dataclass(frozen=True)
class TuiActionResult:
    """
    TUI 动作执行结果。

    :param spec: 动作定义
    :param payload: CLI JSON 负载
    """

    spec: TuiActionSpec
    payload: dict[str, object] | None = None
    external_exit_code: int | None = None
    external_message: str | None = None

    @property
    def ok(self) -> bool:
        """
        判断动作是否执行成功。

        :return: 是否成功
        """
        if self.external_exit_code is not None:
            return self.external_exit_code == 0
        return bool(isinstance(self.payload, dict) and self.payload.get('ok', False))

    @property
    def message(self) -> str:
        """
        获取动作结果摘要。

        :return: 结果摘要
        """
        if self.external_message is not None:
            return self.external_message
        return TUI_ADAPTER_MODEL_RENDERER.extract_payload_message(self.payload)
