import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, ValidationInfo, field_validator, model_validator
from pydantic.alias_generators import to_camel

from plugins.core.runtime.task_cleanup import pending_plugin_tasks

if TYPE_CHECKING:
    from plugins.core.runtime.explicit import ExplicitPluginRuntime, LoadedExplicitPlugin
    from plugins.core.runtime.health import PluginHealthResult
    from plugins.core.runtime.metrics import PluginMetricSeries

MAX_DIAGNOSTIC_PLUGINS = 1024


class _DiagnosticModel(BaseModel):
    """只接收有界的宿主观测字段，禁止混入插件业务对象或额外字段。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra='forbid', strict=True)

    @model_validator(mode='before')
    @classmethod
    def require_complete_wire_fields(cls, value: Any, info: ValidationInfo) -> Any:
        """
        读取远端快照时要求每个已声明字段显式存在，不把缺失观测补成默认零值。

        :param value: 当前层级待校验的输入，远端协议只接受 JSON 对象
        :param info: 校验上下文，仅 require_complete_snapshot 开启时要求完整协议字段
        :return: 字段完整的原始输入；本地构造仍保留模型默认值
        """
        if not isinstance(info.context, Mapping) or not info.context.get('require_complete_snapshot'):
            return value
        if not isinstance(value, Mapping):
            raise ValueError('远端运行诊断必须使用完整 JSON 对象')
        missing = [
            field.alias or name for name, field in cls.model_fields.items() if (field.alias or name) not in value
        ]
        if missing:
            raise ValueError(f'远端运行诊断缺少协议字段：{", ".join(missing)}')
        return value


class PluginActivationHealth(_DiagnosticModel):
    """最近一次激活健康检查摘要，不表示持续健康且不保存插件返回的描述或详情。"""

    status: Literal['unknown', 'healthy', 'unhealthy', 'error', 'timeout'] = 'unknown'
    checked_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PluginLifespanDiagnostic(_DiagnosticModel):
    """宿主管理的生命周期状态；正常存活的任务不等于等待取消的任务。"""

    managed: bool
    started: bool
    ready: bool
    task_active: bool


class PluginConnectionDiagnostic(_DiagnosticModel):
    """已经接受的 WebSocket 和已开始响应的 SSE 连接数量。"""

    sse: NonNegativeInt = 0
    websocket: NonNegativeInt = 0


class PluginConfigDiagnostic(_DiagnosticModel):
    """不透明配置版本；按需读取完成不代表插件业务已经应用新配置。"""

    startup_revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    last_read_revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    last_read_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PluginDiagnosticError(_DiagnosticModel):
    """宿主指标中最近错误的关联字段，不包含异常消息或请求内容。"""

    error_type: str = Field(min_length=1, max_length=80)
    request_id: str | None = Field(default=None, max_length=128)
    at: float = Field(ge=0, allow_inf_nan=False)


class PluginRuntimeDiagnostic(_DiagnosticModel):
    """一个 worker 已加载的显式插件状态；身份始终来自实际加载对象。"""

    plugin_id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,63}$')
    version: str = Field(max_length=128)
    digest: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    generation: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    active: bool
    ready: bool
    closing: bool
    lifespan: PluginLifespanDiagnostic | None = None
    connections: PluginConnectionDiagnostic = Field(default_factory=PluginConnectionDiagnostic)
    active_jobs: NonNegativeInt = 0
    pending_connection_tasks: NonNegativeInt = 0
    pending_job_tasks: NonNegativeInt = 0
    activation_health: PluginActivationHealth = Field(default_factory=PluginActivationHealth)
    config: PluginConfigDiagnostic = Field(default_factory=PluginConfigDiagnostic)
    last_error: PluginDiagnosticError | None = None


class PluginRuntimeDiagnosticSnapshot(_DiagnosticModel):
    """
    当前进程的只读诊断快照，与已有运行指标协议独立。

    worker_pending_cleanup_tasks 是宿主通用回收器与全部插件连接回收器的去重总数，
    包含各插件的待回收子项，不能与它们再次相加。未受宿主跟踪的业务任务不在此范围内。
    """

    schema_version: Literal[1] = 1
    worker_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    collected_at: float = Field(ge=0, allow_inf_nan=False)
    plugins: list[PluginRuntimeDiagnostic] = Field(default_factory=list, max_length=MAX_DIAGNOSTIC_PLUGINS)
    worker_pending_cleanup_tasks: NonNegativeInt = 0
    dropped_plugins: NonNegativeInt = 0

    @field_validator('schema_version', mode='before')
    @classmethod
    def validate_schema_version(cls, value: Any) -> int:
        """
        要求显式协议版本为整数 1，拒绝布尔值和数值相等的浮点值。

        :param value: 显式提供的协议版本
        :return: 通过严格类型与版本检查的整数
        """
        if type(value) is not int or value != 1:
            raise ValueError('schemaVersion 必须为整数 1')
        return value

    @model_validator(mode='after')
    def validate_unique_plugins(self) -> 'PluginRuntimeDiagnosticSnapshot':
        """
        拒绝单个 worker 在同一快照中重复报告同一插件。

        :return: 插件身份唯一的诊断快照
        """
        if len({plugin.plugin_id for plugin in self.plugins}) != len(self.plugins):
            raise ValueError('插件运行诊断快照包含重复插件 ID')
        return self


def activation_health_observation(result: 'PluginHealthResult') -> PluginActivationHealth:
    """
    将激活检查结果转换为固定状态集合，丢弃插件提供的任意文本及详情。

    :param result: 激活期间由宿主完成的健康检查结果
    :return: 带完成时间和耗时的安全摘要
    """
    status = 'healthy' if result.ok else result.status if result.status in {'timeout', 'error'} else 'unhealthy'
    return PluginActivationHealth(status=status, checked_at=time.time(), duration_ms=result.duration_ms)


def _recent_errors(runtime: 'ExplicitPluginRuntime') -> dict[str, PluginDiagnosticError]:
    """
    从已有指标中选取每个插件最近的错误，不读取异常正文或业务内容。

    :param runtime: 当前 worker 的显式插件运行时
    :return: 按插件 ID 索引的错误关联摘要
    """
    latest: dict[str, PluginMetricSeries] = {}
    for series in runtime.metrics.series.values():
        if series.last_error_at is None or not series.last_error_type:
            continue
        previous = latest.get(series.plugin_id)
        if previous is None or series.last_error_at > previous.last_error_at:
            latest[series.plugin_id] = series
    return {
        plugin_id: PluginDiagnosticError(
            error_type=series.last_error_type,
            request_id=series.last_error_request_id,
            at=series.last_error_at,
        )
        for plugin_id, series in latest.items()
    }


def _plugin_observation(
    runtime: 'ExplicitPluginRuntime', loaded: 'LoadedExplicitPlugin', last_error: PluginDiagnosticError | None
) -> PluginRuntimeDiagnostic:
    """
    复制单个已加载插件的宿主状态，不执行插件代码或外部查询。

    :param runtime: 当前 worker 的显式插件运行时
    :param loaded: 已加载的插件资源记录
    :param last_error: 已从宿主指标选取的最近错误
    :return: 不含任务对象、配置明文或请求数据的插件诊断
    """
    plugin = loaded.plugin.discovered_plugin
    manager = loaded.gateway.connections if loaded.gateway is not None else None
    binding = loaded.jobs
    job_tasks = frozenset(task for task in binding.tasks if not task.done()) if binding is not None else frozenset()
    closing = runtime._closing or bool(manager and manager.closing) or bool(binding and binding.closing)
    lifespan = loaded.lifespan
    observation = runtime.metrics.configurations.get(loaded.plugin.plugin_id)
    return PluginRuntimeDiagnostic(
        plugin_id=loaded.plugin.plugin_id,
        version=plugin.manifest.version,
        digest=plugin.artifact_digest,
        generation=plugin.artifact_generation,
        active=loaded.active,
        ready=loaded.active and not closing and (lifespan is None or lifespan.ready),
        closing=closing,
        lifespan=(
            PluginLifespanDiagnostic(
                managed=lifespan.managed,
                started=lifespan.started,
                ready=lifespan.ready,
                task_active=lifespan.has_pending_task,
            )
            if lifespan is not None
            else None
        ),
        connections=PluginConnectionDiagnostic(**manager.connection_counts())
        if manager
        else PluginConnectionDiagnostic(),
        active_jobs=len(job_tasks),
        pending_connection_tasks=len(manager.pending_tasks()) if manager else 0,
        pending_job_tasks=len(pending_plugin_tasks(job_tasks)),
        activation_health=loaded.activation_health.model_copy(deep=True),
        config=PluginConfigDiagnostic(
            startup_revision=observation.startup_revision if observation else loaded.host.config_revision,
            last_read_revision=observation.last_read_revision if observation else None,
            last_read_at=observation.last_read_at if observation else None,
        ),
        last_error=last_error,
    )


def collect_runtime_diagnostics(runtime: 'ExplicitPluginRuntime') -> PluginRuntimeDiagnosticSnapshot:
    """
    在当前事件循环采样宿主已跟踪的插件资源，读取期间不触发回调或改变取消状态。

    :param runtime: 当前 worker 的显式插件运行时
    :return: 有界且独立于后续资源变化的诊断快照
    """
    pending = set(pending_plugin_tasks())
    for loaded in runtime.loaded.values():
        if loaded.gateway is not None:
            pending.update(loaded.gateway.connections.pending_tasks())
    errors = _recent_errors(runtime)
    selected = sorted(runtime.loaded.items())[:MAX_DIAGNOSTIC_PLUGINS]
    return PluginRuntimeDiagnosticSnapshot(
        worker_id=runtime.metrics.worker_id,
        collected_at=time.time(),
        plugins=[_plugin_observation(runtime, loaded, errors.get(plugin_id)) for plugin_id, loaded in selected],
        worker_pending_cleanup_tasks=len(pending),
        dropped_plugins=max(0, len(runtime.loaded) - len(selected)),
    )
