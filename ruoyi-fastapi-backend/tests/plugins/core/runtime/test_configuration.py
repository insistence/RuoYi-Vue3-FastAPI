import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.env import JwtConfig
from plugins.core.management.entity.do.models import SysPluginConfig
from plugins.core.management.entity.vo.schemas import PluginConfigUpdateModel
from plugins.core.management.service.service import PluginService
from plugins.core.manifest.schema import PluginConfigItemManifest
from plugins.core.runtime.configuration import (
    PluginConfigObservation,
    PluginConfigReader,
    build_config_status,
    config_revision,
)
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from plugins.core.runtime.metrics import PluginRuntimeMetrics
from plugins.core.runtime.metrics_store import PluginMetricsReporter
from plugins.core.runtime.startup import PluginRuntimeStartupManager
from plugins.core.sdk import PluginConfigSnapshot, PluginHostContext
from tests.plugins.core.runtime.test_explicit import clear_modules, write_plugin  # noqa: F401
from tests.plugins.core.runtime.test_metrics_store import MetricsRedis


@pytest_asyncio.fixture
async def config_sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """使用独立 SQLite 验证配置落库、解密和重启读取。"""
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "config.sqlite"}')
    async with engine.begin() as db:
        await db.run_sync(SysPluginConfig.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def test_revision_is_stable_secret_sensitive_and_bound_to_host_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """相同配置顺序不影响版本，密文配置变动和宿主密钥变化会改变版本。"""
    first = config_revision('config_demo', {'secret': 'first', 'label': 'value'})
    assert first == config_revision('config_demo', {'label': 'value', 'secret': 'first'})
    assert first != config_revision('config_demo', {'secret': 'second', 'label': 'value'})
    assert first != config_revision('other_demo', {'secret': 'first', 'label': 'value'})
    monkeypatch.setattr(JwtConfig, 'jwt_secret_key', 'different-test-key')
    assert first != config_revision('config_demo', {'secret': 'first', 'label': 'value'})


def test_snapshot_is_independent_and_hides_values_in_repr() -> None:
    """调用方修改原始数据或快照嵌套值不会污染另一个快照。"""
    values = {'private': {'list': ['secret-value']}}
    snapshot = PluginConfigSnapshot(values, 'a' * 64)
    values['private']['list'].append('later')
    assert snapshot.values['private']['list'] == ['secret-value']
    with pytest.raises(TypeError):
        snapshot.values['private'] = None
    assert 'secret-value' not in repr(snapshot)


@pytest.mark.asyncio
async def test_missing_reader_fails_explicitly(tmp_path: Path) -> None:
    """手动构造的旧上下文不能伪装成已完成最新配置读取。"""
    with pytest.raises(RuntimeError, match='按需配置读取'):
        await PluginHostContext('config_demo', tmp_path).read_config()


@pytest.mark.asyncio
async def test_database_changes_dynamic_reads_and_restart_snapshots_remain_distinct(
    tmp_path: Path, config_sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实配置保存与解密改变按需读取，直到下一次启动才更新启动版本。"""
    plugin = write_plugin(tmp_path)
    discovered = plugin.discovered_plugin
    discovered.manifest.config.items = [
        PluginConfigItemManifest(key='greeting', default='before'),
        PluginConfigItemManifest(key='api_key', default='private-first', secret=True),
    ]
    monkeypatch.setattr('plugins.core.runtime.startup.DataSourceRegistry.session', config_sessions)
    app = FastAPI()
    runtime = ExplicitPluginRuntime(SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True)))
    initial = await PluginRuntimeStartupManager.load_explicit_plugin_config(plugin)
    runtime.prepare(plugin, app, startup_write_enabled=False, config_values=initial)
    await runtime.activate(plugin.plugin_id, app)
    host = runtime.loaded[plugin.plugin_id].host
    try:
        initial_revision = host.config_revision
        async with config_sessions() as db:
            await PluginService.update_plugin_config_services(
                db, discovered, PluginConfigUpdateModel(values={'greeting': 'after', 'api_key': 'private-second'})
            )
            await db.commit()
        latest = await host.read_config()
        assert dict(latest.values) == {'greeting': 'after', 'api_key': 'private-second'}
        assert latest.revision != initial_revision
        assert host.config['greeting'] == 'before'
        assert host.config_revision == initial_revision
        report = await runtime.metrics_reporter.read(plugin.plugin_id)
        assert 'private-first' not in json.dumps(report) and 'private-second' not in json.dumps(report)
        state = build_config_status(plugin.plugin_id, latest.revision, report)
        assert state['state'] == 'restart_required'
        assert state['scope'] == 'current_worker'
        assert state['workers'][0]['lastReadRevision'] == latest.revision
        assert state['workers'][0]['matchesDesired'] is False
        async with config_sessions() as db:
            masked = await PluginService.update_plugin_config_services(
                db, discovered, PluginConfigUpdateModel(values={'api_key': '******'})
            )
            await db.commit()
        assert next(item.value for item in masked if item.key == 'api_key') == '******'
        assert (await host.read_config()).revision == latest.revision
    finally:
        await runtime.shutdown()
    assert runtime.metrics.configurations[plugin.plugin_id].active is False
    restarted = ExplicitPluginRuntime(SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True)))
    restarted_app = FastAPI()
    restarted.prepare(
        plugin,
        restarted_app,
        startup_write_enabled=False,
        config_values=await PluginRuntimeStartupManager.load_explicit_plugin_config(plugin),
    )
    await restarted.activate(plugin.plugin_id, restarted_app)
    try:
        report = await restarted.metrics_reporter.read(plugin.plugin_id)
        state = build_config_status(plugin.plugin_id, latest.revision, report)
        assert state['state'] == 'observed_match'
        assert state['workers'][0]['startupRevision'] == latest.revision
        assert state['workers'][0]['lastReadRevision'] is None
    finally:
        await restarted.shutdown()


@pytest.mark.asyncio
async def test_remote_configuration_versions_do_not_claim_whole_cluster_activation() -> None:
    """旧进程配置、无配置上报的旧宿主和 Redis 故障均保留可观测范围。"""
    redis = MetricsRedis()
    reporters = []
    for worker_id, revision in [('a', 'a'), ('b', 'b'), ('c', None)]:
        metrics = PluginRuntimeMetrics(worker_id=worker_id * 32)
        metrics.register('config_demo', '1.0.0', None, None)
        if revision:
            metrics.configurations['config_demo'] = PluginConfigObservation(
                plugin_id='config_demo',
                version='1.0.0',
                active=True,
                startup_revision=revision * 64,
            )
        reporter = PluginMetricsReporter(metrics)
        reporter.start(redis, 'config-test:metrics')
        await reporter.publish()
        reporters.append(reporter)
    try:
        report = await reporters[0].read('config_demo')
        state = build_config_status('config_demo', 'a' * 64, report)
        assert state['state'] == 'restart_required'
        assert state['matchedWorkers'] == state['pendingWorkers'] == 1
        assert state['unknownWorkers'] == 1
        assert state['scope'] == 'reporting_workers'
        redis.fail = True
        local = build_config_status('config_demo', 'a' * 64, await reporters[0].read('config_demo'))
        assert local['state'] == 'observed_match' and local['scope'] == 'current_worker'
        assert local['clusterAvailable'] is False
        unknown = build_config_status('config_demo', 'a' * 64, {'scope': 'unavailable'})
        assert unknown['state'] == 'unobserved'
    finally:
        redis.fail = False
        for reporter in reporters:
            await reporter.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled', [False, True])
async def test_failed_or_cancelled_read_keeps_previous_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancelled: bool
) -> None:
    """读取失败或取消时关闭独立会话，且不能上报新的读取版本。"""
    entered = asyncio.Event()
    closed = []

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        try:
            yield object()
        finally:
            closed.append(True)

    async def read(*args: object, **kwargs: object) -> list:
        entered.set()
        if cancelled:
            await asyncio.Event().wait()
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(PluginService, 'get_plugin_config_services', read)
    plugin = write_plugin(tmp_path).discovered_plugin
    observation = PluginConfigObservation(plugin_id=plugin.manifest.id, version='1.0.0', startup_revision='a' * 64)
    reader = PluginConfigReader(plugin, session, observation)
    task = asyncio.create_task(reader.read())
    await asyncio.wait_for(entered.wait(), timeout=2)
    if cancelled:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
        await task
    assert closed == [True]
    assert observation.last_read_revision is observation.last_read_at is None
