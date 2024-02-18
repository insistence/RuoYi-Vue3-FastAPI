from fastapi import APIRouter
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService
from module_admin.service.log_service import *
from utils.response_util import *
from utils.log_util import *
from utils.page_util import *
from utils.common_util import bytes2file_response
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


logController = APIRouter(prefix='/monitor', dependencies=[Depends(LoginService.get_current_user)])


@logController.get("/operlog/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:operlog:list'))])
async def get_system_operation_log_list(request: Request, operation_log_page_query: OperLogPageQueryModel = Depends(OperLogPageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        # 获取分页数据
        operation_log_page_query_result = OperationLogService.get_operation_log_list_services(query_db, operation_log_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=operation_log_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.delete("/operlog/clean", dependencies=[Depends(CheckUserInterfaceAuth('monitor:operlog:remove'))])
@log_decorator(title='操作日志管理', business_type=9)
async def clear_system_operation_log(request: Request, query_db: Session = Depends(get_db)):
    try:
        clear_operation_log_result = OperationLogService.clear_operation_log_services(query_db)
        if clear_operation_log_result.is_success:
            logger.info(clear_operation_log_result.message)
            return ResponseUtil.success(msg=clear_operation_log_result.message)
        else:
            logger.warning(clear_operation_log_result.message)
            return ResponseUtil.failure(msg=clear_operation_log_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.delete("/operlog/{oper_ids}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:operlog:remove'))])
@log_decorator(title='操作日志管理', business_type=3)
async def delete_system_operation_log(request: Request, oper_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_operation_log = DeleteOperLogModel(operIds=oper_ids)
        delete_operation_log_result = OperationLogService.delete_operation_log_services(query_db, delete_operation_log)
        if delete_operation_log_result.is_success:
            logger.info(delete_operation_log_result.message)
            return ResponseUtil.success(msg=delete_operation_log_result.message)
        else:
            logger.warning(delete_operation_log_result.message)
            return ResponseUtil.failure(msg=delete_operation_log_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.post("/operlog/export", dependencies=[Depends(CheckUserInterfaceAuth('monitor:operlog:export'))])
@log_decorator(title='操作日志管理', business_type=5)
async def export_system_operation_log_list(request: Request, operation_log_page_query: OperLogPageQueryModel = Depends(OperLogPageQueryModel.as_form), query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        operation_log_query_result = OperationLogService.get_operation_log_list_services(query_db, operation_log_page_query, is_page=False)
        operation_log_export_result = await OperationLogService.export_operation_log_list_services(request, operation_log_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(operation_log_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.get("/logininfor/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:logininfor:list'))])
async def get_system_login_log_list(request: Request, login_log_page_query: LoginLogPageQueryModel = Depends(LoginLogPageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        # 获取分页数据
        login_log_page_query_result = LoginLogService.get_login_log_list_services(query_db, login_log_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=login_log_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.delete("/logininfor/clean", dependencies=[Depends(CheckUserInterfaceAuth('monitor:logininfor:remove'))])
@log_decorator(title='登录日志管理', business_type=9)
async def clear_system_login_log(request: Request, query_db: Session = Depends(get_db)):
    try:
        clear_login_log_result = LoginLogService.clear_login_log_services(query_db)
        if clear_login_log_result.is_success:
            logger.info(clear_login_log_result.message)
            return ResponseUtil.success(msg=clear_login_log_result.message)
        else:
            logger.warning(clear_login_log_result.message)
            return ResponseUtil.failure(msg=clear_login_log_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.delete("/logininfor/{info_ids}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:logininfor:remove'))])
@log_decorator(title='登录日志管理', business_type=3)
async def delete_system_login_log(request: Request, info_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_login_log = DeleteLoginLogModel(infoIds=info_ids)
        delete_login_log_result = LoginLogService.delete_login_log_services(query_db, delete_login_log)
        if delete_login_log_result.is_success:
            logger.info(delete_login_log_result.message)
            return ResponseUtil.success(msg=delete_login_log_result.message)
        else:
            logger.warning(delete_login_log_result.message)
            return ResponseUtil.failure(msg=delete_login_log_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.get("/logininfor/unlock/{user_name}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:logininfor:unlock'))])
@log_decorator(title='登录日志管理', business_type=0)
async def clear_system_login_log(request: Request, user_name: str, query_db: Session = Depends(get_db)):
    try:
        unlock_user = UnlockUser(userName=user_name)
        unlock_user_result = await LoginLogService.unlock_user_services(request, unlock_user)
        if unlock_user_result.is_success:
            logger.info(unlock_user_result.message)
            return ResponseUtil.success(msg=unlock_user_result.message)
        else:
            logger.warning(unlock_user_result.message)
            return ResponseUtil.failure(msg=unlock_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@logController.post("/logininfor/export", dependencies=[Depends(CheckUserInterfaceAuth('monitor:logininfor:export'))])
@log_decorator(title='登录日志管理', business_type=5)
async def export_system_login_log_list(request: Request, login_log_page_query: LoginLogPageQueryModel = Depends(LoginLogPageQueryModel.as_form), query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        login_log_query_result = LoginLogService.get_login_log_list_services(query_db, login_log_page_query, is_page=False)
        login_log_export_result = LoginLogService.export_login_log_list_services(login_log_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(login_log_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
