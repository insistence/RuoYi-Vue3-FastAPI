import asyncio
import json
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError

from plugins.core.sdk.context import PluginHostContext, PluginRequestContext
from plugins.core.sdk.definition import await_plugin_callback
from plugins.core.sdk.request import PluginHttpRequest, current_plugin_request_id

DEFAULT_PLUGIN_BODY_LIMIT = 1024 * 1024


async def _read_json_body(request: Request, limit: int, model: type[BaseModel] | None) -> Any:
    """
    按实际接收字节数限制 JSON 请求体，并可选地执行业务模型校验。

    :param request: 当前 HTTP 请求
    :param limit: 请求体允许的最大字节数
    :param model: 可选的 Pydantic 请求体模型
    :return: JSON 请求体或模型校验后的 JSON 数据
    :raises HTTPException: 请求类型、体积或内容不符合要求
    """
    content_type = request.headers.get('content-type', '').partition(';')[0].strip().lower()
    if content_type != 'application/json' and not (
        content_type.startswith('application/') and content_type.endswith('+json')
    ):
        raise HTTPException(status_code=415, detail='插件接口需要 JSON 请求体')
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail='插件请求体超过大小限制')
        body.extend(chunk)
    try:
        # allow_nan=False 的往返校验拒绝 NaN/Infinity，保持跨语言 JSON 契约。
        value = json.loads(body)
        json.dumps(value, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise HTTPException(status_code=400, detail='插件请求体不是有效 JSON') from exc
    if model is not None:
        try:
            value = model.model_validate(value).model_dump(mode='json')
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.errors(include_input=False, include_context=False, include_url=False),
            ) from exc
    return value


def plugin_endpoint(
    callback: Callable[..., Any],
    *,
    permission: str,
    timeout: float = 30.0,
    json_body: bool = False,
    body_model: type[BaseModel] | None = None,
    max_body_bytes: int = DEFAULT_PLUGIN_BODY_LIMIT,
) -> Callable[..., Any]:
    """
    原生函数只接收已鉴权的上下文，返回 awaitable；不让 FastAPI 反射原生签名。

    :param callback: 接收插件请求上下文并返回可等待对象的业务回调
    :param permission: 调用业务回调要求的接口权限标识
    :param timeout: 业务回调等待超时时间，单位为秒
    :param json_body: 是否显式读取 JSON 请求体，默认只提供路径和查询参数
    :param body_model: 可选的请求体校验模型，设置后自动读取 JSON 请求体
    :param max_body_bytes: JSON 请求体最大字节数，默认 1 MiB
    :return: 具有固定 Request 参数的 FastAPI 端点函数
    """

    if type(max_body_bytes) is not int or max_body_bytes <= 0:
        raise ValueError('插件请求体大小限制必须是正整数')
    if body_model is not None and (not isinstance(body_model, type) or not issubclass(body_model, BaseModel)):
        raise TypeError('插件请求体模型必须是 Pydantic BaseModel 子类')

    async def endpoint(request: Request) -> Any:
        context = getattr(request.state, 'plugin_context', None)
        if not isinstance(context, PluginRequestContext):
            raise HTTPException(status_code=401, detail='缺少宿主插件请求上下文')
        try:
            context.require_permission(permission)
            body = (
                await asyncio.wait_for(_read_json_body(request, max_body_bytes, body_model), timeout=timeout)
                if json_body or body_model
                else None
            )
            request_data = PluginHttpRequest(
                method=request.method,
                path=request.url.path,
                path_params=jsonable_encoder(request.path_params),
                query={key: tuple(request.query_params.getlist(key)) for key in request.query_params},
                body=body,
            )
            context = replace(
                context, request=request_data, request_id=context.request_id or current_plugin_request_id()
            )
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
