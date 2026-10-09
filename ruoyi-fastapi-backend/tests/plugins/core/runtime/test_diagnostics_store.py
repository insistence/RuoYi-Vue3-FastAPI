import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from redis._parsers.encoders import Encoder
from redis.client import NEVER_DECODE

from plugins.core.runtime import diagnostics_store as module
from plugins.core.runtime.application import PluginApplicationRuntime
from plugins.core.runtime.diagnostics import PluginRuntimeDiagnostic, PluginRuntimeDiagnosticSnapshot
from plugins.core.runtime.diagnostics_query import build_runtime_diagnostics
from plugins.core.runtime.diagnostics_store import (
    DIAGNOSTICS_TTL_SECONDS,
    PluginDiagnosticsReporter,
    diagnostics_namespace,
    read_runtime_diagnostics,
)
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from plugins.core.runtime.route_guard import UnavailablePluginRouteStateGateway

NAMESPACE = diagnostics_namespace('test-environment:ready')


class DiagnosticsRedis:
    """提供隔离的快照读写，并记录查询过程中是否出现写入。"""

    def __init__(self) -> None:
        self.values: dict[str | bytes, bytes] = {}
        self.expirations: dict[str, int] = {}
        self.writes = 0
        self.fail = False
        self.encoder = Encoder('utf-8', 'strict', decode_responses=True)

    async def set(self, key: str, value: bytes, *, ex: int) -> None:
        if self.fail:
            raise ConnectionError('private-diagnostic-password')
        self.writes += 1
        self.values[key] = value
        self.expirations[key] = ex

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def scan_iter(self, *, match: str, count: int, **options: object) -> AsyncIterator[str | bytes]:
        if self.fail:
            raise ConnectionError('private-diagnostic-password')
        for key in self.values:
            raw_key = key.encode() if isinstance(key, str) else key
            if fnmatchcase(raw_key, match.encode()):
                yield raw_key if NEVER_DECODE in options else self.encoder.decode(raw_key)

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        return [self.values.get(key) for key in keys]

    async def execute_command(self, command: str, *keys: str, **options: object) -> list[bytes | str | None]:
        assert command == 'MGET'
        values = await self.mget(list(keys))
        return [value if value is None or NEVER_DECODE in options else self.encoder.decode(value) for value in values]


def snapshot(worker_id: str, *, pending: int = 0, collected_at: float | None = None) -> PluginRuntimeDiagnosticSnapshot:
    """构造真正观测到零插件的宿主快照，不添加虚假的插件计数。"""
    return PluginRuntimeDiagnosticSnapshot(
        worker_id=worker_id,
        collected_at=time.time() if collected_at is None else collected_at,
        plugins=[],
        worker_pending_cleanup_tasks=pending,
        dropped_plugins=0,
    )


def store(redis: DiagnosticsRedis, value: PluginRuntimeDiagnosticSnapshot, namespace: str = NAMESPACE) -> None:
    """放入独立序列化快照以模拟另一个 worker 的定期发布。"""
    redis.values[f'{namespace}:{value.worker_id}'] = value.model_dump_json(by_alias=True).encode()


@pytest.mark.asyncio
async def test_reader_never_fabricates_local_worker_or_writes_and_isolates_namespace() -> None:
    redis = DiagnosticsRedis()
    store(redis, snapshot('a' * 32))
    store(redis, snapshot('b' * 32), diagnostics_namespace('other-environment'))
    redis.values['test-environment:ready:metrics:legacy'] = b'old-schema-unchanged'
    result = await read_runtime_diagnostics(redis, NAMESPACE, 'task_demo')
    assert result['scope'] == 'reporting_workers'
    assert result['currentWorkerId'] is None
    assert result['observedWorkers'] == 1
    assert result['workers'][0]['workerId'] == 'a' * 32
    assert result['workers'][0]['plugins'] == []
    assert result['workers'][0]['source'] == 'redis'
    assert redis.writes == 0
    unavailable = await read_runtime_diagnostics(None, NAMESPACE)
    assert unavailable['scope'] == 'unavailable'
    assert unavailable['workers'] == []


@pytest.mark.asyncio
async def test_plugin_filter_retains_worker_scope_without_other_plugin_details() -> None:
    redis = DiagnosticsRedis()
    value = snapshot('a' * 32, pending=3)
    value.plugins = [
        PluginRuntimeDiagnostic(plugin_id=plugin_id, version='1.0.0', active=True, ready=True, closing=False)
        for plugin_id in ('task_demo', 'private_demo')
    ]
    store(redis, value)
    result = await read_runtime_diagnostics(redis, NAMESPACE, 'task_demo')
    assert [plugin['pluginId'] for plugin in result['workers'][0]['plugins']] == ['task_demo']
    assert result['workers'][0]['workerPendingCleanupTasks'] == value.worker_pending_cleanup_tasks
    assert 'private_demo' not in json.dumps(result)
    assert (await read_runtime_diagnostics(redis, NAMESPACE, 'unknown_demo'))['workers'][0]['plugins'] == []


@pytest.mark.asyncio
async def test_local_real_snapshot_replaces_own_redis_copy_and_failure_is_explicit() -> None:
    redis = DiagnosticsRedis()
    store(redis, snapshot('a' * 32, pending=9))
    store(redis, snapshot('b' * 32, pending=2))
    reporter = PluginDiagnosticsReporter(lambda: snapshot('a' * 32, pending=1), 'a' * 32)
    reporter.redis, reporter.namespace = redis, NAMESPACE
    result = await reporter.read()
    expected_workers = 2
    assert len(result['workers']) == expected_workers
    assert result['workers'][0]['workerPendingCleanupTasks'] == 1
    assert result['workers'][0]['source'] == 'current_worker'
    redis.fail = True
    result = await reporter.read()
    assert result['scope'] == 'current_worker'
    assert result['clusterAvailable'] is False
    assert result['observedWorkers'] == 1
    assert 'private-diagnostic-password' not in json.dumps(result)
    assert (await read_runtime_diagnostics(redis, NAMESPACE))['workers'] == []


@pytest.mark.asyncio
async def test_stale_future_invalid_and_identity_conflicts_never_supply_counters() -> None:
    redis = DiagnosticsRedis()
    store(redis, snapshot('a' * 32, collected_at=time.time() - DIAGNOSTICS_TTL_SECONDS - 1))
    store(redis, snapshot('b' * 32, collected_at=time.time() + 100))
    redis.values[f'{NAMESPACE}:{"c" * 32}'] = b'{private-malformed-content'
    redis.values[f'{NAMESPACE}:{"d" * 32}'] = snapshot('e' * 32).model_dump_json().encode()
    newer = snapshot('f' * 32).model_dump(by_alias=True)
    newer['schemaVersion'] = 99
    redis.values[f'{NAMESPACE}:{"f" * 32}'] = json.dumps(newer).encode()
    result = await read_runtime_diagnostics(redis, NAMESPACE)
    assert result['workers'] == []
    assert result['staleWorkerIds'] == ['a' * 32, 'b' * 32]
    assert result['invalidWorkerIds'] == ['c' * 32, 'd' * 32, 'f' * 32]
    assert 'private-malformed-content' not in json.dumps(result)


@pytest.mark.asyncio
async def test_invalid_utf8_key_and_value_do_not_hide_healthy_workers() -> None:
    redis = DiagnosticsRedis()
    store(redis, snapshot('a' * 32))
    redis.values[f'{NAMESPACE}:{"b" * 32}'] = b'\xff'
    redis.values[NAMESPACE.encode() + b':\xff'] = b'invalid-key'
    result = await read_runtime_diagnostics(redis, NAMESPACE)
    assert result['clusterAvailable'] is True
    assert result['observedWorkers'] == 1
    assert result['workers'][0]['workerId'] == 'a' * 32
    expected_invalid = 2
    assert result['invalidSnapshots'] == expected_invalid
    assert result['invalidWorkerIds'] == ['b' * 32]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'missing_field',
    [
        'schemaVersion',
        'workerPendingCleanupTasks',
        'plugins',
        'plugins.0.activeJobs',
        'plugins.0.connections.sse',
        'plugins.0.pendingConnectionTasks',
        'plugins.0.config.lastReadAt',
    ],
)
async def test_incomplete_remote_snapshot_cannot_supply_default_zero_counters(missing_field: str) -> None:
    redis = DiagnosticsRedis()
    store(redis, snapshot('a' * 32))
    incomplete = snapshot('b' * 32)
    incomplete.plugins = [
        PluginRuntimeDiagnostic(plugin_id='task_demo', version='1.0.0', active=True, ready=True, closing=False)
    ]
    payload = incomplete.model_dump(by_alias=True)
    parts = missing_field.split('.')
    node = payload
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    node.pop(parts[-1])
    redis.values[f'{NAMESPACE}:{"b" * 32}'] = json.dumps(payload).encode()
    result = await read_runtime_diagnostics(redis, NAMESPACE, 'task_demo')
    assert result['invalidWorkerIds'] == ['b' * 32]
    assert result['observedWorkers'] == 1
    assert result['workers'][0]['workerId'] == 'a' * 32
    assert result['workers'][0]['plugins'] == []


@pytest.mark.asyncio
async def test_size_and_worker_limits_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = DiagnosticsRedis()
    monkeypatch.setattr(module, 'MAX_DIAGNOSTICS_SNAPSHOT_BYTES', 10)
    store(redis, snapshot('a' * 32))
    assert (await read_runtime_diagnostics(redis, NAMESPACE))['invalidWorkerIds'] == ['a' * 32]
    monkeypatch.setattr(module, 'MAX_DIAGNOSTICS_SNAPSHOT_BYTES', 512 * 1024)
    monkeypatch.setattr(module, 'MAX_DIAGNOSTICS_WORKERS', 1)
    store(redis, snapshot('b' * 32))
    result = await read_runtime_diagnostics(redis, NAMESPACE)
    assert result['workerLimitReached'] is True
    assert result['observedWorkers'] == 1


@pytest.mark.asyncio
async def test_expired_during_read_is_unknown_and_io_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = DiagnosticsRedis()
    store(redis, snapshot('a' * 32))
    with patch.object(redis, 'mget', AsyncMock(return_value=[None])):
        result = await read_runtime_diagnostics(redis, NAMESPACE)
    assert result['staleWorkerIds'] == ['a' * 32]
    assert result['workers'] == []
    monkeypatch.setattr(module, 'DIAGNOSTICS_IO_TIMEOUT_SECONDS', 0.01)

    async def blocked_read(keys: list[str]) -> list[bytes | None]:
        await asyncio.Event().wait()
        return []

    with patch.object(redis, 'mget', blocked_read):
        result = await read_runtime_diagnostics(redis, NAMESPACE)
    assert result['scope'] == 'unavailable'
    assert result['workers'] == []


@pytest.mark.asyncio
async def test_publication_failure_recovers_and_stop_only_deletes_owned_snapshot() -> None:
    redis = DiagnosticsRedis()
    reporter = PluginDiagnosticsReporter(lambda: snapshot('a' * 32), 'a' * 32)
    reporter.start(redis, NAMESPACE)
    try:
        redis.fail = True
        await reporter.publish()
        assert reporter.publication_failed is True
        redis.fail = False
        await reporter.publish()
        assert reporter.publication_failed is False
        assert redis.expirations[reporter.key] == DIAGNOSTICS_TTL_SECONDS
        store(redis, snapshot('b' * 32))
        redis.values['business:key'] = b'unchanged'
    finally:
        await reporter.stop()
    assert reporter.task is None
    assert set(redis.values) == {f'{NAMESPACE}:{"b" * 32}', 'business:key'}


@pytest.mark.asyncio
async def test_wrong_local_identity_cannot_be_published_or_appear_as_current_worker() -> None:
    redis = DiagnosticsRedis()
    reporter = PluginDiagnosticsReporter(lambda: snapshot('b' * 32), 'a' * 32)
    reporter.redis, reporter.namespace = redis, NAMESPACE
    await reporter.publish()
    assert reporter.publication_failed is True
    assert not redis.values
    result = await reporter.read()
    assert result['localSnapshotAvailable'] is False
    assert result['workers'] == []


@pytest.mark.asyncio
async def test_application_owns_diagnostics_lifecycle_even_when_shutdown_fails() -> None:
    redis = DiagnosticsRedis()
    app = FastAPI()
    app.state.redis = redis
    explicit = ExplicitPluginRuntime(UnavailablePluginRouteStateGateway())
    app.state.plugin_explicit_runtime = explicit
    manager = MagicMock()
    manager.shutdown = AsyncMock(side_effect=RuntimeError('shutdown failed'))
    runtime = PluginApplicationRuntime(startup_manager=manager, ready_key='isolated:ready')
    with patch.object(runtime, '_startup_coordinated', AsyncMock()):
        await runtime.startup(app, create_tables=AsyncMock())
    reporter = app.state.plugin_diagnostics_reporter
    await reporter.publish()
    assert reporter.worker_id == explicit.metrics.worker_id
    assert reporter.namespace == diagnostics_namespace('isolated:ready')
    assert reporter.key in redis.values
    try:
        with pytest.raises(RuntimeError, match='shutdown failed'):
            await asyncio.wait_for(runtime.shutdown(app), timeout=3)
        assert reporter.task is None
        assert reporter.key not in redis.values
    finally:
        await explicit.shutdown()


@pytest.mark.asyncio
async def test_empty_runtime_uses_release_worker_identity_without_fabricating_missing_worker() -> None:
    app = FastAPI()
    explicit = ExplicitPluginRuntime(UnavailablePluginRouteStateGateway())
    app.state.plugin_explicit_runtime = explicit
    worker_id = 'b' * 32
    worker = SimpleNamespace(
        worker_id=worker_id,
        start=AsyncMock(),
        ready=AsyncMock(),
        stop=AsyncMock(),
        generation=lambda base: 'isolated-generation',
    )
    manager = MagicMock()
    manager.shutdown = AsyncMock()
    runtime = PluginApplicationRuntime(startup_manager=manager, release_worker=worker, startup_generation='test')
    with patch.object(runtime, '_startup_coordinated', AsyncMock()):
        await runtime.startup(app, create_tables=AsyncMock())
    try:
        report = await app.state.plugin_diagnostics_reporter.read('task_demo')
        assert explicit.metrics.worker_id == worker_id
        assert report['currentWorkerId'] == worker_id
        now = time.time()
        release = {
            'supported': True,
            'available': True,
            'releases': [{'pluginId': 'task_demo', 'expectedWorkers': 1}],
            'workers': [
                {
                    'workerId': worker_id,
                    'pluginId': '__runtime__',
                    'state': 'ready',
                    'heartbeatTime': datetime.fromtimestamp(now - 1, timezone.utc).isoformat(),
                }
            ],
        }
        result = build_runtime_diagnostics('task_demo', report, release, now=now)
        assert result['missingWorkers'] == 0
        assert len(result['workers']) == 1
        assert result['workers'][0]['observation'] == 'not_loaded'
        assert result['workers'][0]['actual'] is None
    finally:
        await runtime.shutdown(app)
