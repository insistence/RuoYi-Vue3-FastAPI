import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from starlette import status
from starlette.types import Message, Receive, Scope, Send

from middlewares.trace_middleware import TraceCtx
from middlewares.trace_middleware.ctx import CTX_REQUEST_ID
from plugins.core.runtime.metrics import (
    PluginMetricSnapshot,
    PluginObservedASGI,
    PluginRuntimeMetrics,
    aggregate_metric_snapshots,
)


def collector(worker_id: str = 'a' * 32, version: str = '1.0.0', generation: str | None = None) -> PluginRuntimeMetrics:
    """构建包含固定插件身份的指标收集器。"""
    metrics = PluginRuntimeMetrics(worker_id=worker_id)
    metrics.register('metric_demo', version, 'c' * 64, generation)
    return metrics


def test_invocation_counts_duration_histogram_and_is_idempotent() -> None:
    """在途、结果计数及直方图始终保持一致，重复结束不会重复记账。"""
    now = [0.0]
    metrics = collector()
    metrics.clock = lambda: now[0]
    invocation = metrics.begin('metric_demo', 'http', 'trace-1')
    assert metrics.snapshot().series[0].active == 1
    now[0] = 0.2
    invocation.finish('succeeded')
    invocation.finish('failed', error_type='Ignored')
    sample = metrics.snapshot()
    series = sample.series[0]
    assert (series.started, series.active, series.succeeded, series.failed) == (1, 0, 1, 0)
    expected_duration = 200.0
    assert series.duration_sum_ms == expected_duration
    assert sum(series.latency_buckets) == 1
    assert series.to_payload()['averageDurationMs'] == expected_duration
    assert series.to_payload()['failureRatePercent'] == 0
    expected_p95 = 250.0
    assert series.to_payload()['p95UpperBoundMs'] == expected_p95
    PluginMetricSnapshot.model_validate_json(sample.model_dump_json())
    metrics.begin('metric_demo', 'http', 'trace-2')
    assert sample.series[0].started == 1


@pytest.mark.parametrize('job_id', ['t', 'sync-users', 'sync_users'])
def test_task_metric_names_accept_all_manifest_job_id_forms(job_id: str) -> None:
    """指标标签兼容清单允许的短任务 ID 和连接符。"""
    metrics = collector()
    invocation = metrics.begin('metric_demo', f'job:{job_id}', 'job-request')
    invocation.finish('succeeded')
    assert any(series.operation == f'job:{job_id}' for series in metrics.snapshot().series)


def test_aggregate_preserves_version_and_generation_boundaries() -> None:
    """同版本多进程合并，新版本或新代际单独展示。"""
    first, second = collector(), collector('b' * 32)
    new_version = collector('d' * 32, '2.0.0')
    new_generation = collector('e' * 32, generation='f' * 32)
    first.begin('metric_demo', 'http', 'first').finish('succeeded')
    second.begin('metric_demo', 'http', 'second').finish('failed', error_type='TimeoutError', timed_out=True)
    rows = aggregate_metric_snapshots([item.snapshot() for item in (first, second, new_version, new_generation)], None)
    expected_groups = 3
    assert len(rows) == expected_groups
    shared = next(row for row in rows if row['version'] == '1.0.0' and row['generation'] is None)
    assert (shared['started'], shared['succeeded'], shared['failed'], shared['timedOut']) == (2, 1, 1, 1)
    assert shared['lastErrorRequestId'] == 'second'
    expected_failure_rate = 50.0
    assert shared['failureRatePercent'] == expected_failure_rate
    assert aggregate_metric_snapshots([first.snapshot()], 'other_demo') == []


@pytest.mark.asyncio
async def test_http_observer_tracks_responses_without_recording_paths_or_content() -> None:
    """收集器包含鉴权拒绝和失败，不按动态 URL 建标签或记录业务数据。"""
    metrics = collector()
    child = FastAPI()
    seen = []

    @child.get('/items/{item_id}')
    async def item(item_id: str) -> dict[str, str]:
        seen.append(TraceCtx.get_request_id())
        if item_id == 'denied':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        if item_id == 'timeout':
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT)
        if item_id == 'failed':
            raise RuntimeError('never-store-secret')
        return {'value': item_id}

    app = PluginObservedASGI(child, metrics, 'metric_demo')
    previous = CTX_REQUEST_ID.set('host-id')
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test'
        ) as client:
            for item_id in ('private-item-a', 'private-item-b', 'denied', 'timeout', 'failed'):
                await client.get(f'/items/{item_id}?token=private-query')
        assert TraceCtx.get_request_id() == 'host-id'
    finally:
        CTX_REQUEST_ID.reset(previous)
    assert seen == ['host-id'] * len(seen)
    snapshot = metrics.snapshot()
    assert len(snapshot.series) == 1
    series = snapshot.series[0]
    assert (series.started, series.active, series.succeeded, series.rejected, series.failed, series.timed_out) == (
        5,
        0,
        2,
        1,
        2,
        1,
    )
    serialized = snapshot.model_dump_json()
    for forbidden in ('private-item', 'private-query', 'never-store-secret', '/items/'):
        assert forbidden not in serialized
    assert series.last_error_type == 'RuntimeError'
    assert series.last_error_request_id == 'host-id'


@pytest.mark.asyncio
async def test_cancelled_asgi_request_removes_active_count() -> None:
    """取消未完成请求仍减少在途数量并恢复请求上下文。"""
    entered = asyncio.Event()
    metrics = collector()

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        entered.set()
        await asyncio.Event().wait()

    app = PluginObservedASGI(child, metrics, 'metric_demo')
    task = asyncio.create_task(app({'type': 'http'}, AsyncMock(), AsyncMock()))
    await asyncio.wait_for(entered.wait(), 2)
    assert metrics.snapshot().series[0].active == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    series = metrics.snapshot().series[0]
    assert (series.active, series.cancelled) == (0, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'accepted,code,outcome', [(False, 1008, 'rejected'), (True, 1000, 'succeeded'), (True, 1011, 'failed')]
)
async def test_websocket_observation_covers_handshake_and_close(accepted: bool, code: int, outcome: str) -> None:
    """WebSocket 统计覆盖握手拒绝和连接关闭，不将正常长连接计为失败。"""
    metrics = collector()
    messages: list[Message] = []

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        if accepted:
            await send({'type': 'websocket.accept'})
        await send({'type': 'websocket.close', 'code': code})

    async def send(message: Message) -> None:
        messages.append(message)

    await PluginObservedASGI(child, metrics, 'metric_demo')({'type': 'websocket'}, AsyncMock(), send)
    series = next(item for item in metrics.snapshot().series if item.operation == 'websocket')
    assert getattr(series, outcome) == 1
    assert series.active == 0
    assert messages[-1]['code'] == code


def test_invalid_remote_counter_snapshot_is_rejected() -> None:
    """不一致的计数或额外敏感字段不能进入跨 worker 聚合。"""
    value = collector().snapshot().model_dump(by_alias=True)
    value['series'][0]['active'] = 1
    with pytest.raises(ValueError, match='计数不一致'):
        PluginMetricSnapshot.model_validate_json(json.dumps(value))
    value['series'][0]['active'] = 0
    value['series'][0]['body'] = 'forbidden'
    with pytest.raises(ValueError):
        PluginMetricSnapshot.model_validate_json(json.dumps(value))


def test_metric_capacity_does_not_interrupt_business(monkeypatch: pytest.MonkeyPatch) -> None:
    """指标达到上限时停止扩张，不使业务调用失败。"""
    from plugins.core.runtime import metrics as module  # noqa: PLC0415

    monkeypatch.setattr(module, 'MAX_METRIC_SERIES', 1)
    metrics = collector()
    assert metrics.begin('metric_demo', 'job:next', 'trace') is None
    assert metrics.dropped_series == 1
