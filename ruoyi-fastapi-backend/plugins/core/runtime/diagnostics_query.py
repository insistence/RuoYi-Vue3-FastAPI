import asyncio
import time
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from plugins.core.runtime.diagnostics_store import DIAGNOSTICS_TTL_SECONDS, MAX_CLOCK_SKEW_SECONDS

DIAGNOSTICS_QUERY_TIMEOUT_SECONDS = 3
RUNTIME_COUNTERS = ('activeJobs', 'pendingConnectionTasks', 'pendingJobTasks')
DEFAULT_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _heartbeat_fresh(report: Mapping[str, Any] | None, now: float, ttl: float) -> bool:
    """
    判断数据库报告是否仍在发布心跳窗口内，不修改发布收敛规则。

    :param report: 包含 ISO 心跳时刻的数据库报告，缺失时为 None
    :param now: 本次诊断使用的 Unix 时刻
    :param ttl: 发布心跳有效秒数
    :return: 心跳是否携带时区且处于有效窗口内
    """
    if report is None:
        return False
    try:
        heartbeat = datetime.fromisoformat(report['heartbeatTime'])
        return heartbeat.tzinfo is not None and 0 <= now - heartbeat.timestamp() <= ttl
    except (KeyError, TypeError, ValueError):
        return False


def _release_report(report: Mapping[str, Any] | None, now: float, ttl: float) -> dict[str, Any] | None:
    """
    只公开发布报告的固定状态字段，避免错误正文或数据库路径进入运行诊断。

    :param report: 原始宿主或插件发布报告，缺失时为 None
    :param now: 本次诊断使用的 Unix 时刻
    :param ttl: 发布心跳有效秒数
    :return: 经过字段白名单筛选且带时效的报告，缺失时为 None
    """
    if report is None:
        return None
    return {
        **{
            key: report.get(key)
            for key in (
                'workerId',
                'pluginId',
                'digest',
                'version',
                'generation',
                'state',
                'heartbeatTime',
            )
        },
        'fresh': _heartbeat_fresh(report, now, ttl),
        'failureReason': 'worker_failed' if report.get('state') == 'failed' else None,
    }


def _release_summary(summary: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """
    保留发布目标与计数，维护错误只暴露固定分类。

    :param summary: 现有发布服务返回的插件摘要，缺失时为 None
    :return: 不包含错误正文的发布摘要
    """
    if summary is None:
        return None
    return {
        **{
            key: summary[key]
            for key in (
                'pluginId',
                'targetDigest',
                'generation',
                'status',
                'restartRequired',
                'expectedWorkers',
                'liveWorkers',
                'healthyWorkers',
                'disabledWorkers',
                'mismatchWorkers',
                'staleWorkers',
                'missingWorkers',
                'failedWorkers',
                'prepareStatus',
                'installedVersion',
                'enabled',
                'preparedDigest',
                'preparedVersion',
                'previousDigest',
            )
            if key in summary
        },
        'failureReason': 'preparation_failed' if summary.get('prepareStatus') == 'failed' else None,
    }


def build_runtime_diagnostics(
    plugin_id: str,
    report: Mapping[str, Any],
    release: Mapping[str, Any],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """
    关联运行快照与发布报告；实际加载身份及计数仅来自汇总时仍有效的运行快照。

    :param plugin_id: 当前诊断插件 ID
    :param report: 经过报告器身份与 TTL 校验的运行观测结果
    :param release: 包含可用性及心跳 TTL 的发布查询结果
    :param now: 可选的 Unix 汇总时刻，未指定时使用当前时刻
    :return: 明确区分实际观测、发布目标和缺失数据的运行诊断负载
    """
    now = time.time() if now is None else now
    reported_snapshots = {worker['workerId']: worker for worker in report.get('workers', [])}
    sample_ttl = report.get('sampleTtlSeconds', DIAGNOSTICS_TTL_SECONDS)
    snapshots = {
        worker_id: snapshot
        for worker_id, snapshot in reported_snapshots.items()
        if -MAX_CLOCK_SKEW_SECONDS <= now - snapshot['collectedAt'] <= sample_ttl
    }
    reports = release.get('workers', [])
    hosts = {row['workerId']: row for row in reports if row['pluginId'] == '__runtime__'}
    plugins = {row['workerId']: row for row in reports if row['pluginId'] == plugin_id}
    summary = next((row for row in release.get('releases', []) if row['pluginId'] == plugin_id), None)
    ttl = float(release.get('workerTtlSeconds', 60))
    stale_ids = set(report.get('staleWorkerIds', []))
    expired_ids = reported_snapshots.keys() - snapshots.keys()
    stale_count = max(report.get('staleSnapshots', 0), len(stale_ids)) + len(expired_ids - stale_ids)
    stale_ids.update(expired_ids)
    invalid_ids = set(report.get('invalidWorkerIds', []))
    live_hosts = {
        worker_id
        for worker_id, host in hosts.items()
        if host.get('state') != 'stopped' and _heartbeat_fresh(host, now, ttl)
    }
    workers = []
    for worker_id in sorted(set(snapshots) | set(hosts) | set(plugins) | stale_ids | invalid_ids):
        snapshot = snapshots.get(worker_id)
        reported_snapshot = reported_snapshots.get(worker_id)
        actual = (
            next((plugin for plugin in snapshot.get('plugins', []) if plugin['pluginId'] == plugin_id), None)
            if snapshot
            else None
        )
        freshness = (
            'fresh'
            if snapshot
            else 'stale'
            if worker_id in stale_ids
            else 'invalid'
            if worker_id in invalid_ids
            else 'missing'
        )
        host = hosts.get(worker_id)
        worker_report = plugins.get(worker_id)
        workers.append(
            {
                'workerId': worker_id,
                'source': reported_snapshot.get('source') if reported_snapshot else None,
                'freshness': freshness,
                'observation': (
                    'observed'
                    if actual
                    else 'unknown'
                    if snapshot and snapshot.get('droppedPlugins')
                    else 'not_loaded'
                    if snapshot
                    else freshness
                ),
                'collectedAt': reported_snapshot.get('collectedAt') if reported_snapshot else None,
                'ageSeconds': round(max(0, now - reported_snapshot['collectedAt']), 3) if reported_snapshot else None,
                'actual': actual,
                'workerPendingCleanupTasks': snapshot.get('workerPendingCleanupTasks') if snapshot else None,
                'droppedPlugins': snapshot.get('droppedPlugins') if snapshot else None,
                'host': _release_report(host, now, ttl),
                'releaseReport': _release_report(worker_report, now, ttl),
            }
        )
    observed = [worker for worker in workers if worker['actual'] is not None]
    totals = None
    if observed:
        totals = {
            **{key: sum(worker['actual'][key] for worker in observed) for key in RUNTIME_COUNTERS},
            'sse': sum(worker['actual']['connections']['sse'] for worker in observed),
            'websocket': sum(worker['actual']['connections']['websocket'] for worker in observed),
        }
    expected = summary.get('expectedWorkers') if summary else None
    missing = len(live_hosts - set(snapshots))
    if expected is not None:
        # 历史宿主的缓存观测不能填补当前发布的宿主容量缺口。
        missing += max(0, expected - len(live_hosts))
    limited = bool(report.get('workerLimitReached')) or any(
        worker.get('droppedPlugins') for worker in snapshots.values()
    )
    incomplete = bool(
        missing
        or limited
        or report.get('invalidSnapshots')
        or report.get('scope') == 'current_worker'
        or report.get('localSnapshotAvailable') is False
    )
    state = 'partial' if snapshots and incomplete else 'observed' if snapshots else 'unobserved'
    if report.get('scope') == 'unavailable':
        state = 'unavailable'
    return {
        'pluginId': plugin_id,
        'supported': report.get('supported', True),
        'state': state,
        'generatedAt': now,
        **{
            key: report.get(key)
            for key in (
                'scope',
                'clusterAvailable',
                'currentWorkerId',
                'sampleIntervalSeconds',
                'sampleTtlSeconds',
                'invalidSnapshots',
                'workerLimitReached',
                'localSnapshotAvailable',
            )
        },
        'staleSnapshots': stale_count,
        'observedWorkers': len(observed),
        'freshWorkers': len(snapshots),
        'expectedWorkers': expected,
        'missingWorkers': missing if release.get('available') and (expected is not None or live_hosts) else None,
        'observedTotals': totals,
        'totalsScope': 'fresh_observed_workers',
        'release': {
            'supported': release.get('supported', False),
            'available': release.get('available', False),
            'summary': _release_summary(summary),
            'workerTtlSeconds': release.get('workerTtlSeconds'),
        },
        'workers': workers,
    }


async def _read_release_status(plugin_id: str, backend_root: Path | None) -> dict[str, Any]:
    """
    按需读取现有发布表；制品功能关闭时不查询相关表。

    :param plugin_id: 当前诊断插件 ID
    :param backend_root: 用于解析发布配置的后端目录，未指定时使用当前项目
    :return: 带功能支持及查询可用性标记的发布状态
    """
    from plugins.core.deployment.config import PluginDeploymentConfig  # noqa: PLC0415
    from plugins.core.deployment.service import PluginDeploymentService  # noqa: PLC0415

    try:
        config = PluginDeploymentConfig.from_settings(backend_root or DEFAULT_BACKEND_ROOT)
        if not config.enabled:
            return {'supported': False, 'available': False}
        payload = await asyncio.wait_for(
            PluginDeploymentService(config).status(plugin_id), DIAGNOSTICS_QUERY_TIMEOUT_SECONDS
        )
        return {**payload, 'supported': True, 'available': True, 'workerTtlSeconds': config.worker_ttl_seconds}
    except Exception:
        return {'supported': True, 'available': False}


async def read_plugin_runtime_diagnostics(
    plugin_id: str,
    *,
    reporter: Any = None,
    redis: Any = None,
    ready_key: str | None = None,
    backend_root: Path | None = None,
) -> dict[str, Any]:
    """
    为 API 与 CLI 读取相同运行诊断，观测失败独立于静态诊断结果。

    :param plugin_id: 当前诊断插件 ID
    :param reporter: 当前服务 worker 的报告器；CLI 不传入本地报告器
    :param redis: 无报告器时用于只读查询的 Redis 客户端
    :param ready_key: 可选的宿主启动命名空间前缀
    :param backend_root: 用于解析发布配置的后端目录
    :return: 发布状态与有效运行快照的只读聚合结果
    """
    from plugins.core.runtime.diagnostics_store import (  # noqa: PLC0415
        diagnostics_namespace,
        read_runtime_diagnostics,
    )

    try:
        if reporter is not None:
            operation = reporter.read(plugin_id)
        else:
            namespace = diagnostics_namespace(ready_key) if ready_key is not None else diagnostics_namespace()
            operation = read_runtime_diagnostics(redis, namespace, plugin_id)
        report = await asyncio.wait_for(operation, DIAGNOSTICS_QUERY_TIMEOUT_SECONDS)
    except Exception:
        report = {'scope': 'unavailable', 'clusterAvailable': False, 'workers': []}
    release = await _read_release_status(plugin_id, backend_root)
    return build_runtime_diagnostics(plugin_id, report, release)


async def read_cli_runtime_diagnostics(plugin_id: str, *, backend_root: Path | None = None) -> dict[str, Any]:
    """
    CLI 仅查询服务 worker 的快照，不登记或发布诊断进程的本地计数。

    :param plugin_id: 当前诊断插件 ID
    :param backend_root: 用于解析发布配置的后端目录
    :return: 关闭本次 Redis 连接后返回的运行诊断负载
    """
    from config.get_redis import RedisUtil  # noqa: PLC0415

    redis = None
    try:
        redis = await asyncio.wait_for(
            RedisUtil.create_redis_pool(log_enabled=False), DIAGNOSTICS_QUERY_TIMEOUT_SECONDS
        )
    except Exception:
        pass
    try:
        return await read_plugin_runtime_diagnostics(plugin_id, redis=redis, backend_root=backend_root)
    finally:
        if redis is not None:
            with suppress(Exception):
                await asyncio.wait_for(redis.aclose(), DIAGNOSTICS_QUERY_TIMEOUT_SECONDS)
