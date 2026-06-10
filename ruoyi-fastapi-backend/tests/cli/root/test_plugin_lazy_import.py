import importlib
import sys


def unload_plugin_modules() -> None:
    """
    卸载当前解释器中已导入的插件命令与 core 模块。

    :return: None
    """
    for module_name in list(sys.modules):
        if module_name == 'plugins' or module_name.startswith('plugins.'):
            sys.modules.pop(module_name)
        if module_name.startswith(('cli.groups.plugin', 'cli.runtime.plugin')):
            sys.modules.pop(module_name)


def test_cli_main_import_does_not_load_plugin_command_or_runtime() -> None:
    """
    校验导入 CLI 根入口时不加载 plugin 命令与运行时。

    :return: None
    """
    unload_plugin_modules()
    sys.modules.pop('cli.main', None)

    importlib.import_module('cli.main')

    assert 'cli.groups.plugin.command' not in sys.modules
    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'cli.runtime.plugin.service' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules


def test_cli_application_builder_registers_plugin_by_module_path() -> None:
    """
    校验 CLI 根应用构建器按模块路径延迟加载 plugin 命令组。

    :return: None
    """
    unload_plugin_modules()

    app_builder = importlib.import_module('cli.core.app_builder')
    registry = app_builder.DEFAULT_COMMAND_GROUP_REGISTRY

    assert registry.command_modules['plugin'] == 'cli.groups.plugin'


def test_plugin_runtime_import_does_not_load_plugin_core() -> None:
    """
    校验导入 plugin CLI runtime 包时不加载插件核心模块。

    :return: None
    """
    unload_plugin_modules()

    importlib.import_module('cli.runtime.plugin')

    assert 'cli.runtime.plugin.service' in sys.modules
    assert 'cli.runtime.plugin.gateway' in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules
    assert 'plugins.core.management.service.gateway' not in sys.modules
    assert 'plugins.core.runtime.support' not in sys.modules


def test_plugin_command_import_does_not_load_plugin_core() -> None:
    """
    校验导入 plugin 命令模块时不加载 controller、插件核心模块和插件 runtime service。

    :return: None
    """
    unload_plugin_modules()

    importlib.import_module('cli.groups.plugin.command')

    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'cli.runtime.plugin.service' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules
    assert 'plugins.core.management.service.gateway' not in sys.modules
    assert 'plugins.core.runtime.support' not in sys.modules


def test_plugin_command_registration_modules_do_not_load_plugin_core() -> None:
    """
    校验 plugin 命令注册模块导入时不加载 controller、插件核心模块和插件 runtime service。

    :return: None
    """
    unload_plugin_modules()

    importlib.import_module('cli.groups.plugin.commands.configuration')
    importlib.import_module('cli.groups.plugin.commands.dependency')
    importlib.import_module('cli.groups.plugin.commands.developer')
    importlib.import_module('cli.groups.plugin.commands.discovery')
    importlib.import_module('cli.groups.plugin.commands.lifecycle')

    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'cli.runtime.plugin.service' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules
    assert 'plugins.core.management.service.gateway' not in sys.modules
    assert 'plugins.core.runtime.support' not in sys.modules


def test_plugin_registered_commands_match_workflow_groups() -> None:
    """
    校验 plugin 实际注册命令与工作流分组保持一致。

    :return: None
    """
    unload_plugin_modules()

    command_module = importlib.import_module('cli.groups.plugin.command')
    workflow_commands = {
        'list',
        'info',
        'check',
        'health',
        'diagnose',
        'docs',
        'config',
        'check-deps',
        'install-deps',
        'precheck',
        'plan',
        'batch',
        'install',
        'upgrade',
        'enable',
        'disable',
        'uninstall',
        'purge',
        'test',
        'create',
    }

    assert {command.name for command in command_module.app.registered_commands} == workflow_commands


def test_plugin_discovery_commands_are_registered_from_workflow_module() -> None:
    """
    校验 plugin 发现诊断命令由独立工作流模块注册。

    :return: None
    """
    unload_plugin_modules()

    command_module = importlib.import_module('cli.groups.plugin.command')
    discovery_commands = {'list', 'info', 'check', 'health', 'diagnose', 'docs'}
    callbacks = {
        command.name: command.callback
        for command in command_module.app.registered_commands
        if command.name in discovery_commands
    }

    assert set(callbacks) == discovery_commands
    assert all(callback.__module__ == 'cli.groups.plugin.commands.discovery' for callback in callbacks.values())
    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules


def test_plugin_configuration_command_is_registered_from_workflow_module() -> None:
    """
    校验 plugin 配置命令由独立工作流模块注册。

    :return: None
    """
    unload_plugin_modules()

    command_module = importlib.import_module('cli.groups.plugin.command')
    config_command = next(command for command in command_module.app.registered_commands if command.name == 'config')

    assert config_command.callback.__module__ == 'cli.groups.plugin.commands.configuration'
    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules


def test_plugin_dependency_commands_are_registered_from_workflow_module() -> None:
    """
    校验 plugin 依赖与预检命令由独立工作流模块注册。

    :return: None
    """
    unload_plugin_modules()

    command_module = importlib.import_module('cli.groups.plugin.command')
    dependency_commands = {'check-deps', 'install-deps', 'precheck', 'plan'}
    callbacks = {
        command.name: command.callback
        for command in command_module.app.registered_commands
        if command.name in dependency_commands
    }

    assert set(callbacks) == dependency_commands
    assert all(callback.__module__ == 'cli.groups.plugin.commands.dependency' for callback in callbacks.values())
    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules


def test_plugin_lifecycle_commands_are_registered_from_workflow_module() -> None:
    """
    校验 plugin 生命周期命令由独立工作流模块注册。

    :return: None
    """
    unload_plugin_modules()

    command_module = importlib.import_module('cli.groups.plugin.command')
    lifecycle_commands = {'batch', 'install', 'upgrade', 'enable', 'disable', 'uninstall', 'purge'}
    callbacks = {
        command.name: command.callback
        for command in command_module.app.registered_commands
        if command.name in lifecycle_commands
    }

    assert set(callbacks) == lifecycle_commands
    assert all(callback.__module__ == 'cli.groups.plugin.commands.lifecycle' for callback in callbacks.values())
    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules


def test_plugin_developer_commands_are_registered_from_workflow_module() -> None:
    """
    校验 plugin 开发者命令由独立工作流模块注册。

    :return: None
    """
    unload_plugin_modules()

    command_module = importlib.import_module('cli.groups.plugin.command')
    developer_commands = {'test', 'create'}
    callbacks = {
        command.name: command.callback
        for command in command_module.app.registered_commands
        if command.name in developer_commands
    }

    assert set(callbacks) == developer_commands
    assert all(callback.__module__ == 'cli.groups.plugin.commands.developer' for callback in callbacks.values())
    assert 'cli.groups.plugin.controller' not in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules


def test_plugin_command_controller_is_created_lazily() -> None:
    """
    校验 plugin 命令入口导入时不立即创建命令控制器。

    :return: None
    """
    unload_plugin_modules()

    command_module = importlib.import_module('cli.groups.plugin.command')

    assert command_module._get_plugin_command_controller.cache_info().currsize == 0
    assert 'cli.groups.plugin.controller' not in sys.modules

    controller = command_module._get_plugin_command_controller()

    assert command_module._get_plugin_command_controller.cache_info().currsize == 1
    assert controller is command_module._get_plugin_command_controller()
    assert 'cli.groups.plugin.controller' in sys.modules
    assert 'cli.runtime.plugin.service' not in sys.modules


def test_plugin_controller_lazily_loads_plugin_runtime() -> None:
    """
    校验 plugin controller 仅在执行命令访问 runtime 时加载插件 CLI runtime。

    :return: None
    """
    unload_plugin_modules()

    controller_module = importlib.import_module('cli.groups.plugin.controller')
    controller = controller_module.PluginCommandController()

    assert 'cli.runtime.plugin.service' not in sys.modules

    _ = controller.plugin_runtime

    assert 'cli.runtime.plugin.service' in sys.modules
    assert 'plugins.core.runtime.service' not in sys.modules
