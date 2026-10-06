from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from cli.groups.plugin.commands.developer import register_developer_commands
from cli.groups.plugin.options import PluginCreateCommandOptions


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
