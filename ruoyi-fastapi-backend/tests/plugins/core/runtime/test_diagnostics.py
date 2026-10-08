import asyncio
import json
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from plugins.core.discovery.registry import RegisteredPlugin
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.schema import PluginManifestFactory
from plugins.core.runtime.asgi import PluginGatewayASGI, PluginLifespanManager
from plugins.core.runtime.configuration import PluginConfigObservation
from plugins.core.runtime.diagnostics import PluginRuntimeDiagnostic, PluginRuntimeDiagnosticSnapshot
from plugins.core.runtime.explicit import ExplicitPluginRuntime, LoadedExplicitPlugin
from plugins.core.runtime.health import PluginHealthChecker, PluginHealthResult
from plugins.core.runtime.task_cleanup import cancel_plugin_tasks, pending_plugin_tasks
from plugins.core.sdk import PluginDefinition, PluginHostContext, PluginRequestContext


def diagnostic_runtime(tmp_path: Path, plugin_id: str = 'diagnostic_demo') -> ExplicitPluginRuntime:
    """
    构造已加载且未执行回调的真实运行时容器。

    :param tmp_path: 隔离测试资源目录
    :param plugin_id: 测试插件标识
    :return: 包含显式定义、实际制品身份及安全配置观测的运行时
    """
    manifest = PluginManifestFactory.create(
        {
            'manifestVersion': 2,
            'id': plugin_id,
            'name': 'Diagnostic demo',
            'version': '1.2.0',
            'backend': {'module': f'plugins.{plugin_id}', 'entrypoint': f'plugins.{plugin_id}:create_plugin'},
        }
    )
    discovered = DiscoveredPlugin(manifest, tmp_path, tmp_path / 'plugin.yaml', 'a' * 64, 'b' * 32)
    host = PluginHostContext(
        plugin_id,
        tmp_path,
        config={'password': 'private-config-value'},
        config_revision='c' * 64,
        config_reader=AsyncMock(side_effect=AssertionError('sampling must not read configuration')),
    )
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    runtime.loaded[plugin_id] = LoadedExplicitPlugin(
        RegisteredPlugin(discovered, None, True, 'installed'), host, PluginDefinition()
    )
    runtime.metrics.register(plugin_id, manifest.version, discovered.artifact_digest, discovered.artifact_generation)
    runtime.metrics.configurations[plugin_id] = PluginConfigObservation(
        plugin_id=plugin_id,
        version=manifest.version,
        digest=discovered.artifact_digest,
        generation=discovered.artifact_generation,
        startup_revision='c' * 64,
        last_read_revision='d' * 64,
        last_read_at=123.0,
    )
    return runtime


def test_snapshot_copies_actual_identity_config_and_most_recent_error(tmp_path: Path) -> None:
    """快照使用实际加载身份且不保留配置明文、回调或后续可变对象。"""
    runtime = diagnostic_runtime(tmp_path)
    loaded = runtime.loaded['diagnostic_demo']
    loaded.active = True
    runtime.metrics.identities['diagnostic_demo']['digest'] = 'e' * 64
    runtime.metrics.identities['diagnostic_demo']['generation'] = 'f' * 32
    first = runtime.metrics.begin('diagnostic_demo', 'http', 'old-request')
    first.finish('failed', error_type='OldError')
    first.series.last_error_at = 124.0
    second = runtime.metrics.begin('diagnostic_demo', 'job:refresh', 'latest-request')
    second.finish('failed', error_type='NewError')
    second.series.last_error_at = 125.0
    snapshot = runtime.diagnostic_snapshot()
    plugin = snapshot.plugins[0]
    assert snapshot.worker_id == runtime.metrics.worker_id
    assert (plugin.version, plugin.digest, plugin.generation) == ('1.2.0', 'a' * 64, 'b' * 32)
    assert plugin.active and plugin.ready and not plugin.closing
    assert plugin.lifespan is None
    assert plugin.activation_health.status == 'unknown'
    assert plugin.activation_health.checked_at is None
    assert plugin.last_error.model_dump(by_alias=True) == {
        'errorType': 'NewError',
        'requestId': 'latest-request',
        'at': 125.0,
    }
    assert plugin.config.startup_revision == 'c' * 64
    assert plugin.config.last_read_revision == 'd' * 64
    assert 'private-config-value' not in snapshot.model_dump_json()
    loaded.host.config_reader.assert_not_called()
    runtime.metrics.configurations['diagnostic_demo'].last_read_revision = 'e' * 64
    runtime.loaded['diagnostic_demo'].activation_health.status = 'unhealthy'
    second.series.last_error_type = 'LaterError'
    assert plugin.config.last_read_revision == 'd' * 64
    assert plugin.activation_health.status == 'unknown'
    assert plugin.last_error.error_type == 'NewError'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('raw_status', 'ok', 'expected'),
    [
        ('healthy', True, 'healthy'),
        ('private-status', False, 'unhealthy'),
        ('unknown', False, 'unhealthy'),
        ('error', True, 'healthy'),
        ('timeout', False, 'timeout'),
        ('error', False, 'error'),
    ],
)
async def test_activation_health_is_cached_without_rechecking_or_exposing_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_status: str, ok: bool, expected: str
) -> None:
    """采样保留激活检查时间与固定状态，任意插件详情和异常正文不会进入快照。"""
    runtime = diagnostic_runtime(tmp_path)
    loaded = runtime.loaded['diagnostic_demo']
    loaded.plugin.discovered_plugin.manifest.backend.health.checker = 'plugins.diagnostic_demo:health'
    result = PluginHealthResult(
        'diagnostic_demo',
        ok,
        raw_status,
        'private-health-message',
        'plugins.diagnostic_demo:health',
        3.5,
        {'secret': 'private-health-details'},
        'private-exception-body',
    )
    checker = AsyncMock(return_value=result)
    monkeypatch.setattr(PluginHealthChecker, 'check', checker)
    if ok:
        await runtime._check_health(loaded, FastAPI())
    else:
        with pytest.raises(RuntimeError, match='健康检查'):
            await runtime._check_health(loaded, FastAPI())
    first = runtime.diagnostic_snapshot().plugins[0].activation_health
    second = runtime.diagnostic_snapshot().plugins[0].activation_health
    assert first == second
    assert first.status == expected
    assert first.checked_at is not None
    assert first.duration_ms == result.duration_ms
    checker.assert_awaited_once()
    payload = runtime.diagnostic_snapshot().model_dump_json()
    for private in ('private-health-message', 'private-health-details', 'private-exception-body', 'private-status'):
        assert private not in payload


@pytest.mark.asyncio
async def test_real_lifespan_exit_changes_readiness_without_marking_pending_cancellation(tmp_path: Path) -> None:
    """正常 lifespan 任务计为存活，意外退出立即失去就绪且不虚构取消超时。"""
    runtime = diagnostic_runtime(tmp_path)
    loaded = runtime.loaded['diagnostic_demo']
    release = asyncio.Event()

    async def application(scope: dict, receive: object, send: object) -> None:
        await receive()
        await send({'type': 'lifespan.startup.complete'})
        await release.wait()

    loaded.lifespan = PluginLifespanManager(application, timeout=0.05, cancel_timeout=0.01)
    try:
        await loaded.lifespan.startup()
        loaded.active = True
        running = runtime.diagnostic_snapshot()
        assert running.plugins[0].lifespan.task_active
        assert running.plugins[0].ready
        assert running.worker_pending_cleanup_tasks == 0
        release.set()
        await asyncio.wait({loaded.lifespan._task}, timeout=1)
        stopped = runtime.diagnostic_snapshot()
        assert not stopped.plugins[0].lifespan.task_active
        assert not stopped.plugins[0].ready
        assert stopped.worker_pending_cleanup_tasks == 0
    finally:
        release.set()
        with suppress(RuntimeError):
            await loaded.lifespan.shutdown()


@pytest.mark.asyncio
async def test_live_connection_counts_do_not_include_ordinary_http_or_auth_data(tmp_path: Path) -> None:
    """真实 SSE、WebSocket 的打开和关闭改变计数，普通响应及身份内容不进入连接快照。"""
    runtime = diagnostic_runtime(tmp_path)
    loaded = runtime.loaded['diagnostic_demo']
    loaded.active = True
    opened = {'http': asyncio.Event(), 'websocket': asyncio.Event()}
    release = asyncio.Event()

    async def authorize(scope: dict) -> PluginRequestContext:
        return PluginRequestContext(loaded.host, user=SimpleNamespace(private='private-user'))

    async def application(scope: dict, receive: object, send: object) -> None:
        if scope['path'] == '/ordinary':
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'private-response'})
            return
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.accept'})
        else:
            await send(
                {'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'text/event-stream')]}
            )
        opened[scope['type']].set()
        await release.wait()

    async def receive() -> dict:
        await asyncio.Event().wait()
        return {}

    async def send(message: dict) -> None:
        return None

    loaded.lifespan = PluginLifespanManager(application, managed=False)
    await loaded.lifespan.startup()
    loaded.gateway = PluginGatewayASGI(application, loaded.lifespan, authorize, recheck_interval=60)
    requests = []
    try:
        for kind in ('http', 'websocket'):
            scope = {'type': kind, 'path': '/private-path', 'headers': [(b'authorization', b'private-token')]}
            requests.append(asyncio.create_task(loaded.gateway(scope, receive, send)))
        await asyncio.gather(*(asyncio.wait_for(event.wait(), timeout=1) for event in opened.values()))
        await loaded.gateway({'type': 'http', 'path': '/ordinary', 'headers': []}, receive, send)
        first = runtime.diagnostic_snapshot()
        assert first.plugins[0].connections.model_dump() == {'sse': 1, 'websocket': 1}
        assert first.plugins[0].pending_connection_tasks == 0
        assert 'private-' not in first.model_dump_json()
        release.set()
        await asyncio.gather(*requests)
        assert runtime.diagnostic_snapshot().plugins[0].connections.model_dump() == {'sse': 0, 'websocket': 0}
        assert first.plugins[0].connections.sse == 1
    finally:
        release.set()
        await loaded.gateway.drain()
        await asyncio.gather(*requests, return_exceptions=True)
        await loaded.lifespan.shutdown()


@pytest.mark.asyncio
async def test_pending_cleanup_is_deduplicated_and_late_completion_disappears(tmp_path: Path) -> None:
    """同一任务被多个宿主回收器保留时 worker 总数去重，采样不再次取消任务。"""
    runtime = diagnostic_runtime(tmp_path)
    loaded = runtime.loaded['diagnostic_demo']
    started, interrupted, release = (asyncio.Event() for _ in range(3))
    cancellation_count = 0

    async def resistant() -> None:
        nonlocal cancellation_count
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_count += 1
            interrupted.set()
            await release.wait()

    task = asyncio.create_task(resistant())
    await started.wait()
    manager = PluginGatewayASGI(AsyncMock(), PluginLifespanManager(AsyncMock(), managed=False), AsyncMock()).connections
    loaded.gateway = SimpleNamespace(connections=manager)
    try:
        await cancel_plugin_tasks({task}, timeout=0.01)
        await interrupted.wait()
        # 模拟同一任务同时由通用回收器与连接回收器保留，诊断只能计算一次。
        manager._unfinished.add(task)
        manager._unfinished.add(asyncio.current_task())
        snapshot = runtime.diagnostic_snapshot()
        expected_pending = 2
        assert snapshot.worker_pending_cleanup_tasks == expected_pending
        assert snapshot.plugins[0].pending_connection_tasks == expected_pending
        assert pending_plugin_tasks({task}) == frozenset({task})
        assert cancellation_count == 1
        manager._unfinished.discard(asyncio.current_task())
        assert runtime.diagnostic_snapshot().worker_pending_cleanup_tasks == 1
        release.set()
        await task
        # 完成回调尚未运行时也必须过滤已退出任务，不能等待下一轮回调才减少计数。
        assert not pending_plugin_tasks({task})
        assert runtime.diagnostic_snapshot().worker_pending_cleanup_tasks == 0
    finally:
        release.set()
        manager._unfinished.clear()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('invalid', ['duplicate', 'negative', 'extra', 'worker', 'capacity'])
def test_remote_snapshot_rejects_duplicate_ids_unbounded_or_invalid_fields(tmp_path: Path, invalid: str) -> None:
    """远端不能通过重复插件、负计数或未声明字段污染宿主诊断。"""
    payload = diagnostic_runtime(tmp_path).diagnostic_snapshot().model_dump(by_alias=True)
    if invalid == 'duplicate':
        payload['plugins'].append(payload['plugins'][0].copy())
    elif invalid == 'negative':
        payload['plugins'][0]['pendingJobTasks'] = -1
    elif invalid == 'extra':
        payload['plugins'][0]['errorMessage'] = 'must-not-be-accepted'
    elif invalid == 'worker':
        payload['workerId'] = 'not-a-worker'
    else:
        payload['plugins'] = [{**payload['plugins'][0], 'pluginId': f'demo_{index}'} for index in range(1025)]
    with pytest.raises(ValidationError):
        PluginRuntimeDiagnosticSnapshot.model_validate_json(json.dumps(payload))


def test_capacity_reports_dropped_plugins_without_affecting_old_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """诊断达到容量上限时明确报告丢弃数，不改变旧版指标协议。"""
    from plugins.core.runtime import diagnostics  # noqa: PLC0415

    runtime = diagnostic_runtime(tmp_path, 'first_demo')
    other = diagnostic_runtime(tmp_path, 'second_demo')
    runtime.loaded.update(other.loaded)
    monkeypatch.setattr(diagnostics, 'MAX_DIAGNOSTIC_PLUGINS', 1)
    snapshot = runtime.diagnostic_snapshot()
    assert [plugin.plugin_id for plugin in snapshot.plugins] == ['first_demo']
    assert snapshot.dropped_plugins == 1
    previous = runtime.metrics.snapshot().model_dump(by_alias=True)
    assert previous['schemaVersion'] == 1
    assert 'plugins' not in previous
    assert 'workerPendingCleanupTasks' not in previous


def test_complete_wire_roundtrip_preserves_local_constructor_defaults() -> None:
    """本地构造可用默认值，但发布完整 JSON 后远端必须验证全部字段。"""
    plugin = PluginRuntimeDiagnostic(
        plugin_id='diagnostic_demo', version='1.0.0', active=False, ready=False, closing=False
    )
    local = PluginRuntimeDiagnosticSnapshot(worker_id='a' * 32, collected_at=123.0, plugins=[plugin])
    parsed = PluginRuntimeDiagnosticSnapshot.model_validate_json(
        local.model_dump_json(by_alias=True), context={'require_complete_snapshot': True}
    )
    assert parsed == local
    assert local.schema_version == 1
    assert local.worker_pending_cleanup_tasks == 0
    assert local.plugins[0].active_jobs == 0
    assert local.plugins[0].activation_health.status == 'unknown'
    assert local.plugins[0].config.startup_revision is None


def test_wire_snapshot_requires_every_nested_serialized_field(tmp_path: Path) -> None:
    """逐个删除每层已声明字段，缺失项均不能被远端读取补成零或未知状态。"""
    payload = diagnostic_runtime(tmp_path).diagnostic_snapshot().model_dump(by_alias=True)
    payload['plugins'][0]['lifespan'] = {'managed': True, 'started': True, 'ready': True, 'taskActive': True}
    payload['plugins'][0]['lastError'] = {'errorType': 'RuntimeError', 'requestId': None, 'at': 125.0}
    context = {'require_complete_snapshot': True}
    PluginRuntimeDiagnosticSnapshot.model_validate_json(json.dumps(payload), context=context)
    objects = [
        (),
        ('plugins', 0),
        ('plugins', 0, 'lifespan'),
        ('plugins', 0, 'connections'),
        ('plugins', 0, 'activationHealth'),
        ('plugins', 0, 'config'),
        ('plugins', 0, 'lastError'),
    ]
    for path in objects:
        original = payload
        for component in path:
            original = original[component]
        for field in original:
            incomplete = deepcopy(payload)
            target = incomplete
            for component in path:
                target = target[component]
            del target[field]
            with pytest.raises(ValidationError, match='缺少协议字段'):
                PluginRuntimeDiagnosticSnapshot.model_validate_json(json.dumps(incomplete), context=context)


@pytest.mark.parametrize('version', [True, False, 1.0, '1', 0, 2, None])
def test_wire_schema_version_requires_integer_one(tmp_path: Path, version: object) -> None:
    """JSON 布尔值或浮点数即使等于 1 也不代表受支持的协议版本。"""
    payload = diagnostic_runtime(tmp_path).diagnostic_snapshot().model_dump(by_alias=True)
    payload['schemaVersion'] = version
    with pytest.raises(ValidationError, match='schemaVersion'):
        PluginRuntimeDiagnosticSnapshot.model_validate_json(
            json.dumps(payload), context={'require_complete_snapshot': True}
        )


def test_wire_requires_camel_case_alias_even_when_local_field_names_are_allowed(tmp_path: Path) -> None:
    """远端不能用本地 Python 字段名绕过协议完整性，本地构造仍兼容这些字段名。"""
    payload = diagnostic_runtime(tmp_path).diagnostic_snapshot().model_dump(by_alias=True)
    payload['worker_pending_cleanup_tasks'] = payload.pop('workerPendingCleanupTasks')
    assert PluginRuntimeDiagnosticSnapshot.model_validate(payload).worker_pending_cleanup_tasks == 0
    with pytest.raises(ValidationError, match='workerPendingCleanupTasks'):
        PluginRuntimeDiagnosticSnapshot.model_validate_json(
            json.dumps(payload), context={'require_complete_snapshot': True}
        )
