import asyncio
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from plugins.core.sdk.context import PluginHostContext, PluginRequestContext
from plugins.core.sdk.definition import await_plugin_callback


def plugin_endpoint(callback: Callable[..., Any], *, permission: str, timeout: float = 30.0) -> Callable[..., Any]:
    """
    原生函数只接收已鉴权的上下文，返回 awaitable；不让 FastAPI 反射原生签名。

    :param callback: 接收插件请求上下文并返回可等待对象的业务回调
    :param permission: 调用业务回调要求的接口权限标识
    :param timeout: 业务回调等待超时时间，单位为秒
    :return: 具有固定 Request 参数的 FastAPI 端点函数
    """

    async def endpoint(request: Request) -> Any:
        context = getattr(request.state, 'plugin_context', None)
        if not isinstance(context, PluginRequestContext):
            raise HTTPException(status_code=401, detail='缺少宿主插件请求上下文')
        try:
            context.require_permission(permission)
            return await await_plugin_callback(callback, context, timeout=timeout)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail='插件调用超时') from exc

    return endpoint


def plugin_lifespan(
    host: PluginHostContext,
    on_startup: Callable[..., Any],
    on_shutdown: Callable[..., Any],
    *,
    timeout: float = 30.0,
) -> Callable[..., Any]:
    """
    把固定参数的原生 awaitable 转换为 FastAPI lifespan。

    启动回调返回请求可读的 state。启动部分失败也调用关闭回调，因此关闭必须幂等。
    插件只关闭自身资源，不能关闭 host.redis 或宿主数据库连接池。

    :param host: 当前插件的宿主能力上下文
    :param on_startup: 返回请求共享状态的异步启动回调
    :param on_shutdown: 释放插件自身资源的异步关闭回调
    :param timeout: 各生命周期回调等待超时时间，单位为秒
    :return: 可传给 FastAPI 的异步生命周期上下文管理器
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[dict[str, Any], None]:
        """
        执行插件启动和关闭回调，并在请求期间提供共享状态。

        :param app: 使用该生命周期管理器的 FastAPI 子应用
        :return: 供子应用请求使用的共享状态字典迭代器
        """
        try:
            state = await await_plugin_callback(on_startup, host, timeout=timeout)
            if state is not None and not isinstance(state, Mapping):
                raise TypeError('插件启动回调必须返回状态字典或 None')
            yield dict(state or {})
        finally:
            await await_plugin_callback(on_shutdown, host, timeout=timeout)

    return lifespan
