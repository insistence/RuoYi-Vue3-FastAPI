from fastapi import APIRouter, Depends, Request
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.server_vo import ServerMonitorModel
from module_admin.service.login_service import LoginService
from module_admin.service.server_service import ServerService
from utils.response_util import ResponseUtil
from utils.log_util import logger


serverController = APIRouter(prefix='/monitor/server', dependencies=[Depends(LoginService.get_current_user)])


@serverController.get(
    '', response_model=ServerMonitorModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:server:list'))]
)
async def get_monitor_server_info(request: Request):
    # 获取全量数据
    server_info_query_result = await ServerService.get_server_monitor_info()
    logger.info('获取成功')

    return ResponseUtil.success(data=server_info_query_result)
