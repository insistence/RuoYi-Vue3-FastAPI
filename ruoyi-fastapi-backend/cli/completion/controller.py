from pathlib import Path

import typer

from cli.completion.doctor import COMPLETION_DOCTOR, CompletionDoctorService
from cli.completion.installers import COMPLETION_INSTALLER, CompletionInstallerService
from cli.completion.presenter import CompletionCommandPresenter
from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)


class CompletionCommandController:
    """
    completion 命令控制器。

    该控制器负责组织 `completion` 命令组的上下文准备、payload 生成、
    文本渲染与脚本输出收口。

    :param root_cli: 根 Typer 应用
    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: completion 命令文本渲染器
    :param installer_service: completion 安装与脚本生成服务
    :param doctor_service: completion 诊断服务
    """

    def __init__(
        self,
        root_cli: typer.Typer,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: CompletionCommandPresenter | None = None,
        installer_service: CompletionInstallerService | None = None,
        doctor_service: CompletionDoctorService | None = None,
    ) -> None:
        """
        初始化 completion 命令控制器。

        :param root_cli: 根 Typer 应用
        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: completion 命令文本渲染器
        :param installer_service: completion 安装与脚本生成服务
        :param doctor_service: completion 诊断服务
        :return: None
        """
        self.root_cli = root_cli
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or CompletionCommandPresenter()
        self.installer_service = installer_service or COMPLETION_INSTALLER
        self.doctor_service = doctor_service or COMPLETION_DOCTOR

    def show(self, shell: str) -> None:
        """
        输出指定 shell 的 completion 脚本。

        :param shell: shell 名称
        :return: None
        """
        typer.echo(self.installer_service.render_completion_script(self.root_cli, shell), nl=False)

    def install(
        self,
        output: str,
        *,
        shell: str | None,
        target_file: Path | None,
        activate: bool,
        rc_file: Path | None,
        force: bool,
    ) -> None:
        """
        安装指定 shell 的 completion 脚本。

        :param output: 输出格式
        :param shell: shell 名称
        :param target_file: completion 脚本目标文件路径
        :param activate: 是否写入 shell rc 文件激活命令
        :param rc_file: 自定义 shell rc 文件路径
        :param force: 是否强制覆盖已存在文件
        :return: None
        """
        ctx = self.context_factory.build_readonly('dev', output)
        payload = self.installer_service.install_completion_script(
            self.root_cli,
            shell,
            target_file=target_file,
            activate=activate,
            rc_file=rc_file,
            force=force,
        )
        self.execution_service.complete_payload_result(
            ctx,
            payload,
            text_builder=self.presenter.build_completion_install_text,
        )

    def doctor(self, output: str) -> None:
        """
        检查当前 completion 配置状态。

        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly('dev', output)
        payload = self.doctor_service.build_completion_doctor_payload()
        self.execution_service.complete_payload_result(
            ctx,
            payload,
            text_builder=self.presenter.build_completion_doctor_text,
        )
