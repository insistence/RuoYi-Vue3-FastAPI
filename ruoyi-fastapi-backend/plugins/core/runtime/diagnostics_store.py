import asyncio
import re
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from redis.client import NEVER_DECODE

from common.constant import LockConstant
from plugins.core.runtime.diagnostics import PluginRuntimeDiagnosticSnapshot
from utils.log_util import logger

DIAGNOSTICS_PUBLISH_SECONDS = 15
DIAGNOSTICS_TTL_SECONDS = 60
DIAGNOSTICS_IO_TIMEOUT_SECONDS = 2
MAX_DIAGNOSTICS_SNAPSHOT_BYTES = 512 * 1024
MAX_DIAGNOSTICS_WORKERS = 64
MAX_CLOCK_SKEW_SECONDS = 5


def diagnostics_namespace(ready_key: str = LockConstant.PLUGIN_STARTUP_READY_KEY) -> str:
    """
    从宿主启动命名空间派生独立的诊断键空间，不改变现有指标协议。

    :param ready_key: 当前部署的宿主启动协调键
    :return: 带诊断协议版本的 Redis 命名空间
    """
    return f'{ready_key}:diagnostics:v1'


async def _read_snapshots(redis: Any, namespace: str) -> dict[str, Any]:
    """
    有界读取有效诊断快照，仅保留无敏感数据的损坏或过期 worker 标识。

    :param redis: 宿主或只读查询进程提供的 Redis 客户端
    :param namespace: 当前部署的诊断命名空间
    :return: 快照、无效及过期记录数量和查询是否达到上限
    """
    keys: list[str] = []
    invalid = 0
    limited = False
    scanned = 0
    async for raw_key in redis.scan_iter(match=f'{namespace}:*', count=100, **{NEVER_DECODE: True}):
        if scanned >= MAX_DIAGNOSTICS_WORKERS:
            limited = True
            break
        scanned += 1
        try:
            key = raw_key.decode('utf-8') if isinstance(raw_key, bytes) else raw_key
        except UnicodeError:
            invalid += 1
            continue
        if not isinstance(key, str) or not re.fullmatch(rf'{re.escape(namespace)}:[0-9a-f]{{32}}', key):
            invalid += 1
            continue
        if key not in keys:
            keys.append(key)
    # 共享客户端通常自动解码；逐命令保留字节，避免一个坏 UTF-8 值使整批观测失效。
    values = await redis.execute_command('MGET', *keys, **{NEVER_DECODE: True}) if keys else []
    snapshots = []
    invalid_worker_ids = []
    stale_worker_ids = []
    now = time.time()
    for key, raw in zip(keys, values, strict=True):
        worker_id = key.rsplit(':', 1)[1]
        if raw is None:
            # 扫描之后过期的键同样没有可用观测，不能补成零计数。
            stale_worker_ids.append(worker_id)
            continue
        value = raw.encode('utf-8') if isinstance(raw, str) else raw
        if not isinstance(value, bytes) or len(value) > MAX_DIAGNOSTICS_SNAPSHOT_BYTES:
            invalid += 1
            invalid_worker_ids.append(worker_id)
            continue
        try:
            snapshot = PluginRuntimeDiagnosticSnapshot.model_validate_json(
                value, context={'require_complete_snapshot': True}
            )
        except ValueError:
            invalid += 1
            invalid_worker_ids.append(worker_id)
            continue
        if snapshot.worker_id != worker_id:
            invalid += 1
            invalid_worker_ids.append(worker_id)
            continue
        age = now - snapshot.collected_at
        if age > DIAGNOSTICS_TTL_SECONDS or age < -MAX_CLOCK_SKEW_SECONDS:
            stale_worker_ids.append(worker_id)
            continue
        snapshots.append(snapshot)
    return {
        'snapshots': snapshots,
        'invalidSnapshots': invalid,
        'staleSnapshots': len(stale_worker_ids),
        'staleWorkerIds': sorted(stale_worker_ids),
        'invalidWorkerIds': sorted(invalid_worker_ids),
        'workerLimitReached': limited,
    }


async def read_runtime_diagnostics(redis: Any, namespace: str, plugin_id: str | None = None) -> dict[str, Any]:
    """
    只读取发布中的 worker 快照，不为 CLI 或管理进程创建虚假的本地采样。

    :param redis: Redis 客户端；不可用时为 None
    :param namespace: 当前部署的诊断命名空间
    :param plugin_id: 可选的插件过滤条件
    :return: 采样范围、时效、缺失原因和当前有效 worker 明细
    """
    result: dict[str, Any] = {
        'ok': True,
        'supported': True,
        'scope': 'unavailable',
        'clusterAvailable': False,
        'currentWorkerId': None,
        'observedWorkers': 0,
        'sampleIntervalSeconds': DIAGNOSTICS_PUBLISH_SECONDS,
        'sampleTtlSeconds': DIAGNOSTICS_TTL_SECONDS,
        'invalidSnapshots': 0,
        'staleSnapshots': 0,
        'staleWorkerIds': [],
        'invalidWorkerIds': [],
        'workerLimitReached': False,
        'workers': [],
    }
    if redis is None:
        return result
    try:
        cluster = await asyncio.wait_for(_read_snapshots(redis, namespace), DIAGNOSTICS_IO_TIMEOUT_SECONDS)
    except Exception:
        # 连接错误可能包含凭据或地址；诊断响应仅说明无法观测。
        return result
    snapshots = cluster.pop('snapshots')
    result.update(cluster, scope='reporting_workers', clusterAvailable=True)
    result['workers'] = [_worker_payload(snapshot, plugin_id, source='redis') for snapshot in snapshots]
    result['workers'].sort(key=lambda worker: worker['workerId'])
    result['observedWorkers'] = len(result['workers'])
    return result


def _worker_payload(snapshot: PluginRuntimeDiagnosticSnapshot, plugin_id: str | None, *, source: str) -> dict[str, Any]:
    """
    复制指定插件的观测值，同时保留真实 worker 的空插件列表。

    :param snapshot: 已通过身份与时效校验的宿主快照
    :param plugin_id: 可选的插件过滤条件
    :param source: 当前进程即时采样或 Redis 周期采样
    :return: 不含其他插件明细的独立 worker 负载
    """
    payload = snapshot.model_dump(by_alias=True)
    payload.pop('schemaVersion')
    payload['plugins'] = [item for item in payload['plugins'] if plugin_id is None or item['pluginId'] == plugin_id]
    payload.update(source=source, freshness='fresh', ageSeconds=max(0.0, time.time() - snapshot.collected_at))
    return payload


class PluginDiagnosticsReporter:
    """
    发布独立版本的运行诊断快照，查询故障时仅返回当前进程的真实观测。
    """

    def __init__(self, snapshot_provider: Callable[[], PluginRuntimeDiagnosticSnapshot], worker_id: str) -> None:
        """
        绑定宿主提供的纯内存采样函数，不执行插件回调。

        :param snapshot_provider: 复制当前运行时状态的同步函数
        :param worker_id: 与发布心跳和指标一致的进程标识
        :return: None
        """
        if re.fullmatch(r'[0-9a-f]{32}', worker_id) is None:
            raise ValueError('诊断 worker 标识无效')
        self.snapshot_provider = snapshot_provider
        self.worker_id = worker_id
        self.redis: Any = None
        self.namespace = ''
        self.task: asyncio.Task | None = None
        self.publication_failed = False
        self._stopping = False

    @property
    def key(self) -> str:
        """
        返回当前 worker 独占的快照键。

        :return: 当前 worker 的 Redis 键
        """
        return f'{self.namespace}:{self.worker_id}'

    def start(self, redis: Any, namespace: str) -> None:
        """
        启动有界周期采样，Redis 不可用时仍可读取当前进程。

        :param redis: 当前宿主 Redis 客户端
        :param namespace: 当前部署的诊断键空间
        :return: None
        """
        if self.task is not None:
            return
        self.redis = redis
        self.namespace = namespace
        self._stopping = False
        if redis is not None:
            self.task = asyncio.create_task(self._run(), name=f'plugin-diagnostics-{self.worker_id}')

    def _snapshot(self) -> PluginRuntimeDiagnosticSnapshot:
        """
        校验采样身份，防止误用其他 worker 的快照。

        :return: 当前 worker 的独立采样
        """
        snapshot = self.snapshot_provider()
        if snapshot.worker_id != self.worker_id:
            raise ValueError('诊断快照的 worker 标识不匹配')
        return snapshot

    async def publish(self) -> None:
        """
        发布有大小限制和 TTL 的运行快照，失败时保留本地查询能力。

        :return: None
        """
        if self.redis is None:
            return
        try:
            snapshot = self._snapshot().model_dump_json(by_alias=True).encode('utf-8')
            if len(snapshot) > MAX_DIAGNOSTICS_SNAPSHOT_BYTES:
                raise ValueError('运行诊断快照超过大小限制')
            await asyncio.wait_for(
                self.redis.set(self.key, snapshot, ex=DIAGNOSTICS_TTL_SECONDS), DIAGNOSTICS_IO_TIMEOUT_SECONDS
            )
        except Exception:
            if not self.publication_failed:
                logger.warning('插件运行诊断发布不可用，远程快照将按 TTL 过期')
            self.publication_failed = True
        else:
            self.publication_failed = False

    async def _run(self) -> None:
        """
        在启动后尽快发布，随后定期复制纯内存状态。

        :return: None
        """
        while not self._stopping:
            await self.publish()
            if not self._stopping:
                await asyncio.sleep(DIAGNOSTICS_PUBLISH_SECONDS)

    async def read(self, plugin_id: str | None = None) -> dict[str, Any]:
        """
        用当前即时采样替换本 worker 的 Redis 副本，避免重复计数。

        :param plugin_id: 可选的插件过滤条件
        :return: 具有明确来源和观测范围的运行诊断数据
        """
        result = await read_runtime_diagnostics(self.redis, self.namespace, plugin_id)
        result['currentWorkerId'] = self.worker_id
        try:
            local = _worker_payload(self._snapshot(), plugin_id, source='current_worker')
        except Exception:
            result['localSnapshotAvailable'] = False
            return result
        result['localSnapshotAvailable'] = True
        result['workers'] = [worker for worker in result['workers'] if worker['workerId'] != self.worker_id]
        result['workers'].append(local)
        result['workers'].sort(key=lambda worker: worker['workerId'])
        result['observedWorkers'] = len(result['workers'])
        result['scope'] = 'reporting_workers' if result['clusterAvailable'] else 'current_worker'
        return result

    async def stop(self) -> None:
        """
        停止周期发布并仅删除本 worker 的快照，删除失败时依赖 TTL。

        :return: None
        """
        self._stopping = True
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        if self.redis is not None and self.namespace:
            with suppress(Exception):
                await asyncio.wait_for(self.redis.delete(self.key), DIAGNOSTICS_IO_TIMEOUT_SECONDS)
