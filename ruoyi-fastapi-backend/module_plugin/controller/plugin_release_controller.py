from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import Annotated, Any

from fastapi import Query, Response

from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from utils.log_util import logger
from utils.response_util import ResponseUtil

plugin_release_controller = APIRouterPro(
    prefix='/system/plugin',
    order_num=6,
    tags=['系统管理-插件制品发布'],
    dependencies=[PreAuthDependency(), UserInterfaceAuthDependency('system:plugin:query')],
)


def get_plugin_deployment_service() -> Any:
    """
    按需创建制品发布查询服务，功能关闭时不访问新增数据库表。

    :return: 当前宿主配置下的制品发布服务
    :raises ValueError: 签名制品发布功能未启用或存储配置无效
    """
    config_class = import_module('plugins.core.deployment.config').PluginDeploymentConfig
    config = config_class.from_settings(Path(__file__).resolve().parents[2])
    config.require_enabled()
    service_class = import_module('plugins.core.deployment.service').PluginDeploymentService
    return service_class(config)


async def _read_release_payload(operation: Callable[[], Awaitable[dict[str, Any]]]) -> Response:
    """
    统一执行发布只读查询，并转换预检失败及内部异常响应。

    :param operation: 不接收参数并异步返回发布查询数据的操作
    :return: 成功数据或不暴露内部连接信息的失败响应
    """
    try:
        payload = await operation()
    except ValueError as exc:
        return ResponseUtil.failure(msg=str(exc), data={'ok': False, 'status': 'blocked'})
    except Exception:
        logger.exception('读取插件制品发布状态失败')
        return ResponseUtil.failure(msg='读取插件制品发布状态失败')
    if not payload.get('ok', True):
        return ResponseUtil.failure(msg=str(payload.get('message') or '插件发布预检未通过'), data=payload)
    return ResponseUtil.success(data=payload)


@plugin_release_controller.get(
    '/artifacts/list',
    summary='获取已验证插件制品列表接口',
    description='用于获取已验证的插件制品列表，支持按插件ID筛选',
    response_model=DataResponseModel[dict],
)
async def list_plugin_artifacts(
    plugin_id: Annotated[
        str | None, Query(alias='pluginId', description='插件ID', pattern=r'^[a-z][a-z0-9_]{1,63}$')
    ] = None,
) -> Response:
    return await _read_release_payload(lambda: get_plugin_deployment_service().catalog.list_artifacts(plugin_id))


@plugin_release_controller.get(
    '/release/status',
    summary='获取插件发布状态接口',
    description='用于查询插件发布目标及各工作进程的实际状态，支持按插件ID筛选',
    response_model=DataResponseModel[dict],
)
async def get_plugin_release_status(
    plugin_id: Annotated[
        str | None, Query(alias='pluginId', description='插件ID', pattern=r'^[a-z][a-z0-9_]{1,63}$')
    ] = None,
) -> Response:
    return await _read_release_payload(lambda: get_plugin_deployment_service().status(plugin_id))


@plugin_release_controller.get(
    '/release/plan',
    summary='获取插件发布预检计划接口',
    description='用于根据插件ID和制品摘要获取维护发布前的静态预检计划',
    response_model=DataResponseModel[dict],
)
async def plan_plugin_release(
    plugin_id: Annotated[str, Query(alias='pluginId', description='插件ID', pattern=r'^[a-z][a-z0-9_]{1,63}$')],
    digest: Annotated[str, Query(description='插件制品SHA256摘要', pattern=r'^[0-9a-f]{64}$')],
) -> Response:
    return await _read_release_payload(lambda: get_plugin_deployment_service().plan(plugin_id, digest))
