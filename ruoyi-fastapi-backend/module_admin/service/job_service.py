import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import CommonConstant
from common.vo import CrudResponseModel, PageModel
from config.scheduler.job_adapter import JobAdapter
from config.scheduler.manager import SchedulerManager
from exceptions.exception import ServiceException
from module_admin.dao.job_dao import JobDao
from module_admin.dao.job_runtime_dao import JobRuntimeDao
from module_admin.entity.vo.job_runtime_vo import JobExecutionQueryModel, JobSyncQueryModel
from module_admin.entity.vo.job_vo import DeleteJobModel, EditJobModel, JobModel, JobPageQueryModel
from module_admin.service.dict_service import DictDataService
from utils.cron_util import CronUtil
from utils.excel_util import ExcelUtil
from utils.log_util import logger
from utils.time_util import TimezoneUtil


class JobService:
    """
    定时任务管理模块服务层
    """

    RUNTIME_FIELDS = {
        'cron_next_time',
        'next_run_time',
        'schedule_observed_time',
        'config_version',
        'applied_version',
        'sync_status',
        'sync_error',
        'applied_time',
    }

    @staticmethod
    def _validate_job(job: JobModel, *, check_target_permission: bool = True) -> JobModel:
        """
        在业务事务提交前完成与调度注册相同的配置校验

        :param job: 任务对象信息
        :param check_target_permission: 是否校验管理接口的调用目标白名单
        :return: 校验后的任务对象
        """
        job = JobAdapter.normalize(job)
        try:
            if check_target_permission:
                JobAdapter.validate_allowed_target(job.invoke_target)
            SchedulerManager._prepare_scheduler_job_add(job)
        except Exception as exc:
            raise ServiceException(message=f'任务配置无效：{exc}') from exc
        return job

    @classmethod
    async def _after_commit(cls, states: list[dict[str, Any]], action: str) -> CrudResponseModel:
        """
        反馈已提交修改的同步结果，后续同步失败不伪装成事务回滚

        :param states: 已提交的任务同步状态
        :param action: 任务操作类型
        :return: 业务提交及调度同步结果
        """
        job_ids = {state['jobId'] for state in states}
        try:
            sync = await SchedulerManager.request_scheduler_sync(job_ids, immediate=True)
        except Exception as exc:
            logger.exception('任务修改已提交，同步请求失败')
            sync = {'syncStatus': 'failed', 'syncError': str(exc)[:2000], 'jobs': []}
        results = {state['jobId']: state for state in states}
        for result in sync['jobs']:
            results[result['jobId']] = {**results.get(result['jobId'], {}), **result}
        submitted = {'新增': '新增已保存', '更新': '修改已保存', '删除': '删除已提交', '同步': '同步请求已提交'}[action]
        message = {
            'applied': f'{action}成功，调度已生效',
            'pending': f'{submitted}，等待调度生效',
            'failed': f'{submitted}，但调度同步失败，请查看同步状态',
        }[sync['syncStatus']]
        return CrudResponseModel(
            is_success=True, message=message, result={**sync, 'saved': True, 'jobs': list(results.values())}
        )

    @classmethod
    async def get_job_list_services(
        cls, query_db: AsyncSession, query_object: JobPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取定时任务列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 定时任务列表信息对象
        """
        job_list_result = await JobDao.get_job_list(query_db, query_object, is_page)
        rows = job_list_result.rows if isinstance(job_list_result, PageModel) else job_list_result
        states = await JobRuntimeDao.get_states(query_db, [row['jobId'] for row in rows])
        for row in rows:
            row['cronNextTime'] = cls._get_next_valid_time(row.get('cronExpression'), row.get('timeZone'))
            row.update(states.get(row['jobId'], {'syncStatus': 'pending'}))
            row['nextRunTime'] = cls._get_observed_next_run_time(row)

        return job_list_result

    @staticmethod
    def _get_observed_next_run_time(row: dict[str, Any]) -> datetime | None:
        """
        只展示已生效且近期被Leader观测到的实际调度时刻

        :param row: 包含任务状态与调度观测数据的字典
        :return: 实际下次调度时刻，停用、同步未完成或观测过期时返回None
        """
        observed = row.get('scheduleObservedTime')
        if row.get('status') != '0' or row.get('syncStatus') != 'applied' or not observed:
            return None
        if TimezoneUtil.utc_now() - TimezoneUtil.to_utc(observed) > timedelta(seconds=30):
            return None
        return row.get('nextRunTime')

    @staticmethod
    def _get_next_valid_time(cron_expression: str | None, time_zone: str | None) -> datetime | None:
        """
        根据任务时区计算Cron理论预览，不代表调度器已安排执行

        :param cron_expression: 任务Cron表达式
        :param time_zone: 任务IANA时区名称
        :return: 下一次UTC执行时刻，配置缺失或无未来结果时返回None
        """
        if not cron_expression or not time_zone:
            return None
        try:
            times = CronUtil.next_run_times(cron_expression, time_zone, TimezoneUtil.utc_now(), count=1)
        except (TypeError, ValueError):
            return None
        return times[0] if times else None

    @classmethod
    async def check_job_unique_services(cls, query_db: AsyncSession, page_object: JobModel) -> bool:
        """
        校验定时任务是否存在service

        :param query_db: orm对象
        :param page_object: 定时任务对象
        :return: 校验结果
        """
        job_id = -1 if page_object.job_id is None else page_object.job_id
        job = await JobDao.get_job_detail_by_info(query_db, page_object)
        if job and job.job_id != job_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def add_job_services(cls, query_db: AsyncSession, page_object: JobModel) -> CrudResponseModel:
        """
        新增定时任务信息service

        :param query_db: orm对象
        :param page_object: 新增定时任务对象
        :return: 新增定时任务校验结果
        """
        page_object = cls._validate_job(page_object.model_copy(update={'job_id': None}))
        if not await cls.check_job_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增定时任务{page_object.job_name}失败，定时任务已存在')
        try:
            db_job = await JobDao.add_job_dao(query_db, page_object)
            page_object = page_object.model_copy(update={'job_id': db_job.job_id})
            state = await JobRuntimeDao.record_configuration(query_db, db_job.job_id, page_object)
            await query_db.commit()
        except Exception as e:
            await query_db.rollback()
            raise e

        return await cls._after_commit([JobRuntimeDao.state_result(state)], '新增')

    @classmethod
    def _deal_edit_job(cls, page_object: EditJobModel, edit_job: dict[str, Any]) -> None:
        """
        处理编辑定时任务字典

        :param page_object: 编辑定时任务对象
        :param edit_job: 编辑定时任务字典
        """
        if page_object.type == 'status':
            for key in set(edit_job) - {'job_id', 'status', 'update_by'}:
                edit_job.pop(key)
        else:
            edit_job.pop('type', None)

    @classmethod
    async def edit_job_services(cls, query_db: AsyncSession, page_object: EditJobModel) -> CrudResponseModel:
        """
        编辑定时任务信息service

        :param query_db: orm对象
        :param page_object: 编辑定时任务对象
        :return: 编辑定时任务校验结果
        """
        edit_job = page_object.model_dump(
            exclude_unset=True,
            exclude={'create_time', 'update_time'} | cls.RUNTIME_FIELDS,
        )
        cls._deal_edit_job(page_object, edit_job)
        try:
            db_job, _state = await JobRuntimeDao.lock_job(query_db, page_object.job_id)
            if db_job is None:
                raise ServiceException(message='定时任务不存在')
            job_info = JobAdapter.from_record(db_job)
            changed = job_info.model_copy(update=edit_job)
            if page_object.type != 'status' or changed.status == '0':
                changed = cls._validate_job(changed, check_target_permission=page_object.type != 'status')
            for name in set(edit_job) & set(JobAdapter.CONFIG_FIELDS):
                edit_job[name] = getattr(changed, name)
            if page_object.type != 'status' and not await cls.check_job_unique_services(query_db, changed):
                raise ServiceException(message=f'修改定时任务{changed.job_name}失败，定时任务已存在')
            await JobDao.edit_job_dao(query_db, edit_job, job_info)
            state = await JobRuntimeDao.record_configuration(query_db, job_info.job_id, changed)
            await query_db.commit()
        except Exception:
            await query_db.rollback()
            raise
        return await cls._after_commit([JobRuntimeDao.state_result(state)], '更新')

    @classmethod
    async def execute_job_once_services(
        cls,
        query_db: AsyncSession,
        page_object: JobModel,
        *,
        requested_by: str | None = None,
    ) -> CrudResponseModel:
        """
        执行一次定时任务service

        :param query_db: orm对象
        :param page_object: 定时任务对象
        :param requested_by: 手动执行提交者
        :return: 执行一次定时任务结果
        """
        try:
            db_job, _state = await JobRuntimeDao.lock_job(query_db, page_object.job_id)
            if db_job is None:
                raise ServiceException(message='定时任务不存在')
            job_info = cls._validate_job(JobAdapter.from_record(db_job), check_target_permission=False)
            execution = await JobRuntimeDao.create_request(query_db, job_info, requested_by)
            await query_db.commit()
            result = JobRuntimeDao.execution_result(execution)
        except Exception:
            await query_db.rollback()
            raise
        await SchedulerManager.request_execution_dispatch()
        return CrudResponseModel(is_success=True, message='已提交执行，请查看执行记录', result=result)

    @classmethod
    async def delete_job_services(cls, query_db: AsyncSession, page_object: DeleteJobModel) -> CrudResponseModel:
        """
        删除定时任务信息service

        :param query_db: orm对象
        :param page_object: 删除定时任务对象
        :return: 删除定时任务校验结果
        """
        if page_object.job_ids:
            try:
                job_id_list = sorted({int(value) for value in page_object.job_ids.split(',')})
                if any(job_id <= 0 for job_id in job_id_list):
                    raise ValueError
            except ValueError as exc:
                raise ServiceException(message='任务ID必须为正整数') from exc
            states = []
            try:
                for job_id in job_id_list:
                    await JobRuntimeDao.lock_job(query_db, job_id)
                    await JobDao.delete_job_dao(query_db, JobModel(jobId=job_id))
                    state = await JobRuntimeDao.record_configuration(query_db, job_id, None)
                    states.append(JobRuntimeDao.state_result(state))
                await JobRuntimeDao.cancel_unstarted(query_db, job_id_list)
                await query_db.commit()
            except Exception as e:
                await query_db.rollback()
                raise e
            return await cls._after_commit(states, '删除')
        raise ServiceException(message='传入定时任务id为空')

    @classmethod
    async def job_detail_services(cls, query_db: AsyncSession, job_id: int) -> JobModel:
        """
        获取定时任务详细信息service

        :param query_db: orm对象
        :param job_id: 定时任务id
        :return: 定时任务id对应的信息
        """
        job = await JobDao.get_job_detail_by_id(query_db, job_id=job_id)
        if job is None:
            raise ServiceException(message='定时任务不存在')
        result = JobAdapter.from_record(job)
        result.cron_next_time = cls._get_next_valid_time(result.cron_expression, result.time_zone)
        state = (await JobRuntimeDao.get_states(query_db, [job_id])).get(job_id, {'syncStatus': 'pending'})
        result = result.model_copy(
            update={
                'config_version': state.get('configVersion'),
                'applied_version': state.get('appliedVersion'),
                'sync_status': state.get('syncStatus'),
                'sync_error': state.get('syncError'),
                'applied_time': state.get('appliedTime'),
                'next_run_time': cls._get_observed_next_run_time({**state, 'status': result.status}),
                'schedule_observed_time': state.get('scheduleObservedTime'),
            }
        )

        return result

    @classmethod
    async def execution_detail_services(cls, query_db: AsyncSession, execution_id: str) -> dict[str, Any]:
        """
        查询执行结果，任务删除后仍可按执行 ID 追踪

        :param query_db: orm对象
        :param execution_id: 执行ID
        :return: 执行状态及时间信息
        """
        execution = await JobRuntimeDao.get_execution(query_db, execution_id)
        if execution is None:
            raise ServiceException(message='执行记录不存在')
        return JobRuntimeDao.execution_result(execution)

    @staticmethod
    async def execution_list_services(query_db: AsyncSession, query: JobExecutionQueryModel) -> PageModel:
        """
        查询任务执行记录及未执行原因

        :param query_db: orm对象
        :param query: 查询参数对象
        :return: 执行记录分页信息
        """
        return await JobRuntimeDao.execution_page(query_db, query)

    @staticmethod
    async def sync_list_services(query_db: AsyncSession, query: JobSyncQueryModel) -> PageModel:
        """
        查询配置和删除操作的调度应用状态

        :param query_db: orm对象
        :param query: 查询参数对象
        :return: 同步状态分页信息
        """
        return await JobRuntimeDao.sync_page(query_db, query)

    @classmethod
    async def retry_sync_services(cls, query_db: AsyncSession, job_id: int) -> CrudResponseModel:
        """
        重试指定任务的最新配置或删除记录，不重复保存业务修改

        :param query_db: orm对象
        :param job_id: 任务ID
        :return: 调度同步结果
        """
        states = await JobRuntimeDao.get_states(query_db, [job_id])
        if job_id not in states:
            raise ServiceException(message='调度同步记录不存在')
        return await cls._after_commit([states[job_id]], '同步')

    @staticmethod
    async def export_job_list_services(request: Request, job_list: list) -> bytes:
        """
        导出定时任务信息service

        :param request: Request对象
        :param job_list: 定时任务信息列表
        :return: 定时任务信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'jobId': '任务编码',
            'jobName': '任务名称',
            'jobGroup': '任务组名',
            'jobStore': '调度存储',
            'jobExecutor': '任务执行器',
            'invokeTarget': '调用目标字符串',
            'jobArgs': '位置参数',
            'jobKwargs': '关键字参数',
            'cronExpression': 'cron执行表达式',
            'timeZone': 'cron时区',
            'misfireGraceTime': '允许延迟秒数',
            'coalesce': '积压处理',
            'maxInstances': '最大并发数',
            'status': '状态',
            'createBy': '创建者',
            'createTime': '创建时间',
            'updateBy': '更新者',
            'updateTime': '更新时间',
            'remark': '备注',
        }

        job_executor_list = await DictDataService.query_dict_data_list_from_cache_services(
            request.app.state.redis, dict_type='sys_job_executor'
        )
        job_executor_option = [
            {'label': item.get('dictLabel'), 'value': item.get('dictValue')} for item in job_executor_list
        ]
        job_executor_option_dict = {item.get('value'): item for item in job_executor_option}

        for item in job_list:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '暂停'
            if str(item.get('jobExecutor')) in job_executor_option_dict:
                item['jobExecutor'] = job_executor_option_dict.get(str(item.get('jobExecutor'))).get('label')
            item['misfireGraceTime'] = (
                item.get('misfireGraceTime') if item.get('misfireGraceTime') is not None else '不限'
            )
            item['coalesce'] = '只执行最近一次' if item.get('coalesce') else '逐次执行'
            item['jobArgs'] = json.dumps(item.get('jobArgs', []), ensure_ascii=False)
            item['jobKwargs'] = json.dumps(item.get('jobKwargs', {}), ensure_ascii=False)
        binary_data = ExcelUtil.export_list2excel(job_list, mapping_dict)

        return binary_data
