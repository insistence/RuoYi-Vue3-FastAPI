from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Form, Path, Query, Request, Response
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from module_admin.entity.vo.job_vo import (
    DeleteJobLogModel,
    DeleteJobModel,
    EditJobModel,
    JobLogPageQueryModel,
    JobModel,
    JobPageQueryModel,
)
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.job_log_service import JobLogService
from module_admin.service.job_service import JobService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.page_util import PageResponseModel
from utils.response_util import ResponseUtil

job_controller = APIRouter(prefix='/monitor', dependencies=[PreAuthDependency()])


@job_controller.get(
    '/job/list',
    response_model=PageResponseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:job:list')],
)
async def get_system_job_list(
    request: Request,
    job_page_query: Annotated[JobPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    notice_page_query_result = await JobService.get_job_list_services(query_db, job_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=notice_page_query_result)


@job_controller.post(
    '/job',
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
    response_model=JobModel,
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
    response_model=PageResponseModel,
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
