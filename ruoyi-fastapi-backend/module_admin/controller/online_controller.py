from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import ResponseBaseModel
from module_admin.entity.vo.online_vo import DeleteOnlineModel, OnlinePageResponseModel, OnlineQueryModel
from module_admin.service.online_service import OnlineService
from utils.log_util import logger
from utils.response_util import ResponseUtil

online_controller = APIRouterPro(
    prefix='/monitor/online', order_num=12, tags=['系统监控-在线用户'], dependencies=[PreAuthDependency()]
)


@online_controller.get(
    '/list',
    summary='获取在线用户分页列表接口',
    description='用于获取在线用户分页列表',
    response_model=OnlinePageResponseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:online:list')],
)
async def get_monitor_online_list(
    request: Request,
    online_page_query: Annotated[OnlineQueryModel, Query()],
) -> Response:
    # 获取全量数据
    online_query_result = await OnlineService.get_online_list_services(request, online_page_query)
    logger.info('获取成功')

    return ResponseUtil.success(
        model_content=OnlinePageResponseModel(rows=online_query_result, total=len(online_query_result))
    )


@online_controller.delete(
    '/{token_ids}',
    summary='强退在线用户接口',
    description='用于强退指定会话编号的在线用户',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:online:forceLogout')],
)
@Log(title='在线用户', business_type=BusinessType.FORCE)
async def delete_monitor_online(
    request: Request,
    token_ids: Annotated[str, Path(description='需要强退的会话编号')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_online = DeleteOnlineModel(tokenIds=token_ids)
    delete_online_result = await OnlineService.delete_online_services(request, delete_online)
    logger.info(delete_online_result.message)

    return ResponseUtil.success(msg=delete_online_result.message)
