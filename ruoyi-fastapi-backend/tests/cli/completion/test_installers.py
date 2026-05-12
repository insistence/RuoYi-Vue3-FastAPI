from pathlib import Path

import typer
from pytest import MonkeyPatch

from cli.completion.installers import (
    CompletionInstallerService,
    CompletionInstallerShellSupport,
    CompletionShellRuntimePolicy,
    CompletionShellRuntimePolicyRegistry,
)


def test_build_source_command_uses_shell_runtime_policy() -> None:
    """
    校验安装服务会按 shell 运行时策略构建 source 命令。

    :return: None
    """
    installer = CompletionInstallerService()
    target_file = Path('/tmp/ruoyi-completion')

    assert installer.build_source_command(target_file, 'bash') == 'source /tmp/ruoyi-completion'
    assert installer.build_source_command(target_file, 'zsh') == 'source /tmp/ruoyi-completion'
    assert (
        installer.build_source_command(target_file, 'fish')
        == 'status --is-interactive; and source /tmp/ruoyi-completion'
    )
    assert installer.build_source_command(target_file, 'powershell') == '. "/tmp/ruoyi-completion"'


def test_make_bash_completion_script_compatible_wraps_legacy_instructions() -> None:
    """
    校验 Bash 兼容转换会包装旧版 shell 不支持的指令。

    :return: None
    """
    script_text = 'compopt -o dirnames\ncompopt -o default\ncomplete -o nosort -F _ruoyi_completion ruoyi'

    compatible_script = CompletionInstallerShellSupport.make_bash_completion_script_compatible(script_text)

    assert 'if command -v compopt >/dev/null 2>&1; then' in compatible_script
    assert 'complete -F _ruoyi_completion ruoyi' in compatible_script
    assert 'complete -o nosort -F _ruoyi_completion ruoyi 2>/dev/null' in compatible_script


def test_render_completion_script_uses_runtime_policy_transformer(monkeypatch: MonkeyPatch) -> None:
    """
    校验脚本渲染会通过 shell 运行时策略执行脚本后处理。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class DummyComplete:
        """
        模拟 Click completion 生成器。
        """

        def __init__(self, *args, **kwargs) -> None:
            """
            初始化模拟生成器。

            :param args: 位置参数
            :param kwargs: 关键字参数
            :return: None
            """

        @staticmethod
        def source() -> str:
            """
            返回原始脚本文本。

            :return: 原始脚本文本
            """
            return 'raw-script'

    runtime_policy_registry = CompletionShellRuntimePolicyRegistry(
        policies={
            'bash': CompletionShellRuntimePolicy(
                name='bash',
                click_completion_class=DummyComplete,
                script_transformer=lambda script_text: f'transformed::{script_text}',
                source_command_builder=lambda target_file: f'source {target_file}',
            )
        }
    )
    installer = CompletionInstallerService(shell_runtime_policy_registry=runtime_policy_registry)
    monkeypatch.setattr(installer, 'build_completion_click_command', lambda root_cli: object())

    rendered_script = installer.render_completion_script(typer.Typer(), 'bash')

    assert rendered_script == 'transformed::raw-script'


def test_render_powershell_completion_script_contains_native_completer() -> None:
    """
    校验 PowerShell completion 脚本会注册原生命令补全器。

    :return: None
    """
    installer = CompletionInstallerService()
    root_cli = typer.Typer()

    @root_cli.command()
    def demo() -> None:
        return None

    rendered_script = installer.render_completion_script(root_cli, 'powershell')

    assert 'Register-ArgumentCompleter -Native -CommandName ruoyi' in rendered_script
    assert '$env:_RUOYI_COMPLETE = "powershell_complete"' in rendered_script
