import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.discovery.registry import PluginRegistry, RegisteredPlugin  # noqa: E402
from plugins.core.runtime.bootstrap import PluginRuntimeBuilder  # noqa: E402
from plugins.core.runtime.startup import PluginRuntimeStartupManager, PluginStartupMigrationHistoryStore  # noqa: E402


def test_startup_manager_parses_default_enabled_builtin_plugin_ids() -> None:
    """
    校验默认启用内置插件配置按逗号分隔解析。

    :return: None
    """
    plugin_ids = PluginRuntimeStartupManager.parse_default_enabled_builtin_plugin_ids('ai, demo, ,report')

    assert plugin_ids == {'ai', 'demo', 'report'}


def test_startup_manager_reads_default_enabled_builtin_plugins_from_app_config() -> None:
    """
    校验启动管理器默认从应用配置读取内置默认启用插件列表。

    :return: None
    """
    with patch('plugins.core.runtime.startup.AppConfig.app_default_enabled_plugins', 'ai,demo'):
        startup_manager = PluginRuntimeStartupManager(MagicMock())

    assert startup_manager.default_enabled_builtin_plugin_ids == {'ai', 'demo'}


@pytest.mark.asyncio
async def test_prepare_enabled_plugins_loads_registry_and_imports_entities() -> None:
    """
    校验插件启动协调器准备启用插件实体。

    :return: None
    """
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_default_enabled_builtin_plugin_install_states = AsyncMock()
    startup_manager.load_registry_from_database = AsyncMock()
    startup_manager.check_enabled_plugin_python_dependencies = AsyncMock(return_value=set())
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


@pytest.mark.asyncio
async def test_prepare_enabled_plugins_skips_builtin_state_sync_when_startup_write_disabled() -> None:
    """
    校验非启动写入 worker 不初始化内置默认启用插件状态。

    :return: None
    """
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_default_enabled_builtin_plugin_install_states = AsyncMock()
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
    """
    校验插件启动协调器激活启用插件资源。

    :return: None
    """
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_enabled_plugin_install_states = AsyncMock()
    startup_manager.install_enabled_plugin_resources = AsyncMock()
    startup_manager.register_enabled_plugin_routers = MagicMock()
    startup_manager.run_enabled_plugin_hooks = AsyncMock()

    await startup_manager.activate_enabled_plugins(app)

    startup_manager.sync_enabled_plugin_install_states.assert_awaited_once_with(app)
    startup_manager.install_enabled_plugin_resources.assert_awaited_once_with(app)
    startup_manager.register_enabled_plugin_routers.assert_called_once_with(app)
    startup_manager.run_enabled_plugin_hooks.assert_awaited_once_with(
        app,
        'on_startup',
        startup_write_enabled=True,
    )


@pytest.mark.asyncio
async def test_activate_enabled_plugins_skips_resource_install_when_startup_write_disabled() -> None:
    """
    校验非启动写入 worker 会跳过插件资源安装，但仍注册本 worker 路由和执行本地钩子。

    :return: None
    """
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.sync_enabled_plugin_install_states = AsyncMock()
    startup_manager.install_enabled_plugin_resources = AsyncMock()
    startup_manager.register_enabled_plugin_routers = MagicMock()
    startup_manager.run_enabled_plugin_hooks = AsyncMock()

    await startup_manager.activate_enabled_plugins(app, startup_write_enabled=False)

    startup_manager.sync_enabled_plugin_install_states.assert_not_awaited()
    startup_manager.install_enabled_plugin_resources.assert_not_awaited()
    startup_manager.register_enabled_plugin_routers.assert_called_once_with(app)
    startup_manager.run_enabled_plugin_hooks.assert_awaited_once_with(
        app,
        'on_startup',
        startup_write_enabled=False,
    )


@pytest.mark.asyncio
async def test_sync_enabled_plugin_install_states_marks_missing_database_plugin_installed() -> None:
    """
    校验启动写入 worker 会将默认启用但未落库的插件同步为已安装。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
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
    fake_gateway.mark_plugin_installed = AsyncMock()
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with (
        patch('plugins.core.runtime.startup.get_db', fake_get_db),
        patch.object(startup_manager, 'load_registry_from_database', new_callable=AsyncMock) as load_registry,
        patch.object(startup_manager, 'run_plugin_install_scripts', new_callable=AsyncMock) as run_install_scripts,
    ):
        await startup_manager.sync_enabled_plugin_install_states(app)

    fake_gateway.upsert_discovered_plugin.assert_awaited_once_with(
        fake_session,
        discovered_plugin,
        fake_builder.plugins_root,
        fake_builder.frontend_plugins_root,
    )
    run_install_scripts.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_gateway.mark_plugin_installed.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_session.commit.assert_awaited_once()
    load_registry.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_sync_enabled_plugin_install_states_keeps_installed_plugin_unchanged() -> None:
    """
    校验已安装插件不会在启动期重复标记安装。

    :return: None
    """
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
    """
    校验内置默认启用插件缺少数据库状态时会初始化为已安装。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
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
    fake_gateway.mark_plugin_installed = AsyncMock()
    startup_manager = PluginRuntimeStartupManager(fake_builder, fake_gateway)

    with (
        patch('plugins.core.runtime.startup.get_db', fake_get_db),
        patch.object(startup_manager, 'run_plugin_install_scripts', new_callable=AsyncMock) as run_install_scripts,
    ):
        await startup_manager.sync_default_enabled_builtin_plugin_install_states()

    fake_gateway.list_plugins.assert_awaited_once_with(fake_session)
    fake_gateway.upsert_discovered_plugin.assert_awaited_once_with(
        fake_session,
        discovered_plugin,
        fake_builder.plugins_root,
        fake_builder.frontend_plugins_root,
    )
    run_install_scripts.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_gateway.mark_plugin_installed.assert_awaited_once_with(fake_session, discovered_plugin)
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_default_enabled_builtin_plugin_install_states_respects_uninstalled_builtin() -> None:
    """
    校验用户卸载后的内置插件不会在重启时被自动重新安装。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
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

    with patch('plugins.core.runtime.startup.get_db', fake_get_db):
        await startup_manager.sync_default_enabled_builtin_plugin_install_states()

    fake_gateway.list_plugins.assert_awaited_once_with(fake_session)
    fake_gateway.upsert_discovered_plugin.assert_not_awaited()
    fake_gateway.mark_plugin_installed.assert_not_awaited()
    fake_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_plugin_install_scripts_runs_migrations_and_seeds() -> None:
    """
    校验启动期安装脚本会执行 migration 和 seed。

    :return: None
    """
    fake_session = object()
    discovered_plugin = MagicMock()
    fake_gateway = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock(), fake_gateway)
    migration_runner = MagicMock()
    migration_runner.run = AsyncMock()
    seed_runner = MagicMock()
    seed_runner.run = AsyncMock()

    with (
        patch('plugins.core.runtime.startup.PluginMigrationRunner', return_value=migration_runner) as runner_class,
        patch('plugins.core.runtime.startup.PluginSeedRunner', return_value=seed_runner) as seed_runner_class,
    ):
        await startup_manager.run_plugin_install_scripts(fake_session, discovered_plugin)

    runner_class.assert_called_once()
    assert runner_class.call_args.args[0] is discovered_plugin
    assert isinstance(runner_class.call_args.args[1], PluginStartupMigrationHistoryStore)
    migration_runner.run.assert_awaited_once_with(fake_session)
    seed_runner_class.assert_called_once_with(discovered_plugin)
    seed_runner.run.assert_awaited_once_with(fake_session)


@pytest.mark.asyncio
async def test_shutdown_runs_plugin_shutdown_hooks() -> None:
    """
    校验插件关闭协调器执行关闭钩子。

    :return: None
    """
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
    """
    校验启动协调器会按数据库插件状态重建运行时注册表。

    :return: None
    """
    fake_session = object()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
        yield fake_session

    fake_registry = PluginRegistry.build([])
    fake_builder = MagicMock()
    fake_builder.build_registry.return_value = fake_registry
    fake_gateway = MagicMock()
    fake_gateway.list_plugins = AsyncMock(return_value=[])
    app = FastAPI()

    with patch('plugins.core.runtime.startup.get_db', fake_get_db):
        await PluginRuntimeStartupManager(fake_builder, fake_gateway).load_registry_from_database(app)

    fake_gateway.list_plugins.assert_awaited_once_with(fake_session)
    assert app.state.plugin_registry is fake_registry
    fake_builder.build_registry.assert_called_once_with([])


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_marks_missing_dependency_error() -> None:
    """
    校验启用插件 Python 依赖缺失时会标记插件运行时异常。

    :return: None
    """
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
    mark_plugin_runtime_error.assert_awaited_once_with(
        app,
        'ai',
        '插件启动依赖检查失败：Python 依赖未安装：agno',
    )


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_skips_database_write_when_startup_write_disabled() -> None:
    """
    校验非启动写入 worker 只返回依赖失败插件，不写入插件错误状态。

    :return: None
    """
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
        failed_plugin_ids = await startup_manager.check_enabled_plugin_python_dependencies(
            app,
            startup_write_enabled=False,
        )

    assert failed_plugin_ids == {'ai'}
    python_dependency_inspector.check.assert_called_once_with(['agno==2.4.8'])
    mark_plugin_runtime_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_skips_satisfied_dependencies() -> None:
    """
    校验启用插件 Python 依赖满足时不会标记异常。

    :return: None
    """
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
async def test_check_enabled_plugin_python_dependencies_installs_when_confirmed() -> None:
    """
    校验交互确认后会安装缺失 Python 依赖并重新检查。

    :return: None
    """
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
    satisfied_item = MagicMock(ok=True, message='Python 依赖已满足：agno')
    first_inspector = MagicMock()
    first_inspector.check.return_value = [missing_item]
    refreshed_inspector = MagicMock()
    refreshed_inspector.check.return_value = [satisfied_item]
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
        python_dependency_inspector_factory=MagicMock(return_value=refreshed_inspector),
        command_runner_gateway=command_runner_gateway,
    )

    with (
        patch.object(startup_manager, '_can_prompt_dependency_install', return_value=True),
        patch('builtins.input', return_value='y'),
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_plugin_runtime_error,
    ):
        await startup_manager.check_enabled_plugin_python_dependencies(app)

    command_runner_gateway.run_command.assert_called_once()
    refreshed_inspector.check.assert_called_once_with(['agno==2.4.8'])
    mark_plugin_runtime_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_enabled_plugin_python_dependencies_marks_error_when_install_declined() -> None:
    """
    校验交互拒绝安装时仍会标记插件异常。

    :return: None
    """
    app = FastAPI()
    plugin = MagicMock(plugin_id='ai')
    plugin.discovered_plugin.manifest.dependencies.python = ['agno==2.4.8']
    app.state.plugin_registry = MagicMock()
    app.state.plugin_registry.list_enabled_plugins.return_value = [plugin]
    dependency_item = MagicMock(ok=False, message='Python 依赖未安装：agno')
    python_dependency_inspector = MagicMock()
    python_dependency_inspector.check.return_value = [dependency_item]
    command_runner_gateway = MagicMock()
    startup_manager = PluginRuntimeStartupManager(
        MagicMock(),
        python_dependency_inspector=python_dependency_inspector,
        command_runner_gateway=command_runner_gateway,
    )

    with (
        patch.object(startup_manager, '_can_prompt_dependency_install', return_value=True),
        patch('builtins.input', return_value='n'),
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_plugin_runtime_error,
    ):
        await startup_manager.check_enabled_plugin_python_dependencies(app)

    command_runner_gateway.run_command.assert_not_called()
    mark_plugin_runtime_error.assert_awaited_once_with(
        app,
        'ai',
        '插件启动依赖检查失败：Python 依赖未安装：agno',
    )


def test_can_prompt_dependency_install_requires_single_worker_tty() -> None:
    """
    校验启动期交互安装仅允许单 worker TTY 环境。

    :return: None
    """
    with (
        patch('plugins.core.runtime.startup.AppConfig.app_workers', 1),
        patch('plugins.core.runtime.startup.sys.stdin.isatty', return_value=True),
    ):
        assert PluginRuntimeStartupManager._can_prompt_dependency_install() is True

    with (
        patch('plugins.core.runtime.startup.AppConfig.app_workers', 2),
        patch('plugins.core.runtime.startup.sys.stdin.isatty', return_value=True),
    ):
        assert PluginRuntimeStartupManager._can_prompt_dependency_install() is False

    with (
        patch('plugins.core.runtime.startup.AppConfig.app_workers', 1),
        patch('plugins.core.runtime.startup.sys.stdin.isatty', return_value=False),
    ):
        assert PluginRuntimeStartupManager._can_prompt_dependency_install() is False


def test_register_enabled_plugin_routers_uses_enabled_plugin_ids(tmp_path: Path) -> None:
    """
    校验插件路由注册只向路由注册器传递启用且允许自动扫描的插件 ID。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    demo_controller = backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py'
    manual_controller = backend_root / 'plugins' / 'manual' / 'controller' / 'manual_controller.py'
    for path in (demo_controller, manual_controller):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')

    class FakePluginRegistry:
        """
        测试用插件运行时注册表。
        """

        def list_enabled_plugins(self) -> list[MagicMock]:
            """
            获取启用插件列表。

            :return: 插件列表
            """
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
    startup_manager = PluginRuntimeStartupManager(builder)

    with patch('plugins.core.runtime.startup.auto_register_controller_files') as auto_register_controller_files:
        startup_manager.register_enabled_plugin_routers(app)
        startup_manager.register_enabled_plugin_routers(app)

    controller_files = auto_register_controller_files.call_args.args[1]
    assert controller_files == [str(demo_controller)]
    assert app.state.plugin_routes_registered is True


def test_find_plugin_controller_files_filters_private_and_missing_plugins(tmp_path: Path) -> None:
    """
    校验启动协调器只查找指定插件的公开 controller 文件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
async def test_install_enabled_plugin_menus_commits_after_service_call() -> None:
    """
    校验启动协调器会安装启用插件菜单并提交事务。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
        yield fake_session

    app = FastAPI()
    app.state.plugin_registry = PluginRegistry.build([])
    fake_gateway = MagicMock()
    fake_gateway.install_enabled_plugin_menus = AsyncMock()

    with patch('plugins.core.runtime.startup.get_db', fake_get_db):
        await PluginRuntimeStartupManager(MagicMock(), fake_gateway).install_enabled_plugin_menus(app)

    fake_gateway.install_enabled_plugin_menus.assert_awaited_once_with(fake_session, app.state.plugin_registry)
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_install_enabled_plugin_configs_commits_after_service_call() -> None:
    """
    校验启动协调器会安装启用插件默认配置并提交事务。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
        yield fake_session

    app = FastAPI()
    app.state.plugin_registry = PluginRegistry.build([])
    fake_gateway = MagicMock()
    fake_gateway.install_enabled_plugin_configs = AsyncMock()

    with patch('plugins.core.runtime.startup.get_db', fake_get_db):
        await PluginRuntimeStartupManager(MagicMock(), fake_gateway).install_enabled_plugin_configs(app)

    fake_gateway.install_enabled_plugin_configs.assert_awaited_once_with(fake_session, app.state.plugin_registry)
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_install_enabled_plugin_jobs_commits_after_service_call() -> None:
    """
    校验启动协调器会安装启用插件定时任务并提交事务。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
        yield fake_session

    app = FastAPI()
    app.state.plugin_registry = PluginRegistry.build([])
    fake_gateway = MagicMock()
    fake_gateway.install_enabled_plugin_jobs = AsyncMock()

    with patch('plugins.core.runtime.startup.get_db', fake_get_db):
        await PluginRuntimeStartupManager(MagicMock(), fake_gateway).install_enabled_plugin_jobs(app)

    fake_gateway.install_enabled_plugin_jobs.assert_awaited_once_with(fake_session, app.state.plugin_registry)
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_install_enabled_plugin_resource_skips_without_registry() -> None:
    """
    校验启动资源安装在插件注册表缺失时跳过。

    :return: None
    """
    app = FastAPI()
    installer = AsyncMock()

    await PluginRuntimeStartupManager(MagicMock()).install_enabled_plugin_resource(app, installer)

    installer.assert_not_awaited()


def test_disable_runtime_plugins_marks_plugins_disabled_in_current_registry() -> None:
    """
    校验当前 worker 可在运行时注册表中过滤失败插件，避免继续导入或注册。

    :return: None
    """
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
    """
    校验运行时异常会写入插件错误状态并刷新运行时注册表。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
        yield fake_session

    app = FastAPI()
    fake_gateway = MagicMock()
    fake_gateway.mark_plugin_error = AsyncMock()
    fake_gateway.mark_plugin_error.return_value.is_success = True
    startup_manager = PluginRuntimeStartupManager(MagicMock(), fake_gateway)

    with (
        patch('plugins.core.runtime.startup.get_db', fake_get_db),
        patch.object(startup_manager, 'load_registry_from_database', new_callable=AsyncMock) as load_registry,
    ):
        await startup_manager.mark_plugin_runtime_error(app, 'demo', 'broken')

    fake_gateway.mark_plugin_error.assert_awaited_once_with(fake_session, 'demo', 'broken')
    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_awaited()
    load_registry.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_mark_plugin_runtime_error_upserts_discovered_plugin_when_missing() -> None:
    """
    校验数据库缺少插件记录时会先写入发现插件再标记异常。

    :return: None
    """
    fake_session = AsyncMock()

    async def fake_get_db() -> object:
        """
        生成测试数据库会话。

        :return: 测试数据库会话
        """
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
        patch('plugins.core.runtime.startup.get_db', fake_get_db),
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
    """
    校验启用插件实体导入失败时会标记插件异常。

    :return: None
    """
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
    """
    校验非启动写入 worker 导入插件实体失败时只返回失败插件，不写入插件错误状态。

    :return: None
    """
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
        failed_plugin_ids = await startup_manager.import_enabled_plugin_entities(
            app,
            startup_write_enabled=False,
        )

    assert failed_plugin_ids == {'demo'}
    fake_builder.import_plugin_entities.assert_called_once_with(app.state.plugin_registry)
    mark_plugin_runtime_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_enabled_plugin_hooks_runs_startup_hooks() -> None:
    """
    校验启动协调器会执行启用插件生命周期钩子。

    :return: None
    """
    discovered_plugin = MagicMock()
    fake_registered_plugin = MagicMock(discovered_plugin=discovered_plugin)
    fake_registry = MagicMock()
    fake_registry.list_enabled_plugins.return_value = [fake_registered_plugin]
    app = FastAPI()
    app.state.plugin_registry = fake_registry

    with patch('plugins.core.runtime.startup.PluginHookRunner') as hook_runner:
        hook_runner.return_value.run = AsyncMock()

        await PluginRuntimeStartupManager(MagicMock()).run_enabled_plugin_hooks(app, 'on_startup')

    hook_runner.assert_called_once_with(discovered_plugin)
    hook_runner.return_value.run.assert_awaited_once_with('on_startup', app=app, startup_write_enabled=True)


@pytest.mark.asyncio
async def test_run_enabled_plugin_hooks_marks_error_and_continues() -> None:
    """
    校验插件生命周期钩子失败时会标记异常并继续执行后续插件。

    :return: None
    """
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

    with (
        patch(
            'plugins.core.runtime.startup.PluginHookRunner', side_effect=[broken_runner, healthy_runner]
        ) as hook_runner,
        patch.object(startup_manager, 'mark_plugin_runtime_error', new_callable=AsyncMock) as mark_plugin_runtime_error,
    ):
        await startup_manager.run_enabled_plugin_hooks(app, 'on_startup')

    expected_hook_runner_call_count = 2
    assert hook_runner.call_count == expected_hook_runner_call_count
    broken_runner.run.assert_awaited_once_with('on_startup', app=app, startup_write_enabled=True)
    healthy_runner.run.assert_awaited_once_with('on_startup', app=app, startup_write_enabled=True)
    mark_plugin_runtime_error.assert_awaited_once_with(app, 'broken', 'broken hook')
