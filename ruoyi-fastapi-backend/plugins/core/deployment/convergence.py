import math
import re
from asyncio import ensure_future, gather, sleep, wait
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any

from plugins.core.deployment.state import RUNTIME_PLUGIN_ID, aggregate_release
from plugins.core.utils import validate_plugin_id_value
from utils.time_util import TimezoneUtil

STATUS_READ_TIMEOUT_SECONDS = 10
COUNT_FIELDS = (
    'liveWorkers',
    'healthyWorkers',
    'disabledWorkers',
    'mismatchWorkers',
    'staleWorkers',
    'missingWorkers',
    'failedWorkers',
)
SUMMARY_FIELDS = (
    'pluginId',
    'targetDigest',
    'generation',
    'expectedWorkers',
    'enabled',
    'status',
    'restartRequired',
    *COUNT_FIELDS,
    'prepareStatus',
)
REASONS = {
    'converged': '全部有效存活 worker 已加载固定发布目标且达到预期数量',
    'not_converged': '固定发布目标尚未在全部有效存活 worker 中就绪',
    'timeout': '等待固定发布目标收敛超时',
    'target_missing': '请求的插件没有发布目标',
    'target_changed': '发布目标、代际或预期 worker 数量已变化，停止等待',
    'target_disabled': '固定发布目标已停用，不能通过启用状态验收',
    'worker_failed': '有效存活 worker 已报告运行或目标加载失败',
    'unavailable': '发布状态暂不可读取，未使用历史观测判定成功',
    'invalid_observation': '发布状态结构或 worker 报告不一致，无法判定收敛',
}


@dataclass(frozen=True)
class _ReleaseTarget:
    """调用方固定的插件、制品、代际和预期容量，轮询期间不跟随数据库目标变化。"""

    plugin_id: str
    digest: str
    generation: str
    expected_workers: int

    def __post_init__(self) -> None:
        """
        校验固定发布身份及容量，拒绝布尔值冒充预期 worker 数量。

        :return: None
        :raises ValueError: 插件 ID、摘要、代际或预期数量不合法
        """
        validate_plugin_id_value(self.plugin_id)
        if not _hex(self.digest, 64):
            raise ValueError('制品 digest 必须是64位小写 SHA256')
        if not _hex(self.generation, 32):
            raise ValueError('发布代际必须是32位小写 UUID 十六进制字符串')
        if not _integer(self.expected_workers, minimum=1):
            raise ValueError('预期 worker 数量必须是正整数')

    def to_payload(self) -> dict[str, Any]:
        """
        序列化固定目标，不使用后续查询结果覆盖调用方身份。

        :return: 使用管理端字段名的固定发布目标
        """
        return {
            'pluginId': self.plugin_id,
            'digest': self.digest,
            'generation': self.generation,
            'expectedWorkers': self.expected_workers,
        }


def _hex(value: object, length: int) -> bool:
    """
    判断标识是否为指定长度的小写十六进制字符串。

    :param value: 待检查标识
    :param length: 标识要求的字符数量
    :return: 标识是否合法
    """
    return isinstance(value, str) and re.fullmatch(rf'[0-9a-f]{{{length}}}', value) is not None


def _integer(value: object, *, minimum: int = 0) -> bool:
    """
    校验真实整数及其下界，拒绝布尔类型。

    :param value: 待检查数值
    :param minimum: 允许的最小整数
    :return: 数值是否为满足下界的整数
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _seconds(value: object, *, allow_zero: bool = False) -> bool:
    """
    校验有限的等待时间，不接受负数、无穷或非数值。

    :param value: 待检查秒数
    :param allow_zero: 是否允许零秒作为单次断言
    :return: 时间参数是否合法
    """
    try:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and (value >= 0 if allow_zero else value > 0)
        )
    except OverflowError:
        return False


def _valid_summary(summary: Mapping[str, Any]) -> bool:
    """
    验证发布摘要的必需字段和基本计数关系，避免损坏摘要被当作成功。

    :param summary: 发布状态查询返回的单个插件摘要
    :return: 摘要是否具备可安全比较的身份和计数
    """
    if (
        not all(field in summary for field in SUMMARY_FIELDS)
        or not _integer(summary.get('expectedWorkers'), minimum=1)
        or not _hex(summary.get('generation'), 32)
        or (summary.get('targetDigest') is not None and not _hex(summary['targetDigest'], 64))
        or not isinstance(summary.get('enabled'), bool)
        or not isinstance(summary.get('restartRequired'), bool)
        or not isinstance(summary.get('status'), str)
        or summary['status'] not in {'no_target', 'active', 'disabled', 'partial', 'failed', 'pending_restart'}
        or not isinstance(summary.get('prepareStatus'), str)
        or summary['prepareStatus'] not in {'idle', 'preparing', 'prepared', 'failed'}
        or any(not _integer(summary.get(field)) for field in COUNT_FIELDS)
    ):
        return False
    live = summary['liveWorkers']
    accounted = sum(
        summary[field] for field in ('healthyWorkers', 'disabledWorkers', 'mismatchWorkers', 'failedWorkers')
    )
    if accounted > live or summary['missingWorkers'] != max(live, summary['expectedWorkers']) - accounted:
        return False
    matched = summary['healthyWorkers'] if summary['enabled'] else summary['disabledWorkers']
    if summary['targetDigest'] is None:
        expected_status = 'no_target'
    elif live >= summary['expectedWorkers'] and matched == live:
        expected_status = 'active' if summary['enabled'] else 'disabled'
    elif matched:
        expected_status = 'partial'
    elif summary['failedWorkers']:
        expected_status = 'failed'
    else:
        expected_status = 'pending_restart'
    expected_restart = summary['targetDigest'] is not None and expected_status not in {'active', 'disabled'}
    return (
        summary['status'] == expected_status
        and summary['restartRequired'] == expected_restart
        and (expected_status not in {'active', 'disabled'} or summary['missingWorkers'] == 0)
    )


def _worker_reports(raw: object, plugin_id: str) -> list[dict[str, Any]]:
    """
    严格验证 worker 身份、重复记录和必需字段，再转换为现有聚合器的输入。

    :param raw: 发布状态查询返回的 worker 报告列表
    :param plugin_id: 本次唯一允许的业务插件 ID
    :return: 不包含错误正文的内部字段报告列表
    :raises ValueError: 报告字段缺失、身份重复或数据不一致
    """
    if not isinstance(raw, list):
        raise ValueError('worker 报告列表不可用')
    reports = []
    seen = set()
    for row in raw:
        if (
            not isinstance(row, Mapping)
            or not _hex(row.get('workerId'), 32)
            or not all(
                field in row for field in ('pluginId', 'digest', 'version', 'generation', 'state', 'heartbeatTime')
            )
        ):
            raise ValueError('worker 身份无效')
        row_plugin = row.get('pluginId')
        identity = (row['workerId'], row_plugin)
        if row_plugin not in {RUNTIME_PLUGIN_ID, plugin_id} or identity in seen:
            raise ValueError('worker 报告重复或插件身份不符')
        if row.get('state') not in {'starting', 'ready', 'failed', 'stopped'}:
            raise ValueError('worker 状态无效')
        heartbeat = row.get('heartbeatTime')
        if not isinstance(heartbeat, str):
            raise ValueError('worker 心跳缺失')
        heartbeat = datetime.fromisoformat(heartbeat)
        if heartbeat.tzinfo is None or heartbeat.utcoffset() is None:
            raise ValueError('worker 心跳必须携带时区')
        digest, generation = row.get('digest'), row.get('generation')
        if (
            (digest is not None and not _hex(digest, 64))
            or (generation is not None and not _hex(generation, 32))
            or (
                row_plugin == RUNTIME_PLUGIN_ID
                and any(row.get(field) is not None for field in ('digest', 'version', 'generation'))
            )
        ):
            raise ValueError('worker 制品身份无效')
        seen.add(identity)
        reports.append(
            {
                'worker_id': row['workerId'],
                'plugin_id': row_plugin,
                'state': row['state'],
                'heartbeat_time': heartbeat,
                'artifact_digest': digest,
                'generation': generation,
            }
        )
    return reports


def _evaluate(payload: object, target: _ReleaseTarget, worker_ttl_seconds: float) -> tuple[str, dict[str, Any] | None]:
    """
    在查询返回时重新校验心跳，只对固定目标作出收敛判定。

    :param payload: 当前只读状态查询结果
    :param target: 调用方固定的发布身份
    :param worker_ttl_seconds: 发布 worker 的有效心跳秒数
    :return: 判定原因与经过字段白名单过滤的最近摘要
    """
    if not isinstance(payload, Mapping) or payload.get('ok') is not True:
        return (
            'unavailable' if isinstance(payload, Mapping) and payload.get('ok') is False else 'invalid_observation'
        ), None
    rows = payload.get('releases')
    if not isinstance(rows, list) or any(
        not isinstance(row, Mapping) or not isinstance(row.get('pluginId'), str) for row in rows
    ):
        return 'invalid_observation', None
    matches = [row for row in rows if row.get('pluginId') == target.plugin_id]
    if not matches:
        return 'target_missing', None
    if len(matches) != 1 or not _valid_summary(matches[0]):
        return 'invalid_observation', None
    summary = matches[0]
    observed = {key: summary[key] for key in SUMMARY_FIELDS}
    if summary['targetDigest'] is None:
        return 'target_missing', observed
    if (
        summary['targetDigest'] != target.digest
        or summary['generation'] != target.generation
        or summary['expectedWorkers'] != target.expected_workers
    ):
        return 'target_changed', observed
    if not summary['enabled']:
        return 'target_disabled', observed
    try:
        reports = _worker_reports(payload.get('workers'), target.plugin_id)
        current = aggregate_release(
            {
                'plugin_id': target.plugin_id,
                'target_digest': target.digest,
                'generation': target.generation,
                'expected_workers': target.expected_workers,
                'prepare_status': summary['prepareStatus'],
            },
            reports,
            now=TimezoneUtil.utc_now(),
            ttl_seconds=worker_ttl_seconds,
        ).to_payload()
    except (TypeError, ValueError):
        return 'invalid_observation', observed
    observed.update({key: current[key] for key in ('status', 'restartRequired', *COUNT_FIELDS)})
    if current['failedWorkers']:
        return 'worker_failed', observed
    return ('converged' if current['status'] == 'active' else 'not_converged'), observed


def _result(
    target: _ReleaseTarget,
    reason: str,
    observed: dict[str, Any] | None,
    attempts: int,
    started: float,
    timeout: float,
    interval: float,
) -> dict[str, Any]:
    """
    构建不会泄露连接错误或 worker 异常正文的固定结果契约。

    :param target: 调用方固定的发布身份
    :param reason: 收敛或停止等待的固定原因
    :param observed: 最近一次可解释的发布摘要
    :param attempts: 已发起的只读查询次数
    :param started: 等待开始的单调时刻
    :param timeout: 调用方配置的总体等待秒数
    :param interval: 调用方配置的轮询间隔秒数
    :return: 可由 CLI 直接用于成功或非零退出的发布等待结果
    """
    return {
        'ok': reason == 'converged',
        'operation': 'release_wait',
        'reason': reason,
        'message': REASONS[reason],
        'target': target.to_payload(),
        'lastObserved': observed,
        'attempts': attempts,
        'elapsedSeconds': round(max(0, monotonic() - started), 3),
        'timeoutSeconds': timeout,
        'intervalSeconds': interval,
    }


async def _read_once(
    status_reader: Callable[[str], Awaitable[dict[str, Any]]], plugin_id: str, read_limit: float
) -> tuple[bool, object]:
    """
    显式记录读取预算是否耗尽，取消后的迟到结果不能覆盖已发生的超时。

    :param status_reader: 发布状态只读查询函数
    :param plugin_id: 固定查询的插件 ID
    :param read_limit: 本轮读取预算秒数
    :return: 是否在预算内完成以及正常完成时的查询结果
    :raises Exception: 查询自身异常，包含查询主动抛出的超时异常
    :raises asyncio.CancelledError: 外部取消，清理查询任务后继续传播
    """
    task = ensure_future(status_reader(plugin_id))
    try:
        done, _ = await wait({task}, timeout=read_limit)
        if task not in done:
            return False, None
        return True, task.result()
    finally:
        if not task.done():
            task.cancel()
        await gather(task, return_exceptions=True)


async def wait_for_release(
    status_reader: Callable[[str], Awaitable[dict[str, Any]]],
    plugin_id: str,
    digest: str,
    *,
    expected_generation: str,
    expected_workers: int,
    worker_ttl_seconds: float,
    timeout_seconds: float = 300,
    poll_interval_seconds: float = 2,
) -> dict[str, Any]:
    """
    只读等待固定发布目标；零超时执行一次断言，取消保持协程取消语义。

    :param status_reader: 每轮创建新查询会话的发布状态读取函数
    :param plugin_id: 固定验收的插件 ID
    :param digest: 固定验收的制品 SHA256 摘要
    :param expected_generation: 固定验收的发布代际
    :param expected_workers: 必须与发布记录一致的预期 worker 数量
    :param worker_ttl_seconds: 发布 worker 的有效心跳秒数
    :param timeout_seconds: 总体等待秒数，零表示一次断言
    :param poll_interval_seconds: 尚未收敛时再次读取前的间隔秒数
    :return: 收敛成功或明确失败原因及最后可用状态
    :raises ValueError: 固定身份或等待参数不合法
    :raises asyncio.CancelledError: 调用方取消当前等待，取消不转换成成功或继续轮询
    """
    target = _ReleaseTarget(plugin_id, digest, expected_generation, expected_workers)
    if not _seconds(timeout_seconds, allow_zero=True):
        raise ValueError('等待超时必须是有限的非负秒数')
    if not _seconds(poll_interval_seconds) or not _seconds(worker_ttl_seconds):
        raise ValueError('轮询间隔和心跳 TTL 必须是有限的正秒数')
    started = monotonic()
    deadline = started + timeout_seconds
    attempts = 0
    observed = None
    while True:
        remaining = deadline - monotonic() if timeout_seconds else STATUS_READ_TIMEOUT_SECONDS
        if remaining <= 0:
            return _result(target, 'timeout', observed, attempts, started, timeout_seconds, poll_interval_seconds)
        attempts += 1
        try:
            completed, payload = await _read_once(status_reader, plugin_id, min(STATUS_READ_TIMEOUT_SECONDS, remaining))
        except Exception:
            return _result(target, 'unavailable', observed, attempts, started, timeout_seconds, poll_interval_seconds)
        if not completed:
            # asyncio 定时器可能早于粗粒度单调时钟触发，按预算来源而非触发后时钟归类。
            reason = 'timeout' if timeout_seconds and remaining <= STATUS_READ_TIMEOUT_SECONDS else 'unavailable'
            return _result(target, reason, observed, attempts, started, timeout_seconds, poll_interval_seconds)
        try:
            reason, current = _evaluate(payload, target, worker_ttl_seconds)
        except (KeyError, TypeError, ValueError, OverflowError):
            # 外部状态损坏不得泄漏内部异常，也不能继承上次成功判断。
            reason, current = 'invalid_observation', None
        observed = current if current is not None else observed
        if timeout_seconds and monotonic() >= deadline:
            reason = 'timeout'
        if reason != 'not_converged' or not timeout_seconds:
            return _result(target, reason, observed, attempts, started, timeout_seconds, poll_interval_seconds)
        await sleep(min(poll_interval_seconds, max(0, deadline - monotonic())))
