from datetime import datetime
from typing import Annotated

from fastapi import Form, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_admin.entity.vo.post_vo import DeletePostModel, PostModel, PostPageQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.post_service import PostService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

post_controller = APIRouterPro(
    prefix='/system/post', order_num=7, tags=['系统管理-岗位管理'], dependencies=[PreAuthDependency()]
)


@post_controller.get(
    '/list',
    summary='获取岗位分页列表接口',
    description='用于获取岗位分页列表',
    response_model=PageResponseModel[PostModel],
    dependencies=[UserInterfaceAuthDependency('system:post:list')],
)
async def get_system_post_list(
    request: Request,
    post_page_query: Annotated[PostPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    post_page_query_result = await PostService.get_post_list_services(query_db, post_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=post_page_query_result)


@post_controller.post(
    '',
    summary='新增岗位接口',
    description='用于新增岗位',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:post:add')],
)
@ValidateFields(validate_model='add_post')
@Log(title='岗位管理', business_type=BusinessType.INSERT)
async def add_system_post(
    request: Request,
    add_post: PostModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_post.create_by = current_user.user.user_name
    add_post.create_time = datetime.now()
    add_post.update_by = current_user.user.user_name
    add_post.update_time = datetime.now()
    add_post_result = await PostService.add_post_services(query_db, add_post)
    logger.info(add_post_result.message)

    return ResponseUtil.success(msg=add_post_result.message)


@post_controller.put(
    '',
    summary='编辑岗位接口',
    description='用于编辑岗位',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:post:edit')],
)
@ValidateFields(validate_model='edit_post')
@Log(title='岗位管理', business_type=BusinessType.UPDATE)
async def edit_system_post(
    request: Request,
    edit_post: PostModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_post.update_by = current_user.user.user_name
    edit_post.update_time = datetime.now()
    edit_post_result = await PostService.edit_post_services(query_db, edit_post)
    logger.info(edit_post_result.message)

    return ResponseUtil.success(msg=edit_post_result.message)


@post_controller.delete(
    '/{post_ids}',
    summary='删除岗位接口',
    description='用于删除岗位',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:post:remove')],
)
@Log(title='岗位管理', business_type=BusinessType.DELETE)
async def delete_system_post(
    request: Request,
    post_ids: Annotated[str, Path(description='需要删除的岗位ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_post = DeletePostModel(postIds=post_ids)
    delete_post_result = await PostService.delete_post_services(query_db, delete_post)
    logger.info(delete_post_result.message)

    return ResponseUtil.success(msg=delete_post_result.message)


@post_controller.get(
    '/{post_id}',
    summary='获取岗位详情接口',
    description='用于获取指定岗位的详细信息',
    response_model=DataResponseModel[PostModel],
    dependencies=[UserInterfaceAuthDependency('system:post:query')],
)
async def query_detail_system_post(
    request: Request,
    post_id: Annotated[int, Path(description='岗位ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    post_detail_result = await PostService.post_detail_services(query_db, post_id)
    logger.info(f'获取post_id为{post_id}的信息成功')

    return ResponseUtil.success(data=post_detail_result)


@post_controller.post(
    '/export',
    summary='导出岗位列表接口',
    description='用于导出当前符合查询条件的岗位列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回岗位列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('system:post:export')],
)
@Log(title='岗位管理', business_type=BusinessType.EXPORT)
async def export_system_post_list(
    request: Request,
    post_page_query: Annotated[PostPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    post_query_result = await PostService.get_post_list_services(query_db, post_page_query, is_page=False)
    post_export_result = await PostService.export_post_list_services(post_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(post_export_result))
