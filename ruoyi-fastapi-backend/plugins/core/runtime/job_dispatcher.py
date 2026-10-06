import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from middlewares.trace_middleware.ctx import CTX_REQUEST_ID
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.entrypoint import PluginEntrypointLoader
from plugins.core.runtime.metrics import MetricOutcome, PluginRuntimeMetrics
from plugins.core.runtime.route_guard import PluginRouteStateGateway
from plugins.core.sdk import PluginHostContext, PluginTaskContext, await_plugin_callback
from utils.log_util import logger

DISPATCH_TARGET = 'plugins.core.runtime.job_dispatcher.dispatch_plugin_job'


@dataclass
class PluginJobBinding:
    """
    当前进程中已准备好的插件任务能力。

    :param plugin: 任务所属的已发现插件
    :param host: 任务使用的宿主能力上下文
    :param gateway: 插件启用状态查询网关
    :param ready: 查询插件是否就绪的回调
    :param loop: 所属宿主事件循环
    :param tasks: 当前仍在执行的插件异步任务集合
    :param metrics: 可选的当前 worker 指标收集器
    """

    plugin: DiscoveredPlugin
    host: PluginHostContext
    gateway: PluginRouteStateGateway
    ready: Callable[[], bool]
    loop: asyncio.AbstractEventLoop
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    metrics: PluginRuntimeMetrics | None = None


_bindings: dict[str, PluginJobBinding] = {}


def bind_plugin_jobs(
    plugin: DiscoveredPlugin,
    host: PluginHostContext,
    gateway: PluginRouteStateGateway,
    ready: Callable[[], bool],
    *,
    metrics: PluginRuntimeMetrics | None = None,
) -> PluginJobBinding:
    """
    独占注册；同进程的第二个应用不能覆盖已有插件资源。

    :param plugin: 任务所属的已发现插件
    :param host: 任务使用的宿主能力上下文
    :param gateway: 插件启用状态查询网关
    :param ready: 查询插件是否就绪的回调
    :param metrics: 可选的运行指标收集器
    :return: 绑定到当前事件循环的插件任务能力
    """
    plugin_id = plugin.manifest.id
    if plugin_id in _bindings:
        raise RuntimeError(f'插件任务运行时已绑定：{plugin_id}')
    if host.plugin_id != plugin_id or host.session_factory is None:
        raise ValueError('任务宿主身份不匹配或缺少数据库会话工厂')
    binding = PluginJobBinding(plugin, host, gateway, ready, asyncio.get_running_loop(), metrics=metrics)
    _bindings[plugin_id] = binding
    return binding


async def unbind_plugin_jobs(binding: PluginJobBinding) -> None:
    """
    先停止接收，再取消并等待任务释放会话，最后由调用方关闭子应用。

    :param binding: 待解除的插件任务绑定
    :return: None
    """
    plugin_id = binding.plugin.manifest.id
    if _bindings.get(plugin_id) is binding:
        del _bindings[plugin_id]
    tasks = [task for task in binding.tasks if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def dispatch_plugin_job(plugin_id: str, job_id: str, version: str) -> Any:
    """
    APScheduler 仅保存此函数及三个字符串；不持久化上下文或原生 callable。

    :param plugin_id: 任务所属的插件 ID
    :param job_id: 插件清单声明的任务 ID
    :param version: 调度记录绑定的插件版本
    :return: 插件异步任务回调的执行结果
    """
    binding = _bindings.get(plugin_id)
    if binding is None or not binding.ready():
        raise RuntimeError(f'插件任务运行时未就绪：{plugin_id}')
    if asyncio.get_running_loop() is not binding.loop:
        raise RuntimeError('插件任务必须在所属宿主事件循环执行')
    manifest = binding.plugin.manifest
    if manifest.version != version:
        raise RuntimeError(f'插件任务版本不匹配：{plugin_id}，需重启并重新同步任务')
    job = next((item for item in manifest.backend.jobs if item.id == job_id), None)
    if job is None:
        raise LookupError(f'插件未声明任务：{plugin_id}:{job_id}')
    task = asyncio.current_task()
    binding.tasks.add(task)
    request_id = uuid4().hex
    token = CTX_REQUEST_ID.set(request_id)
    invocation = binding.metrics.begin(plugin_id, f'job:{job_id}', request_id) if binding.metrics is not None else None
    log_fields = (
        binding.metrics.log_fields(plugin_id, f'job:{job_id}')
        if binding.metrics is not None
        else {'plugin_id': plugin_id, 'plugin_operation': f'job:{job_id}'}
    )
    outcome: MetricOutcome = 'failed'
    error_type = None
    timed_out = False
    try:
        with logger.contextualize(**log_fields):
            async with binding.host.session_factory() as db:
                if not await binding.gateway.is_plugin_enabled(db, plugin_id):
                    raise PermissionError(f'插件未启用：{plugin_id}')
            # 数据库等待期间可能开始关闭，不能在解绑后再启动原生回调。
            if _bindings.get(plugin_id) is not binding or not binding.ready():
                raise RuntimeError(f'插件任务运行时已停止：{plugin_id}')
            module, name = job.callable.rsplit('.', 1)
            callback = PluginEntrypointLoader(binding.plugin).load_callable(f'{module}:{name}')
            result = await await_plugin_callback(
                callback,
                PluginTaskContext(binding.host, job_id, request_id=request_id),
                *job.args,
                kwargs=job.kwargs,
                timeout=job.timeout_seconds,
            )
        outcome = 'succeeded'
        return result
    except asyncio.CancelledError:
        outcome, error_type = 'cancelled', 'CancelledError'
        raise
    except PermissionError:
        outcome, error_type = 'rejected', 'PermissionError'
        raise
    except Exception as exc:
        error_type = type(exc).__name__
        timed_out = isinstance(exc, (TimeoutError, asyncio.TimeoutError))
        raise
    finally:
        if invocation is not None:
            invocation.finish(outcome, error_type=error_type, timed_out=timed_out)
        CTX_REQUEST_ID.reset(token)
        binding.tasks.discard(task)
