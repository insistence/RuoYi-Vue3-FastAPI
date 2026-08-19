from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from plugins.core.discovery.registry import PluginRegistry, RegisteredPlugin
from plugins.core.runtime.bootstrap import PluginRuntimeBuilder
from plugins.core.runtime.startup import PluginRuntimeStartupManager, PluginStartupMigrationHistoryStore

BACKEND_ROOT = Path(__file__).resolve().parents[4]


def patch_startup_get_db(fake_get_db: object) -> object:
    """patch 启动管理器方法实际使用的 get_db 全局引用。"""
    return patch.dict(PluginRuntimeStartupManager.load_registry_from_database.__globals__, {'get_db': fake_get_db})


def patch_startup_global(name: str, value: object) -> object:
    """patch 启动管理器方法实际使用的模块全局引用。"""
    return patch.dict(PluginRuntimeStartupManager.load_registry_from_database.__globals__, {name: value})


def test_startup_manager_parses_default_enabled_builtin_plugin_ids() -> None:
    """校验默认启用内置插件配置按逗号分隔解析。"""
    plugin_ids = PluginRuntimeStartupManager.parse_default_enabled_builtin_plugin_ids('ai, demo, ,report')

    assert plugin_ids == {'ai', 'demo', 'report'}


def test_startup_manager_reads_default_enabled_builtin_plugins_from_app_config() -> None:
    """校验启动管理器默认从应用配置读取内置默认启用插件列表。"""
    with patch('plugins.core.runtime.startup.AppConfig.app_default_enabled_plugins', 'ai,demo'):
        startup_manager = PluginRuntimeStartupManager(MagicMock())

    assert startup_manager.default_enabled_builtin_plugin_ids == {'ai', 'demo'}


def test_startup_manager_skips_frontend_structure_validation_in_prod(tmp_path: Path) -> None:
    """校验生产启动首次安装不依赖前端源码目录。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    plugin_root.mkdir(parents=True)
    (plugin_root / 'plugin.yaml').write_text(
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.demo
frontend:
  menus:
    - name: Demo
      path: demo
      component: plugin/demo/index
        """,
        encoding='utf-8',
    )
    (plugin_root / 'controller').mkdir()
    builder = PluginRuntimeBuilder(backend_root)
    discovered_plugin = builder.discover_plugins()[0]
    startup_manager = PluginRuntimeStartupManager(builder)

    with patch('plugins.core.runtime.startup.AppConfig.app_env', 'prod'):
        startup_manager.validate_plugin_structure(discovered_plugin)


@pytest.mark.asyncio
async def test_prepare_enabled_plugins_loads_registry_and_imports_entities() -> None:
    """校验插件启动协调器准备启用插件实体。"""
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_default_enabled_builtin_plugin_install_states = AsyncMock(return_value={'builtin'})
    startup_manager.load_registry_from_database = AsyncMock()
    startup_manager.check_enabled_plugin_python_dependencies = AsyncMock(return_value={'enabled'})
    startup_manager.import_enabled_plugin_entities = AsyncMock(return_value=set())

    await startup_manager.prepare_enabled_plugins(app)

    startup_manager.sync_default_enabled_builtin_plugin_install_states.assert_awaited_once_with()
    startup_manager.load_registry_from_database.assert_awaited_once_with(app)
    startup_manager.check_enabled_plugin_python_dependencies.assert_awaited_once_with(
        app,
        startup_write_enabled=True,
    )
    startup_manager.import_enabled_plugin_entities.assert_awaited_once_with(
        app,
        startup_write_enabled=True,
    )
    assert app.state.plugin_dependency_failed_plugin_ids == {'builtin', 'enabled'}


@pytest.mark.asyncio
async def test_prepare_enabled_plugins_skips_builtin_state_sync_when_startup_write_disabled() -> None:
    """校验非启动写入 worker 不初始化内置默认启用插件状态。"""
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_default_enabled_builtin_plugin_install_states = AsyncMock(return_value=set())
    startup_manager.load_registry_from_database = AsyncMock()
    startup_manager.check_enabled_plugin_python_dependencies = AsyncMock(return_value=set())
    startup_manager.import_enabled_plugin_entities = AsyncMock(return_value=set())

    await startup_manager.prepare_enabled_plugins(app, startup_write_enabled=False)

    startup_manager.sync_default_enabled_builtin_plugin_install_states.assert_not_awaited()
    startup_manager.load_registry_from_database.assert_awaited_once_with(app)
    startup_manager.check_enabled_plugin_python_dependencies.assert_awaited_once_with(
        app,
        startup_write_enabled=False,
    )
    startup_manager.import_enabled_plugin_entities.assert_awaited_once_with(
        app,
        startup_write_enabled=False,
    )


@pytest.mark.asyncio
async def test_activate_enabled_plugins_installs_resources_and_runs_hooks() -> None:
    """校验插件启动协调器激活启用插件资源。"""
    app = MagicMock()
    calls = []
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_enabled_plugin_install_states = AsyncMock(side_effect=lambda *_args: calls.append('sync'))
    startup_manager.install_enabled_plugin_resources = AsyncMock(side_effect=lambda *_args: calls.append('resources'))
    startup_manager.register_enabled_plugin_routers = MagicMock(
        side_effect=lambda *_args, **_kwargs: calls.append('routers')
    )
    startup_manager.run_enabled_plugin_hooks = AsyncMock(side_effect=lambda *_args, **_kwargs: calls.append('hooks'))

    await startup_manager.activate_enabled_plugins(app)

    assert calls == ['sync', 'resources', 'hooks', 'routers']
    startup_manager.sync_enabled_plugin_install_states.assert_awaited_once_with(app)
    startup_manager.install_enabled_plugin_resources.assert_awaited_once_with(app)
    startup_manager.register_enabled_plugin_routers.assert_called_once_with(app, startup_write_enabled=True)
    startup_manager.run_enabled_plugin_hooks.assert_awaited_once_with(
        app,
        'on_startup',
        startup_write_enabled=True,
    )


@pytest.mark.asyncio
async def test_activate_enabled_plugins_skips_resource_install_when_startup_write_disabled() -> None:
    """校验非启动写入 worker 会跳过插件资源安装，但仍注册本 worker 路由和执行本地钩子。"""
    app = MagicMock()
    calls = []
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_enabled_plugin_install_states = AsyncMock()
    startup_manager.install_enabled_plugin_resources = AsyncMock()
    startup_manager.register_enabled_plugin_routers = MagicMock(
        side_effect=lambda *_args, **_kwargs: calls.append('routers')
    )
    startup_manager.run_enabled_plugin_hooks = AsyncMock(side_effect=lambda *_args, **_kwargs: calls.append('hooks'))

    await startup_manager.activate_enabled_plugins(app, startup_write_enabled=False)

    assert calls == ['hooks', 'routers']
    startup_manager.sync_enabled_plugin_install_states.assert_not_awaited()
    startup_manager.install_enabled_plugin_resources.assert_not_awaited()
    startup_manager.register_enabled_plugin_routers.assert_called_once_with(app, startup_write_enabled=False)
    startup_manager.run_enabled_plugin_hooks.assert_awaited_once_with(
        app,
        'on_startup',
        startup_write_enabled=False,
    )


@pytest.mark.asyncio
async def test_sync_enabled_plugin_install_states_marks_missing_database_plugin_installed() -> None:
    """校验启动写入 worker 会将默认启用但未落库的插件同步为已安装。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    discovered_plugin = MagicMock()
    discovered_plugin.manifest.id = 'ai'
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry(
        [RegisteredPlugin(discovered_plugin, None, enabled=True, status='discovered')]
    )
    fake_builder = MagicMock()
    fake_builder.plugins_root = BACKEND_ROOT / 'plugins'
    fake_builder.frontend_plugins_root = BACKEND_ROOT.parent / 'frontend' / 'plugins'
    fake_gateway = MagicMock()
    fake_gateway.upsert_discovered_plugin = AsyncMock()
    fake_gateway.install_plugin_resources = AsyncMock()
    fake_gateway.mark_plugin_installed = AsyncMock()
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(startup_manager, 'load_registry_from_database', new_callable=AsyncMock) as load_registry,
        patch.object(startup_manager, 'validate_plugin_structure') as validate_structure,
        patch.object(startup_manager, 'run_plugin_install_scripts', new_callable=AsyncMock) as run_install_scripts,
        patch.object(startup_manager, 'run_plugin_install_hook', new_callable=AsyncMock) as run_install_hook,
    ):
        await startup_manager.sync_enabled_plugin_install_states(app)

    fake_gateway.upsert_discovered_plugin.assert_awaited_once_with(
        fake_session,
        discovered_plugin,
        fake_builder.plugins_root,
        fake_builder.frontend_plugins_root,
    )
    validate_structure.assert_called_once_with(discovered_plugin)
    fake_gateway.install_plugin_resources.assert_awaited_once_with(
        fake_session,
        discovered_plugin,
        enabled=True,
    )
    run_install_scripts.assert_awaited_once_with(fake_session, discovered_plugin)
    run_install_hook.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_gateway.mark_plugin_installed.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_session.commit.assert_awaited_once()
    load_registry.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_sync_enabled_plugin_install_states_keeps_installed_plugin_unchanged() -> None:
    """校验已安装插件不会在启动期重复标记安装。"""
    discovered_plugin = MagicMock()
    database_plugin = MagicMock(installed_version='1.0.0', status='installed')
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry(
        [RegisteredPlugin(discovered_plugin, database_plugin, enabled=True, status='installed')]
    )
    fake_gateway = MagicMock()
    fake_gateway.upsert_discovered_plugin = AsyncMock()
    fake_gateway.mark_plugin_installed = AsyncMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock(), fake_gateway)

    with patch.object(startup_manager, 'load_registry_from_database', new_callable=AsyncMock) as load_registry:
        await startup_manager.sync_enabled_plugin_install_states(app)

    fake_gateway.upsert_discovered_plugin.assert_not_awaited()
    fake_gateway.mark_plugin_installed.assert_not_awaited()
    load_registry.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_default_enabled_builtin_plugin_install_states_installs_missing_builtin() -> None:
    """校验内置默认启用插件缺少数据库状态时会初始化为已安装。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    discovered_plugin = MagicMock()
    discovered_plugin.manifest.id = 'ai'
    fake_builder = MagicMock()
    fake_builder.plugins_root = BACKEND_ROOT / 'plugins'
    fake_builder.frontend_plugins_root = BACKEND_ROOT.parent / 'frontend' / 'plugins'
    fake_builder.discover_plugins.return_value = [discovered_plugin]
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[])
    fake_gateway.upsert_discovered_plugin = AsyncMock()
    fake_gateway.install_plugin_resources = AsyncMock()
    fake_gateway.mark_plugin_installed = AsyncMock()
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(startup_manager, 'validate_plugin_structure') as validate_structure,
        patch.object(startup_manager, 'run_plugin_install_scripts', new_callable=AsyncMock) as run_install_scripts,
        patch.object(startup_manager, 'run_plugin_install_hook', new_callable=AsyncMock) as run_install_hook,
    ):
        await startup_manager.sync_default_enabled_builtin_plugin_install_states()

    fake_gateway.list_plugins.assert_awaited_once_with(fake_session)
    fake_gateway.upsert_discovered_plugin.assert_awaited_once_with(
        fake_session,
        discovered_plugin,
        fake_builder.plugins_root,
        fake_builder.frontend_plugins_root,
    )
    validate_structure.assert_called_once_with(discovered_plugin)
    fake_gateway.install_plugin_resources.assert_awaited_once_with(
        fake_session,
        discovered_plugin,
        enabled=True,
    )
    run_install_scripts.assert_awaited_once_with(fake_session, discovered_plugin)
    run_install_hook.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_gateway.mark_plugin_installed.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_default_enabled_builtin_checks_dependencies_before_install_scripts() -> None:
    """校验默认启用内置插件会在安装脚本前检查依赖。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """提供测试用数据库会话生成器。"""
        yield fake_session

    discovered_plugin = MagicMock()
    discovered_plugin.manifest.id = 'ai'
    discovered_plugin.manifest.dependencies.python = ['missing-package>=1.0.0']
    fake_builder = MagicMock()
    fake_builder.plugins_root = BACKEND_ROOT / 'plugins'
    fake_builder.frontend_plugins_root = BACKEND_ROOT.parent / 'frontend' / 'plugins'
    fake_builder.discover_plugins.return_value = [discovered_plugin]
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[])
    fake_gateway.upsert_discovered_plugin = AsyncMock()
    fake_gateway.mark_plugin_error = AsyncMock()
    fake_gateway.mark_plugin_installed = AsyncMock()
    dependency_item = MagicMock(ok=False, message='Python 依赖未安装：missing-package')
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [dependency_item]
    startup_manager = PluginRuntimeStartupManager(
        fake_builder,
        fake_gateway,
        python_dependency_inspector=python_dependency_inspector,
        default_enabled_builtin_plugin_ids={'ai'},
    )

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(startup_manager, 'run_plugin_install_scripts', new_callable=AsyncMock) as run_install_scripts,
    ):
        await startup_manager.sync_default_enabled_builtin_plugin_install_states()

    python_dependency_inspector.check.assert_called_once_with(['missing-package>=1.0.0'])
    python_dependency_inspector.refresh.assert_called_once_with()
    fake_gateway.mark_plugin_error.assert_awaited_once_with(
        fake_session,
        'ai',
        (
            '插件启动依赖检查失败：Python 依赖未安装：missing-package；'
            '安装依赖请执行：ruoyi plugin install-deps ai --env=dev --yes'
        ),
    )
    run_install_scripts.assert_not_awaited()
    fake_gateway.mark_plugin_installed.assert_not_awaited()
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_default_enabled_builtin_plugin_install_states_respects_uninstalled_builtin() -> None:
    """校验用户卸载后的内置插件不会在重启时被自动重新安装。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    discovered_plugin = MagicMock()
    discovered_plugin.manifest.id = 'ai'
    database_plugin = MagicMock(plugin_id='ai', installed_version=None, status='discovered', enabled='1')
    fake_builder = MagicMock()
    fake_builder.discover_plugins.return_value = [discovered_plugin]
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[database_plugin])
    fake_gateway.upsert_discovered_plugin = AsyncMock()
    fake_gateway.mark_plugin_installed = AsyncMock()
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with patch_startup_get_db(fake_get_db):
        await startup_manager.sync_default_enabled_builtin_plugin_install_states()

    fake_gateway.list_plugins.assert_awaited_once_with(fake_session)
    fake_gateway.upsert_discovered_plugin.assert_not_awaited()
    fake_gateway.mark_plugin_installed.assert_not_awaited()
    fake_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_write_is_required_when_default_builtin_state_is_missing() -> None:
    """校验旧 ready 标记不能掩盖默认插件安装状态缺失。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    discovered_plugin = MagicMock()
    discovered_plugin.manifest.id = 'ai'
    fake_builder = MagicMock()
    fake_builder.discover_plugins.return_value = [discovered_plugin]
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[])
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with patch_startup_get_db(fake_get_db):
        requires_write = await startup_manager.requires_startup_write()

    assert requires_write is True
    fake_gateway.list_plugins.assert_awaited_once_with(fake_session)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('database_plugin', 'expected'),
    [
        (MagicMock(plugin_id='ai', installed_version='1.0.0', status='installed', enabled='0'), False),
        (MagicMock(plugin_id='ai', installed_version=None, status='discovered', enabled='1'), False),
    ],
)
async def test_startup_write_respects_installed_or_explicitly_uninstalled_builtin(
    database_plugin: object,
    expected: bool,
) -> None:
    """校验已安装插件和用户明确卸载的插件不会触发重复自动安装。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    discovered_plugin = MagicMock()
    discovered_plugin.manifest.id = 'ai'
    fake_builder = MagicMock()
    fake_builder.discover_plugins.return_value = [discovered_plugin]
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[database_plugin])
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with patch_startup_get_db(fake_get_db):
        requires_write = await startup_manager.requires_startup_write()

    assert requires_write is expected


@pytest.mark.asyncio
async def test_run_plugin_install_scripts_runs_migrations_and_seeds() -> None:
    """校验启动期安装脚本会执行 migration 和 seed。"""
    fake_session = object()
    fake_migration_session = object()
    discovered_plugin = MagicMock()
    fake_gateway = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock(), fake_gateway)
    migration_runner = MagicMock()
    migration_runner.run = AsyncMock()
    seed_runner = MagicMock()
    seed_runner.run = AsyncMock()
    runner_class = MagicMock(return_value=migration_runner)
    seed_runner_class = MagicMock(return_value=seed_runner)
    migration_session_context = MagicMock()
    migration_session_context.__aenter__ = AsyncMock(return_value=fake_migration_session)
    migration_session_context.__aexit__ = AsyncMock(return_value=None)
    async_session_local = MagicMock(return_value=migration_session_context)

    with (
        patch_startup_global('AsyncSessionLocal', async_session_local),
        patch_startup_global('PluginMigrationRunner', runner_class),
        patch_startup_global('PluginSeedRunner', seed_runner_class),
    ):
        await startup_manager.run_plugin_install_scripts(fake_session, discovered_plugin)

    runner_class.assert_called_once()
    assert runner_class.call_args.args[0] is discovered_plugin
    assert isinstance(runner_class.call_args.args[1], PluginStartupMigrationHistoryStore)
    assert runner_class.call_args.args[1].async_session_local is async_session_local
    assert runner_class.call_args.kwargs['manage_execution_transaction'] is True
    migration_runner.run.assert_awaited_once_with(fake_migration_session)
    seed_runner_class.assert_called_once_with(discovered_plugin)
    seed_runner.run.assert_awaited_once_with(fake_session)


@pytest.mark.asyncio
async def test_shutdown_runs_plugin_shutdown_hooks() -> None:
    """校验插件关闭协调器执行关闭钩子。"""
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.run_enabled_plugin_hooks = AsyncMock()

    await startup_manager.shutdown(app)

    startup_manager.run_enabled_plugin_hooks.assert_awaited_once_with(
        app,
        'on_shutdown',
        startup_write_enabled=True,
    )


@pytest.mark.asyncio
async def test_load_registry_from_database_rebuilds_registry() -> None:
    """校验启动协调器会按数据库插件状态重建运行时注册表。"""
    fake_session = object()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    fake_registry = PluginRegistry.build([])
    fake_builder = MagicMock()
    fake_builder.build_registry.return_value = fake_registry
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[])
    app = FastAPI()

    with patch_startup_get_db(fake_get_db):
        await PluginRuntimeStartupManager(fake_builder, fake_gateway).load_registry_from_database(app)

    fake_gateway.list_plugins.assert_awaited_once_with(fake_session)
    assert app.state.plugin_registry is fake_registry
    fake_builder.build_registry.assert_called_once_with([])


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_marks_missing_dependency_error() -> None:
    """校验启用插件 Python 依赖缺失时会标记插件运行时异常。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    plugin.discovered_plugin.manifest.dependencies.python = ['agno==2.4.8']
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = [plugin]
    dependency_item = MagicMock(ok=False, message='Python 依赖未安装：agno')
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [dependency_item]
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
    )

    with patch.object(
        startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock
    ) as mark_plugin_runtime_error:
        await startup_manager.check_enabled_plugin_python_dependencies(app)

    python_dependency_inspector.check.assert_called_once_with(['agno==2.4.8'])
    python_dependency_inspector.refresh.assert_called_once_with()
    mark_plugin_runtime_error.assert_awaited_once_with(
        app,
        'ai',
        ('插件启动依赖检查失败：Python 依赖未安装：agno；安装依赖请执行：ruoyi plugin install-deps ai --env=dev --yes'),
    )


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_skips_database_write_when_startup_write_disabled() -> None:
    """校验非启动写入 worker 只返回依赖失败插件，不写入插件错误状态。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    plugin.discovered_plugin.manifest.dependencies.python = ['agno==2.4.8']
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = [plugin]
    dependency_item = MagicMock(ok=False, message='Python 依赖未安装：agno')
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [dependency_item]
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
    )
    mocked_logger = MagicMock()

    with (
        patch.object(
            startup_manager,
            'mark_plugin_runtime_error',
            new_callable=AsyncMock,
        ) as mark_plugin_runtime_error,
        patch_startup_global('logger', mocked_logger),
    ):
        failed_plugin_ids = await startup_manager.check_enabled_plugin_python_dependencies(
            app,
            startup_write_enabled=False,
        )

    assert failed_plugin_ids == {'ai'}
    python_dependency_inspector.check.assert_called_once_with(['agno==2.4.8'])
    mark_plugin_runtime_error.assert_not_awaited()
    mocked_logger.bind.assert_called_once_with(
        plugin_id='ai',
        startup_generation=None,
        plugin_startup_role_at_creation='reader',
        startup_write_enabled=False,
    )
    assert '插件启动依赖检查失败' in mocked_logger.bind.return_value.error.call_args.args[0]


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_skips_satisfied_dependencies() -> None:
    """校验启用插件 Python 依赖满足时不会标记异常。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='demo')
    plugin.discovered_plugin.manifest.dependencies.python = ['requests>=2.0.0']
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = [plugin]
    dependency_item = MagicMock(ok=True, message='Python 依赖已满足：requests')
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [dependency_item]
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
    )

    with patch.object(
        startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock
    ) as mark_plugin_runtime_error:
        await startup_manager.check_enabled_plugin_python_dependencies(app)

    python_dependency_inspector.check.assert_called_once_with(['requests>=2.0.0'])
    mark_plugin_runtime_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_rechecks_dependency_error_plugin() -> None:
    """校验插件因依赖错误被隔离后，下一次启动仍会重新检查其依赖。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    plugin.discovered_plugin.manifest.dependencies.python = ['agno==2.4.8']
    plugin.database_plugin.status = 'error'
    plugin.database_plugin.last_error = (
        '插件启动依赖检查失败：Python 依赖未安装：agno；安装依赖请执行：ruoyi plugin install-deps ai --env=dev --yes'
    )
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = []
    app.state.plugin_registry.list_plugins.return_value = [plugin]
    dependency_item = MagicMock(ok=False, message='Python 依赖未安装：agno')
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [dependency_item]
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
    )

    with patch.object(
        startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock
    ) as mark_plugin_runtime_error:
        failed_plugin_ids = await startup_manager.check_enabled_plugin_python_dependencies(app)

    assert failed_plugin_ids == {'ai'}
    python_dependency_inspector.check.assert_called_once_with(['agno==2.4.8'])
    mark_plugin_runtime_error.assert_awaited_once_with(
        app,
        'ai',
        ('插件启动依赖检查失败：Python 依赖未安装：agno；安装依赖请执行：ruoyi plugin install-deps ai --env=dev --yes'),
    )


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_recovers_satisfied_dependency_error_plugin() -> None:
    """校验启动依赖重新满足后会恢复此前被隔离的插件。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    plugin.discovered_plugin.manifest.dependencies.python = ['agno==2.4.8']
    plugin.database_plugin.status = 'error'
    plugin.database_plugin.last_error = (
        '插件启动依赖检查失败：Python 依赖未安装：agno；安装依赖请执行：ruoyi plugin install-deps ai --env=dev --yes'
    )
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = []
    app.state.plugin_registry.list_plugins.return_value = [plugin]
    dependency_item = MagicMock(ok=True, message='Python 依赖已满足：agno')
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [dependency_item]
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
    )

    with (
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_runtime_error,
        patch.object(
            startup_manager,
            'recover_plugin_dependency_errors',
            new_callable=AsyncMock,
        ) as recover_dependency_errors,
    ):
        failed_plugin_ids = await startup_manager.check_enabled_plugin_python_dependencies(app)

    assert failed_plugin_ids == set()
    python_dependency_inspector.check.assert_called_once_with(['agno==2.4.8'])
    mark_runtime_error.assert_not_awaited()
    recover_dependency_errors.assert_awaited_once_with(app, [plugin])


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_reader_does_not_write_recovered_state() -> None:
    """校验非启动写入 worker 不重复写入已恢复依赖的插件状态。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    plugin.discovered_plugin.manifest.dependencies.python = ['agno==2.4.8']
    plugin.database_plugin.status = 'error'
    plugin.database_plugin.last_error = '插件启动依赖检查失败：Python 依赖未安装：agno'
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = []
    app.state.plugin_registry.list_plugins.return_value = [plugin]
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [MagicMock(ok=True)]
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
    )

    with patch.object(
        startup_manager,
        'recover_plugin_dependency_errors',
        new_callable=AsyncMock,
    ) as recover_dependency_errors:
        failed_plugin_ids = await startup_manager.check_enabled_plugin_python_dependencies(
            app,
            startup_write_enabled=False,
        )

    assert failed_plugin_ids == set()
    recover_dependency_errors.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_skips_unrelated_disabled_error_plugin() -> None:
    """校验普通错误或手动停用插件不会被启动依赖检查误选中。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='demo')
    plugin.discovered_plugin.manifest.dependencies.python = ['requests>=2.0.0']
    plugin.database_plugin.status = 'error'
    plugin.database_plugin.last_error = '插件启动钩子执行失败：broken startup'
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = []
    app.state.plugin_registry.list_plugins.return_value = [plugin]
    python_dependency_inspector = MagicMock()
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
    )

    failed_plugin_ids = await startup_manager.check_enabled_plugin_python_dependencies(app)

    assert failed_plugin_ids == set()
    python_dependency_inspector.refresh.assert_called_once_with()
    python_dependency_inspector.check.assert_not_called()


@pytest.mark.asyncio
async def test_recover_plugin_dependency_errors_commits_and_reloads_registry() -> None:
    """校验启动依赖恢复状态统一提交后刷新运行时注册表。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    fake_gateway = MagicMock()
    fake_gateway.recover_plugin_dependency_error = AsyncMock(
        return_value=MagicMock(is_success=True, message='插件启动依赖已恢复')
    )
    startup_manager = PluginRuntimeStartupManager(MagicMock(), fake_gateway)

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(startup_manager, 'load_registry_from_database', new_callable=AsyncMock) as load_registry,
    ):
        await startup_manager.recover_plugin_dependency_errors(app, [plugin])

    fake_gateway.recover_plugin_dependency_error.assert_awaited_once_with(
        fake_session,
        plugin.discovered_plugin,
    )
    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_awaited()
    load_registry.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_never_installs_during_startup() -> None:
    """校验启动期只做依赖门禁，不再交互安装缺失 Python 依赖。"""
    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    plugin.discovered_plugin.manifest.dependencies.python = ['agno==2.4.8']
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = [plugin]
    missing_item = MagicMock(
        ok=False,
        message='Python 依赖未安装：agno',
        kind='python',
        requirement='agno==2.4.8',
        name='agno',
        installed=False,
        version_satisfied=False,
        installed_version=None,
        required_version='==2.4.8',
        status='checked',
    )
    first_inspector = MagicMock()
    first_inspector.check.return_value = [missing_item]
    command_runner_gateway = MagicMock()
    command_runner_gateway.run_command.return_value = CompletedProcess(
        args=['python', '-m', 'pip', 'install', 'agno==2.4.8'],
        returncode=0,
        stdout='installed',
        stderr='',
    )
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=first_inspector,
        python_dependency_inspector_factory=MagicMock(),
        command_runner_gateway=command_runner_gateway,
    )

    with (
        patch.object(startup_manager, '_can_prompt_dependency_install', return_value=True),
        patch('builtins.input', return_value='y'),
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_plugin_runtime_error,
    ):
        await startup_manager.check_enabled_plugin_python_dependencies(app)

    command_runner_gateway.run_command.assert_not_called()
    startup_manager.python_dependency_inspector_factory.assert_not_called()
    mark_plugin_runtime_error.assert_awaited_once_with(
        app,
        'ai',
        ('插件启动依赖检查失败：Python 依赖未安装：agno；安装依赖请执行：ruoyi plugin install-deps ai --env=dev --yes'),
    )


def test_build_dependency_startup_error_message_uses_current_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验启动依赖失败提示使用当前应用环境构建可执行命令。"""
    monkeypatch.setattr('plugins.core.runtime.startup.AppConfig.app_env', 'stage')
    monkeypatch.setattr('plugins.core.runtime.startup.get_config.run_env', 'stage')

    error_message = PluginRuntimeStartupManager._build_dependency_startup_error_message(
        'demo',
        ['Python 依赖未安装：example-package'],
    )

    assert error_message == (
        '插件启动依赖检查失败：Python 依赖未安装：example-package；'
        '安装依赖请执行：ruoyi plugin install-deps demo --env=stage --yes'
    )


@pytest.mark.parametrize('run_env', ['prod', 'dockermy', 'dockerpg'])
def test_build_dependency_startup_error_message_builds_executable_prod_command(
    monkeypatch: pytest.MonkeyPatch,
    run_env: str,
) -> None:
    """校验生产及 Docker 启动依赖失败提示包含 CLI 安装所需的显式授权参数。"""
    monkeypatch.setattr('plugins.core.runtime.startup.AppConfig.app_env', 'prod')
    monkeypatch.setattr('plugins.core.runtime.startup.get_config.run_env', run_env)

    error_message = PluginRuntimeStartupManager._build_dependency_startup_error_message(
        'demo',
        ['Python 依赖未安装：example-package'],
    )

    assert error_message == (
        '插件启动依赖检查失败：Python 依赖未安装：example-package；'
        f'安装依赖请执行：ruoyi plugin install-deps demo --env={run_env} --yes '
        '--allow-prod --allow-unlisted --no-require-lockfile'
    )


def test_register_enabled_plugin_routers_uses_enabled_plugin_ids(tmp_path: Path) -> None:
    """校验插件路由注册只向路由注册器传递启用且允许自动扫描的插件 ID。"""
    backend_root = tmp_path / 'backend'
    demo_controller = backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py'
    manual_controller = backend_root / 'plugins' / 'manual' / 'controller' / 'manual_controller.py'
    for path in (demo_controller, manual_controller):
        path.parent.mkdir(parents=True, exist_ok=True)
    demo_controller.write_text(
        "from common.router import APIRouterPro\n\ndemo_controller = APIRouterPro(prefix='/demo/items')\n",
        encoding='utf-8',
    )
    manual_controller.write_text(
        "from common.router import APIRouterPro\n\nmanual_controller = APIRouterPro(prefix='/manual/items')\n",
        encoding='utf-8',
    )

    class FakePluginRegistry:
        """
        测试用插件运行时注册表。
        """

        def list_enabled_plugins(self) -> list[MagicMock]:
            """获取启用插件列表。"""
            return [
                MagicMock(
                    plugin_id='demo',
                    discovered_plugin=MagicMock(
                        manifest=MagicMock(backend=MagicMock(routers=MagicMock(auto_scan=True)))
                    ),
                ),
                MagicMock(
                    plugin_id='manual',
                    discovered_plugin=MagicMock(
                        manifest=MagicMock(backend=MagicMock(routers=MagicMock(auto_scan=False)))
                    ),
                ),
            ]

    app = FastAPI()
    app.state.plugin_registry = FakePluginRegistry()
    app.state.plugin_routes_registered = False
    builder = MagicMock()
    builder.backend_root = backend_root
    route_state_gateway = MagicMock()
    startup_manager = PluginRuntimeStartupManager(builder, route_state_gateway=route_state_gateway)

    auto_register_controller_files = MagicMock()
    with patch_startup_global('auto_register_controller_files', auto_register_controller_files):
        startup_manager.register_enabled_plugin_routers(app)
        startup_manager.register_enabled_plugin_routers(app)

    auto_register_controller_files.assert_called_once()
    controller_files = auto_register_controller_files.call_args.args[1]
    dependencies = auto_register_controller_files.call_args.kwargs['dependencies']
    assert controller_files == [str(demo_controller)]
    assert len(dependencies) == 1
    assert dependencies[0].dependency.plugin_id == 'demo'
    assert dependencies[0].dependency.state_gateway is route_state_gateway
    assert app.state.plugin_routes_registered is True


def test_register_enabled_plugin_routers_skips_invalid_route_prefix(tmp_path: Path) -> None:
    """校验启动期路由注册会再次拦截越过插件命名空间的 controller。"""
    backend_root = tmp_path / 'backend'
    valid_controller = backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py'
    invalid_controller = backend_root / 'plugins' / 'bad' / 'controller' / 'bad_controller.py'
    valid_controller.parent.mkdir(parents=True, exist_ok=True)
    invalid_controller.parent.mkdir(parents=True, exist_ok=True)
    valid_controller.write_text(
        "from common.router import APIRouterPro\n\ndemo_controller = APIRouterPro(prefix='/demo/items')\n",
        encoding='utf-8',
    )
    invalid_controller.write_text(
        "from common.router import APIRouterPro\n\nbad_controller = APIRouterPro(prefix='/system/user')\n",
        encoding='utf-8',
    )

    class FakePluginRegistry:
        """
        测试用插件运行时注册表。
        """

        def list_enabled_plugins(self) -> list[MagicMock]:
            """获取启用插件列表。"""
            return [
                MagicMock(
                    plugin_id='demo',
                    discovered_plugin=MagicMock(
                        manifest=MagicMock(backend=MagicMock(routers=MagicMock(auto_scan=True)))
                    ),
                ),
                MagicMock(
                    plugin_id='bad',
                    discovered_plugin=MagicMock(
                        manifest=MagicMock(backend=MagicMock(routers=MagicMock(auto_scan=True)))
                    ),
                ),
            ]

    app = FastAPI()
    app.state.plugin_registry = FakePluginRegistry()
    app.state.plugin_routes_registered = False
    builder = MagicMock()
    builder.backend_root = backend_root
    startup_manager = PluginRuntimeStartupManager(builder)

    auto_register_controller_files = MagicMock()
    with patch_startup_global('auto_register_controller_files', auto_register_controller_files):
        startup_manager.register_enabled_plugin_routers(app)

    auto_register_controller_files.assert_called_once()
    assert auto_register_controller_files.call_args.args[1] == [str(valid_controller)]
    assert app.state.plugin_routes_registered is True


def test_register_enabled_plugin_routers_skips_unrecognized_router_factory(tmp_path: Path) -> None:
    """校验启动期路由注册会跳过无法静态确认路由前缀的 controller。"""
    backend_root = tmp_path / 'backend'
    controller = backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        "from common.router import APIRouterPro as Router\n\nrouter = Router(prefix='/demo/items')\n",
        encoding='utf-8',
    )

    class FakePluginRegistry:
        """
        测试用插件运行时注册表。
        """

        def list_enabled_plugins(self) -> list[MagicMock]:
            """获取启用插件列表。"""
            return [
                MagicMock(
                    plugin_id='demo',
                    discovered_plugin=MagicMock(
                        manifest=MagicMock(backend=MagicMock(routers=MagicMock(auto_scan=True)))
                    ),
                )
            ]

    app = FastAPI()
    app.state.plugin_registry = FakePluginRegistry()
    app.state.plugin_routes_registered = False
    builder = MagicMock()
    builder.backend_root = backend_root
    startup_manager = PluginRuntimeStartupManager(builder)

    auto_register_controller_files = MagicMock()
    with patch_startup_global('auto_register_controller_files', auto_register_controller_files):
        startup_manager.register_enabled_plugin_routers(app)

    auto_register_controller_files.assert_not_called()
    assert app.state.plugin_routes_registered is True


def test_find_plugin_controller_files_filters_private_and_missing_plugins(tmp_path: Path) -> None:
    """校验启动协调器只查找指定插件的公开 controller 文件。"""
    backend_root = tmp_path / 'backend'
    plugin_controller = backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py'
    private_controller = backend_root / 'plugins' / 'demo' / 'controller' / '_private_controller.py'
    other_controller = backend_root / 'plugins' / 'other' / 'controller' / 'other_controller.py'
    for path in (plugin_controller, private_controller, other_controller):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    startup_manager = PluginRuntimeStartupManager(PluginRuntimeBuilder(backend_root))

    controller_files = startup_manager._find_plugin_controller_files(['demo', 'missing'])

    assert controller_files == [str(plugin_controller)]


@pytest.mark.asyncio
async def test_install_enabled_plugin_resources_isolates_failed_plugin() -> None:
    """校验单个插件资源同步失败不会阻断其他插件。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """提供测试数据库会话生成器。"""
        yield fake_session

    broken_plugin = MagicMock()
    broken_plugin.manifest.id = 'broken'
    healthy_plugin = MagicMock()
    healthy_plugin.manifest.id = 'healthy'
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry(
        [
            RegisteredPlugin(broken_plugin, MagicMock(), enabled=True, status='installed'),
            RegisteredPlugin(healthy_plugin, MagicMock(), enabled=True, status='installed'),
        ]
    )
    fake_gateway = MagicMock()
    fake_gateway.install_plugin_resources = AsyncMock(side_effect=[RuntimeError('broken resource'), None])
    startup_manager = PluginRuntimeStartupManager(MagicMock(), fake_gateway)

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_error,
    ):
        await startup_manager.install_enabled_plugin_resources(app)

    assert [call.args[1] for call in fake_gateway.install_plugin_resources.await_args_list] == [
        broken_plugin,
        healthy_plugin,
    ]
    fake_session.rollback.assert_awaited_once()
    fake_session.commit.assert_awaited_once()
    mark_error.assert_awaited_once_with(app, 'broken', '插件启动资源同步失败：broken resource')


@pytest.mark.asyncio
async def test_sync_default_enabled_builtin_plugins_isolates_install_failure() -> None:
    """校验默认内置插件首次安装失败不会阻断后续插件。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """提供测试数据库会话生成器。"""
        yield fake_session

    broken_plugin = MagicMock()
    broken_plugin.manifest.id = 'broken'
    healthy_plugin = MagicMock()
    healthy_plugin.manifest.id = 'healthy'
    fake_builder = MagicMock()
    fake_builder.discover_plugins.return_value = [broken_plugin, healthy_plugin]
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[])
    startup_manager = PluginRuntimeStartupManager(
        fake_builder,
        fake_gateway,
        default_enabled_builtin_plugin_ids={'broken', 'healthy'},
    )

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(
            startup_manager,
            'sync_plugin_install',
            new_callable=AsyncMock,
            side_effect=[RuntimeError('broken install'), None],
        ) as sync_install,
        patch.object(
            startup_manager,
            'mark_discovered_plugin_startup_error',
            new_callable=AsyncMock,
        ) as mark_error,
    ):
        failed_plugin_ids = await startup_manager.sync_default_enabled_builtin_plugin_install_states()

    assert [call.args[0] for call in sync_install.await_args_list] == [broken_plugin, healthy_plugin]
    assert failed_plugin_ids == {'broken'}
    mark_error.assert_awaited_once_with(broken_plugin, '插件启动安装失败：broken install')


def test_disable_runtime_plugins_marks_plugins_disabled_in_current_registry() -> None:
    """校验当前 worker 可在运行时注册表中过滤失败插件，避免继续导入或注册。"""
    ai_discovered_plugin = MagicMock()
    ai_discovered_plugin.manifest.id = 'ai'
    demo_discovered_plugin = MagicMock()
    demo_discovered_plugin.manifest.id = 'demo'
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry(
        [
            RegisteredPlugin(ai_discovered_plugin, None, enabled=True, status='installed'),
            RegisteredPlugin(demo_discovered_plugin, None, enabled=True, status='installed'),
        ]
    )

    PluginRuntimeStartupManager.disable_runtime_plugins(app, {'ai'})

    assert app.state.plugin_registry.get_plugin('ai').enabled is False
    assert app.state.plugin_registry.get_plugin('ai').status == 'error'
    assert [plugin.plugin_id for plugin in app.state.plugin_registry.list_enabled_plugins()] == ['demo']


@pytest.mark.asyncio
async def test_mark_plugin_runtime_error_updates_database_and_rebuilds_registry() -> None:
    """校验运行时异常会写入插件错误状态并刷新运行时注册表。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    app = FastAPI()
    fake_gateway = MagicMock()
    fake_gateway.mark_plugin_error = AsyncMock()
    fake_gateway.mark_plugin_error.return_value.is_success = True
    startup_manager = PluginRuntimeStartupManager(MagicMock(), fake_gateway)

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(startup_manager, 'load_registry_from_database', new_callable=AsyncMock) as load_registry,
    ):
        await startup_manager.mark_plugin_runtime_error(app, 'demo', 'broken')

    fake_gateway.mark_plugin_error.assert_awaited_once_with(fake_session, 'demo', 'broken')
    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_awaited()
    load_registry.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_mark_plugin_runtime_error_upserts_discovered_plugin_when_missing() -> None:
    """校验数据库缺少插件记录时会先写入发现插件再标记异常。"""
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """生成测试数据库会话。"""
        yield fake_session

    app = FastAPI()
    fake_builder = MagicMock()
    fake_builder.plugins_root = BACKEND_ROOT / 'plugins'
    fake_builder.frontend_plugins_root = BACKEND_ROOT.parent / 'frontend' / 'plugins'
    fake_registered_plugin = MagicMock()
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.get_plugin.return_value = fake_registered_plugin
    fake_gateway = MagicMock()
    fake_gateway.mark_plugin_error = AsyncMock()
    fake_gateway.upsert_discovered_plugin = AsyncMock()
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with (
        patch_startup_get_db(fake_get_db),
        patch.object(startup_manager, 'load_registry_from_database', new_callable=AsyncMock) as load_registry,
    ):
        failed_result = MagicMock(is_success=False, message='插件不存在')
        success_result = MagicMock(is_success=True)
        fake_gateway.mark_plugin_error.side_effect = [failed_result, success_result]

        await startup_manager.mark_plugin_runtime_error(app, 'demo', 'broken')

    expected_mark_error_call_count = 2
    assert fake_gateway.mark_plugin_error.await_count == expected_mark_error_call_count
    fake_session.rollback.assert_awaited_once()
    fake_gateway.upsert_discovered_plugin.assert_awaited_once_with(
        fake_session,
        fake_registered_plugin.discovered_plugin,
        fake_builder.plugins_root,
        fake_builder.frontend_plugins_root,
    )
    fake_session.commit.assert_awaited_once()
    load_registry.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_import_enabled_plugin_entities_marks_failures() -> None:
    """校验启用插件实体导入失败时会标记插件异常。"""
    app = FastAPI()
    app.state.plugin_registry = MagicMock()
    fake_builder = MagicMock()
    fake_builder.import_plugin_entities.return_value.failures = [
        MagicMock(plugin_id='demo', error_message='broken entity')
    ]
    startup_manager = PluginRuntimeStartupManager(fake_builder)

    with patch.object(
        startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock
    ) as mark_plugin_runtime_error:
        await startup_manager.import_enabled_plugin_entities(app)

    fake_builder.import_plugin_entities.assert_called_once_with(app.state.plugin_registry)
    mark_plugin_runtime_error.assert_awaited_once_with(app, 'demo', 'broken entity')


@pytest.mark.asyncio
async def test_import_enabled_plugin_entities_skips_database_write_when_startup_write_disabled() -> None:
    """校验非启动写入 worker 导入插件实体失败时只返回失败插件，不写入插件错误状态。"""
    app = FastAPI()
    app.state.plugin_registry = MagicMock()
    fake_builder = MagicMock()
    fake_builder.import_plugin_entities.return_value.failures = [
        MagicMock(plugin_id='demo', error_message='broken entity')
    ]
    startup_manager = PluginRuntimeStartupManager(fake_builder)
    mocked_logger = MagicMock()

    with (
        patch.object(
            startup_manager,
            'mark_plugin_runtime_error',
            new_callable=AsyncMock,
        ) as mark_plugin_runtime_error,
        patch_startup_global('logger', mocked_logger),
    ):
        failed_plugin_ids = await startup_manager.import_enabled_plugin_entities(
            app,
            startup_write_enabled=False,
        )

    assert failed_plugin_ids == {'demo'}
    fake_builder.import_plugin_entities.assert_called_once_with(app.state.plugin_registry)
    mark_plugin_runtime_error.assert_not_awaited()
    mocked_logger.bind.assert_called_once_with(
        plugin_id='demo',
        startup_generation=None,
        plugin_startup_role_at_creation='reader',
        startup_write_enabled=False,
    )
    mocked_logger.bind.return_value.error.assert_called_once_with('❌ 插件实体导入失败：broken entity')


@pytest.mark.asyncio
async def test_run_enabled_plugin_hooks_runs_startup_hooks() -> None:
    """校验启动协调器会执行启用插件生命周期钩子。"""
    discovered_plugin = MagicMock()
    fake_registered_plugin = MagicMock(discovered_plugin=discovered_plugin)
    fake_registry = MagicMock()
    fake_registry.list_enabled_plugins.return_value = [fake_registered_plugin]
    app = FastAPI()
    app.state.plugin_registry = fake_registry

    hook_runner = MagicMock()
    hook_runner.return_value.run = AsyncMock()
    with patch_startup_global('PluginHookRunner', hook_runner):
        await PluginRuntimeStartupManager(MagicMock()).run_enabled_plugin_hooks(app, 'on_startup')

    hook_runner.assert_called_once_with(discovered_plugin)
    hook_runner.return_value.run.assert_awaited_once_with('on_startup', app=app, startup_write_enabled=True)


@pytest.mark.asyncio
async def test_run_enabled_plugin_hooks_marks_error_and_continues() -> None:
    """校验插件生命周期钩子失败时会标记异常并继续执行后续插件。"""
    broken_discovered_plugin = MagicMock()
    healthy_discovered_plugin = MagicMock()
    broken_plugin = MagicMock(plugin_id='broken', discovered_plugin=broken_discovered_plugin)
    healthy_plugin = MagicMock(plugin_id='healthy', discovered_plugin=healthy_discovered_plugin)
    fake_registry = MagicMock()
    fake_registry.list_enabled_plugins.return_value = [broken_plugin, healthy_plugin]
    app = FastAPI()
    app.state.plugin_registry = fake_registry
    startup_manager = PluginRuntimeStartupManager(MagicMock())

    broken_runner = MagicMock()
    broken_runner.run = AsyncMock(side_effect=RuntimeError('broken hook'))
    healthy_runner = MagicMock()
    healthy_runner.run = AsyncMock()

    hook_runner = MagicMock(side_effect=[broken_runner, healthy_runner])
    with (
        patch_startup_global('PluginHookRunner', hook_runner),
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_plugin_runtime_error,
    ):
        await startup_manager.run_enabled_plugin_hooks(app, 'on_startup')

    expected_hook_runner_call_count = 2
    assert hook_runner.call_count == expected_hook_runner_call_count
    broken_runner.run.assert_awaited_once_with('on_startup', app=app, startup_write_enabled=True)
    healthy_runner.run.assert_awaited_once_with('on_startup', app=app, startup_write_enabled=True)
    mark_plugin_runtime_error.assert_awaited_once_with(app, 'broken', 'broken hook')


@pytest.mark.asyncio
async def test_reader_worker_startup_hook_failure_is_locally_isolated() -> None:
    """校验非写入 worker 的启动钩子失败后不会继续注册该插件路由。"""
    broken_discovered_plugin = MagicMock()
    broken_discovered_plugin.manifest.id = 'broken'
    healthy_discovered_plugin = MagicMock()
    healthy_discovered_plugin.manifest.id = 'healthy'
    broken_plugin = RegisteredPlugin(
        broken_discovered_plugin,
        MagicMock(),
        enabled=True,
        status='installed',
    )
    healthy_plugin = RegisteredPlugin(
        healthy_discovered_plugin,
        MagicMock(),
        enabled=True,
        status='installed',
    )
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry([broken_plugin, healthy_plugin])
    startup_manager = PluginRuntimeStartupManager(MagicMock())

    broken_runner = MagicMock()
    broken_runner.run = AsyncMock(side_effect=RuntimeError('broken local hook'))
    healthy_runner = MagicMock()
    healthy_runner.run = AsyncMock()

    hook_runner = MagicMock(side_effect=[broken_runner, healthy_runner])
    with (
        patch_startup_global('PluginHookRunner', hook_runner),
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_plugin_runtime_error,
    ):
        await startup_manager.run_enabled_plugin_hooks(
            app,
            'on_startup',
            startup_write_enabled=False,
        )

    assert [plugin.plugin_id for plugin in app.state.plugin_registry.list_enabled_plugins()] == ['healthy']
    mark_plugin_runtime_error.assert_not_awaited()
    healthy_runner.run.assert_awaited_once_with('on_startup', app=app, startup_write_enabled=False)
