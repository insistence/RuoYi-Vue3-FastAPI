import asyncio
import re
import time
from contextlib import suppress
from typing import Any

from plugins.core.runtime.metrics import PluginMetricSnapshot, PluginRuntimeMetrics, aggregate_metric_snapshots
from utils.log_util import logger

METRICS_PUBLISH_SECONDS = 15
METRICS_TTL_SECONDS = 60
METRICS_IO_TIMEOUT_SECONDS = 2
MAX_METRICS_SNAPSHOT_BYTES = 512 * 1024
MAX_METRICS_WORKERS = 64
MAX_CLOCK_SKEW_SECONDS = 5


class PluginMetricsReporter:
    """
    将进程累计指标定期发布到 Redis；观测失败不影响插件业务或发布状态。
    """

    def __init__(self, metrics: PluginRuntimeMetrics) -> None:
        """
        初始化尚未连接外部存储的指标报告器。

        :param metrics: 当前 worker 的本地指标收集器
        :return: None
        """
        self.metrics = metrics
        self.redis: Any = None
        self.namespace = ''
        self.task: asyncio.Task[None] | None = None
        self.publication_failed = False

    @property
    def key(self) -> str:
        """
        返回当前 worker 的独占快照键。

        :return: 带运行环境前缀的 Redis 键
        """
        return f'{self.namespace}:{self.metrics.worker_id}'

    def start(self, redis: Any, namespace: str) -> None:
        """
        在宿主启动成功后启用采样，前缀跟随宿主启动协调配置实现环境隔离。

        :param redis: 当前宿主 Redis 客户端
        :param namespace: 当前环境的指标命名空间
        :return: None
        """
        if self.task is not None:
            return
        self.redis = redis
        self.namespace = namespace
        if redis is not None:
            self.task = asyncio.create_task(self._run(), name=f'plugin-metrics-{self.metrics.worker_id}')

    async def publish(self) -> None:
        """
        发布有界快照并设置过期时间，避免异常退出的进程永久计入汇总。

        :return: None
        """
        if self.redis is None:
            return
        try:
            snapshot = self.metrics.snapshot().model_dump_json(by_alias=True).encode('utf-8')
            if len(snapshot) > MAX_METRICS_SNAPSHOT_BYTES:
                raise ValueError('插件指标快照超过大小限制')
            await asyncio.wait_for(
                self.redis.set(self.key, snapshot, ex=METRICS_TTL_SECONDS), METRICS_IO_TIMEOUT_SECONDS
            )
        except Exception:
            if not self.publication_failed:
                logger.warning('插件指标发布不可用，保留本地指标；远程快照将按 TTL 过期')
            self.publication_failed = True
        else:
            self.publication_failed = False

    async def _run(self) -> None:
        """
        定期采样，不在请求路径同步写入 Redis。

        :return: None
        """
        while True:
            await asyncio.sleep(METRICS_PUBLISH_SECONDS)
            await self.publish()

    async def stop(self) -> None:
        """
        取消采样任务并仅移除本 worker 的快照；清理失败时依赖 TTL。

        :return: None
        """
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        if self.redis is not None:
            with suppress(Exception):
                await asyncio.wait_for(self.redis.delete(self.key), METRICS_IO_TIMEOUT_SECONDS)

    async def _read_cluster(self) -> tuple[list[PluginMetricSnapshot], int, int, bool]:
        """
        有界读取当前命名空间的有效快照，拒绝损坏、过期及不匹配的进程身份。

        :return: 快照列表、无效数量、过期数量以及是否达到 worker 上限
        """
        keys = []
        limited = False
        invalid = 0
        stale = 0
        scanned = 0
        async for raw_key in self.redis.scan_iter(match=f'{self.namespace}:*', count=100):
            if scanned >= MAX_METRICS_WORKERS:
                limited = True
                break
            scanned += 1
            try:
                key = raw_key.decode('utf-8') if isinstance(raw_key, bytes) else raw_key
            except UnicodeError:
                invalid += 1
                continue
            if not isinstance(key, str) or not re.fullmatch(rf'{re.escape(self.namespace)}:[0-9a-f]{{32}}', key):
                invalid += 1
                continue
            if key not in keys:
                keys.append(key)
        values = await self.redis.mget(keys) if keys else []
        snapshots = []
        now = time.time()
        for key, raw in zip(keys, values, strict=True):
            if raw is None:
                continue
            value = raw.encode('utf-8') if isinstance(raw, str) else raw
            if not isinstance(value, bytes) or len(value) > MAX_METRICS_SNAPSHOT_BYTES:
                invalid += 1
                continue
            try:
                snapshot = PluginMetricSnapshot.model_validate_json(value)
            except ValueError:
                invalid += 1
                continue
            if snapshot.worker_id != key.rsplit(':', 1)[1]:
                invalid += 1
                continue
            age = now - snapshot.collected_at
            if age > METRICS_TTL_SECONDS or age < -MAX_CLOCK_SKEW_SECONDS:
                stale += 1
                continue
            snapshots.append(snapshot)
        return snapshots, invalid, stale, limited

    async def read(self, plugin_id: str | None = None) -> dict[str, Any]:
        """
        汇总当前可观测进程；Redis 不可用时明确降级为当前 worker 的数据。

        :param plugin_id: 可选的插件 ID 过滤条件
        :return: 采样范围、worker 明细和按版本分组的累计指标
        """
        snapshots = []
        invalid = stale = 0
        limited = False
        cluster_available = False
        if self.redis is not None:
            try:
                snapshots, invalid, stale, limited = await asyncio.wait_for(
                    self._read_cluster(), METRICS_IO_TIMEOUT_SECONDS
                )
                cluster_available = True
            except Exception:
                # 查询失败不能把当前 worker 的计数伪装成集群汇总。
                snapshots = []
        snapshots = [snapshot for snapshot in snapshots if snapshot.worker_id != self.metrics.worker_id]
        snapshots.append(self.metrics.snapshot())
        workers = [
            {
                'workerId': snapshot.worker_id,
                'collectedAt': snapshot.collected_at,
                'droppedSeries': snapshot.dropped_series,
                'series': [
                    series.to_payload()
                    for series in snapshot.series
                    if plugin_id is None or series.plugin_id == plugin_id
                ],
            }
            for snapshot in sorted(snapshots, key=lambda item: item.worker_id)
        ]
        workers = [worker for worker in workers if worker['series']]
        return {
            'ok': True,
            'supported': True,
            'scope': 'reporting_workers' if cluster_available else 'current_worker',
            'clusterAvailable': cluster_available,
            'currentWorkerId': self.metrics.worker_id,
            'observedWorkers': len(workers),
            'sampleIntervalSeconds': METRICS_PUBLISH_SECONDS,
            'sampleTtlSeconds': METRICS_TTL_SECONDS,
            'invalidSnapshots': invalid,
            'staleSnapshots': stale,
            'workerLimitReached': limited,
            'latencyScope': 'complete_request_or_job',
            'workers': workers,
            'series': aggregate_metric_snapshots(snapshots, plugin_id),
        }
