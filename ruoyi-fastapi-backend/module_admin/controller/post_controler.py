from fastapi import APIRouter, Request
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, CurrentUserModel
from module_admin.service.post_service import *
from module_admin.entity.vo.post_vo import *
from utils.response_util import *
from utils.log_util import *
from utils.page_util import *
from utils.common_util import bytes2file_response
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


postController = APIRouter(prefix='/system/post', dependencies=[Depends(LoginService.get_current_user)])


@postController.get("/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:post:list'))])
async def get_system_post_list(request: Request, post_page_query: PostPageQueryModel = Depends(PostPageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        # 获取分页数据
        post_page_query_result = PostService.get_post_list_services(query_db, post_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=post_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@postController.post("", dependencies=[Depends(CheckUserInterfaceAuth('system:post:add'))])
@log_decorator(title='岗位管理', business_type=1)
async def add_system_post(request: Request, add_post: PostModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_post.create_by = current_user.user.user_name
        add_post.update_by = current_user.user.user_name
        add_post_result = PostService.add_post_services(query_db, add_post)
        if add_post_result.is_success:
            logger.info(add_post_result.message)
            return ResponseUtil.success(msg=add_post_result.message)
        else:
            logger.warning(add_post_result.message)
            return ResponseUtil.failure(msg=add_post_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@postController.put("", dependencies=[Depends(CheckUserInterfaceAuth('system:post:edit'))])
@log_decorator(title='岗位管理', business_type=2)
async def edit_system_post(request: Request, edit_post: PostModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_post.update_by = current_user.user.user_name
        edit_post.update_time = datetime.now()
        edit_post_result = PostService.edit_post_services(query_db, edit_post)
        if edit_post_result.is_success:
            logger.info(edit_post_result.message)
            return ResponseUtil.success(msg=edit_post_result.message)
        else:
            logger.warning(edit_post_result.message)
            return ResponseUtil.failure(msg=edit_post_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@postController.delete("/{post_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:post:remove'))])
@log_decorator(title='岗位管理', business_type=3)
async def delete_system_post(request: Request, post_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_post = DeletePostModel(postIds=post_ids)
        delete_post_result = PostService.delete_post_services(query_db, delete_post)
        if delete_post_result.is_success:
            logger.info(delete_post_result.message)
            return ResponseUtil.success(msg=delete_post_result.message)
        else:
            logger.warning(delete_post_result.message)
            return ResponseUtil.failure(msg=delete_post_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@postController.get("/{post_id}", response_model=PostModel, dependencies=[Depends(CheckUserInterfaceAuth('system:post:query'))])
async def query_detail_system_post(request: Request, post_id: int, query_db: Session = Depends(get_db)):
    try:
        post_detail_result = PostService.post_detail_services(query_db, post_id)
        logger.info(f'获取post_id为{post_id}的信息成功')
        return ResponseUtil.success(data=post_detail_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@postController.post("/export", dependencies=[Depends(CheckUserInterfaceAuth('system:post:export'))])
@log_decorator(title='岗位管理', business_type=5)
async def export_system_post_list(request: Request, post_page_query: PostPageQueryModel = Depends(PostPageQueryModel.as_form), query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        post_query_result = PostService.get_post_list_services(query_db, post_page_query, is_page=False)
        post_export_result = PostService.export_post_list_services(post_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(post_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
