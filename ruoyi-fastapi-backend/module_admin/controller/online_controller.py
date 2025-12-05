from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.interface_auth import CheckUserInterfaceAuth
from common.enums import BusinessType
from config.get_db import get_db
from module_admin.entity.vo.online_vo import DeleteOnlineModel, OnlineQueryModel
from module_admin.service.login_service import LoginService
from module_admin.service.online_service import OnlineService
from utils.log_util import logger
from utils.page_util import PageResponseModel
from utils.response_util import ResponseUtil

online_controller = APIRouter(prefix='/monitor/online', dependencies=[Depends(LoginService.get_current_user)])


@online_controller.get(
    '/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:online:list'))]
)
async def get_monitor_online_list(
    request: Request,
    online_page_query: Annotated[OnlineQueryModel, Query()],
) -> Response:
    # 获取全量数据
    online_query_result = await OnlineService.get_online_list_services(request, online_page_query)
    logger.info('获取成功')

    return ResponseUtil.success(
        model_content=PageResponseModel(rows=online_query_result, total=len(online_query_result))
    )


@online_controller.delete('/{token_ids}', dependencies=[Depends(CheckUserInterfaceAuth('monitor:online:forceLogout'))])
@Log(title='在线用户', business_type=BusinessType.FORCE)
async def delete_monitor_online(
    request: Request,
    token_ids: Annotated[str, Path(description='需要强退的会话编号')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    delete_online = DeleteOnlineModel(tokenIds=token_ids)
    delete_online_result = await OnlineService.delete_online_services(request, delete_online)
    logger.info(delete_online_result.message)

    return ResponseUtil.success(msg=delete_online_result.message)
