from typing import Annotated

from fastapi import Query, Request, Response

from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from plugins.core.runtime.metrics_store import PluginMetricsReporter
from utils.response_util import ResponseUtil

plugin_metrics_controller = APIRouterPro(
    prefix='/system/plugin',
    order_num=6,
    tags=['系统管理-插件运行观测'],
    dependencies=[PreAuthDependency(), UserInterfaceAuthDependency('system:plugin:query')],
)


@plugin_metrics_controller.get(
    '/runtime/metrics',
    summary='获取插件运行指标接口',
    description='用于查询显式插件的请求与任务累计指标，按实际加载版本和可观测worker分组',
    response_model=DataResponseModel[dict],
)
async def get_plugin_runtime_metrics(
    request: Request,
    plugin_id: Annotated[
        str | None, Query(alias='pluginId', description='插件ID', pattern=r'^[a-z][a-z0-9_]{1,63}$')
    ] = None,
) -> Response:
    reporter = getattr(request.app.state, 'plugin_metrics_reporter', None)
    if not isinstance(reporter, PluginMetricsReporter):
        return ResponseUtil.success(
            data={'ok': True, 'supported': False, 'scope': 'unavailable', 'workers': [], 'series': []}
        )
    return ResponseUtil.success(data=await reporter.read(plugin_id))
