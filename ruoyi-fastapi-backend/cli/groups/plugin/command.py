import importlib
from functools import lru_cache
from typing import TYPE_CHECKING

import typer

from .commands.configuration import register_configuration_commands
from .commands.dependency import register_dependency_commands
from .commands.developer import register_developer_commands
from .commands.discovery import register_discovery_commands
from .commands.lifecycle import register_lifecycle_commands

if TYPE_CHECKING:
    from .controller import PluginCommandController

app = typer.Typer(
    help='插件管理相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)


@lru_cache(maxsize=1)
def _get_plugin_command_controller() -> 'PluginCommandController':
    """
    延迟获取插件命令控制器。

    :return: 插件命令控制器
    """
    controller_class = importlib.import_module('cli.groups.plugin.controller').PluginCommandController
    return controller_class()


register_discovery_commands(app, _get_plugin_command_controller)
register_configuration_commands(app, _get_plugin_command_controller)
register_dependency_commands(app, _get_plugin_command_controller)
register_lifecycle_commands(app, _get_plugin_command_controller)
register_developer_commands(app, _get_plugin_command_controller)
