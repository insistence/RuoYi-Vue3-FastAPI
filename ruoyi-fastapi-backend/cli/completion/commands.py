from dataclasses import dataclass, field
from pathlib import Path

import typer

from cli.completion.controller import CompletionCommandController
from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY, CompletionProviderGateway
from cli.context import OutputOption


@dataclass(frozen=True)
class CompletionCommandRegistration:
    """
    completion 子命令注册描述。

    :param name: 子命令名称
    :param help_text: 子命令帮助文本
    """

    name: str
    help_text: str


@dataclass
class CompletionSubcommandRegistrar:
    """
    completion 子命令注册器。

    该对象负责将 `show/install/doctor` 子命令挂载到 completion 应用，
    将 Typer 命令声明细节从构建器主体中拆出。

    :param completion_provider_gateway: completion 提供器对外网关
    """

    completion_provider_gateway: CompletionProviderGateway = field(default_factory=lambda: COMPLETION_PROVIDER_GATEWAY)

    @staticmethod
    def build_registrations() -> tuple[CompletionCommandRegistration, ...]:
        """
        返回 completion 子命令注册描述列表。

        :return: 子命令注册描述元组
        """
        return (
            CompletionCommandRegistration(name='show', help_text='输出指定 shell 的 completion 脚本'),
            CompletionCommandRegistration(name='install', help_text='安装指定 shell 的 completion 脚本'),
            CompletionCommandRegistration(name='doctor', help_text='检查当前 completion 配置状态'),
        )

    def register(self, app: typer.Typer, *, controller: CompletionCommandController) -> None:
        """
        向 completion 应用注册全部子命令。

        :param app: completion 子应用
        :param controller: completion 命令控制器
        :return: None
        """
        registrations = {registration.name: registration for registration in self.build_registrations()}

        @app.command(registrations['show'].name, help=registrations['show'].help_text)
        def show(
            shell: str = typer.Argument(
                ...,
                help='shell 名称，如 bash、zsh、fish',
                autocompletion=self.completion_provider_gateway.complete_shell_names,
            ),
        ) -> None:
            """
            输出指定 shell 的 completion 脚本。

            :param shell: shell 名称
            :return: None
            """
            controller.show(shell)

        @app.command(registrations['install'].name, help=registrations['install'].help_text)
        def install(
            shell: str | None = typer.Option(
                None,
                '--shell',
                help='shell 名称，默认自动识别当前 shell',
                autocompletion=self.completion_provider_gateway.complete_shell_names,
            ),
            output: OutputOption = 'text',
            target_file: Path | None = typer.Option(None, '--target-file', help='completion 脚本目标文件路径'),
            activate: bool = typer.Option(False, '--activate', help='将激活命令写入 shell rc 文件'),
            rc_file: Path | None = typer.Option(None, '--rc-file', help='自定义 shell rc 文件路径'),
            force: bool = typer.Option(False, '--force', help='覆盖已存在且内容不同的目标文件'),
        ) -> None:
            """
            安装指定 shell 的 completion 脚本。

            :param shell: shell 名称，默认自动识别当前 shell
            :param output: 输出格式
            :param target_file: completion 脚本目标文件路径
            :param activate: 是否写入 shell rc 文件激活命令
            :param rc_file: 自定义 shell rc 文件路径
            :param force: 是否强制覆盖已存在文件
            :return: None
            """
            controller.install(
                output,
                shell=shell,
                target_file=target_file,
                activate=activate,
                rc_file=rc_file,
                force=force,
            )

        @app.command(registrations['doctor'].name, help=registrations['doctor'].help_text)
        def doctor(
            output: OutputOption = 'text',
        ) -> None:
            """
            检查当前 completion 配置状态。

            :param output: 输出格式
            :return: None
            """
            controller.doctor(output)


@dataclass
class CompletionCommandBuilder:
    """
    completion 子应用构建器。

    该构建器负责装配 `completion` 子应用，并将控制器实例和子命令注册
    细节收口到类式对象协作中。

    :param completion_subcommand_registrar: completion 子命令注册器
    """

    completion_subcommand_registrar: CompletionSubcommandRegistrar = field(
        default_factory=CompletionSubcommandRegistrar
    )

    def build(self, root_cli: typer.Typer) -> typer.Typer:
        """
        构建 completion 命令组。

        :param root_cli: 根 Typer 应用
        :return: completion 子应用
        """
        app = typer.Typer(
            help='shell completion 相关命令',
            no_args_is_help=True,
            context_settings={'help_option_names': ['-h', '--help']},
        )
        completion_command_controller = CompletionCommandController(root_cli)
        self.completion_subcommand_registrar.register(app, controller=completion_command_controller)
        return app


COMPLETION_COMMAND_BUILDER = CompletionCommandBuilder()
