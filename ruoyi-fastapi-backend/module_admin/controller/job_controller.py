from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession
from config.enums import BusinessType
from config.get_db import get_db
from module_admin.annotation.log_annotation import Log
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
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
from module_admin.service.login_service import LoginService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.page_util import PageResponseModel
from utils.response_util import ResponseUtil


jobController = APIRouter(prefix='/monitor', dependencies=[Depends(LoginService.get_current_user)])


@jobController.get(
    '/job/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:list'))]
)
async def get_system_job_list(
    request: Request,
    job_page_query: JobPageQueryModel = Depends(JobPageQueryModel.as_query),
    query_db: AsyncSession = Depends(get_db),
):
    # 获取分页数据
    notice_page_query_result = await JobService.get_job_list_services(query_db, job_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=notice_page_query_result)


@jobController.post('/job', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:add'))])
@ValidateFields(validate_model='add_job')
@Log(title='定时任务', business_type=BusinessType.INSERT)
async def add_system_job(
    request: Request,
    add_job: JobModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_job.create_by = current_user.user.user_name
    add_job.create_time = datetime.now()
    add_job.update_by = current_user.user.user_name
    add_job.update_time = datetime.now()
    add_job_result = await JobService.add_job_services(query_db, add_job)
    logger.info(add_job_result.message)

    return ResponseUtil.success(msg=add_job_result.message)


@jobController.put('/job', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:edit'))])
@ValidateFields(validate_model='edit_job')
@Log(title='定时任务', business_type=BusinessType.UPDATE)
async def edit_system_job(
    request: Request,
    edit_job: EditJobModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    edit_job.update_by = current_user.user.user_name
    edit_job.update_time = datetime.now()
    edit_job_result = await JobService.edit_job_services(query_db, edit_job)
    logger.info(edit_job_result.message)

    return ResponseUtil.success(msg=edit_job_result.message)


@jobController.put('/job/changeStatus', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:changeStatus'))])
@Log(title='定时任务', business_type=BusinessType.UPDATE)
async def change_system_job_status(
    request: Request,
    change_job: EditJobModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
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


@jobController.put('/job/run', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:changeStatus'))])
@Log(title='定时任务', business_type=BusinessType.UPDATE)
async def execute_system_job(request: Request, execute_job: JobModel, query_db: AsyncSession = Depends(get_db)):
    execute_job_result = await JobService.execute_job_once_services(query_db, execute_job)
    logger.info(execute_job_result.message)

    return ResponseUtil.success(msg=execute_job_result.message)


@jobController.delete('/job/{job_ids}', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:remove'))])
@Log(title='定时任务', business_type=BusinessType.DELETE)
async def delete_system_job(request: Request, job_ids: str, query_db: AsyncSession = Depends(get_db)):
    delete_job = DeleteJobModel(jobIds=job_ids)
    delete_job_result = await JobService.delete_job_services(query_db, delete_job)
    logger.info(delete_job_result.message)

    return ResponseUtil.success(msg=delete_job_result.message)


@jobController.get(
    '/job/{job_id}', response_model=JobModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:query'))]
)
async def query_detail_system_job(request: Request, job_id: int, query_db: AsyncSession = Depends(get_db)):
    job_detail_result = await JobService.job_detail_services(query_db, job_id)
    logger.info(f'获取job_id为{job_id}的信息成功')

    return ResponseUtil.success(data=job_detail_result)


@jobController.post('/job/export', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:export'))])
@Log(title='定时任务', business_type=BusinessType.EXPORT)
async def export_system_job_list(
    request: Request,
    job_page_query: JobPageQueryModel = Form(),
    query_db: AsyncSession = Depends(get_db),
):
    # 获取全量数据
    job_query_result = await JobService.get_job_list_services(query_db, job_page_query, is_page=False)
    job_export_result = await JobService.export_job_list_services(request, job_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(job_export_result))


@jobController.get(
    '/jobLog/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:list'))]
)
async def get_system_job_log_list(
    request: Request,
    job_log_page_query: JobLogPageQueryModel = Depends(JobLogPageQueryModel.as_query),
    query_db: AsyncSession = Depends(get_db),
):
    # 获取分页数据
    job_log_page_query_result = await JobLogService.get_job_log_list_services(
        query_db, job_log_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=job_log_page_query_result)


@jobController.delete('/jobLog/clean', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:remove'))])
@Log(title='定时任务调度日志', business_type=BusinessType.CLEAN)
async def clear_system_job_log(request: Request, query_db: AsyncSession = Depends(get_db)):
    clear_job_log_result = await JobLogService.clear_job_log_services(query_db)
    logger.info(clear_job_log_result.message)

    return ResponseUtil.success(msg=clear_job_log_result.message)


@jobController.delete('/jobLog/{job_log_ids}', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:remove'))])
@Log(title='定时任务调度日志', business_type=BusinessType.DELETE)
async def delete_system_job_log(request: Request, job_log_ids: str, query_db: AsyncSession = Depends(get_db)):
    delete_job_log = DeleteJobLogModel(jobLogIds=job_log_ids)
    delete_job_log_result = await JobLogService.delete_job_log_services(query_db, delete_job_log)
    logger.info(delete_job_log_result.message)

    return ResponseUtil.success(msg=delete_job_log_result.message)


@jobController.post('/jobLog/export', dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:export'))])
@Log(title='定时任务调度日志', business_type=BusinessType.EXPORT)
async def export_system_job_log_list(
    request: Request,
    job_log_page_query: JobLogPageQueryModel = Form(),
    query_db: AsyncSession = Depends(get_db),
):
    # 获取全量数据
    job_log_query_result = await JobLogService.get_job_log_list_services(query_db, job_log_page_query, is_page=False)
    job_log_export_result = await JobLogService.export_job_log_list_services(request, job_log_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(job_log_export_result))
