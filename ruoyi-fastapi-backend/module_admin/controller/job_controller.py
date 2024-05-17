from fastapi import APIRouter
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, CurrentUserModel
from module_admin.service.job_service import *
from module_admin.service.job_log_service import *
from utils.response_util import *
from utils.log_util import *
from utils.page_util import *
from utils.common_util import bytes2file_response
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


jobController = APIRouter(prefix='/monitor', dependencies=[Depends(LoginService.get_current_user)])


@jobController.get("/job/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:list'))])
async def get_system_job_list(request: Request, job_page_query: JobPageQueryModel = Depends(JobPageQueryModel.as_query), query_db: AsyncSession = Depends(get_db)):
    try:
        # 获取分页数据
        notice_page_query_result = await JobService.get_job_list_services(query_db, job_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=notice_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.post("/job", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:add'))])
@log_decorator(title='定时任务管理', business_type=1)
async def add_system_job(request: Request, add_job: JobModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_job.create_by = current_user.user.user_name
        add_job.update_by = current_user.user.user_name
        add_job_result = await JobService.add_job_services(query_db, add_job)
        if add_job_result.is_success:
            logger.info(add_job_result.message)
            return ResponseUtil.success(msg=add_job_result.message)
        else:
            logger.warning(add_job_result.message)
            return ResponseUtil.failure(msg=add_job_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.put("/job", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:edit'))])
@log_decorator(title='定时任务管理', business_type=2)
async def edit_system_job(request: Request, edit_job: EditJobModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_job.update_by = current_user.user.user_name
        edit_job.update_time = datetime.now()
        edit_job_result = await JobService.edit_job_services(query_db, edit_job)
        if edit_job_result.is_success:
            logger.info(edit_job_result.message)
            return ResponseUtil.success(msg=edit_job_result.message)
        else:
            logger.warning(edit_job_result.message)
            return ResponseUtil.failure(msg=edit_job_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.put("/job/changeStatus", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:changeStatus'))])
@log_decorator(title='定时任务管理', business_type=2)
async def edit_system_job(request: Request, edit_job: EditJobModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_job.update_by = current_user.user.user_name
        edit_job.update_time = datetime.now()
        edit_job.type = 'status'
        edit_job_result = await JobService.edit_job_services(query_db, edit_job)
        if edit_job_result.is_success:
            logger.info(edit_job_result.message)
            return ResponseUtil.success(msg=edit_job_result.message)
        else:
            logger.warning(edit_job_result.message)
            return ResponseUtil.failure(msg=edit_job_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.put("/job/run", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:changeStatus'))])
@log_decorator(title='定时任务管理', business_type=2)
async def execute_system_job(request: Request, execute_job: JobModel, query_db: AsyncSession = Depends(get_db)):
    try:
        execute_job_result = await JobService.execute_job_once_services(query_db, execute_job)
        if execute_job_result.is_success:
            logger.info(execute_job_result.message)
            return ResponseUtil.success(msg=execute_job_result.message)
        else:
            logger.warning(execute_job_result.message)
            return ResponseUtil.failure(msg=execute_job_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.delete("/job/{job_ids}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:remove'))])
@log_decorator(title='定时任务管理', business_type=3)
async def delete_system_job(request: Request, job_ids: str, query_db: AsyncSession = Depends(get_db)):
    try:
        delete_job = DeleteJobModel(jobIds=job_ids)
        delete_job_result = await JobService.delete_job_services(query_db, delete_job)
        if delete_job_result.is_success:
            logger.info(delete_job_result.message)
            return ResponseUtil.success(msg=delete_job_result.message)
        else:
            logger.warning(delete_job_result.message)
            return ResponseUtil.failure(msg=delete_job_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.get("/job/{job_id}", response_model=JobModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:query'))])
async def query_detail_system_job(request: Request, job_id: int, query_db: AsyncSession = Depends(get_db)):
    try:
        job_detail_result = await JobService.job_detail_services(query_db, job_id)
        logger.info(f'获取job_id为{job_id}的信息成功')
        return ResponseUtil.success(data=job_detail_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.post("/job/export", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:export'))])
@log_decorator(title='定时任务管理', business_type=5)
async def export_system_job_list(request: Request, job_page_query: JobPageQueryModel = Depends(JobPageQueryModel.as_form), query_db: AsyncSession = Depends(get_db)):
    try:
        # 获取全量数据
        job_query_result = await JobService.get_job_list_services(query_db, job_page_query, is_page=False)
        job_export_result = await JobService.export_job_list_services(request, job_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(job_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.get("/jobLog/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:list'))])
async def get_system_job_log_list(request: Request, job_log_page_query: JobLogPageQueryModel = Depends(JobLogPageQueryModel.as_query), query_db: AsyncSession = Depends(get_db)):
    try:
        # 获取分页数据
        job_log_page_query_result = await JobLogService.get_job_log_list_services(query_db, job_log_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=job_log_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.delete("/jobLog/clean", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:remove'))])
@log_decorator(title='定时任务日志管理', business_type=9)
async def clear_system_job_log(request: Request, query_db: AsyncSession = Depends(get_db)):
    try:
        clear_job_log_result = await JobLogService.clear_job_log_services(query_db)
        if clear_job_log_result.is_success:
            logger.info(clear_job_log_result.message)
            return ResponseUtil.success(msg=clear_job_log_result.message)
        else:
            logger.warning(clear_job_log_result.message)
            return ResponseUtil.failure(msg=clear_job_log_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.delete("/jobLog/{job_log_ids}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:remove'))])
@log_decorator(title='定时任务日志管理', business_type=3)
async def delete_system_job_log(request: Request, job_log_ids: str, query_db: AsyncSession = Depends(get_db)):
    try:
        delete_job_log = DeleteJobLogModel(jobLogIds=job_log_ids)
        delete_job_log_result = await JobLogService.delete_job_log_services(query_db, delete_job_log)
        if delete_job_log_result.is_success:
            logger.info(delete_job_log_result.message)
            return ResponseUtil.success(msg=delete_job_log_result.message)
        else:
            logger.warning(delete_job_log_result.message)
            return ResponseUtil.failure(msg=delete_job_log_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@jobController.post("/jobLog/export", dependencies=[Depends(CheckUserInterfaceAuth('monitor:job:export'))])
@log_decorator(title='定时任务日志管理', business_type=5)
async def export_system_job_log_list(request: Request, job_log_page_query: JobLogPageQueryModel = Depends(JobLogPageQueryModel.as_form), query_db: AsyncSession = Depends(get_db)):
    try:
        # 获取全量数据
        job_log_query_result = await JobLogService.get_job_log_list_services(query_db, job_log_page_query, is_page=False)
        job_log_export_result = await JobLogService.export_job_log_list_services(request, job_log_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(job_log_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
