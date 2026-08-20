from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from config.env import AppConfig
from plugins.core.runtime.application import (
    get_plugin_application_runtime as get_runtime_plugin_application_runtime,
)
from server import (
    _initialize_application_runtime,
    _shutdown_application_runtime,
    _stop_background_tasks,
    create_app,
    get_plugin_application_runtime,
    lifespan,
)


def test_server_reuses_plugin_application_runtime_getter() -> None:
    """校验 server 入口不直接装配插件管理适配器。"""
    assert get_plugin_application_runtime is get_runtime_plugin_application_runtime


def test_create_app_registers_builtin_routes_and_binds_plugin_runtime() -> None:
    """校验 create_app 保持内置路由注册，并绑定插件应用运行时。"""
    fake_plugin_runtime = MagicMock()

    with (
        patch('server.APIDocsUtil.setup_docs_static_resources'),
        patch('server.APIDocsUtil.custom_api_docs_router'),
        patch('server.handle_sub_applications'),
        patch('server.handle_middleware'),
        patch('server.handle_exception'),
        patch('server.auto_register_routers') as auto_register_routers,
        patch('server.get_plugin_application_runtime', return_value=fake_plugin_runtime),
    ):
        app = create_app()

    auto_register_routers.assert_called_once_with(app)
    fake_plugin_runtime.bind_app.assert_called_once_with(app)


@pytest.mark.asyncio
async def test_initialize_application_runtime_delegates_plugin_steps() -> None:
    """校验应用启动流程保留原系统初始化，并只委托插件专属步骤。"""
    fake_app = MagicMock()
    fake_plugin_runtime = MagicMock()
    fake_plugin_runtime.startup = AsyncMock()

    with (
        patch('server.get_plugin_application_runtime', return_value=fake_plugin_runtime),
        patch('server.init_create_table', new_callable=AsyncMock) as init_create_table,
        patch('server.RedisUtil.check_redis_connection', new_callable=AsyncMock) as check_redis_connection,
        patch('server.RedisUtil.init_sys_dict', new_callable=AsyncMock) as init_sys_dict,
        patch('server.RedisUtil.init_sys_config', new_callable=AsyncMock) as init_sys_config,
        patch('server._start_background_tasks', new_callable=AsyncMock) as start_background_tasks,
    ):
        await _initialize_application_runtime(fake_app, application_leader=True)
        fake_plugin_runtime.prepare_metadata.assert_called_once_with(fake_app)
        init_create_table.assert_awaited_once_with(
            stage='platform',
            log_success_enabled=True,
        )
        startup_call = fake_plugin_runtime.startup.await_args
        assert startup_call.args == (fake_app,)
        create_plugin_entity_tables = startup_call.kwargs['create_tables']
        await create_plugin_entity_tables()
        assert init_create_table.await_args_list[-1].kwargs == {
            'stage': 'plugin_entities',
            'log_success_enabled': True,
        }
        check_redis_connection.assert_awaited_once_with(
            fake_app.state.redis,
            log_enabled=True,
            log_error_enabled=True,
        )
        init_sys_dict.assert_awaited_once_with(fake_app.state.redis)
        init_sys_config.assert_awaited_once_with(fake_app.state.redis)
        start_background_tasks.assert_awaited_once_with(fake_app)
        assert fake_app.state.plugin_application_runtime_started is True


@pytest.mark.asyncio
async def test_non_leader_plugin_writer_still_runs_global_plugin_sync() -> None:
    """校验Application非leader仍可成为插件writer并输出插件全局写入阶段。"""
    fake_app = MagicMock()
    fake_plugin_runtime = MagicMock()

    async def run_as_plugin_writer(
        _app: object,
        *,
        create_tables: Callable[[], Awaitable[None]],
    ) -> None:
        """模拟当前非leader worker获得插件生命周期锁。"""
        await create_tables()

    fake_plugin_runtime.startup = AsyncMock(side_effect=run_as_plugin_writer)

    with (
        patch('server.get_plugin_application_runtime', return_value=fake_plugin_runtime),
        patch('server.init_create_table', new_callable=AsyncMock) as init_create_table,
        patch('server.RedisUtil.check_redis_connection', new_callable=AsyncMock) as check_redis_connection,
        patch('server.RedisUtil.init_sys_dict', new_callable=AsyncMock),
        patch('server.RedisUtil.init_sys_config', new_callable=AsyncMock),
        patch('server._start_background_tasks', new_callable=AsyncMock),
    ):
        await _initialize_application_runtime(fake_app, application_leader=False)

    assert init_create_table.await_args_list == [
        call(stage='platform', log_success_enabled=False),
        call(stage='plugin_entities', log_success_enabled=True),
    ]
    check_redis_connection.assert_awaited_once_with(
        fake_app.state.redis,
        log_enabled=False,
        log_error_enabled=True,
    )
    fake_plugin_runtime.startup.assert_awaited_once()
    assert fake_app.state.plugin_application_runtime_started is True


@pytest.mark.asyncio
async def test_lifespan_only_application_leader_outputs_banner_and_addresses() -> None:
    """校验仅Application leader输出横幅、成功摘要和访问地址。"""
    app = SimpleNamespace(state=SimpleNamespace())
    redis = MagicMock()
    database_registry = MagicMock()
    database_registry.initialize = AsyncMock()
    fake_logger = MagicMock()
    fake_logger.complete = AsyncMock()

    with (
        patch('server.RedisUtil.create_redis_pool', new=AsyncMock(return_value=redis)),
        patch('server.DataSourceRegistry', database_registry),
        patch('server.SchedulerUtil.get_application_lock_owner_token', return_value='owner-1'),
        patch('server.StartupUtil.acquire_application_leader', new=AsyncMock(return_value=True)),
        patch('server.SchedulerUtil.start_application_lock_renewal') as start_renewal,
        patch('server.SchedulerUtil.is_application_leader', return_value=True),
        patch('server.TransportKeyProvider.validate_runtime_configuration'),
        patch('server._initialize_application_runtime', new_callable=AsyncMock) as initialize_runtime,
        patch('server._shutdown_application_runtime', new_callable=AsyncMock) as shutdown_runtime,
        patch('server.asyncio.sleep', new_callable=AsyncMock),
        patch('server.IPUtil.get_local_ip', return_value='127.0.0.1'),
        patch('server.IPUtil.get_network_ips', return_value=['192.0.2.1']),
        patch('server.worship') as worship,
        patch('server.logger', fake_logger),
    ):
        async with lifespan(app):
            pass

    start_renewal.assert_called_once_with(redis)
    database_registry.initialize.assert_awaited_once_with(log_enabled=True)
    initialize_runtime.assert_awaited_once_with(app, application_leader=True)
    worship.assert_called_once_with()
    fake_logger.bind.return_value.info.assert_has_calls(
        [
            call(f'⏰️ {AppConfig.app_name}开始启动'),
            call(f'🚀 {AppConfig.app_name}启动成功'),
        ]
    )
    assert any(
        logged_call.args[0].startswith('💻 应用地址:')
        for logged_call in fake_logger.opt.return_value.info.call_args_list
    )
    fake_logger.complete.assert_awaited_once_with()
    shutdown_runtime.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_lifespan_non_leader_runs_local_initialization_without_display_logs() -> None:
    """校验非leader执行本地初始化，但不输出leader专属展示日志。"""
    app = SimpleNamespace(state=SimpleNamespace())
    redis = MagicMock()
    database_registry = MagicMock()
    database_registry.initialize = AsyncMock()
    fake_logger = MagicMock()
    fake_logger.complete = AsyncMock()

    with (
        patch('server.RedisUtil.create_redis_pool', new=AsyncMock(return_value=redis)),
        patch('server.DataSourceRegistry', database_registry),
        patch('server.SchedulerUtil.get_application_lock_owner_token', return_value='owner-2'),
        patch('server.StartupUtil.acquire_application_leader', new=AsyncMock(return_value=False)),
        patch('server.SchedulerUtil.start_application_lock_renewal') as start_renewal,
        patch('server.SchedulerUtil.is_application_leader') as is_application_leader,
        patch('server.TransportKeyProvider.validate_runtime_configuration'),
        patch('server._initialize_application_runtime', new_callable=AsyncMock) as initialize_runtime,
        patch('server._shutdown_application_runtime', new_callable=AsyncMock) as shutdown_runtime,
        patch('server.worship') as worship,
        patch('server.logger', fake_logger),
    ):
        async with lifespan(app):
            pass

    start_renewal.assert_not_called()
    database_registry.initialize.assert_awaited_once_with(log_enabled=False)
    is_application_leader.assert_not_called()
    initialize_runtime.assert_awaited_once_with(app, application_leader=False)
    worship.assert_not_called()
    fake_logger.bind.return_value.info.assert_not_called()
    fake_logger.opt.assert_not_called()
    fake_logger.complete.assert_awaited_once_with()
    shutdown_runtime.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_lifespan_non_leader_initialization_error_propagates_and_still_cleans_up() -> None:
    """校验非leader初始化异常不被门禁吞掉，并继续执行finally清理。"""
    app = SimpleNamespace(state=SimpleNamespace())
    database_registry = MagicMock()
    database_registry.initialize = AsyncMock()
    fake_logger = MagicMock()
    fake_logger.complete = AsyncMock()

    with (
        patch('server.RedisUtil.create_redis_pool', new=AsyncMock(return_value=MagicMock())),
        patch('server.DataSourceRegistry', database_registry),
        patch('server.SchedulerUtil.get_application_lock_owner_token', return_value='owner-3'),
        patch('server.StartupUtil.acquire_application_leader', new=AsyncMock(return_value=False)),
        patch('server.TransportKeyProvider.validate_runtime_configuration'),
        patch(
            'server._initialize_application_runtime',
            new=AsyncMock(side_effect=RuntimeError('non-leader initialization failed')),
        ) as initialize_runtime,
        patch('server._shutdown_application_runtime', new_callable=AsyncMock) as shutdown_runtime,
        patch('server.logger', fake_logger),
        pytest.raises(RuntimeError, match='non-leader initialization failed'),
    ):
        async with lifespan(app):
            pass

    initialize_runtime.assert_awaited_once_with(app, application_leader=False)
    database_registry.initialize.assert_awaited_once_with(log_enabled=False)
    fake_logger.bind.return_value.info.assert_not_called()
    fake_logger.complete.assert_not_awaited()
    shutdown_runtime.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_lifespan_skips_database_initialization_when_redis_creation_fails() -> None:
    """校验Redis前置初始化失败时不创建数据库资源，并执行幂等清理。"""
    app = SimpleNamespace(state=SimpleNamespace())
    database_registry = MagicMock()
    database_registry.initialize = AsyncMock()
    database_registry.dispose_all = AsyncMock()
    fake_logger = MagicMock()
    fake_logger.complete = AsyncMock()

    with (
        patch('server.DataSourceRegistry', database_registry),
        patch(
            'server.RedisUtil.create_redis_pool',
            new=AsyncMock(side_effect=RuntimeError('redis unavailable')),
        ),
        patch('server.logger', fake_logger),
        pytest.raises(RuntimeError, match='redis unavailable'),
    ):
        async with lifespan(app):
            pass

    database_registry.initialize.assert_not_awaited()
    database_registry.dispose_all.assert_awaited_once_with()
    fake_logger.complete.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_lifespan_database_initialization_failure_releases_redis_and_database_resources() -> None:
    """校验Redis和租约创建后数据库初始化失败仍走统一关闭流程。"""
    app = SimpleNamespace(state=SimpleNamespace())
    redis = MagicMock()
    database_registry = MagicMock()
    database_registry.initialize = AsyncMock(side_effect=RuntimeError('database unavailable'))

    with (
        patch('server.RedisUtil.create_redis_pool', new=AsyncMock(return_value=redis)),
        patch('server.DataSourceRegistry', database_registry),
        patch('server.SchedulerUtil.get_application_lock_owner_token', return_value='owner-db-failure'),
        patch('server.StartupUtil.acquire_application_leader', new=AsyncMock(return_value=False)),
        patch('server._shutdown_application_runtime', new_callable=AsyncMock) as shutdown_runtime,
        pytest.raises(RuntimeError, match='database unavailable'),
    ):
        async with lifespan(app):
            pass

    database_registry.initialize.assert_awaited_once_with(log_enabled=False)
    shutdown_runtime.assert_awaited_once_with(app)


@pytest.mark.asyncio
async def test_shutdown_application_runtime_preserves_cleanup_order() -> None:
    """校验插件关闭先执行，随后按Scheduler、Redis、数据库顺序释放资源。"""
    events: list[str] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            plugin_application_runtime_started=True,
            redis=object(),
        )
    )
    plugin_runtime = MagicMock()

    async def record_plugin_shutdown(_app: object) -> None:
        events.append('plugin')

    async def record_scheduler_shutdown() -> None:
        events.append('scheduler')

    async def record_redis_shutdown(_app: object) -> None:
        events.append('redis')

    async def record_database_shutdown() -> None:
        events.append('database')

    async def record_log_complete() -> None:
        events.append('logs')

    plugin_runtime.shutdown = AsyncMock(side_effect=record_plugin_shutdown)
    with (
        patch('server.get_plugin_application_runtime', return_value=plugin_runtime),
        patch(
            'server.SchedulerUtil.close_system_scheduler',
            new=AsyncMock(side_effect=record_scheduler_shutdown),
        ),
        patch(
            'server.RedisUtil.close_redis_pool',
            new=AsyncMock(side_effect=record_redis_shutdown),
        ),
        patch('server.DataSourceRegistry.dispose_all', new=AsyncMock(side_effect=record_database_shutdown)),
        patch('server.logger.complete', new=AsyncMock(side_effect=record_log_complete)),
    ):
        await _shutdown_application_runtime(app)

    assert events == ['plugin', 'scheduler', 'redis', 'database', 'logs']


@pytest.mark.asyncio
async def test_shutdown_application_runtime_releases_resources_when_plugin_hook_fails() -> None:
    """校验插件关闭钩子失败时仍执行基础设施清理。"""
    app = SimpleNamespace(state=SimpleNamespace(plugin_application_runtime_started=True))
    plugin_runtime = MagicMock()
    plugin_runtime.shutdown = AsyncMock(side_effect=RuntimeError('shutdown hook failed'))

    with (
        patch('server.get_plugin_application_runtime', return_value=plugin_runtime),
        patch('server._stop_background_tasks', new_callable=AsyncMock) as stop_background_tasks,
        patch('server.logger.complete', new_callable=AsyncMock) as complete_logs,
        pytest.raises(RuntimeError, match='shutdown hook failed'),
    ):
        await _shutdown_application_runtime(app)

    stop_background_tasks.assert_awaited_once_with(app)
    complete_logs.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_stop_background_tasks_closes_redis_and_database_when_scheduler_close_fails() -> None:
    """校验Scheduler释放异常不会跳过Redis和数据库清理。"""
    app = SimpleNamespace(state=SimpleNamespace(redis=object()))

    with (
        patch(
            'server.SchedulerUtil.close_system_scheduler',
            new=AsyncMock(side_effect=RuntimeError('scheduler close failed')),
        ),
        patch('server.RedisUtil.close_redis_pool', new_callable=AsyncMock) as close_redis_pool,
        patch('server.DataSourceRegistry.dispose_all', new_callable=AsyncMock) as dispose_all,
        pytest.raises(RuntimeError, match='scheduler close failed'),
    ):
        await _stop_background_tasks(app)

    close_redis_pool.assert_awaited_once_with(app)
    dispose_all.assert_awaited_once_with()
