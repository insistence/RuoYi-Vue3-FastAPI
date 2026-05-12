import os
from dataclasses import dataclass, field

import typer
from click.shell_completion import shell_complete as click_shell_complete
from typer.completion import shell_complete as typer_shell_complete

from cli.completion.shells import ensure_custom_completion_classes_registered


@dataclass(frozen=True)
class CompletionInstructionSupport:
    """
    completion 指令解析支持对象。

    该对象负责管理 completion 环境变量名、受支持 shell 列表，以及
    Click / Typer 两种指令格式的判定逻辑。

    :param complete_env_var: completion 环境变量名
    :param supported_shells: 支持的 shell 名称列表
    """

    complete_env_var: str = '_RUOYI_COMPLETE'
    supported_shells: tuple[str, ...] = ('bash', 'zsh', 'fish', 'powershell')

    def is_click_style_instruction(self, instruction: str) -> bool:
        """
        判断 completion 指令是否为 Click 原生格式。

        Click 原生格式为 `<shell>_<instruction>`，例如 `bash_complete`。

        :param instruction: completion 指令文本
        :return: 是否为 Click 风格指令
        """
        return any(instruction.startswith(f'{shell}_') for shell in self.supported_shells)

    def is_typer_style_instruction(self, instruction: str) -> bool:
        """
        判断 completion 指令是否为 Typer 兼容格式。

        Typer 兼容格式为 `<instruction>_<shell>`，例如 `complete_bash`。

        :param instruction: completion 指令文本
        :return: 是否为 Typer 风格指令
        """
        return any(instruction.endswith(f'_{shell}') for shell in self.supported_shells)


@dataclass(frozen=True)
class CompletionInstructionReader:
    """
    completion 指令读取器。

    该对象负责从当前进程环境中读取并规范化 completion 指令。

    :param support: completion 指令解析支持对象
    """

    support: CompletionInstructionSupport

    def read_instruction(self) -> str:
        """
        读取当前进程中的 completion 指令文本。

        :return: 规范化后的 completion 指令文本
        """
        return os.environ.get(self.support.complete_env_var, '').strip()


@dataclass(frozen=True)
class CompletionDispatcher:
    """
    shell completion 请求分发器。

    该对象负责识别 Click 与 Typer 两种 completion 指令格式，
    并在命中时直接执行补全流程后退出当前进程。

    :param support: completion 指令解析支持对象
    :param instruction_reader: completion 指令读取器
    """

    support: CompletionInstructionSupport = field(default_factory=CompletionInstructionSupport)
    instruction_reader: CompletionInstructionReader = field(init=False)

    def __post_init__(self) -> None:
        """
        初始化 completion 指令读取器。

        :return: None
        """
        object.__setattr__(self, 'instruction_reader', CompletionInstructionReader(self.support))

    def dispatch(self, cli: typer.Typer) -> None:
        """
        处理 shell completion 请求并在命中时直接退出。

        这里同时兼容 Click 与 Typer 两种 completion 指令格式，避免
        生成脚本格式和运行时解析格式不一致时出现 `Shell complete not supported.`。

        :param cli: Typer 根应用
        :return: None
        """
        ensure_custom_completion_classes_registered()
        instruction = self.instruction_reader.read_instruction()
        if not instruction:
            return

        click_command = typer.main.get_command(cli)
        if self.support.is_click_style_instruction(instruction):
            raise SystemExit(
                click_shell_complete(click_command, {}, 'ruoyi', self.support.complete_env_var, instruction)
            )
        if self.support.is_typer_style_instruction(instruction):
            raise SystemExit(
                typer_shell_complete(click_command, {}, 'ruoyi', self.support.complete_env_var, instruction)
            )

        raise SystemExit(1)


DEFAULT_COMPLETION_INSTRUCTION_SUPPORT = CompletionInstructionSupport()
