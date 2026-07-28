from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI

from plugins.core.discovery.scanner import PluginScanner
from plugins.core.runtime.hooks import PluginHookRunner


def write_plugin_with_hook(plugin_root: Path, hook_content: str, hook_path: str = 'hooks:on_startup') -> None:
    """写入带生命周期钩子的测试插件。"""
    plugin_root.mkdir(parents=True)
    (plugin_root / 'hooks.py').write_text(hook_content, encoding='utf-8')
    (plugin_root / 'plugin.yaml').write_text(
        f"""
id: demo_hook
name: Demo Hook
version: 1.0.0
backend:
  module: plugins.demo_hook
  hooks:
    onStartup: {hook_path}
""",
        encoding='utf-8',
    )


@pytest.mark.asyncio
async def test_plugin_hook_runner_executes_async_hook_with_context(tmp_path: Path) -> None:
    """校验生命周期钩子运行器可以执行异步钩子并传入上下文。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(
        plugin_root,
        'async def on_startup(context):\n    context.app.append(context.plugin_id)\n',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    app = []

    result = await PluginHookRunner(discovered_plugin).run('on_startup', app=app)

    assert app == ['demo_hook']
    assert result is not None
    assert result.hook_name == 'on_startup'
    assert result.module_name == 'plugins.demo_hook.hooks'


@pytest.mark.asyncio
async def test_plugin_hook_context_exposes_startup_write_gate(tmp_path: Path) -> None:
    """校验启动期钩子上下文会暴露当前 worker 是否允许执行全局写入。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(
        plugin_root,
        'async def on_startup(context):\n    context.app.append(context.startup_write_enabled)\n',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    app = []

    await PluginHookRunner(discovered_plugin).run('on_startup', app=app, startup_write_enabled=False)

    assert app == [False]


@pytest.mark.asyncio
async def test_plugin_hook_context_and_logs_include_startup_origin_fields(tmp_path: Path) -> None:
    """校验Hook上下文及日志来源标签包含代际、角色和插件信息。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(
        plugin_root,
        (
            'async def on_startup(context):\n'
            '    context.app.state.captured = (\n'
            '        context.startup_generation,\n'
            '        context.plugin_startup_role_at_creation,\n'
            '    )\n'
        ),
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    app = FastAPI()
    app.state.plugin_startup_generation = 'release-1'

    with patch('plugins.core.runtime.hooks.logger') as mocked_logger:
        await PluginHookRunner(discovered_plugin).run(
            'on_startup',
            app=app,
            startup_write_enabled=False,
        )

    assert app.state.captured == ('release-1', 'reader')
    mocked_logger.contextualize.assert_called_once_with(
        plugin_id='demo_hook',
        plugin_hook='on_startup',
        startup_generation='release-1',
        plugin_startup_role_at_creation='reader',
        startup_write_enabled=False,
        origin_hook='on_startup',
        created_during_startup=True,
    )
    mocked_logger.debug.assert_any_call('🔄 开始执行插件生命周期钩子')
    mocked_logger.debug.assert_any_call('✅ 插件生命周期钩子执行完成')


@pytest.mark.asyncio
async def test_plugin_hook_runner_executes_full_module_path_hook(tmp_path: Path) -> None:
    """校验生命周期钩子运行器支持完整插件模块路径。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(
        plugin_root,
        'async def on_startup():\n    return None\n',
        hook_path='plugins.demo_hook.hooks:on_startup',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHookRunner(discovered_plugin).run('on_startup')

    assert result is not None
    assert result.module_name == 'plugins.demo_hook.hooks'


@pytest.mark.asyncio
async def test_plugin_hook_runner_skips_undeclared_hook(tmp_path: Path) -> None:
    """校验未声明的生命周期钩子会被跳过。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(plugin_root, 'def on_startup():\n    return None\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    result = await PluginHookRunner(discovered_plugin).run('on_shutdown')

    assert result is None


@pytest.mark.asyncio
async def test_plugin_hook_runner_rejects_foreign_plugin_module(tmp_path: Path) -> None:
    """校验生命周期钩子不能指向其他插件模块。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(
        plugin_root,
        'def on_startup():\n    return None\n',
        hook_path='plugins.other.hooks:on_startup',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    with pytest.raises(RuntimeError, match='当前插件模块'):
        await PluginHookRunner(discovered_plugin).run('on_startup')


@pytest.mark.asyncio
async def test_plugin_hook_runner_times_out_async_hook(tmp_path: Path) -> None:
    """校验生命周期钩子超时时会失败并返回清晰错误。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(
        plugin_root,
        'import asyncio\nasync def on_startup(context):\n    await asyncio.sleep(1)\n',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    with pytest.raises(TimeoutError, match='生命周期钩子执行超时'):
        await PluginHookRunner(discovered_plugin, timeout_seconds=0.01).run('on_startup')


@pytest.mark.asyncio
async def test_plugin_hook_runner_rejects_sync_hook_without_executing_it(tmp_path: Path) -> None:
    """校验同步生命周期钩子会在执行前被拒绝，避免超时后继续产生副作用。"""
    plugin_root = tmp_path / 'plugins' / 'demo_hook'
    write_plugin_with_hook(
        plugin_root,
        'def on_startup(context):\n    context.app.append("executed")\n',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    app: list[str] = []

    with pytest.raises(TypeError, match='必须使用 async def'):
        await PluginHookRunner(discovered_plugin, timeout_seconds=0.01).run('on_startup', app=app)

    assert app == []
