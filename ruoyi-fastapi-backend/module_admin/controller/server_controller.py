from fastapi import APIRouter, Request
from fastapi import Depends
from module_admin.service.login_service import LoginService
from module_admin.service.server_service import *
from utils.response_util import *
from utils.log_util import *
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth


serverController = APIRouter(prefix='/monitor/server', dependencies=[Depends(LoginService.get_current_user)])


@serverController.get("", response_model=ServerMonitorModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:server:list'))])
async def get_monitor_server_info(request: Request):
    try:
        # 获取全量数据
        server_info_query_result = ServerService.get_server_monitor_info()
        logger.info('获取成功')
        return ResponseUtil.success(data=server_info_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
