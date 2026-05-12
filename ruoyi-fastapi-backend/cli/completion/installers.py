import io
import os
from contextlib import redirect_stderr
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import typer
import typer.main
from click.shell_completion import BashComplete, FishComplete, ZshComplete

from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY, CompletionProviderGateway
from cli.completion.shells import PowerShellComplete, ensure_custom_completion_classes_registered
from cli.exit_codes import ARGUMENT_ERROR, RUNTIME_ERROR
from cli.metadata import COMPLETION_SHELL_SPEC_REGISTRY, CompletionShellSpec, CompletionShellSpecRegistry

CLICK_COMPLETE_ENV_VAR = '_RUOYI_COMPLETE'


class CompletionInstallerShellSupport:
    """
    completion shell 差异支持对象。

    该对象负责封装不同 shell 在脚本兼容处理和 source 命令构建上的差异，
    供安装服务通过轻量 strategy 协作对象统一复用。
    """

    @staticmethod
    def keep_script_text(script_text: str) -> str:
        """
        保持脚本文本原样返回。

        :param script_text: 原始脚本文本
        :return: 原样脚本文本
        """
        return script_text

    @staticmethod
    def make_bash_completion_script_compatible(script_text: str) -> str:
        """
        对 Click 生成的 Bash completion 脚本做旧版本兼容处理。

        兼容目标主要包括 macOS 默认 Bash 3.2：

        - `complete -o nosort` 在旧 Bash 上会在 `source` 阶段直接报错
        - `compopt` 在旧 Bash 上可能不存在

        :param script_text: Click 原始 Bash completion 脚本文本
        :return: 兼容处理后的脚本文本
        """
        compatible_lines: list[str] = []
        for line in script_text.splitlines():
            stripped_line = line.strip()
            if stripped_line == 'compopt -o dirnames':
                indent = line[: len(line) - len(line.lstrip(' '))]
                compatible_lines.extend(
                    [
                        f'{indent}if command -v compopt >/dev/null 2>&1; then',
                        f'{indent}    compopt -o dirnames',
                        f'{indent}fi',
                    ]
                )
                continue
            if stripped_line == 'compopt -o default':
                indent = line[: len(line) - len(line.lstrip(' '))]
                compatible_lines.extend(
                    [
                        f'{indent}if command -v compopt >/dev/null 2>&1; then',
                        f'{indent}    compopt -o default',
                        f'{indent}fi',
                    ]
                )
                continue
            if stripped_line.startswith('complete -o nosort -F '):
                compatibility_line = stripped_line.replace('complete -o nosort -F ', '', 1)
                function_name, command_name = compatibility_line.split(' ', 1)
                compatible_lines.extend(
                    [
                        f'if complete -o nosort -F {function_name} {command_name} 2>/dev/null; then',
                        '    :',
                        'else',
                        f'    complete -F {function_name} {command_name}',
                        'fi',
                    ]
                )
                continue
            compatible_lines.append(line)
        return '\n'.join(compatible_lines) + '\n'

    @staticmethod
    def build_posix_source_command(target_file: Path) -> str:
        """
        构建 POSIX shell 使用的 source 命令。

        :param target_file: completion 脚本文件路径
        :return: source 命令
        """
        return f'source {target_file}'

    @staticmethod
    def build_fish_source_command(target_file: Path) -> str:
        """
        构建 Fish shell 使用的 source 命令。

        :param target_file: completion 脚本文件路径
        :return: source 命令
        """
        return f'status --is-interactive; and source {target_file}'

    @staticmethod
    def build_powershell_source_command(target_file: Path) -> str:
        """
        构建 PowerShell 使用的 source 命令。

        :param target_file: completion 脚本文件路径
        :return: source 命令
        """
        return f'. "{target_file}"'


@dataclass(frozen=True)
class CompletionShellRuntimePolicy:
    """
    completion shell 运行时策略定义。

    :param name: shell 名称
    :param click_completion_class: Click completion 生成器类型
    :param script_transformer: 脚本文本后处理函数
    :param source_command_builder: 激活命令构建函数
    """

    name: str
    click_completion_class: type[Any]
    script_transformer: Any
    source_command_builder: Any


@dataclass(frozen=True)
class CompletionShellRuntimePolicyRegistry:
    """
    completion shell 运行时策略注册表。

    :param policies: 按 shell 名称索引的运行时策略映射
    """

    policies: dict[str, CompletionShellRuntimePolicy]

    def get(self, shell_name: str) -> CompletionShellRuntimePolicy | None:
        """
        获取指定 shell 的运行时策略。

        :param shell_name: shell 名称
        :return: 运行时策略，不存在时返回 None
        """
        return self.policies.get(shell_name)


DEFAULT_COMPLETION_SHELL_RUNTIME_POLICIES = CompletionShellRuntimePolicyRegistry(
    policies={
        'bash': CompletionShellRuntimePolicy(
            name='bash',
            click_completion_class=BashComplete,
            script_transformer=CompletionInstallerShellSupport.make_bash_completion_script_compatible,
            source_command_builder=CompletionInstallerShellSupport.build_posix_source_command,
        ),
        'zsh': CompletionShellRuntimePolicy(
            name='zsh',
            click_completion_class=ZshComplete,
            script_transformer=CompletionInstallerShellSupport.keep_script_text,
            source_command_builder=CompletionInstallerShellSupport.build_posix_source_command,
        ),
        'fish': CompletionShellRuntimePolicy(
            name='fish',
            click_completion_class=FishComplete,
            script_transformer=CompletionInstallerShellSupport.keep_script_text,
            source_command_builder=CompletionInstallerShellSupport.build_fish_source_command,
        ),
        'powershell': CompletionShellRuntimePolicy(
            name='powershell',
            click_completion_class=PowerShellComplete,
            script_transformer=CompletionInstallerShellSupport.keep_script_text,
            source_command_builder=CompletionInstallerShellSupport.build_powershell_source_command,
        ),
    }
)


class CompletionInstallerService:
    """
    completion 安装与脚本生成服务。

    该服务负责 shell 元数据解析、脚本生成、目标路径解析、激活命令构建、
    rc 文件写入以及安装结果收口。

    :param completion_provider_gateway: completion 提供器对外网关
    :param shell_spec_registry: shell 元数据注册表
    :param shell_runtime_policy_registry: shell 运行时策略注册表
    """

    def __init__(
        self,
        *,
        completion_provider_gateway: CompletionProviderGateway | None = None,
        shell_spec_registry: CompletionShellSpecRegistry | None = None,
        shell_runtime_policy_registry: CompletionShellRuntimePolicyRegistry | None = None,
    ) -> None:
        """
        初始化 completion 安装服务。

        :param completion_provider_gateway: completion 提供器对外网关
        :param shell_spec_registry: shell 元数据注册表
        :param shell_runtime_policy_registry: shell 运行时策略注册表
        :return: None
        """
        self.completion_provider_gateway = completion_provider_gateway or COMPLETION_PROVIDER_GATEWAY
        self.shell_spec_registry = shell_spec_registry or COMPLETION_SHELL_SPEC_REGISTRY
        self.shell_runtime_policy_registry = shell_runtime_policy_registry or DEFAULT_COMPLETION_SHELL_RUNTIME_POLICIES
        ensure_custom_completion_classes_registered()

    def resolve_completion_shell_spec(self, shell: str) -> CompletionShellSpec:
        """
        获取指定 shell 的 completion 元数据。

        :param shell: shell 名称
        :return: shell 元数据
        :raises typer.BadParameter: shell 不存在时抛出异常
        """
        normalized_shell = shell.strip().lower()
        shell_spec = self.shell_spec_registry.get_spec(normalized_shell)
        if shell_spec is None:
            supported_shells = ', '.join(self.completion_provider_gateway.list_completion_shells())
            raise typer.BadParameter(f'不支持的 shell：{shell}，可选值为 {supported_shells}')
        return shell_spec

    def resolve_shell_runtime_policy(self, shell: str) -> CompletionShellRuntimePolicy:
        """
        获取指定 shell 的运行时策略。

        :param shell: shell 名称
        :return: shell 运行时策略
        :raises typer.BadParameter: 当前 shell 未实现运行时策略时抛出异常
        """
        shell_spec = self.resolve_completion_shell_spec(shell)
        runtime_policy = self.shell_runtime_policy_registry.get(shell_spec.name)
        if runtime_policy is None:
            raise typer.BadParameter(f'{shell_spec.name} completion 当前版本未实现')
        return runtime_policy

    @staticmethod
    def build_completion_click_command(root_cli: typer.Typer) -> click.Command:
        """
        将 Typer 根应用转换为 Click 命令对象，供 shell completion 生成使用。

        :param root_cli: Typer 根应用
        :return: Click 命令对象
        """
        return typer.main.get_command(root_cli)

    def render_completion_script(self, root_cli: typer.Typer, shell: str) -> str:
        """
        生成指定 shell 的 completion 脚本文本。

        :param root_cli: Typer 根应用
        :param shell: shell 名称
        :return: completion 脚本文本
        :raises typer.BadParameter: 当前 shell 未实现脚本生成时抛出异常
        """
        shell_spec = self.resolve_completion_shell_spec(shell)
        if not shell_spec.supported or shell_spec.generator not in {'click', 'custom'}:
            raise typer.BadParameter(f'{shell_spec.name} completion 当前版本未实现')

        runtime_policy = self.resolve_shell_runtime_policy(shell_spec.name)
        click_command = self.build_completion_click_command(root_cli)
        stderr_buffer = io.StringIO()
        with redirect_stderr(stderr_buffer):
            script_text = runtime_policy.click_completion_class(
                click_command,
                {},
                'ruoyi',
                CLICK_COMPLETE_ENV_VAR,
            ).source()
        return runtime_policy.script_transformer(script_text)

    def resolve_completion_target(self, shell: str, target_file: Path | None = None) -> Path:
        """
        解析 completion 脚本目标文件路径。

        :param shell: shell 名称
        :param target_file: 用户显式指定的目标文件
        :return: 目标文件绝对路径
        """
        if target_file is not None:
            return target_file.expanduser().resolve()

        shell_spec = self.resolve_completion_shell_spec(shell)
        return (Path.home() / shell_spec.default_target).expanduser().resolve()

    def resolve_completion_rc_file(self, shell: str, rc_file: Path | None = None) -> Path | None:
        """
        解析 completion 激活所使用的 rc 文件路径。

        :param shell: shell 名称
        :param rc_file: 用户显式指定的 rc 文件
        :return: rc 文件绝对路径，若当前 shell 无 rc 文件则返回 None
        """
        if rc_file is not None:
            return rc_file.expanduser().resolve()

        shell_spec = self.resolve_completion_shell_spec(shell)
        if shell_spec.default_rc_file is None:
            return None
        return (Path.home() / shell_spec.default_rc_file).expanduser().resolve()

    def build_source_command(self, target_file: Path, shell: str) -> str:
        """
        构建当前 shell 对应的激活命令。

        :param target_file: completion 脚本文件路径
        :param shell: shell 名称
        :return: 激活命令文本
        """
        runtime_policy = self.resolve_shell_runtime_policy(shell)
        return runtime_policy.source_command_builder(target_file)

    @staticmethod
    def detect_active_shell() -> str:
        """
        检测当前进程环境下的活跃 shell 名称。

        :return: shell 名称，未知时返回空字符串
        """
        shell_path = os.environ.get('SHELL', '').strip()
        if not shell_path:
            return ''
        return Path(shell_path).name.lower()

    def resolve_install_shell(self, shell: str | None) -> str:
        """
        解析安装命令实际使用的 shell。

        :param shell: 用户显式指定的 shell，允许为空
        :return: 实际使用的 shell 名称
        :raises typer.BadParameter: 无法推断或不支持时抛出异常
        """
        if shell and shell.strip():
            return self.resolve_completion_shell_spec(shell).name

        active_shell = self.detect_active_shell()
        if not active_shell:
            raise typer.BadParameter('未检测到当前 shell，请显式传入 --shell')

        shell_spec = self.shell_spec_registry.get_spec(active_shell)
        if shell_spec is None:
            supported_shells = ', '.join(self.completion_provider_gateway.list_completion_shells())
            raise typer.BadParameter(
                f'当前 shell `{active_shell}` 不在支持列表中，请显式传入 --shell，可选值为 {supported_shells}'
            )
        return shell_spec.name

    @staticmethod
    def append_activation_line(rc_file: Path, source_command: str) -> bool:
        """
        将激活命令追加到 rc 文件，若已存在则不重复写入。

        :param rc_file: rc 文件路径
        :param source_command: 激活命令文本
        :return: 本次是否发生写入
        """
        existing_text = ''
        if rc_file.exists():
            existing_text = rc_file.read_text(encoding='utf-8')
            if source_command in existing_text:
                return False

        rc_file.parent.mkdir(parents=True, exist_ok=True)
        with rc_file.open('a', encoding='utf-8') as file_object:
            if existing_text and not existing_text.endswith('\n'):
                file_object.write('\n')
            file_object.write(f'{source_command}\n')
        return True

    def install_completion_script(
        self,
        root_cli: typer.Typer,
        shell: str | None,
        *,
        target_file: Path | None = None,
        activate: bool = False,
        rc_file: Path | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        安装指定 shell 的 completion 脚本文件。

        :param root_cli: Typer 根应用
        :param shell: shell 名称
        :param target_file: completion 脚本目标文件
        :param activate: 是否写入 rc 文件激活命令
        :param rc_file: 自定义 rc 文件路径
        :param force: 目标文件已存在时是否强制覆盖
        :return: 安装结果字典
        """
        resolved_shell = self.resolve_install_shell(shell)
        shell_spec = self.resolve_completion_shell_spec(resolved_shell)
        if not shell_spec.supported:
            return {
                'ok': False,
                'message': f'{shell_spec.name} completion 当前版本未实现',
                'shell': shell_spec.name,
                'exit_code': ARGUMENT_ERROR,
            }

        resolved_target_file = self.resolve_completion_target(shell_spec.name, target_file)
        script_text = self.render_completion_script(root_cli, shell_spec.name)
        existing_text = resolved_target_file.read_text(encoding='utf-8') if resolved_target_file.exists() else None

        if existing_text is not None and existing_text != script_text and not force:
            return {
                'ok': False,
                'message': '目标文件已存在且内容不同，请传入 --force 覆盖',
                'shell': shell_spec.name,
                'targetFile': str(resolved_target_file),
                'exit_code': RUNTIME_ERROR,
            }

        resolved_target_file.parent.mkdir(parents=True, exist_ok=True)
        resolved_target_file.write_text(script_text, encoding='utf-8')

        source_command = self.build_source_command(resolved_target_file, shell_spec.name)
        activated = shell_spec.auto_discovery
        rc_file_path = self.resolve_completion_rc_file(shell_spec.name, rc_file)
        rc_file_updated = False
        activation_required = not shell_spec.auto_discovery
        detected_shell = self.detect_active_shell() or None

        if activate and rc_file_path is not None:
            rc_file_updated = self.append_activation_line(rc_file_path, source_command)
            activated = True

        next_step = '当前 shell 会自动发现 completion 脚本，无需额外 source 命令'
        if activation_required and not activate:
            next_step = f'请执行 `{source_command}`，或重新运行并传入 --activate'
        elif activation_required and activate:
            next_step = '请重启当前 shell，或手动执行 rc 文件中的 source 命令使其立即生效'

        return {
            'ok': True,
            'message': 'completion 脚本已安装',
            'shell': shell_spec.name,
            'detectedShell': detected_shell,
            'targetFile': str(resolved_target_file),
            'activated': activated,
            'activateRequested': activate,
            'rcFile': str(rc_file_path) if rc_file_path is not None else None,
            'rcFileUpdated': rc_file_updated,
            'sourceCommand': source_command,
            'autoDiscovery': shell_spec.auto_discovery,
            'activationRequired': activation_required,
            'nextStep': next_step,
            'completeEnvVar': CLICK_COMPLETE_ENV_VAR,
        }


COMPLETION_INSTALLER = CompletionInstallerService()
