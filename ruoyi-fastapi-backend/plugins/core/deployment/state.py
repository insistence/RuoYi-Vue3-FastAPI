from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

RUNTIME_PLUGIN_ID = '__runtime__'


def _field(row: object, name: str, default: Any = None) -> Any:
    """
    从映射或对象属性中读取统一的状态字段。

    :param row: 状态字段所在的映射或对象
    :param name: 需要读取的字段名称
    :param default: 字段不存在时使用的默认值
    :return: 指定字段值，不存在时返回默认值
    """
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)


def _fresh(report: object, *, now: datetime, cutoff: datetime) -> bool:
    """
    判断报告心跳是否带时区且位于当前有效时间窗口内。

    :param report: 插件进程报告，缺少报告时可为 None
    :param now: 本次汇总使用的带时区 UTC 时间
    :param cutoff: 仍可视为有效心跳的最早时间
    :return: 心跳是否有效且没有位于未来时间
    """
    heartbeat = _field(report, 'heartbeat_time')
    return (
        isinstance(heartbeat, datetime)
        and heartbeat.tzinfo is not None
        and heartbeat.utcoffset() is not None
        and cutoff <= heartbeat <= now
    )


def _worker_state(
    host: object,
    report: object,
    target_digest: str | None,
    generation: str | None,
    *,
    now: datetime,
    cutoff: datetime,
    enabled: bool,
) -> str:
    """
    对比宿主和插件报告，判定该进程对当前目标的加载状态。

    :param host: 宿主进程的运行状态报告
    :param report: 插件进程报告，缺少报告时可为 None
    :param target_digest: 当前发布目标的制品摘要
    :param generation: 发布代际标识
    :param now: 本次汇总使用的带时区 UTC 时间
    :param cutoff: 仍可视为有效心跳的最早时间
    :param enabled: 插件目标是否启用
    :return: 健康、停用、失败、陈旧、缺失或目标不匹配状态
    """
    if _field(host, 'state') == 'failed':
        return 'failed'
    if report is None:
        return 'missing'
    if not _fresh(report, now=now, cutoff=cutoff):
        return 'stale'
    if _field(report, 'artifact_digest') != target_digest or _field(report, 'generation') != generation:
        return 'mismatch'
    if _field(report, 'state') == 'failed':
        return 'failed'
    if not enabled and target_digest and _field(host, 'state') == 'ready' and _field(report, 'state') == 'stopped':
        return 'disabled'
    if target_digest and _field(host, 'state') == 'ready' and _field(report, 'state') == 'ready':
        return 'healthy'
    return 'missing'


def _release_status(target_digest: str | None, live: int, healthy: int, failed: int, expected: int) -> str:
    """
    根据当前目标、有效进程数量和健康情况生成汇总状态。

    :param target_digest: 当前发布目标的制品摘要
    :param live: 有效期内未停止的宿主进程数量
    :param healthy: 已就绪且加载当前目标的进程数量
    :param failed: 报告加载或宿主运行失败的进程数量
    :param expected: 发布配置要求的预期宿主进程数量
    :return: 发布状态标识
    """
    if not target_digest:
        return 'no_target'
    if live >= expected and healthy == live:
        return 'active'
    if healthy:
        return 'partial'
    if failed:
        return 'failed'
    return 'pending_restart'


@dataclass(frozen=True)
class PluginReleaseSummary:
    """
    发布目标在全部存活宿主进程中的状态汇总。
    """

    plugin_id: str
    target_digest: str | None
    generation: str | None
    status: str
    restart_required: bool
    expected_workers: int
    live_workers: int
    healthy_workers: int
    disabled_workers: int
    mismatch_workers: int
    stale_workers: int
    missing_workers: int
    failed_workers: int
    prepare_status: str
    last_error: str | None

    def to_payload(self) -> dict[str, object]:
        """
        将发布汇总对象转换为管理端使用的字段格式。

        :return: 使用驼峰字段名的发布状态字典
        """
        return {
            'pluginId': self.plugin_id,
            'targetDigest': self.target_digest,
            'generation': self.generation,
            'status': self.status,
            'restartRequired': self.restart_required,
            'expectedWorkers': self.expected_workers,
            'liveWorkers': self.live_workers,
            'healthyWorkers': self.healthy_workers,
            'disabledWorkers': self.disabled_workers,
            'mismatchWorkers': self.mismatch_workers,
            'staleWorkers': self.stale_workers,
            'missingWorkers': self.missing_workers,
            'failedWorkers': self.failed_workers,
            'prepareStatus': self.prepare_status,
            'lastError': self.last_error,
        }


def aggregate_release(
    release: object,
    worker_reports: Iterable[object],
    *,
    now: datetime,
    ttl_seconds: float = 60,
    enabled: bool = True,
) -> PluginReleaseSummary:
    """
    汇总全部存活宿主对发布目标的实际加载情况。

    只有全部存活宿主均加载目标且达到预期数量时才报告 active。
    报告集合必须包含宿主的 __runtime__ 行；过期及已停止进程仅保留诊断信息。

    :param release: 插件发布目标及维护准备记录
    :param worker_reports: 包含宿主行和插件行的进程报告集合
    :param now: 本次汇总使用的带时区 UTC 时间
    :param ttl_seconds: 进程心跳的有效时长，单位为秒
    :param enabled: 插件目标是否启用
    :return: 发布目标的集群状态摘要
    :raises ValueError: 当前时间未携带时区，或心跳有效期及预期进程数量不合法
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now必须是带时区的UTC时刻')
    if ttl_seconds <= 0:
        raise ValueError('心跳TTL必须大于零')
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(seconds=ttl_seconds)
    plugin_id = _field(release, 'plugin_id', '')
    target_digest = _field(release, 'target_digest')
    generation = _field(release, 'generation')
    expected_workers = _field(release, 'expected_workers', 1)
    if isinstance(expected_workers, bool) or not isinstance(expected_workers, int) or expected_workers < 1:
        raise ValueError('expected_workers必须为正整数')
    hosts: dict[str, object] = {}
    plugins: dict[str, object] = {}
    for report in worker_reports:
        report_plugin = _field(report, 'plugin_id')
        worker_id = _field(report, 'worker_id')
        if report_plugin == RUNTIME_PLUGIN_ID:
            hosts[worker_id] = report
        elif report_plugin == plugin_id:
            plugins[worker_id] = report

    live_hosts = {
        worker_id: report
        for worker_id, report in hosts.items()
        if _field(report, 'state') != 'stopped' and _fresh(report, now=now, cutoff=cutoff)
    }
    stale = {
        worker_id
        for worker_id, report in hosts.items()
        if _field(report, 'state') != 'stopped' and not _fresh(report, now=now, cutoff=cutoff)
    }
    counts = {'healthy': 0, 'disabled': 0, 'mismatch': 0, 'missing': 0, 'failed': 0, 'stale': 0}
    for worker_id, host in live_hosts.items():
        state = _worker_state(
            host, plugins.get(worker_id), target_digest, generation, now=now, cutoff=cutoff, enabled=enabled
        )
        counts[state] += 1
        if state == 'stale':
            stale.add(worker_id)
    status = _release_status(target_digest, len(live_hosts), counts['healthy'], counts['failed'], expected_workers)
    if not enabled and target_digest:
        status = 'pending_restart'
        if len(live_hosts) >= expected_workers and counts['disabled'] == len(live_hosts):
            status = 'disabled'
        elif counts['disabled']:
            status = 'partial'
        elif counts['failed']:
            status = 'failed'
    return PluginReleaseSummary(
        plugin_id=plugin_id,
        target_digest=target_digest,
        generation=generation,
        status=status,
        restart_required=bool(target_digest) and status not in {'active', 'disabled'},
        expected_workers=expected_workers,
        live_workers=len(live_hosts),
        healthy_workers=counts['healthy'],
        disabled_workers=counts['disabled'],
        mismatch_workers=counts['mismatch'],
        stale_workers=len(stale),
        missing_workers=counts['missing'] + counts['stale'] + max(0, expected_workers - len(live_hosts)),
        failed_workers=counts['failed'],
        prepare_status=_field(release, 'prepare_status', 'idle'),
        last_error=_field(release, 'last_error'),
    )
