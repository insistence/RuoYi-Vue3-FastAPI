from fastapi import APIRouter
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, Session
from module_admin.service.online_service import *
from utils.response_util import *
from utils.log_util import *
from utils.page_util import *
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


onlineController = APIRouter(prefix='/monitor/online', dependencies=[Depends(LoginService.get_current_user)])


@onlineController.get("/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:online:list'))])
async def get_monitor_online_list(request: Request, online_page_query: OnlineQueryModel = Depends(OnlineQueryModel.as_query)):
    try:
        # 获取全量数据
        online_query_result = await OnlineService.get_online_list_services(request, online_page_query)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=PageResponseModel(rows=online_query_result, total=len(online_query_result)))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@onlineController.delete("/{token_ids}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:online:forceLogout'))])
@log_decorator(title='在线用户', business_type=7)
async def delete_monitor_online(request: Request, token_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_online = DeleteOnlineModel(tokenIds=token_ids)
        delete_online_result = await OnlineService.delete_online_services(request, delete_online)
        if delete_online_result.is_success:
            logger.info(delete_online_result.message)
            return ResponseUtil.success(msg=delete_online_result.message)
        else:
            logger.warning(delete_online_result.message)
            return ResponseUtil.failure(msg=delete_online_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
