import importlib
import json
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def inspect_cold_import(module_name: str, observed_modules: tuple[str, ...]) -> dict[str, bool]:
    """在隔离解释器中检查目标模块的冷导入边界。"""
    script = (
        'import importlib, json, sys; '
        f'importlib.import_module({module_name!r}); '
        f'print(json.dumps({{name: name in sys.modules for name in {observed_modules!r}}}))'
    )
    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_cli_plugin_cold_import_boundaries() -> None:
    """校验插件 CLI 冷导入不会越过约定的模块边界。"""
    cases = [
        (
            'cli.main',
            (
                'cli.groups.plugin.command',
                'cli.groups.plugin.controller',
                'cli.runtime.plugin.service',
                'plugins.core.runtime.service',
            ),
            (False, False, False, False),
        ),
        (
            'cli.runtime.plugin',
            (
                'cli.runtime.plugin.service',
                'cli.runtime.plugin.gateway',
                'plugins.core.environment',
                'plugins.core.runtime.service',
            ),
            (True, True, False, False),
        ),
        (
            'cli.groups.plugin.command',
            (
                'cli.groups.plugin.controller',
                'cli.runtime.plugin.service',
                'plugins.core.runtime.service',
            ),
            (False, False, False),
        ),
    ]

    for module_name, observed_modules, expected_values in cases:
        imported = inspect_cold_import(module_name, observed_modules)
        assert tuple(imported.values()) == expected_values


def test_plugin_commands_have_stable_workflow_ownership() -> None:
    """校验插件命令的工作流归属保持稳定。"""
    command_module = importlib.import_module('cli.groups.plugin.command')
    expected_modules = {
        **dict.fromkeys(('list', 'info', 'check', 'health', 'diagnose', 'docs'), 'discovery'),
        'config': 'configuration',
        **dict.fromkeys(
            ('check-deps', 'precheck', 'plan', 'install-deps', 'lock-deps', 'allowlist-example'),
            'dependency',
        ),
        **dict.fromkeys(
            (
                'batch',
                'install',
                'upgrade',
                'enable',
                'disable',
                'uninstall',
                'purge',
                'migration-list',
                'mark-success',
                'mark-failed',
            ),
            'lifecycle',
        ),
        **dict.fromkeys(('test', 'create'), 'developer'),
    }

    actual_modules = {
        command.name: command.callback.__module__.removeprefix('cli.groups.plugin.commands.')
        for command in command_module.app.registered_commands
    }

    assert actual_modules == expected_modules
    app_builder = importlib.import_module('cli.core.app_builder')
    assert app_builder.DEFAULT_COMMAND_GROUP_REGISTRY.command_modules['plugin'] == 'cli.groups.plugin'


def test_plugin_controller_and_runtime_are_created_lazily() -> None:
    """校验插件控制器和运行时仅在实际使用时创建。"""
    script = """
import importlib
import json
import sys

command_module = importlib.import_module('cli.groups.plugin.command')
initial = {
    'cache': command_module._get_plugin_command_controller.cache_info().currsize,
    'controller': 'cli.groups.plugin.controller' in sys.modules,
}
controller = command_module._get_plugin_command_controller()
after_controller = {
    'cache': command_module._get_plugin_command_controller.cache_info().currsize,
    'controller': 'cli.groups.plugin.controller' in sys.modules,
    'runtime': 'cli.runtime.plugin.service' in sys.modules,
}
_ = controller.plugin_runtime
after_runtime = {
    'runtime': 'cli.runtime.plugin.service' in sys.modules,
    'core': 'plugins.core.runtime.service' in sys.modules,
}
print(json.dumps({'initial': initial, 'afterController': after_controller, 'afterRuntime': after_runtime}))
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    observed = json.loads(completed.stdout)

    assert observed == {
        'initial': {'cache': 0, 'controller': False},
        'afterController': {'cache': 1, 'controller': True, 'runtime': False},
        'afterRuntime': {'runtime': True, 'core': False},
    }
