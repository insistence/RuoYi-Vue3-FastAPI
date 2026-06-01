from dataclasses import dataclass


@dataclass(frozen=True)
class PluginCommandWorkflow:
    """
    插件命令工作流分组。
    """

    name: str
    commands: tuple[str, ...]


PLUGIN_COMMAND_WORKFLOWS: tuple[PluginCommandWorkflow, ...] = (
    PluginCommandWorkflow(
        name='discovery',
        commands=('list', 'info', 'check', 'health', 'diagnose', 'docs'),
    ),
    PluginCommandWorkflow(
        name='dependency',
        commands=('check-deps', 'install-deps', 'precheck', 'plan'),
    ),
    PluginCommandWorkflow(
        name='lifecycle',
        commands=('install', 'enable', 'disable', 'upgrade', 'uninstall', 'purge', 'batch'),
    ),
    PluginCommandWorkflow(
        name='configuration',
        commands=('config',),
    ),
    PluginCommandWorkflow(
        name='developer',
        commands=('create', 'test'),
    ),
)


def list_plugin_command_workflows() -> tuple[PluginCommandWorkflow, ...]:
    """
    获取插件命令工作流分组。

    :return: 插件命令工作流分组
    """
    return PLUGIN_COMMAND_WORKFLOWS
