from fastapi import APIRouter, Request
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, CurrentUserModel
from module_admin.service.notice_service import *
from utils.response_util import *
from utils.log_util import *
from utils.page_util import *
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


noticeController = APIRouter(prefix='/system/notice', dependencies=[Depends(LoginService.get_current_user)])


@noticeController.get("/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:notice:list'))])
async def get_system_notice_list(request: Request, notice_page_query: NoticePageQueryModel = Depends(NoticePageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        # 获取分页数据
        notice_page_query_result = NoticeService.get_notice_list_services(query_db, notice_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=notice_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@noticeController.post("", dependencies=[Depends(CheckUserInterfaceAuth('system:notice:add'))])
@log_decorator(title='通知公告管理', business_type=1)
async def add_system_notice(request: Request, add_notice: NoticeModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_notice.create_by = current_user.user.user_name
        add_notice.update_by = current_user.user.user_name
        add_notice_result = NoticeService.add_notice_services(query_db, add_notice)
        if add_notice_result.is_success:
            logger.info(add_notice_result.message)
            return ResponseUtil.success(msg=add_notice_result.message)
        else:
            logger.warning(add_notice_result.message)
            return ResponseUtil.failure(msg=add_notice_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@noticeController.put("", dependencies=[Depends(CheckUserInterfaceAuth('system:notice:edit'))])
@log_decorator(title='通知公告管理', business_type=2)
async def edit_system_notice(request: Request, edit_notice: NoticeModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_notice.update_by = current_user.user.user_name
        edit_notice.update_time = datetime.now()
        edit_notice_result = NoticeService.edit_notice_services(query_db, edit_notice)
        if edit_notice_result.is_success:
            logger.info(edit_notice_result.message)
            return ResponseUtil.success(msg=edit_notice_result.message)
        else:
            logger.warning(edit_notice_result.message)
            return ResponseUtil.failure(msg=edit_notice_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@noticeController.delete("/{notice_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:notice:remove'))])
@log_decorator(title='通知公告管理', business_type=3)
async def delete_system_notice(request: Request, notice_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_notice = DeleteNoticeModel(noticeIds=notice_ids)
        delete_notice_result = NoticeService.delete_notice_services(query_db, delete_notice)
        if delete_notice_result.is_success:
            logger.info(delete_notice_result.message)
            return ResponseUtil.success(msg=delete_notice_result.message)
        else:
            logger.warning(delete_notice_result.message)
            return ResponseUtil.failure(msg=delete_notice_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@noticeController.get("/{notice_id}", response_model=NoticeModel, dependencies=[Depends(CheckUserInterfaceAuth('system:notice:query'))])
async def query_detail_system_post(request: Request, notice_id: int, query_db: Session = Depends(get_db)):
    try:
        notice_detail_result = NoticeService.notice_detail_services(query_db, notice_id)
        logger.info(f'获取notice_id为{notice_id}的信息成功')
        return ResponseUtil.success(data=notice_detail_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
