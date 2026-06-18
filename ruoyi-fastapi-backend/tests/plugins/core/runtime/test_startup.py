import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.discovery.registry import PluginRegistry  # noqa: E402
from plugins.core.runtime.startup import PluginRuntimeStartupManager  # noqa: E402


@pytest.mark.asyncio
async def test_prepare_enabled_plugins_loads_registry_and_imports_entities() -> None:
    """
    校验插件启动协调器准备启用插件实体。

    :return: None
    """
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.load_registry_from_database = AsyncMock()
    startup_manager.import_enabled_plugin_entities = AsyncMock()

    await startup_manager.prepare_enabled_plugins(app)

    startup_manager.load_registry_from_database.assert_awaited_once_with(app)
    startup_manager.import_enabled_plugin_entities.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_activate_enabled_plugins_installs_resources_and_runs_hooks() -> None:
    """
    校验插件启动协调器激活启用插件资源。

    :return: None
    """
    app = MagicMock()
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.install_enabled_plugin_resources = AsyncMock()
    startup_manager.register_enabled_plugin_routers = MagicMock()
    startup_manager.run_enabled_plugin_hooks = AsyncMock()

    await startup_manager.activate_enabled_plugins(app)

    startup_manager.install_enabled_plugin_resources.assert_awaited_once_with(app)
    startup_manager.register_enabled_plugin_routers.assert_called_once_with(app)
    startup_manager.run_enabled_plugin_hooks.assert_awaited_once_with(app, 'on_startup')


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

    startup_manager.run_enabled_plugin_hooks.assert_awaited_once_with(app, 'on_shutdown')


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


def test_register_enabled_plugin_routers_uses_enabled_plugin_ids() -> None:
    """
    校验插件路由注册只向路由注册器传递启用且允许自动扫描的插件 ID。

    :return: None
    """

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
    startup_manager = PluginRuntimeStartupManager(MagicMock())

    with patch('plugins.core.runtime.startup.auto_register_plugin_routers') as auto_register_plugin_routers:
        startup_manager.register_enabled_plugin_routers(app)
        startup_manager.register_enabled_plugin_routers(app)

    auto_register_plugin_routers.assert_called_once_with(app, ['demo'])
    assert app.state.plugin_routes_registered is True


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
    hook_runner.return_value.run.assert_awaited_once_with('on_startup', app=app)


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
    broken_runner.run.assert_awaited_once_with('on_startup', app=app)
    healthy_runner.run.assert_awaited_once_with('on_startup', app=app)
    mark_plugin_runtime_error.assert_awaited_once_with(app, 'broken', 'broken hook')
