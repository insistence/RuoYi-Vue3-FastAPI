from datetime import datetime
from typing import Annotated

from fastapi import Path, Query, Request, Response
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_admin.entity.vo.notice_vo import DeleteNoticeModel, NoticeModel, NoticePageQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.notice_service import NoticeService
from utils.log_util import logger
from utils.response_util import ResponseUtil

notice_controller = APIRouterPro(
    prefix='/system/notice', order_num=10, tags=['系统管理-通知公告管理'], dependencies=[PreAuthDependency()]
)


@notice_controller.get(
    '/list',
    summary='获取通知公告分页列表接口',
    description='用于获取通知公告分页列表',
    response_model=PageResponseModel[NoticeModel],
    dependencies=[UserInterfaceAuthDependency('system:notice:list')],
)
async def get_system_notice_list(
    request: Request,
    notice_page_query: Annotated[NoticePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    notice_page_query_result = await NoticeService.get_notice_list_services(query_db, notice_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=notice_page_query_result)


@notice_controller.post(
    '',
    summary='新增通知公告接口',
    description='用于新增通知公告',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:notice:add')],
)
@ValidateFields(validate_model='add_notice')
@Log(title='通知公告', business_type=BusinessType.INSERT)
async def add_system_notice(
    request: Request,
    add_notice: NoticeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_notice.create_by = current_user.user.user_name
    add_notice.create_time = datetime.now()
    add_notice.update_by = current_user.user.user_name
    add_notice.update_time = datetime.now()
    add_notice_result = await NoticeService.add_notice_services(query_db, add_notice)
    logger.info(add_notice_result.message)

    return ResponseUtil.success(msg=add_notice_result.message)


@notice_controller.put(
    '',
    summary='编辑通知公告接口',
    description='用于编辑通知公告',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:notice:edit')],
)
@ValidateFields(validate_model='edit_notice')
@Log(title='通知公告', business_type=BusinessType.UPDATE)
async def edit_system_notice(
    request: Request,
    edit_notice: NoticeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_notice.update_by = current_user.user.user_name
    edit_notice.update_time = datetime.now()
    edit_notice_result = await NoticeService.edit_notice_services(query_db, edit_notice)
    logger.info(edit_notice_result.message)

    return ResponseUtil.success(msg=edit_notice_result.message)


@notice_controller.delete(
    '/{notice_ids}',
    summary='删除通知公告接口',
    description='用于删除通知公告',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:notice:remove')],
)
@Log(title='通知公告', business_type=BusinessType.DELETE)
async def delete_system_notice(
    request: Request,
    notice_ids: Annotated[str, Path(description='需要删除的公告ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_notice = DeleteNoticeModel(noticeIds=notice_ids)
    delete_notice_result = await NoticeService.delete_notice_services(query_db, delete_notice)
    logger.info(delete_notice_result.message)

    return ResponseUtil.success(msg=delete_notice_result.message)


@notice_controller.get(
    '/{notice_id}',
    summary='获取通知公告详情接口',
    description='用于获取指定通知公告的详细信息',
    response_model=DataResponseModel[NoticeModel],
    dependencies=[UserInterfaceAuthDependency('system:notice:query')],
)
async def query_detail_system_post(
    request: Request,
    notice_id: Annotated[int, Path(description='公告ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    notice_detail_result = await NoticeService.notice_detail_services(query_db, notice_id)
    logger.info(f'获取notice_id为{notice_id}的信息成功')

    return ResponseUtil.success(data=notice_detail_result)
