from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from plugins.core.sdk import PluginDefinition, PluginHostContext, PluginRequestContext, plugin_endpoint


class EchoBody(BaseModel):
    """
    SDK 请求体模型，约束示例消息长度。
    """

    message: str = Field(min_length=1, max_length=200)


async def echo(context: PluginRequestContext) -> dict[str, Any]:
    return {**context.request.to_payload(), 'requestId': context.request_id}


def create_plugin(host: PluginHostContext) -> PluginDefinition:
    """
    声明子应用工厂，资源初始化交给子应用生命周期。

    :param host: 宿主提供的插件上下文
    :return: 插件能力声明
    """
    return PluginDefinition(app_factory=create_app)


def create_app(host: PluginHostContext) -> FastAPI:
    """
    为当前 worker 创建独立的 ASGI 子应用。

    :param host: 宿主提供的插件上下文
    :return: 包含权限检查和生命周期管理的子应用
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[dict[str, str], None]:
        """
        演示插件自有资源的启动与关闭。

        :param app: 正在启动或关闭的 ASGI 子应用
        :return: 可供请求访问的生命周期状态
        """
        host.logger.info('ASGI 示例启动')
        try:
            yield {'message': '子应用资源已就绪'}
        finally:
            host.logger.info('ASGI 示例关闭')

    app = FastAPI(title='ASGI 插件示例', lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get(
        '/api/info',
        summary='获取ASGI插件信息接口',
        description='用于获取当前插件标识、宿主API版本和子应用资源状态',
    )
    async def info(request: Request) -> dict[str, str]:
        context = request.state.plugin_context
        try:
            context.require_permission('asgi_demo:view')
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {'pluginId': host.plugin_id, 'hostApiVersion': host.api_version, 'message': request.state.message}

    app.add_api_route(
        '/api/echo/{item_id}',
        plugin_endpoint(echo, permission='asgi_demo:view', body_model=EchoBody),
        methods=['POST'],
        summary='验证ASGI插件请求上下文接口',
        description='返回校验后的请求体、路径参数、多值查询参数与宿主追踪标识',
        response_model=dict[str, Any],
    )

    return app
