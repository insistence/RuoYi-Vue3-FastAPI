from fastapi import Request, Response

from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_admin.entity.vo.server_vo import ServerMonitorModel
from module_admin.service.server_service import ServerService
from utils.log_util import logger
from utils.response_util import ResponseUtil

server_controller = APIRouterPro(
    prefix='/monitor/server', order_num=14, tags=['系统监控-服务监控'], dependencies=[PreAuthDependency()]
)


@server_controller.get(
    '',
    summary='获取服务器监控信息接口',
    description='用于获取当前服务器的监控信息',
    response_model=DataResponseModel[ServerMonitorModel],
    dependencies=[UserInterfaceAuthDependency('monitor:server:list')],
)
async def get_monitor_server_info(request: Request) -> Response:
    # 获取全量数据
    server_info_query_result = await ServerService.get_server_monitor_info()
    logger.info('获取成功')

    return ResponseUtil.success(data=server_info_query_result)
