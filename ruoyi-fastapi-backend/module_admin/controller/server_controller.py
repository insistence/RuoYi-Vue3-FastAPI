from fastapi import APIRouter, Depends, Request, Response

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.server_vo import ServerMonitorModel
from module_admin.service.login_service import LoginService
from module_admin.service.server_service import ServerService
from utils.log_util import logger
from utils.response_util import ResponseUtil

server_controller = APIRouter(prefix='/monitor/server', dependencies=[Depends(LoginService.get_current_user)])


@server_controller.get(
    '', response_model=ServerMonitorModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:server:list'))]
)
async def get_monitor_server_info(request: Request) -> Response:
    # 获取全量数据
    server_info_query_result = await ServerService.get_server_monitor_info()
    logger.info('获取成功')

    return ResponseUtil.success(data=server_info_query_result)
