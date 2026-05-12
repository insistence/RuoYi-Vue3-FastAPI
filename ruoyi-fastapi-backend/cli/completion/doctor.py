from pathlib import Path
from typing import Any

from cli.completion.installers import (
    CLICK_COMPLETE_ENV_VAR,
    COMPLETION_INSTALLER,
    CompletionInstallerService,
)
from cli.metadata import (
    COMPLETION_SHELL_SPEC_REGISTRY,
    ENVIRONMENT_OPTION_SERVICE,
    CompletionShellSpecRegistry,
    EnvironmentOptionService,
)


class CompletionDoctorService:
    """
    completion 诊断服务。

    该服务负责汇总活跃 shell、目标脚本路径、rc 文件状态、推荐安装命令
    与环境候选列表，生成 `completion doctor` 所需的结构化结果。

    :param installer_service: completion 安装服务
    :param shell_spec_registry: shell 元数据注册表
    :param environment_option_service: 环境选项服务
    """

    def __init__(
        self,
        *,
        installer_service: CompletionInstallerService | None = None,
        shell_spec_registry: CompletionShellSpecRegistry | None = None,
        environment_option_service: EnvironmentOptionService | None = None,
    ) -> None:
        """
        初始化 completion 诊断服务。

        :param installer_service: completion 安装服务
        :param shell_spec_registry: shell 元数据注册表
        :param environment_option_service: 环境选项服务
        :return: None
        """
        self.installer_service = installer_service or COMPLETION_INSTALLER
        self.shell_spec_registry = shell_spec_registry or COMPLETION_SHELL_SPEC_REGISTRY
        self.environment_option_service = environment_option_service or ENVIRONMENT_OPTION_SERVICE

    def build_completion_doctor_payload(self) -> dict[str, Any]:
        """
        构建 completion 诊断结果。

        :return: 诊断结果字典
        """
        active_shell = self.installer_service.detect_active_shell()
        shells: dict[str, dict[str, Any]] = {}
        for shell_name, shell_spec in self.shell_spec_registry.specs.items():
            target_file = self.installer_service.resolve_completion_target(shell_name)
            rc_file = self.installer_service.resolve_completion_rc_file(shell_name)
            source_command = None
            if shell_spec.supported and shell_spec.generator in {'click', 'custom'}:
                source_command = self.installer_service.build_source_command(target_file, shell_name)
            recommended_install_command = f'ruoyi completion install --shell={shell_name}'
            if shell_spec.supported and not shell_spec.auto_discovery:
                recommended_install_command = f'{recommended_install_command} --activate'
            shells[shell_name] = {
                'supported': shell_spec.supported,
                'detected': shell_name == active_shell,
                'description': shell_spec.description,
                'targetFile': str(target_file),
                'targetFileExists': target_file.exists(),
                'rcFile': str(rc_file) if rc_file is not None else None,
                'rcFileExists': rc_file.exists() if rc_file is not None else None,
                'autoDiscovery': shell_spec.auto_discovery,
                'sourceCommand': source_command,
                'recommendedInstallCommand': recommended_install_command,
            }

        recommended_shell = active_shell if self.shell_spec_registry.get_spec(active_shell) is not None else None
        recommended_install_command = None
        if recommended_shell is not None:
            recommended_install_command = shells[recommended_shell]['recommendedInstallCommand']

        return {
            'ok': True,
            'message': 'completion 诊断信息已生成',
            'activeShell': active_shell or None,
            'projectDir': str(Path.cwd().resolve()),
            'envChoices': self.environment_option_service.discover_env_names(),
            'completeEnvVar': CLICK_COMPLETE_ENV_VAR,
            'recommendedInstallCommand': recommended_install_command,
            'shells': shells,
        }


COMPLETION_DOCTOR = CompletionDoctorService()
