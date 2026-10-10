from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from cli.exit_codes import ARGUMENT_ERROR, SUCCESS
from cli.groups.plugin.commands.developer import register_developer_commands
from cli.groups.plugin.options import PluginCreateCommandOptions

pytestmark = pytest.mark.contract


@pytest.mark.parametrize('template', ['python-asgi', 'python-bundle', 'rust-asgi', 'rust-bundle'])
def test_create_cli_forwards_v2_template_without_changing_default_options(template: str) -> None:
    """
    验证 v2 模板参数传递且不改变既有默认选项。
    """
    recorded: list[tuple[Any, ...]] = []

    class Controller:
        @staticmethod
        def create_plugin(*args: Any) -> None:
            recorded.append(args)

    app = typer.Typer()
    register_developer_commands(app, Controller)
    result = CliRunner().invoke(
        app, ['create', 'invoice_ops_27', '--template', template, '--dry-run', '--output', 'json']
    )
    assert result.exit_code == 0, result.output
    plugin_id, env, output, options = recorded[0]
    assert (plugin_id, env, output) == ('invoice_ops_27', 'dev', 'json')
    assert options == PluginCreateCommandOptions(template=template, dry_run=True)


def test_create_cli_defaults_to_existing_v1_full_stack_template() -> None:
    """
    验证未指定模板时继续生成原有 v1 完整模板。
    """
    recorded: list[PluginCreateCommandOptions] = []

    class Controller:
        @staticmethod
        def create_plugin(plugin_id: str, env: str, output: str, options: PluginCreateCommandOptions) -> None:
            recorded.append(options)

    app = typer.Typer()
    register_developer_commands(app, Controller)
    result = CliRunner().invoke(app, ['create', 'legacy_demo'])
    assert result.exit_code == 0
    assert recorded == [PluginCreateCommandOptions()]


@pytest.mark.parametrize('framework', ['auto', 'vue2', 'vue3'])
def test_create_cli_accepts_fixed_frontend_framework_choices(framework: str) -> None:
    """校验创建命令接受固定框架选项并将原始字符串传递给控制器。"""
    recorded: list[PluginCreateCommandOptions] = []

    class Controller:
        @staticmethod
        def create_plugin(plugin_id: str, env: str, output: str, options: PluginCreateCommandOptions) -> None:
            recorded.append(options)

    app = typer.Typer()
    register_developer_commands(app, Controller)
    result = CliRunner().invoke(app, ['create', 'demo', '--frontend-framework', framework])
    assert result.exit_code == SUCCESS, result.output
    assert recorded[0].frontend_framework == framework


@pytest.mark.parametrize('framework', ['react', 'custom_ui-1', '../react', 'Vue3'])
def test_create_cli_rejects_framework_before_resolving_controller(framework: str) -> None:
    """校验非法框架选项在加载控制器或运行时之前被拒绝。"""

    def unavailable_controller() -> None:
        """禁止参数错误路径加载控制器。"""
        raise AssertionError('不应加载控制器')

    app = typer.Typer()
    register_developer_commands(app, unavailable_controller)
    result = CliRunner().invoke(app, ['create', 'demo', '--frontend-framework', framework])
    assert result.exit_code == ARGUMENT_ERROR
    assert 'Invalid value' in result.output
    assert framework in result.output
    assert 'auto' in result.output and 'vue2' in result.output and 'vue3' in result.output


def test_create_cli_help_displays_fixed_frontend_framework_choices() -> None:
    """校验创建命令帮助展示固定的三种框架选项。"""
    app = typer.Typer()
    register_developer_commands(app, lambda: None)
    result = CliRunner().invoke(app, ['create', '--help'], terminal_width=160)
    assert result.exit_code == SUCCESS
    assert 'auto|vue2|vue3' in result.output
