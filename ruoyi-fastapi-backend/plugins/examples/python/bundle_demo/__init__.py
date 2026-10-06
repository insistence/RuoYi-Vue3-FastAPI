from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from plugins.core.sdk import PluginDefinition, PluginHostContext, PluginRequestContext, plugin_endpoint
from utils.time_util import TimezoneUtil


class EchoInput(BaseModel):
    """
    用于验证 POST 链路的回显请求参数。
    """

    message: str = Field(min_length=1, max_length=80)


async def summary(context: PluginRequestContext) -> dict[str, str]:
    return {
        'pluginId': context.host.plugin_id,
        'userName': context.user.user.user_name,
        'serverTime': TimezoneUtil.utc_now().isoformat(),
    }


def create_plugin(host: PluginHostContext) -> PluginDefinition:
    """
    声明仅提供相对 API 的子应用，页面资源由宿主交付。

    :param host: 宿主提供的插件上下文
    :return: 插件能力声明
    """

    def create_app(context: PluginHostContext) -> FastAPI:
        """
        创建独立前端示例需要的查询和回显接口。

        :param context: 宿主提供的插件上下文
        :return: 插件 ASGI 子应用
        """
        app = FastAPI(title='独立前端示例', docs_url=None, redoc_url=None)
        app.add_api_route(
            '/api/summary',
            plugin_endpoint(summary, permission='bundle_demo:view'),
            summary='获取插件页面概览接口',
            description='用于获取当前插件标识、登录用户名和服务器时间',
            response_model=dict[str, str],
        )

        @app.post(
            '/api/echo',
            summary='回显插件页面消息接口',
            description='用于回显插件页面提交的消息并返回服务器时间',
        )
        async def echo(payload: EchoInput, request: Request) -> dict[str, str]:
            request.state.plugin_context.require_permission('bundle_demo:view')
            return {'message': payload.message, 'serverTime': TimezoneUtil.utc_now().isoformat()}

        return app

    return PluginDefinition(app_factory=create_app)
