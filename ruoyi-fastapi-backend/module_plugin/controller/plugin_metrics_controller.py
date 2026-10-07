from typing import Annotated

from fastapi import Path, Query, Request, Response

from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_plugin.service.plugin_service import get_plugin_runtime_service
from plugins.core.runtime.configuration import build_config_status, config_revision
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


@plugin_metrics_controller.get(
    '/{plugin_id}/config/status',
    summary='获取插件配置生效状态接口',
    description='比较数据库配置与已观测进程的启动快照；按需读取版本仅表示读取完成，不代表业务设置已经应用',
    response_model=DataResponseModel[dict],
)
async def get_plugin_config_status(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID', pattern=r'^[a-z][a-z0-9_]{1,63}$')],
) -> Response:
    payload = await get_plugin_runtime_service().get_plugin_config(plugin_id, reveal_secret=True)
    if not payload.get('ok'):
        return ResponseUtil.failure(msg='插件配置状态读取失败')
    values = {item['key']: item.get('value') for item in payload.get('configs', [])}
    reporter = getattr(request.app.state, 'plugin_metrics_reporter', None)
    report = await reporter.read(plugin_id) if isinstance(reporter, PluginMetricsReporter) else {'scope': 'unavailable'}
    return ResponseUtil.success(data=build_config_status(plugin_id, config_revision(plugin_id, values), report))
