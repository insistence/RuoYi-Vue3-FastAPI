from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from plugins.core.deployment.state import aggregate_release

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
DIGEST = 'a' * 64
GENERATION = 'b' * 32


def release(expected_workers: int = 1, **overrides: object) -> SimpleNamespace:
    """构造发布目标及预期进程数量的测试记录。"""
    return SimpleNamespace(
        **{
            'plugin_id': 'demo',
            'target_digest': DIGEST,
            'generation': GENERATION,
            'expected_workers': expected_workers,
            'prepare_status': 'prepared',
            **overrides,
        }
    )


def host(worker_id: str, **overrides: object) -> SimpleNamespace:
    """构造宿主进程存活报告。"""
    return SimpleNamespace(
        **{'worker_id': worker_id, 'plugin_id': '__runtime__', 'state': 'ready', 'heartbeat_time': NOW, **overrides}
    )


def plugin(worker_id: str, **overrides: object) -> SimpleNamespace:
    """构造插件实际加载状态报告。"""
    return SimpleNamespace(
        **{
            'worker_id': worker_id,
            'plugin_id': 'demo',
            'state': 'ready',
            'heartbeat_time': NOW,
            'artifact_digest': DIGEST,
            'generation': GENERATION,
            **overrides,
        }
    )


def test_active_requires_every_live_host_and_expected_capacity() -> None:
    """验证全部存活宿主就绪且达到预期数量后才能报告 active。"""
    reports = [host('one'), plugin('one'), host('two')]
    summary = aggregate_release(release(), reports, now=NOW)
    assert summary.status == 'partial'
    assert summary.healthy_workers == 1
    assert summary.missing_workers == 1
    assert summary.restart_required
    summary = aggregate_release(release(2), [*reports, plugin('two')], now=NOW)
    assert summary.status == 'active'
    assert not summary.restart_required
    summary = aggregate_release(release(3), [*reports, plugin('two')], now=NOW)
    assert summary.status == 'partial'
    assert summary.missing_workers == 1


def test_report_without_host_cannot_claim_active() -> None:
    """验证缺少宿主报告的插件行不能使发布状态变为 active。"""
    summary = aggregate_release(release(), [plugin('orphan')], now=NOW)
    assert summary.status == 'pending_restart'
    assert summary.healthy_workers == 0
    assert summary.live_workers == 0


@pytest.mark.parametrize('difference', [{'artifact_digest': 'c' * 64}, {'generation': 'd' * 32}])
def test_old_generation_or_digest_requires_restart(difference: dict[str, object]) -> None:
    """验证旧代际或错误制品摘要要求重启。"""
    summary = aggregate_release(release(), [host('one'), plugin('one', **difference)], now=NOW)
    assert summary.status == 'pending_restart'
    assert summary.mismatch_workers == 1
    assert summary.restart_required


def test_stale_and_stopped_workers_do_not_block_fully_replaced_cluster() -> None:
    """验证陈旧或已停止进程不会阻挡新一代集群正常收敛。"""
    reports = [
        host('old', heartbeat_time=NOW - timedelta(seconds=61)),
        plugin('old'),
        host('stopped', state='stopped'),
        plugin('stopped'),
        host('new'),
        plugin('new'),
    ]
    summary = aggregate_release(release(), reports, now=NOW)
    assert summary.status == 'active'
    assert summary.stale_workers == 1
    assert summary.live_workers == 1
    summary = aggregate_release(release(2), reports, now=NOW)
    assert summary.status == 'partial'
    assert summary.missing_workers == 1


def test_expired_plugin_report_under_live_host_is_missing() -> None:
    """验证存活宿主下的过期插件报告按缺失状态处理。"""
    reports = [host('one'), plugin('one', heartbeat_time=NOW - timedelta(seconds=61))]
    summary = aggregate_release(release(), reports, now=NOW)
    assert summary.status == 'pending_restart'
    assert summary.stale_workers == 1
    assert summary.missing_workers == 1
    assert summary.healthy_workers == 0


def test_plugin_failure_is_failed_or_partial_and_preparation_failure_is_separate() -> None:
    """验证插件运行失败与维护准备失败分别汇总。"""
    failed = [host('one'), plugin('one', state='failed')]
    summary = aggregate_release(release(), failed, now=NOW)
    assert summary.status == 'failed'
    assert summary.failed_workers == 1
    summary = aggregate_release(release(), [*failed, host('two'), plugin('two')], now=NOW)
    assert summary.status == 'partial'
    summary = aggregate_release(
        release(prepare_status='failed', last_error='new artifact preparation failed'),
        [host('one'), plugin('one')],
        now=NOW,
    )
    assert summary.status == 'active'
    assert summary.to_payload()['prepareStatus'] == 'failed'


def test_starting_host_and_stopped_plugin_are_not_ready() -> None:
    """验证正在启动的宿主及已停止的插件不能计为就绪。"""
    summary = aggregate_release(release(), [host('one', state='starting'), plugin('one')], now=NOW)
    assert summary.status == 'pending_restart'


def test_disabled_target_converges_only_after_all_live_workers_acknowledge_stop() -> None:
    """验证全部存活进程确认当前代际停止后才汇总为已停用。"""
    reports = [host('one'), plugin('one', state='stopped')]
    summary = aggregate_release(release(), reports, now=NOW, enabled=False)
    assert summary.status == 'disabled'
    assert summary.disabled_workers == 1
    assert summary.healthy_workers == 0
    assert not summary.restart_required
    summary = aggregate_release(release(), [*reports, host('two'), plugin('two')], now=NOW, enabled=False)
    assert summary.status == 'partial'
    assert summary.restart_required
    summary = aggregate_release(release(2), reports, now=NOW, enabled=False)
    assert summary.status == 'partial'
    summary = aggregate_release(
        release(), [host('one'), plugin('one', state='stopped', generation='old')], now=NOW, enabled=False
    )
    assert summary.status == 'pending_restart'
    assert summary.mismatch_workers == 1
    summary = aggregate_release(release(), [host('one'), plugin('one', state='stopped')], now=NOW)
    assert summary.status == 'pending_restart'


def test_no_target_and_future_heartbeats_do_not_claim_active() -> None:
    """验证无目标或未来时间心跳不能产生 active 状态。"""
    assert aggregate_release(release(target_digest=None), [], now=NOW).status == 'no_target'
    assert not aggregate_release(release(target_digest=None), [], now=NOW).restart_required
    summary = aggregate_release(
        release(), [host('one', heartbeat_time=NOW + timedelta(seconds=61)), plugin('one')], now=NOW
    )
    assert summary.status == 'pending_restart'
    assert summary.stale_workers == 1
    with pytest.raises(ValueError, match='时区'):
        aggregate_release(release(), [], now=NOW.replace(tzinfo=None))
