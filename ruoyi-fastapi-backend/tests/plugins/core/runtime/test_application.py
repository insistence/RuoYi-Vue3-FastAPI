import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import FastAPI

from common.constant import LockConstant
from plugins.core.runtime.application import PluginApplicationRuntime, get_plugin_application_runtime
from plugins.core.runtime.service.lifecycle_lock import PluginLifecycleLockResult, RedisPluginLifecycleLock
from plugins.core.runtime.startup import PluginRuntimeStartupManager
from plugins.core.runtime.startup_coordination import PluginStartupGenerationResolver
from plugins.core.runtime.startup_gateway import UnavailablePluginStartupManagementGateway

EXPECTED_REQUIRED_WRITE_CHECK_COUNT = 2
READER_GLOBAL_WRITE_SKIP_MESSAGE = (
    '⏭️ 复用插件 ready 状态，跳过启动期全局写入：'
    'plugin_install_lifecycle=skipped，'
    'plugin_resource_sync=skipped，'
    'plugin_entity_table_sync=skipped'
)


class FakeRedis:
    """
    测试用 Redis。
    """

    def __init__(self, values: dict[str, str] | None = None) -> None:
        """初始化测试 Redis。"""
        self.values = values or {}
        self.deleted_keys: list[str] = []
        self.expires: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        """获取 Redis 值。"""
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """写入 Redis 值。"""
        self.values[key] = value
        if ex is not None:
            self.expires[key] = ex

    async def delete(self, key: str) -> None:
        """删除 Redis key。"""
        self.deleted_keys.append(key)
        self.values.pop(key, None)


class FakeLifecycleLock:
    """
    测试用插件生命周期锁。
    """

    def __init__(self, *, acquired: bool) -> None:
        """初始化测试锁。"""
        self.acquired = acquired
        self.calls: list[tuple[str, str]] = []

    @asynccontextmanager
    async def lock(self, plugin_id: str, operation: str) -> AsyncIterator[PluginLifecycleLockResult]:
        """返回预设锁结果。"""
        self.calls.append((plugin_id, operation))
        yield PluginLifecycleLockResult(acquired=self.acquired)


def build_app(redis: FakeRedis) -> FastAPI:
    """构建测试 FastAPI app。"""
    app = FastAPI()
    app.state.redis = redis
    return app


def test_plugin_application_runtime_binds_startup_manager() -> None:
    """校验应用插件运行时会绑定启动协调器。"""
    app = FastAPI()
    startup_manager = MagicMock()
    runtime = PluginApplicationRuntime(startup_manager=startup_manager)

    runtime.bind_app(app)

    assert app.state.plugin_application_runtime is runtime
    startup_manager.bind_app.assert_called_once_with(app)


def test_plugin_application_runtime_default_startup_manager_uses_runtime_port_only() -> None:
    """校验应用插件运行时默认不装配 management 具体适配器。"""
    runtime = PluginApplicationRuntime()

    assert isinstance(runtime.startup_manager.management_gateway, UnavailablePluginStartupManagementGateway)


def test_plugin_application_runtime_global_getter_uses_management_adapters() -> None:
    """校验应用全局插件运行时完成管理适配器装配。"""
    get_plugin_application_runtime.cache_clear()
    runtime = get_plugin_application_runtime()
    from plugins.core.management.service.startup_gateway import (  # noqa: PLC0415
        PluginManagementRouteStateGateway,
        PluginManagementStartupGateway,
    )

    assert isinstance(
        runtime.startup_manager.management_gateway,
        PluginManagementStartupGateway,
    )
    assert isinstance(
        runtime.startup_manager.route_state_gateway,
        PluginManagementRouteStateGateway,
    )
    assert isinstance(runtime.lifecycle_lock, RedisPluginLifecycleLock)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('enabled', 'status', 'installed_version', 'expected'),
    [
        ('0', 'installed', '1.0.0', True),
        ('0', 'error', '1.0.0', False),
        ('0', 'discovered', None, False),
        ('1', 'installed', '1.0.0', False),
    ],
)
async def test_management_route_state_gateway_uses_runnable_state(
    enabled: str,
    status: str,
    installed_version: str | None,
    expected: bool,
) -> None:
    """校验管理适配器与运行时注册表共享同一可运行状态不变量。"""
    from plugins.core.management.service.startup_gateway import PluginManagementRouteStateGateway  # noqa: PLC0415

    database_plugin = MagicMock(
        enabled=enabled,
        status=status,
        installed_version=installed_version,
    )
    with patch(
        'plugins.core.management.service.startup_gateway.PluginDao.get_plugin_by_id',
        new=AsyncMock(return_value=database_plugin),
    ):
        result = await PluginManagementRouteStateGateway.is_plugin_enabled(MagicMock(), 'demo')

    assert result is expected


def test_prepare_metadata_delegates_builtin_entity_import() -> None:
    """校验插件平台元数据准备委托启动协调器导入内置实体。"""
    app = FastAPI()
    startup_manager = MagicMock()
    runtime = PluginApplicationRuntime(startup_manager=startup_manager)

    runtime.prepare_metadata(app)

    startup_manager.bind_app.assert_called_once_with(app)
    startup_manager.import_builtin_entities.assert_called_once_with()


def test_startup_generation_uses_release_id_when_configured(tmp_path: Path) -> None:
    """校验显式发布标识为各 worker 提供稳定且隔离的启动代际。"""
    first = PluginStartupGenerationResolver(tmp_path, release_id='release-2026-07-27').resolve()
    second = PluginStartupGenerationResolver(tmp_path, release_id='release-2026-07-27').resolve()
    other = PluginStartupGenerationResolver(tmp_path, release_id='release-2026-07-28').resolve()

    assert first == second
    assert first != other


def test_startup_generation_changes_with_plugin_source(tmp_path: Path) -> None:
    """校验未配置发布标识时插件源码变化会产生新代际。"""
    plugin_file = tmp_path / 'plugins' / 'demo' / 'hooks.py'
    plugin_file.parent.mkdir(parents=True)
    plugin_file.write_text('VERSION = 1\n', encoding='utf-8')
    first = PluginStartupGenerationResolver(tmp_path, release_id='').resolve()

    plugin_file.write_text('VERSION = 2\n', encoding='utf-8')
    second = PluginStartupGenerationResolver(tmp_path, release_id='').resolve()

    assert first != second


@pytest.mark.asyncio
async def test_startup_writer_creates_plugin_tables_installs_resources_and_marks_ready() -> None:
    """校验启动写入 worker 会执行插件二次建表、安装资源并标记 ready。"""
    redis = FakeRedis()
    app = build_app(redis)
    startup_manager = MagicMock()
    startup_manager.prepare_enabled_plugins = AsyncMock()
    startup_manager.activate_enabled_plugins = AsyncMock()
    create_tables = AsyncMock()
    lifecycle_lock = FakeLifecycleLock(acquired=True)
    runtime = PluginApplicationRuntime(
        startup_manager=startup_manager,
        lifecycle_lock=lifecycle_lock,
        startup_generation='release-1',
    )

    with patch('plugins.core.runtime.application.logger') as mocked_logger:
        await runtime.startup(app, create_tables=create_tables)

    ready_key = runtime.build_ready_key('release-1')
    assert ready_key in redis.deleted_keys
    assert lifecycle_lock.calls == [('__runtime__', 'startup:release-1')]
    assert app.state.plugin_startup_write_enabled is True
    startup_manager.prepare_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=True)
    create_tables.assert_awaited_once_with()
    startup_manager.activate_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=True)
    assert json.loads(redis.values[ready_key]) == {'generation': 'release-1', 'status': 'success'}
    assert redis.expires[ready_key] == LockConstant.PLUGIN_STARTUP_READY_EXPIRE_SECONDS
    mocked_logger.bind.assert_any_call(
        startup_generation='release-1',
        plugin_startup_role='writer',
        ready_status='initializing',
    )
    mocked_logger.bind.assert_any_call(
        startup_generation='release-1',
        plugin_startup_role='writer',
        ready_status='success',
    )
    mocked_logger.bind.return_value.info.assert_any_call(
        '✅ 插件运行时启动完成：role=writer，generation=release-，enabled=none'
    )


@pytest.mark.asyncio
async def test_mark_startup_ready_warns_when_dependency_failed_plugins_were_isolated() -> None:
    """校验存在依赖失败插件时 ready 日志明确说明隔离结果。"""
    redis = FakeRedis()
    app = build_app(redis)
    app.state.plugin_dependency_failed_plugin_ids = {'demo', 'ai'}
    runtime = PluginApplicationRuntime(startup_manager=MagicMock(), startup_generation='release-1')

    with patch('plugins.core.runtime.application.logger') as mocked_logger:
        await runtime.mark_startup_ready(app)

    assert json.loads(redis.values[runtime.build_ready_key('release-1')]) == {
        'generation': 'release-1',
        'status': 'success',
    }
    mocked_logger.bind.assert_called_once_with(
        startup_generation='release-1',
        plugin_startup_role='writer',
        ready_status='success',
    )
    bound_logger = mocked_logger.bind.return_value
    bound_logger.warning.assert_called_once_with('⚠️ 插件启动协调已完成，依赖检查失败插件已隔离：ai、demo')
    bound_logger.info.assert_not_called()


@pytest.mark.asyncio
async def test_startup_reader_waits_ready_then_activates_without_writes() -> None:
    """校验非启动写入 worker 等待 ready 后只做本地激活。"""
    ready_key = f'{LockConstant.PLUGIN_STARTUP_READY_KEY}:release-1'
    redis = FakeRedis(
        {
            ready_key: json.dumps({'generation': 'release-1', 'status': 'success'}),
        }
    )
    app = build_app(redis)
    calls = []
    startup_manager = MagicMock()
    startup_manager.prepare_enabled_plugins = AsyncMock(side_effect=lambda *args, **kwargs: calls.append('prepare'))
    startup_manager.activate_enabled_plugins = AsyncMock()
    create_tables = AsyncMock()
    lifecycle_lock = FakeLifecycleLock(acquired=False)
    runtime = PluginApplicationRuntime(
        startup_manager=startup_manager,
        lifecycle_lock=lifecycle_lock,
        startup_generation='release-1',
    )

    with patch('plugins.core.runtime.application.logger') as mocked_logger:
        await runtime.startup(app, create_tables=create_tables)

    assert calls == ['prepare']
    assert lifecycle_lock.calls == []
    assert app.state.plugin_startup_write_enabled is False
    startup_manager.prepare_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=False)
    create_tables.assert_not_awaited()
    startup_manager.activate_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=False)
    mocked_logger.bind.assert_any_call(
        startup_generation='release-1',
        plugin_startup_role='reader',
        ready_status='success',
    )
    mocked_logger.bind.assert_any_call(
        startup_generation='release-1',
        plugin_startup_role='reader',
        ready_status='success',
        plugin_install_lifecycle='skipped',
        plugin_resource_sync='skipped',
        plugin_entity_table_sync='skipped',
    )
    mocked_logger.bind.return_value.info.assert_any_call(READER_GLOBAL_WRITE_SKIP_MESSAGE)
    mocked_logger.bind.return_value.info.assert_any_call(
        '✅ 插件运行时启动完成：role=reader，generation=release-，enabled=none'
    )


@pytest.mark.asyncio
async def test_stale_ready_marker_does_not_skip_missing_default_plugin_install() -> None:
    """校验数据库缺少默认插件状态时会忽略同代际旧 ready 标记并重新执行写入。"""
    ready_key = f'{LockConstant.PLUGIN_STARTUP_READY_KEY}:release-1'
    redis = FakeRedis(
        {
            ready_key: json.dumps({'generation': 'release-1', 'status': 'success'}),
        }
    )
    app = build_app(redis)
    startup_manager = PluginRuntimeStartupManager(MagicMock())
    startup_manager.requires_startup_write = AsyncMock(return_value=True)
    startup_manager.prepare_enabled_plugins = AsyncMock()
    startup_manager.activate_enabled_plugins = AsyncMock()
    create_tables = AsyncMock()
    lifecycle_lock = FakeLifecycleLock(acquired=True)
    runtime = PluginApplicationRuntime(
        startup_manager=startup_manager,
        lifecycle_lock=lifecycle_lock,
        startup_generation='release-1',
    )

    with patch('plugins.core.runtime.application.logger') as mocked_logger:
        await runtime.startup(app, create_tables=create_tables)

    assert startup_manager.requires_startup_write.await_count == EXPECTED_REQUIRED_WRITE_CHECK_COUNT
    assert lifecycle_lock.calls == [('__runtime__', 'startup:release-1')]
    assert app.state.plugin_startup_write_enabled is True
    startup_manager.prepare_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=True)
    create_tables.assert_awaited_once_with()
    startup_manager.activate_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=True)
    assert json.loads(redis.values[ready_key]) == {'generation': 'release-1', 'status': 'success'}
    assert call(READER_GLOBAL_WRITE_SKIP_MESSAGE) not in mocked_logger.bind.return_value.info.call_args_list
    mocked_logger.bind.assert_any_call(
        startup_generation='release-1',
        plugin_startup_role='reader',
        ready_status='success',
        stale_ready_ignored=True,
        startup_write_required=True,
        startup_write_reason='missing_default_plugin_state',
    )
    mocked_logger.bind.return_value.warning.assert_called_once_with(
        '⚠️ 数据库默认插件状态缺失，忽略当前代际旧 ready 标记'
    )


@pytest.mark.asyncio
async def test_startup_ignores_ready_state_from_previous_generation() -> None:
    """校验滚动发布不会复用上一代实例的 ready 状态。"""
    old_ready_key = f'{LockConstant.PLUGIN_STARTUP_READY_KEY}:release-old'
    redis = FakeRedis(
        {
            old_ready_key: json.dumps({'generation': 'release-old', 'status': 'success'}),
        }
    )
    app = build_app(redis)
    startup_manager = MagicMock()
    startup_manager.prepare_enabled_plugins = AsyncMock()
    startup_manager.activate_enabled_plugins = AsyncMock()
    create_tables = AsyncMock()
    lifecycle_lock = FakeLifecycleLock(acquired=True)
    runtime = PluginApplicationRuntime(
        startup_manager=startup_manager,
        lifecycle_lock=lifecycle_lock,
        startup_generation='release-new',
    )

    await runtime.startup(app, create_tables=create_tables)

    assert lifecycle_lock.calls == [('__runtime__', 'startup:release-new')]
    create_tables.assert_awaited_once_with()
    assert runtime.build_ready_key('release-new') in redis.values


@pytest.mark.asyncio
async def test_startup_marks_generation_failed_for_waiting_workers() -> None:
    """校验启动写入失败会发布短期失败状态，避免其他 worker 静默等待。"""
    redis = FakeRedis()
    app = build_app(redis)
    startup_manager = MagicMock()
    startup_manager.prepare_enabled_plugins = AsyncMock(side_effect=RuntimeError('broken migration'))
    runtime = PluginApplicationRuntime(
        startup_manager=startup_manager,
        lifecycle_lock=FakeLifecycleLock(acquired=True),
        startup_generation='release-1',
    )

    with (
        patch('plugins.core.runtime.application.logger') as mocked_logger,
        pytest.raises(RuntimeError, match='broken migration'),
    ):
        await runtime.startup(app, create_tables=AsyncMock())

    ready_key = runtime.build_ready_key('release-1')
    assert json.loads(redis.values[ready_key]) == {
        'generation': 'release-1',
        'status': 'failed',
        'error': 'broken migration',
    }
    assert redis.expires[ready_key] == LockConstant.PLUGIN_STARTUP_FAILED_EXPIRE_SECONDS
    mocked_logger.bind.assert_any_call(
        startup_generation='release-1',
        plugin_startup_role='writer',
        ready_status='failed',
    )
    mocked_logger.bind.return_value.exception.assert_called_once_with(
        '❌ 插件全局启动资源同步失败，已写入 failed marker'
    )


@pytest.mark.asyncio
async def test_startup_times_out_when_generation_writer_not_ready() -> None:
    """校验非启动写入 worker 等待插件 ready 超时会失败。"""
    redis = FakeRedis()
    app = build_app(redis)
    runtime = PluginApplicationRuntime(
        startup_manager=MagicMock(),
        lifecycle_lock=FakeLifecycleLock(acquired=False),
        startup_generation='release-1',
        ready_wait_timeout_seconds=0,
        ready_wait_interval_seconds=0,
    )

    with pytest.raises(TimeoutError, match='等待插件启动代际 release-1 ready 超时'):
        await runtime.startup(app, create_tables=AsyncMock())
