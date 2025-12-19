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
from module_admin.entity.vo.job_vo import (
    DeleteJobLogModel,
    DeleteJobModel,
    EditJobModel,
    JobLogModel,
    JobLogPageQueryModel,
    JobModel,
    JobPageQueryModel,
)
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.job_log_service import JobLogService
from module_admin.service.job_service import JobService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

job_controller = APIRouterPro(
    prefix='/monitor', order_num=13, tags=['系统监控-定时任务'], dependencies=[PreAuthDependency()]
)


@job_controller.get(
    '/job/list',
    summary='获取定时任务分页列表接口',
    description='用于获取定时任务分页列表',
    response_model=PageResponseModel[JobModel],
    dependencies=[UserInterfaceAuthDependency('monitor:job:list')],
)
async def get_system_job_list(
    request: Request,
    job_page_query: Annotated[JobPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    job_page_query_result = await JobService.get_job_list_services(query_db, job_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=job_page_query_result)


@job_controller.post(
    '/job',
    summary='新增定时任务接口',
    description='用于新增定时任务',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:add')],
)
@ValidateFields(validate_model='add_job')
@Log(title='定时任务', business_type=BusinessType.INSERT)
async def add_system_job(
    request: Request,
    add_job: JobModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_job.create_by = current_user.user.user_name
    add_job.create_time = datetime.now()
    add_job.update_by = current_user.user.user_name
    add_job.update_time = datetime.now()
    add_job_result = await JobService.add_job_services(query_db, add_job)
    logger.info(add_job_result.message)

    return ResponseUtil.success(msg=add_job_result.message)


@job_controller.put(
    '/job',
    summary='编辑定时任务接口',
    description='用于编辑定时任务',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:edit')],
)
@ValidateFields(validate_model='edit_job')
@Log(title='定时任务', business_type=BusinessType.UPDATE)
async def edit_system_job(
    request: Request,
    edit_job: EditJobModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_job.update_by = current_user.user.user_name
    edit_job.update_time = datetime.now()
    edit_job_result = await JobService.edit_job_services(query_db, edit_job)
    logger.info(edit_job_result.message)

    return ResponseUtil.success(msg=edit_job_result.message)


@job_controller.put(
    '/job/changeStatus',
    summary='修改定时任务状态接口',
    description='用于修改定时任务状态',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:changeStatus')],
)
@Log(title='定时任务', business_type=BusinessType.UPDATE)
async def change_system_job_status(
    request: Request,
    change_job: EditJobModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_job = EditJobModel(
        jobId=change_job.job_id,
        status=change_job.status,
        updateBy=current_user.user.user_name,
        updateTime=datetime.now(),
        type='status',
    )
    edit_job_result = await JobService.edit_job_services(query_db, edit_job)
    logger.info(edit_job_result.message)

    return ResponseUtil.success(msg=edit_job_result.message)


@job_controller.put(
    '/job/run',
    summary='执行定时任务接口',
    description='用于执行指定的定时任务',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:changeStatus')],
)
@Log(title='定时任务', business_type=BusinessType.UPDATE)
async def execute_system_job(
    request: Request,
    execute_job: JobModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    execute_job_result = await JobService.execute_job_once_services(query_db, execute_job)
    logger.info(execute_job_result.message)

    return ResponseUtil.success(msg=execute_job_result.message)


@job_controller.delete(
    '/job/{job_ids}',
    summary='删除定时任务接口',
    description='用于删除定时任务',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:remove')],
)
@Log(title='定时任务', business_type=BusinessType.DELETE)
async def delete_system_job(
    request: Request,
    job_ids: Annotated[str, Path(description='需要删除的定时任务ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_job = DeleteJobModel(jobIds=job_ids)
    delete_job_result = await JobService.delete_job_services(query_db, delete_job)
    logger.info(delete_job_result.message)

    return ResponseUtil.success(msg=delete_job_result.message)


@job_controller.get(
    '/job/{job_id}',
    summary='获取定时任务详情接口',
    description='用于获取指定定时任务的详情信息',
    response_model=DataResponseModel[JobModel],
    dependencies=[UserInterfaceAuthDependency('monitor:job:query')],
)
async def query_detail_system_job(
    request: Request,
    job_id: Annotated[int, Path(description='任务ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    job_detail_result = await JobService.job_detail_services(query_db, job_id)
    logger.info(f'获取job_id为{job_id}的信息成功')

    return ResponseUtil.success(data=job_detail_result)


@job_controller.post(
    '/job/export',
    summary='导出定时任务列表接口',
    description='用于导出当前符合查询条件的定时任务列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回定时任务列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('monitor:job:export')],
)
@Log(title='定时任务', business_type=BusinessType.EXPORT)
async def export_system_job_list(
    request: Request,
    job_page_query: Annotated[JobPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    job_query_result = await JobService.get_job_list_services(query_db, job_page_query, is_page=False)
    job_export_result = await JobService.export_job_list_services(request, job_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(job_export_result))


@job_controller.get(
    '/jobLog/list',
    summary='获取定时任务调度日志分页列表接口',
    description='用于获取定时任务调度日志分页列表',
    response_model=PageResponseModel[JobLogModel],
    dependencies=[UserInterfaceAuthDependency('monitor:job:list')],
)
async def get_system_job_log_list(
    request: Request,
    job_log_page_query: Annotated[JobLogPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    job_log_page_query_result = await JobLogService.get_job_log_list_services(
        query_db, job_log_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=job_log_page_query_result)


@job_controller.delete(
    '/jobLog/clean',
    summary='清空定时任务调度日志接口',
    description='用于清空所有定时任务调度日志',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:remove')],
)
@Log(title='定时任务调度日志', business_type=BusinessType.CLEAN)
async def clear_system_job_log(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    clear_job_log_result = await JobLogService.clear_job_log_services(query_db)
    logger.info(clear_job_log_result.message)

    return ResponseUtil.success(msg=clear_job_log_result.message)


@job_controller.delete(
    '/jobLog/{job_log_ids}',
    summary='删除定时任务调度日志接口',
    description='用于删除定时任务调度日志',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:remove')],
)
@Log(title='定时任务调度日志', business_type=BusinessType.DELETE)
async def delete_system_job_log(
    request: Request,
    job_log_ids: Annotated[str, Path(description='需要删除的定时任务日志ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_job_log = DeleteJobLogModel(jobLogIds=job_log_ids)
    delete_job_log_result = await JobLogService.delete_job_log_services(query_db, delete_job_log)
    logger.info(delete_job_log_result.message)

    return ResponseUtil.success(msg=delete_job_log_result.message)


@job_controller.post(
    '/jobLog/export',
    summary='导出定时任务调度日志列表接口',
    description='用于导出当前符合查询条件的定时任务调度日志列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回定时任务日志列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('monitor:job:export')],
)
@Log(title='定时任务调度日志', business_type=BusinessType.EXPORT)
async def export_system_job_log_list(
    request: Request,
    job_log_page_query: Annotated[JobLogPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    job_log_query_result = await JobLogService.get_job_log_list_services(query_db, job_log_page_query, is_page=False)
    job_log_export_result = await JobLogService.export_job_log_list_services(request, job_log_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(job_log_export_result))
