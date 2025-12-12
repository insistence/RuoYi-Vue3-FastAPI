from typing import Annotated

from fastapi import APIRouter, Form, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.enums import BusinessType
from common.vo import PageResponseModel, ResponseBaseModel
from module_admin.entity.vo.log_vo import (
    DeleteLoginLogModel,
    DeleteOperLogModel,
    LogininforModel,
    LoginLogPageQueryModel,
    OperLogModel,
    OperLogPageQueryModel,
    UnlockUser,
)
from module_admin.service.log_service import LoginLogService, OperationLogService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

log_controller = APIRouter(prefix='/monitor', dependencies=[PreAuthDependency()])


@log_controller.get(
    '/operlog/list',
    response_model=PageResponseModel[OperLogModel],
    dependencies=[UserInterfaceAuthDependency('monitor:operlog:list')],
)
async def get_system_operation_log_list(
    request: Request,
    operation_log_page_query: Annotated[OperLogPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    operation_log_page_query_result = await OperationLogService.get_operation_log_list_services(
        query_db, operation_log_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=operation_log_page_query_result)


@log_controller.delete(
    '/operlog/clean',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:operlog:remove')],
)
@Log(title='操作日志', business_type=BusinessType.CLEAN)
async def clear_system_operation_log(
    request: Request, query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    clear_operation_log_result = await OperationLogService.clear_operation_log_services(query_db)
    logger.info(clear_operation_log_result.message)

    return ResponseUtil.success(msg=clear_operation_log_result.message)


@log_controller.delete(
    '/operlog/{oper_ids}',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:operlog:remove')],
)
@Log(title='操作日志', business_type=BusinessType.DELETE)
async def delete_system_operation_log(
    request: Request,
    oper_ids: Annotated[str, Path(description='需要删除的日志主键')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_operation_log = DeleteOperLogModel(operIds=oper_ids)
    delete_operation_log_result = await OperationLogService.delete_operation_log_services(
        query_db, delete_operation_log
    )
    logger.info(delete_operation_log_result.message)

    return ResponseUtil.success(msg=delete_operation_log_result.message)


@log_controller.post(
    '/operlog/export',
    dependencies=[UserInterfaceAuthDependency('monitor:operlog:export')],
)
@Log(title='操作日志', business_type=BusinessType.EXPORT)
async def export_system_operation_log_list(
    request: Request,
    operation_log_page_query: Annotated[OperLogPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    operation_log_query_result = await OperationLogService.get_operation_log_list_services(
        query_db, operation_log_page_query, is_page=False
    )
    operation_log_export_result = await OperationLogService.export_operation_log_list_services(
        request, operation_log_query_result
    )
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(operation_log_export_result))


@log_controller.get(
    '/logininfor/list',
    response_model=PageResponseModel[LogininforModel],
    dependencies=[UserInterfaceAuthDependency('monitor:logininfor:list')],
)
async def get_system_login_log_list(
    request: Request,
    login_log_page_query: Annotated[LoginLogPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    login_log_page_query_result = await LoginLogService.get_login_log_list_services(
        query_db, login_log_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=login_log_page_query_result)


@log_controller.delete(
    '/logininfor/clean',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:logininfor:remove')],
)
@Log(title='登录日志', business_type=BusinessType.CLEAN)
async def clear_system_login_log(
    request: Request, query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    clear_login_log_result = await LoginLogService.clear_login_log_services(query_db)
    logger.info(clear_login_log_result.message)

    return ResponseUtil.success(msg=clear_login_log_result.message)


@log_controller.delete(
    '/logininfor/{info_ids}',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:logininfor:remove')],
)
@Log(title='登录日志', business_type=BusinessType.DELETE)
async def delete_system_login_log(
    request: Request,
    info_ids: Annotated[str, Path(description='需要删除的访问ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_login_log = DeleteLoginLogModel(infoIds=info_ids)
    delete_login_log_result = await LoginLogService.delete_login_log_services(query_db, delete_login_log)
    logger.info(delete_login_log_result.message)

    return ResponseUtil.success(msg=delete_login_log_result.message)


@log_controller.get(
    '/logininfor/unlock/{user_name}',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:logininfor:unlock')],
)
@Log(title='账户解锁', business_type=BusinessType.OTHER)
async def unlock_system_user(
    request: Request,
    user_name: Annotated[str, Path(description='用户名称')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    unlock_user = UnlockUser(userName=user_name)
    unlock_user_result = await LoginLogService.unlock_user_services(request, unlock_user)
    logger.info(unlock_user_result.message)

    return ResponseUtil.success(msg=unlock_user_result.message)


@log_controller.post(
    '/logininfor/export',
    dependencies=[UserInterfaceAuthDependency('monitor:logininfor:export')],
)
@Log(title='登录日志', business_type=BusinessType.EXPORT)
async def export_system_login_log_list(
    request: Request,
    login_log_page_query: Annotated[LoginLogPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    login_log_query_result = await LoginLogService.get_login_log_list_services(
        query_db, login_log_page_query, is_page=False
    )
    login_log_export_result = await LoginLogService.export_login_log_list_services(login_log_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(login_log_export_result))
