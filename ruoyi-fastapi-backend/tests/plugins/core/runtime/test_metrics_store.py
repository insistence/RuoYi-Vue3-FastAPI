import json
import time
from collections.abc import AsyncIterator
from fnmatch import fnmatchcase

import pytest

from plugins.core.runtime.metrics import PluginRuntimeMetrics
from plugins.core.runtime.metrics_store import METRICS_TTL_SECONDS, PluginMetricsReporter

NAMESPACE = 'isolated-test:ready:metrics'


class MetricsRedis:
    """提供测试所需的键空间隔离和有限指标读写，不连接外部服务。"""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.expirations: dict[str, int] = {}
        self.fail = False

    async def set(self, key: str, value: bytes, *, ex: int) -> None:
        if self.fail:
            raise ConnectionError('private-redis-password')
        self.values[key] = value
        self.expirations[key] = ex

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def scan_iter(self, *, match: str, count: int) -> AsyncIterator[str]:
        if self.fail:
            raise ConnectionError('private-redis-password')
        for key in sorted(self.values):
            if fnmatchcase(key, match):
                yield key

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        return [self.values.get(key) for key in keys]


def reporter(worker_id: str) -> PluginMetricsReporter:
    """构造加载了固定插件的进程报告器。"""
    metrics = PluginRuntimeMetrics(worker_id=worker_id)
    metrics.register('metric_demo', '1.0.0', None, None)
    metrics.begin('metric_demo', 'http', f'trace-{worker_id}').finish('succeeded')
    return PluginMetricsReporter(metrics)


@pytest.mark.asyncio
async def test_reporting_workers_aggregate_without_double_counting_local_snapshot() -> None:
    """本地即时数据替换自己的旧快照，其他部署的命名空间不进入汇总。"""
    redis = MetricsRedis()
    first, second, foreign = reporter('a' * 32), reporter('b' * 32), reporter('c' * 32)
    for item, namespace in ((first, NAMESPACE), (second, NAMESPACE), (foreign, 'foreign:metrics')):
        item.start(redis, namespace)
        await item.publish()
    try:
        first.metrics.begin('metric_demo', 'http', 'new').finish('succeeded')
        result = await first.read('metric_demo')
        assert result['scope'] == 'reporting_workers'
        expected_workers = 2
        expected_requests = 3
        assert result['observedWorkers'] == expected_workers
        assert result['series'][0]['started'] == expected_requests
        assert {item['workerId'] for item in result['workers']} == {'a' * 32, 'b' * 32}
        assert redis.expirations[first.key] == METRICS_TTL_SECONDS
        assert (await first.read('other_demo'))['series'] == []
    finally:
        for item in (first, second, foreign):
            await item.stop()
    assert not redis.values


@pytest.mark.asyncio
async def test_stale_corrupt_and_mismatched_snapshots_are_excluded() -> None:
    """损坏、身份不符和过期的采样不会被当成活跃 worker 的数据。"""
    redis = MetricsRedis()
    current = reporter('a' * 32)
    current.start(redis, NAMESPACE)
    stale = reporter('b' * 32).metrics.snapshot().model_dump(by_alias=True)
    stale['collectedAt'] = time.time() - METRICS_TTL_SECONDS - 1
    redis.values[f'{NAMESPACE}:{"b" * 32}'] = json.dumps(stale).encode()
    redis.values[f'{NAMESPACE}:{"c" * 32}'] = b'{broken'
    redis.values[f'{NAMESPACE}:{"d" * 32}'] = current.metrics.snapshot().model_dump_json().encode()
    try:
        result = await current.read()
        assert result['observedWorkers'] == 1
        assert result['staleSnapshots'] == 1
        expected_invalid = 2
        assert result['invalidSnapshots'] == expected_invalid
    finally:
        await current.stop()


@pytest.mark.asyncio
async def test_redis_failure_returns_explicit_local_scope_and_recovers() -> None:
    """观测 Redis 故障不影响本地统计，恢复后继续发布。"""
    redis = MetricsRedis()
    current = reporter('a' * 32)
    current.start(redis, NAMESPACE)
    redis.fail = True
    try:
        await current.publish()
        assert current.publication_failed
        result = await current.read()
        assert result['scope'] == 'current_worker'
        assert result['clusterAvailable'] is False
        assert result['series'][0]['succeeded'] == 1
        assert 'private-redis-password' not in json.dumps(result)
        redis.fail = False
        await current.publish()
        assert not current.publication_failed
    finally:
        await current.stop()
    assert current.task is None


@pytest.mark.asyncio
async def test_worker_limit_is_reported_and_shutdown_only_deletes_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """限制跨进程查询规模，并保留其他 worker 和业务键。"""
    from plugins.core.runtime import metrics_store as module  # noqa: PLC0415

    monkeypatch.setattr(module, 'MAX_METRICS_WORKERS', 1)
    redis = MetricsRedis()
    current = reporter('a' * 32)
    current.start(redis, NAMESPACE)
    await current.publish()
    other_key = f'{NAMESPACE}:{"b" * 32}'
    redis.values[other_key] = reporter('b' * 32).metrics.snapshot().model_dump_json().encode()
    redis.values['business:key'] = b'unchanged'
    try:
        assert (await current.read())['workerLimitReached'] is True
    finally:
        await current.stop()
    assert redis.values == {other_key: redis.values[other_key], 'business:key': b'unchanged'}
