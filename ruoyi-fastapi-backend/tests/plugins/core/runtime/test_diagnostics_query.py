from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.get_redis import RedisUtil
from plugins.core.runtime import diagnostics_query as query

NOW = 1_800_000_000.0
WORKER = 'a' * 32
OTHER = 'b' * 32
DIGEST = 'd' * 64


def snapshot(worker_id: str = WORKER, **overrides: object) -> dict:
    """构造真正加载但尚无请求的运行快照。"""
    return {
        'workerId': worker_id,
        'collectedAt': NOW,
        'source': 'redis',
        'workerPendingCleanupTasks': 0,
        'droppedPlugins': 0,
        'plugins': [
            {
                'pluginId': 'demo',
                'version': '1.0.0',
                'digest': DIGEST,
                'generation': 'c' * 32,
                'ready': True,
                'closing': False,
                'activeJobs': 0,
                'pendingJobTasks': 0,
                'pendingConnectionTasks': 0,
                'connections': {'sse': 0, 'websocket': 0},
            }
        ],
        **overrides,
    }


def report(*workers: dict, **overrides: object) -> dict:
    """构造已通过报告器校验的集群观测结果。"""
    return {
        'scope': 'reporting_workers',
        'clusterAvailable': True,
        'sampleTtlSeconds': 60,
        'workers': list(workers),
        'invalidSnapshots': 0,
        'staleSnapshots': 0,
        'staleWorkerIds': [],
        'invalidWorkerIds': [],
        'workerLimitReached': False,
        **overrides,
    }


def release(*worker_ids: str, expected: int = 1) -> dict:
    """构造当前发布目标，故意与实际运行摘要不同以检验身份边界。"""
    return {
        'available': True,
        'supported': True,
        'workerTtlSeconds': 60,
        'releases': [{'pluginId': 'demo', 'targetDigest': 'f' * 64, 'expectedWorkers': expected}],
        'workers': [
            {
                'workerId': worker_id,
                'pluginId': plugin_id,
                'state': 'ready',
                'digest': 'f' * 64,
                'generation': 'e' * 32,
                'heartbeatTime': datetime.fromtimestamp(NOW, timezone.utc).isoformat(),
            }
            for worker_id in worker_ids
            for plugin_id in ('__runtime__', 'demo')
        ],
    }


def test_diagnostics_preserves_actual_identity_and_marks_missing_worker_unknown() -> None:
    result = query.build_runtime_diagnostics('demo', report(snapshot()), release(WORKER, OTHER, expected=2), now=NOW)
    first, second = result['workers']
    assert result['state'] == 'partial'
    assert result['missingWorkers'] == 1
    assert first['actual']['digest'] == DIGEST
    assert first['releaseReport']['digest'] == 'f' * 64
    assert first['actual']['activeJobs'] == 0
    assert second['actual'] is None and second['workerPendingCleanupTasks'] is None
    assert second['freshness'] == 'missing'
    assert result['observedTotals']['activeJobs'] == 0
    assert result['totalsScope'] == 'fresh_observed_workers'


def test_stale_and_invalid_workers_never_contribute_zero_or_old_actual_values() -> None:
    result = query.build_runtime_diagnostics(
        'demo',
        report(staleWorkerIds=[WORKER], staleSnapshots=1, invalidWorkerIds=[OTHER], invalidSnapshots=1),
        release(WORKER, OTHER, expected=2),
        now=NOW,
    )
    assert result['observedTotals'] is None
    assert result['observedWorkers'] == 0
    assert {worker['freshness'] for worker in result['workers']} == {'stale', 'invalid'}
    assert all(worker['actual'] is None for worker in result['workers'])


def test_empty_fresh_worker_and_truncated_worker_are_distinct() -> None:
    result = query.build_runtime_diagnostics('demo', report(snapshot(plugins=[])), release(WORKER), now=NOW)
    assert result['workers'][0]['observation'] == 'not_loaded'
    assert result['workers'][0]['actual'] is None
    assert result['observedTotals'] is None
    result = query.build_runtime_diagnostics(
        'demo', report(snapshot(plugins=[], droppedPlugins=1)), release(WORKER), now=NOW
    )
    assert result['workers'][0]['observation'] == 'unknown'
    assert result['state'] == 'partial'


def test_replaced_stale_host_does_not_make_current_coverage_incomplete() -> None:
    deployment = release(WORKER, OTHER)
    for row in deployment['workers']:
        if row['workerId'] == OTHER:
            row['heartbeatTime'] = datetime.fromtimestamp(NOW - 61, timezone.utc).isoformat()
    result = query.build_runtime_diagnostics('demo', report(snapshot()), deployment, now=NOW)
    assert result['state'] == 'observed' and result['missingWorkers'] == 0
    assert result['workers'][1]['actual'] is None


@pytest.mark.asyncio
async def test_unavailable_runtime_and_release_keep_independent_failure_states(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query, '_read_release_status', AsyncMock(return_value={'supported': True, 'available': False}))
    reporter = SimpleNamespace(read=AsyncMock(side_effect=RuntimeError('private-password')))
    result = await query.read_plugin_runtime_diagnostics('demo', reporter=reporter)
    assert result['state'] == 'unavailable'
    assert result['release']['available'] is False
    assert result['observedTotals'] is None
    assert 'private-password' not in str(result)


@pytest.mark.asyncio
async def test_cli_reads_and_closes_redis_without_publishing_local_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = SimpleNamespace(aclose=AsyncMock())
    create = AsyncMock(return_value=redis)
    read = AsyncMock(return_value={'state': 'unobserved'})
    monkeypatch.setattr(RedisUtil, 'create_redis_pool', create)
    monkeypatch.setattr(query, 'read_plugin_runtime_diagnostics', read)
    assert await query.read_cli_runtime_diagnostics('demo') == {'state': 'unobserved'}
    create.assert_awaited_once_with(log_enabled=False)
    read.assert_awaited_once_with('demo', redis=redis, backend_root=None)
    redis.aclose.assert_awaited_once()


def test_current_worker_scope_is_explicitly_partial() -> None:
    result = query.build_runtime_diagnostics(
        'demo', report(snapshot(), scope='current_worker', clusterAvailable=False), release(WORKER), now=NOW
    )
    assert result['state'] == 'partial'
    assert result['workers'][0]['source'] == 'redis'


def test_release_errors_are_not_copied_into_runtime_diagnostics() -> None:
    deployment = release(WORKER)
    deployment['releases'][0].update(prepareStatus='failed', lastError='fake-secret-in-preparation')
    for row in deployment['workers']:
        row.update(state='failed', error='fake-secret-in-worker', internalPath='/private/path')
    result = query.build_runtime_diagnostics('demo', report(snapshot()), deployment, now=NOW)
    assert 'fake-secret' not in str(result) and '/private/path' not in str(result)
    assert result['release']['summary']['failureReason'] == 'preparation_failed'
    assert result['workers'][0]['releaseReport']['failureReason'] == 'worker_failed'


def test_fresh_runtime_cache_of_stale_host_does_not_fill_expected_capacity() -> None:
    deployment = release(WORKER, OTHER, expected=2)
    deployment['workerTtlSeconds'] = 15
    for row in deployment['workers']:
        if row['workerId'] == OTHER:
            row['heartbeatTime'] = datetime.fromtimestamp(NOW - 20, timezone.utc).isoformat()
    result = query.build_runtime_diagnostics(
        'demo', report(snapshot(), snapshot(OTHER, collectedAt=NOW - 20)), deployment, now=NOW
    )
    assert result['missingWorkers'] == 1
    assert result['state'] == 'partial'
    assert result['workers'][1]['freshness'] == 'fresh'
    assert result['workers'][1]['host']['fresh'] is False


def test_no_expected_baseline_does_not_claim_zero_missing_workers() -> None:
    result = query.build_runtime_diagnostics('demo', report(), {'supported': True, 'available': True}, now=NOW)
    assert result['missingWorkers'] is None
    assert result['observedTotals'] is None


def test_snapshot_expiring_during_release_query_is_not_counted_as_fresh() -> None:
    cached = snapshot(collectedAt=NOW - 59)
    cached['plugins'][0]['activeJobs'] = 7
    incoming = report(cached)
    assert query.build_runtime_diagnostics('demo', incoming, release(WORKER), now=NOW)['freshWorkers'] == 1

    result = query.build_runtime_diagnostics('demo', incoming, release(WORKER), now=NOW + 2)

    worker = result['workers'][0]
    assert worker['freshness'] == worker['observation'] == 'stale'
    assert worker['source'] == 'redis'
    assert worker['collectedAt'] == cached['collectedAt']
    assert worker['ageSeconds'] == NOW + 2 - cached['collectedAt']
    assert worker['actual'] is None
    assert worker['workerPendingCleanupTasks'] is None
    assert worker['droppedPlugins'] is None
    assert result['freshWorkers'] == result['observedWorkers'] == 0
    assert result['observedTotals'] is None
    assert result['missingWorkers'] == result['staleSnapshots'] == 1
    assert incoming['staleSnapshots'] == 0


@pytest.mark.parametrize('already_stale', [True, False])
def test_new_expiration_updates_stale_count_without_counting_existing_ids_twice(already_stale: bool) -> None:
    old_stale_ids = [WORKER, OTHER] if already_stale else [OTHER]
    result = query.build_runtime_diagnostics(
        'demo',
        report(snapshot(collectedAt=NOW - 61), staleWorkerIds=old_stale_ids, staleSnapshots=len(old_stale_ids)),
        release(WORKER, OTHER, expected=2),
        now=NOW,
    )
    expected_stale = 2
    assert result['staleSnapshots'] == expected_stale
    assert result['missingWorkers'] == expected_stale
    assert result['observedTotals'] is None


@pytest.mark.parametrize(
    ('age', 'ttl', 'fresh'), [(60, 60, True), (60.001, 60, False), (31, 30, False), (-5, 60, True), (-5.001, 60, False)]
)
def test_aggregation_rechecks_report_ttl_and_future_clock_skew(age: float, ttl: float, fresh: bool) -> None:
    result = query.build_runtime_diagnostics(
        'demo', report(snapshot(collectedAt=NOW - age), sampleTtlSeconds=ttl), release(WORKER), now=NOW
    )
    assert result['workers'][0]['freshness'] == ('fresh' if fresh else 'stale')
    assert result['freshWorkers'] == int(fresh)
    assert result['missingWorkers'] == int(not fresh)
    assert result['staleSnapshots'] == int(not fresh)
    assert (result['observedTotals'] is not None) is fresh
