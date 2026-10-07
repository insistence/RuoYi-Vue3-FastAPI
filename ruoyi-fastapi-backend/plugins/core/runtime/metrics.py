import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, model_validator
from pydantic.alias_generators import to_camel
from starlette import status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from middlewares.trace_middleware.ctx import CTX_REQUEST_ID
from plugins.core.runtime.configuration import PluginConfigObservation
from plugins.core.sdk.request import current_plugin_request_id
from utils.log_util import logger

LATENCY_BUCKETS_MS = (10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)
MAX_METRIC_SERIES = 1024
MetricOutcome = Literal['succeeded', 'rejected', 'failed', 'cancelled']


class PluginMetricSeries(BaseModel):
    """
    一个 worker 上某插件和操作的累计指标，不包含请求参数、路径或用户数据。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra='forbid', strict=True)

    plugin_id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,63}$')
    version: str = Field(max_length=128)
    digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    generation: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    operation: str = Field(pattern=r'^(http|websocket|job:[a-z][a-z0-9_-]{0,63})$')
    started: NonNegativeInt = 0
    active: NonNegativeInt = 0
    succeeded: NonNegativeInt = 0
    rejected: NonNegativeInt = 0
    failed: NonNegativeInt = 0
    cancelled: NonNegativeInt = 0
    timed_out: NonNegativeInt = 0
    duration_sum_ms: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    duration_max_ms: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    latency_buckets: list[NonNegativeInt] = Field(
        default_factory=lambda: [0] * (len(LATENCY_BUCKETS_MS) + 1),
        min_length=len(LATENCY_BUCKETS_MS) + 1,
        max_length=len(LATENCY_BUCKETS_MS) + 1,
    )
    last_error_type: str | None = Field(default=None, max_length=80)
    last_error_request_id: str | None = Field(default=None, max_length=128)
    last_error_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_counters(self) -> 'PluginMetricSeries':
        """
        拒绝损坏或不一致的跨 worker 计数，避免将错误快照混入汇总。

        :return: 校验通过的指标序列
        """
        completed = self.succeeded + self.rejected + self.failed + self.cancelled
        if self.started != self.active + completed or sum(self.latency_buckets) != completed:
            raise ValueError('插件运行指标计数不一致')
        if self.timed_out > self.failed:
            raise ValueError('插件超时次数不能大于失败次数')
        return self

    def to_payload(self) -> dict[str, Any]:
        """
        计算便于管理端展示的平均值和直方图近似 P95。

        :return: 带派生耗时指标的 JSON 数据
        """
        completed = self.started - self.active
        percentile = 0.0
        target = math.ceil(completed * 0.95)
        seen = 0
        for boundary, count in zip((*LATENCY_BUCKETS_MS, self.duration_max_ms), self.latency_buckets, strict=True):
            seen += count
            if completed and seen >= target:
                percentile = float(boundary)
                break
        return {
            **self.model_dump(by_alias=True),
            'completed': completed,
            'failureRatePercent': round(self.failed * 100 / completed, 3) if completed else 0.0,
            'averageDurationMs': round(self.duration_sum_ms / completed, 3) if completed else 0.0,
            'p95UpperBoundMs': percentile,
        }


class PluginMetricSnapshot(BaseModel):
    """
    带采样时间和进程标识的有界指标快照。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra='forbid', strict=True)

    schema_version: Literal[1] = 1
    worker_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    collected_at: float = Field(ge=0, allow_inf_nan=False)
    dropped_series: NonNegativeInt = 0
    series: list[PluginMetricSeries] = Field(max_length=MAX_METRIC_SERIES)
    configurations: list[PluginConfigObservation] = Field(default_factory=list, max_length=MAX_METRIC_SERIES)


@dataclass
class PluginMetricInvocation:
    """
    单次调用的计时记录，结束方法幂等，避免异常分支重复计数。

    :param series: 当前操作的可变指标序列
    :param request_id: 本次调用的追踪标识
    :param clock: 单调计时函数
    :param started_at: 本次调用的开始时间
    :param finished: 是否已记录结束结果
    """

    series: PluginMetricSeries
    request_id: str
    clock: Callable[[], float]
    started_at: float
    finished: bool = False

    def finish(self, outcome: MetricOutcome, *, error_type: str | None = None, timed_out: bool = False) -> None:
        """
        完成调用统计，不保存错误消息或请求内容。

        :param outcome: 成功、客户端拒绝、失败或取消
        :param error_type: 可选的错误类型名称
        :param timed_out: 是否为超时失败
        :return: None
        """
        if self.finished:
            return
        self.finished = True
        duration = max(0.0, (self.clock() - self.started_at) * 1000)
        series = self.series
        series.active -= 1
        setattr(series, outcome, getattr(series, outcome) + 1)
        series.timed_out += int(timed_out and outcome == 'failed')
        series.duration_sum_ms += duration
        series.duration_max_ms = max(series.duration_max_ms, duration)
        bucket = next(
            (index for index, bound in enumerate(LATENCY_BUCKETS_MS) if duration <= bound), len(LATENCY_BUCKETS_MS)
        )
        series.latency_buckets[bucket] += 1
        if error_type:
            series.last_error_type = error_type[:80]
            series.last_error_request_id = self.request_id[:128]
            series.last_error_at = time.time()


@dataclass
class PluginRuntimeMetrics:
    """
    当前事件循环内的插件指标收集器，操作标签仅来自宿主和已声明任务。

    :param worker_id: 当前 worker 唯一标识
    :param clock: 单调计时函数
    :param identities: 插件加载版本、摘要和发布代际
    :param series: 按插件及操作索引的计数器
    :param dropped_series: 超出容量而未采集的调用数
    :param configurations: 当前进程的配置版本观测，不保存配置明文
    """

    worker_id: str = field(default_factory=lambda: uuid4().hex)
    clock: Callable[[], float] = time.perf_counter
    identities: dict[str, dict[str, Any]] = field(default_factory=dict)
    series: dict[tuple[str, str], PluginMetricSeries] = field(default_factory=dict)
    dropped_series: int = 0
    configurations: dict[str, PluginConfigObservation] = field(default_factory=dict)

    def register(self, plugin_id: str, version: str, digest: str | None, generation: str | None) -> None:
        """
        记录当前进程加载的插件身份，注册零值 HTTP 指标以显示尚无请求的插件。

        :param plugin_id: 插件 ID
        :param version: 实际加载版本
        :param digest: 签名制品摘要，源码插件为 None
        :param generation: 实际加载的发布代际
        :return: None
        """
        if plugin_id in self.identities:
            return
        if len(self.identities) >= MAX_METRIC_SERIES:
            self.dropped_series += 1
            return
        self.identities[plugin_id] = {
            'plugin_id': plugin_id,
            'version': version,
            'digest': digest,
            'generation': generation,
        }
        self._series_for(plugin_id, 'http')

    def _series_for(self, plugin_id: str, operation: str) -> PluginMetricSeries | None:
        """
        获取有界操作序列，不按 URL、用户或参数创建指标标签。

        :param plugin_id: 已注册插件 ID
        :param operation: 宿主定义的 HTTP、WebSocket 或任务操作
        :return: 可记录的指标序列，容量不足时为 None
        """
        key = (plugin_id, operation)
        if key in self.series:
            return self.series[key]
        if plugin_id not in self.identities or len(self.series) >= MAX_METRIC_SERIES:
            self.dropped_series += 1
            return None
        series = PluginMetricSeries(**self.identities[plugin_id], operation=operation)
        self.series[key] = series
        return series

    def begin(self, plugin_id: str, operation: str, request_id: str) -> PluginMetricInvocation | None:
        """
        开始一次调用，记录在途数量。

        :param plugin_id: 当前插件 ID
        :param operation: 当前操作标签
        :param request_id: 当前调用的追踪标识
        :return: 调用计时记录，超出容量时为 None
        """
        series = self._series_for(plugin_id, operation)
        if series is None:
            return None
        series.started += 1
        series.active += 1
        return PluginMetricInvocation(series, request_id, self.clock, self.clock())

    def snapshot(self) -> PluginMetricSnapshot:
        """
        在当前事件循环中复制全部计数，返回不受后续请求修改影响的快照。

        :return: 当前 worker 的指标快照
        """
        return PluginMetricSnapshot(
            worker_id=self.worker_id,
            collected_at=time.time(),
            dropped_series=self.dropped_series,
            series=[series.model_copy(deep=True) for _, series in sorted(self.series.items())],
            configurations=[config.model_copy(deep=True) for _, config in sorted(self.configurations.items())],
        )

    def log_fields(self, plugin_id: str, operation: str) -> dict[str, Any]:
        """
        提供结构化日志关联字段，不覆盖宿主已有的 worker 和请求追踪标识。

        :param plugin_id: 当前插件 ID
        :param operation: 当前操作标签
        :return: 可传给日志上下文的插件版本字段
        """
        return {
            'plugin_id': plugin_id,
            'plugin_worker_id': self.worker_id,
            'plugin_operation': operation,
            **{
                f'plugin_{key}': value
                for key, value in self.identities.get(plugin_id, {}).items()
                if key != 'plugin_id'
            },
        }


class PluginObservedASGI:
    """
    统计完整 HTTP 请求与 WebSocket 生命周期，并为插件日志关联宿主追踪上下文。
    """

    def __init__(self, app: ASGIApp, metrics: PluginRuntimeMetrics, plugin_id: str) -> None:
        """
        绑定待观测应用及所属插件。

        :param app: 包含权限门禁的插件应用或路由
        :param metrics: 当前 worker 的指标收集器
        :param plugin_id: 当前插件 ID
        :return: None
        """
        self.app = app
        self.metrics = metrics
        self.plugin_id = plugin_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        记录调用结果，在取消及异常分支仍正确减少在途数量。

        :param scope: 当前请求作用域
        :param receive: 请求消息接收器
        :param send: 响应消息发送器
        :return: None
        """
        if scope['type'] not in {'http', 'websocket'}:
            await self.app(scope, receive, send)
            return
        operation = scope['type']
        request_id = current_plugin_request_id()
        token = CTX_REQUEST_ID.set(request_id)
        invocation = self.metrics.begin(self.plugin_id, operation, request_id)
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        outcome: MetricOutcome = 'failed'
        error_type = None
        timed_out = False

        async def observed_send(message: Message) -> None:
            """
            观察状态码及 WebSocket 握手结果，不读取或复制响应体。

            :param message: 应用输出的 ASGI 消息
            :return: None
            """
            nonlocal status_code
            if message['type'] == 'http.response.start':
                status_code = message['status']
            elif message['type'] == 'websocket.accept':
                status_code = status.HTTP_200_OK
            elif message['type'] == 'websocket.close':
                if status_code != status.HTTP_200_OK:
                    status_code = status.HTTP_403_FORBIDDEN
                elif message.get('code', status.WS_1000_NORMAL_CLOSURE) not in {
                    status.WS_1000_NORMAL_CLOSURE,
                    status.WS_1001_GOING_AWAY,
                }:
                    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            await send(message)

        try:
            with logger.contextualize(**self.metrics.log_fields(self.plugin_id, operation)):
                await self.app(scope, receive, observed_send)
            outcome = (
                'succeeded'
                if status_code < status.HTTP_400_BAD_REQUEST
                else 'rejected'
                if status_code < status.HTTP_500_INTERNAL_SERVER_ERROR
                else 'failed'
            )
            timed_out = status_code == status.HTTP_504_GATEWAY_TIMEOUT
            error_type = f'HTTP{status_code}' if status_code >= status.HTTP_400_BAD_REQUEST else None
        except asyncio.CancelledError:
            outcome, error_type = 'cancelled', 'CancelledError'
            raise
        except Exception as exc:
            error_type = type(exc).__name__
            timed_out = isinstance(exc, (TimeoutError, asyncio.TimeoutError))
            raise
        finally:
            if invocation is not None:
                invocation.finish(outcome, error_type=error_type, timed_out=timed_out)
            CTX_REQUEST_ID.reset(token)


def aggregate_metric_snapshots(snapshots: list[PluginMetricSnapshot], plugin_id: str | None) -> list[dict[str, Any]]:
    """
    按插件版本、制品、代际和操作汇总，避免混合新旧版本的运行指标。

    :param snapshots: 当前有效 worker 的采样数据
    :param plugin_id: 可选的插件过滤条件
    :return: 包含平均耗时和近似 P95 的汇总序列
    """
    groups: dict[tuple[Any, ...], PluginMetricSeries] = {}
    for snapshot in snapshots:
        for series in snapshot.series:
            if plugin_id is not None and series.plugin_id != plugin_id:
                continue
            key = (series.plugin_id, series.version, series.digest, series.generation, series.operation)
            if key not in groups:
                groups[key] = series.model_copy(deep=True)
                continue
            total = groups[key]
            for name in (
                'started',
                'active',
                'succeeded',
                'rejected',
                'failed',
                'cancelled',
                'timed_out',
                'duration_sum_ms',
            ):
                setattr(total, name, getattr(total, name) + getattr(series, name))
            total.duration_max_ms = max(total.duration_max_ms, series.duration_max_ms)
            total.latency_buckets = [
                left + right for left, right in zip(total.latency_buckets, series.latency_buckets, strict=True)
            ]
            if (series.last_error_at or 0) > (total.last_error_at or 0):
                total.last_error_at = series.last_error_at
                total.last_error_type = series.last_error_type
                total.last_error_request_id = series.last_error_request_id
    return [groups[key].to_payload() for key in sorted(groups, key=lambda value: tuple(part or '' for part in value))]
