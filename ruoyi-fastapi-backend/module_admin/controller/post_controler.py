from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession
from config.enums import BusinessType
from config.get_db import get_db
from module_admin.annotation.log_annotation import Log
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.service.login_service import LoginService
from module_admin.service.post_service import PostService
from module_admin.entity.vo.post_vo import DeletePostModel, PostModel, PostPageQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.page_util import PageResponseModel
from utils.response_util import ResponseUtil


postController = APIRouter(prefix='/system/post', dependencies=[Depends(LoginService.get_current_user)])


@postController.get(
    '/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:post:list'))]
)
async def get_system_post_list(
    request: Request,
    post_page_query: PostPageQueryModel = Depends(PostPageQueryModel.as_query),
    query_db: AsyncSession = Depends(get_db),
):
    # 获取分页数据
    post_page_query_result = await PostService.get_post_list_services(query_db, post_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=post_page_query_result)


@postController.post('', dependencies=[Depends(CheckUserInterfaceAuth('system:post:add'))])
@ValidateFields(validate_model='add_post')
@Log(title='岗位管理', business_type=BusinessType.INSERT)
async def add_system_post(
    request: Request,
    add_post: PostModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_post.create_by = current_user.user.user_name
    add_post.create_time = datetime.now()
    add_post.update_by = current_user.user.user_name
    add_post.update_time = datetime.now()
    add_post_result = await PostService.add_post_services(query_db, add_post)
    logger.info(add_post_result.message)

    return ResponseUtil.success(msg=add_post_result.message)


@postController.put('', dependencies=[Depends(CheckUserInterfaceAuth('system:post:edit'))])
@ValidateFields(validate_model='edit_post')
@Log(title='岗位管理', business_type=BusinessType.UPDATE)
async def edit_system_post(
    request: Request,
    edit_post: PostModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    edit_post.update_by = current_user.user.user_name
    edit_post.update_time = datetime.now()
    edit_post_result = await PostService.edit_post_services(query_db, edit_post)
    logger.info(edit_post_result.message)

    return ResponseUtil.success(msg=edit_post_result.message)


@postController.delete('/{post_ids}', dependencies=[Depends(CheckUserInterfaceAuth('system:post:remove'))])
@Log(title='岗位管理', business_type=BusinessType.DELETE)
async def delete_system_post(request: Request, post_ids: str, query_db: AsyncSession = Depends(get_db)):
    delete_post = DeletePostModel(postIds=post_ids)
    delete_post_result = await PostService.delete_post_services(query_db, delete_post)
    logger.info(delete_post_result.message)

    return ResponseUtil.success(msg=delete_post_result.message)


@postController.get(
    '/{post_id}', response_model=PostModel, dependencies=[Depends(CheckUserInterfaceAuth('system:post:query'))]
)
async def query_detail_system_post(request: Request, post_id: int, query_db: AsyncSession = Depends(get_db)):
    post_detail_result = await PostService.post_detail_services(query_db, post_id)
    logger.info(f'获取post_id为{post_id}的信息成功')

    return ResponseUtil.success(data=post_detail_result)


@postController.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('system:post:export'))])
@Log(title='岗位管理', business_type=BusinessType.EXPORT)
async def export_system_post_list(
    request: Request,
    post_page_query: PostPageQueryModel = Form(),
    query_db: AsyncSession = Depends(get_db),
):
    # 获取全量数据
    post_query_result = await PostService.get_post_list_services(query_db, post_page_query, is_page=False)
    post_export_result = await PostService.export_post_list_services(post_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(post_export_result))
