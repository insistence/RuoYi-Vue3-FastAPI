from typing import Any

from cli.exit_codes import DATABASE_ERROR, RUNTIME_ERROR

from .gateway import JobInfrastructureGateway
from .support import JobDomainSupport, JobSchedulerSupport


class JobRuntimeService:
    """
    定时任务运行时服务。

    该服务作为定时任务运行时 facade，对外统一暴露任务列表、详情、日志、
    执行一次、暂停与恢复入口。

    :param infrastructure_gateway: 定时任务基础设施网关
    :param domain_support: 定时任务领域支持对象
    :param scheduler_support: 定时任务调度上下文支持对象
    """

    def __init__(
        self,
        *,
        infrastructure_gateway: JobInfrastructureGateway | None = None,
        domain_support: JobDomainSupport | None = None,
        scheduler_support: JobSchedulerSupport | None = None,
    ) -> None:
        """
        初始化定时任务运行时服务。

        :param infrastructure_gateway: 定时任务基础设施网关
        :param domain_support: 定时任务领域支持对象
        :param scheduler_support: 定时任务调度上下文支持对象
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway or JobInfrastructureGateway()
        self.domain_support = domain_support or JobDomainSupport(self.infrastructure_gateway)
        self.scheduler_support = scheduler_support or JobSchedulerSupport(self.infrastructure_gateway)

    async def list_jobs(
        self,
        *,
        job_name: str = '',
        job_group: str = '',
        status: str | None = None,
        paged: bool = False,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        查询定时任务列表。

        :param job_name: 任务名称过滤条件
        :param job_group: 任务组过滤条件
        :param status: 状态过滤条件
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 定时任务列表结果
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        job_vo_module = self.infrastructure_gateway.get_job_vo_module()
        job_service = self.infrastructure_gateway.get_job_service()
        query_model = job_vo_module.JobPageQueryModel(
            jobName=job_name or None,
            jobGroup=job_group or None,
            status=status,
            pageNum=page_num,
            pageSize=page_size,
        )
        try:
            async with async_session_local() as session:
                result = await job_service.get_job_list_services(session, query_model, is_page=paged)
        except Exception as exc:
            return {'ok': False, 'message': '读取定时任务列表失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        filters = self.domain_support.build_filters(
            job_name=job_name,
            job_group=job_group,
            status=status,
            paged=paged,
            page_num=page_num,
            page_size=page_size,
        )
        return self.domain_support.build_list_payload(result, filters=filters, paged=paged)

    async def get_job_detail(self, job_id: int) -> dict[str, Any]:
        """
        读取单个定时任务详情。

        :param job_id: 任务 ID
        :return: 定时任务详情结果
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        job_service = self.infrastructure_gateway.get_job_service()
        try:
            async with async_session_local() as session:
                job_model = await job_service.job_detail_services(session, job_id)
        except Exception as exc:
            return {'ok': False, 'message': '读取定时任务详情失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        job_payload = self.domain_support.serialize_job_item(job_model)
        if not job_payload.get('jobId'):
            return {
                'ok': False,
                'message': f'定时任务不存在：{job_id}',
                'jobId': job_id,
                'exit_code': RUNTIME_ERROR,
            }
        return {'ok': True, 'job': job_payload}

    async def list_job_logs(
        self,
        *,
        job_name: str = '',
        job_group: str = '',
        status: str | None = None,
        begin_date: str = '',
        end_date: str = '',
        paged: bool = False,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        查询定时任务执行日志列表。

        :param job_name: 任务名称过滤条件
        :param job_group: 任务组过滤条件
        :param status: 执行状态过滤条件
        :param begin_date: 开始日期，格式 `YYYY-MM-DD`
        :param end_date: 结束日期，格式 `YYYY-MM-DD`
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 定时任务日志列表结果
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        job_log_service = self.infrastructure_gateway.get_job_log_service()
        job_vo_module = self.infrastructure_gateway.get_job_vo_module()
        query_model = job_vo_module.JobLogPageQueryModel(
            jobName=job_name or None,
            jobGroup=job_group or None,
            status=status,
            beginTime=begin_date or None,
            endTime=end_date or None,
            pageNum=page_num,
            pageSize=page_size,
        )
        try:
            async with async_session_local() as session:
                result = await job_log_service.get_job_log_list_services(session, query_model, is_page=paged)
        except Exception as exc:
            return {'ok': False, 'message': '读取定时任务日志列表失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        filters = self.domain_support.build_filters(
            job_name=job_name,
            job_group=job_group,
            status=status,
            begin_date=begin_date,
            end_date=end_date,
            paged=paged,
            page_num=page_num,
            page_size=page_size,
        )
        return self.domain_support.build_list_payload(result, filters=filters, paged=paged)

    async def run_with_scheduler_context(
        self,
        operation: str,
        job_id: int,
        *,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        在调度器上下文中执行任务操作。

        :param operation: 操作名称
        :param job_id: 任务ID
        :param status: 目标状态
        :return: 任务操作结果
        """
        operation_metadata = self.domain_support.build_job_operation_metadata(operation)
        redis = None
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        redis_util = self.infrastructure_gateway.get_redis_util()
        scheduler_util = self.infrastructure_gateway.get_scheduler_util()
        job_vo_module = self.infrastructure_gateway.get_job_vo_module()
        job_service = self.infrastructure_gateway.get_job_service()
        try:
            async with async_session_local() as session:
                redis = await redis_util.create_redis_pool(log_enabled=False)
                await scheduler_util.init_system_scheduler(redis)

                if operation == 'run-once':
                    result = await job_service.execute_job_once_services(session, job_vo_module.JobModel(jobId=job_id))
                elif operation in {'pause', 'resume'}:
                    result = await job_service.edit_job_services(
                        session,
                        job_vo_module.EditJobModel(jobId=job_id, status=status, type='status'),
                    )
                else:
                    raise ValueError(f'不支持的任务操作：{operation}')
        except Exception as exc:
            return {'ok': False, 'message': '执行定时任务操作失败', 'error': str(exc), 'exit_code': 22}
        finally:
            await self.scheduler_support.close_scheduler_context(redis)

        return {
            'ok': bool(result.is_success),
            'jobId': job_id,
            'operation': operation,
            'operationLabel': operation_metadata['operationLabel'],
            'targetStatus': status,
            'message': operation_metadata['successMessage'] if result.is_success else '定时任务操作执行失败',
            'serviceMessage': result.message,
        }

    async def run_job_once(self, job_id: int) -> dict[str, Any]:
        """
        执行一次指定定时任务。

        :param job_id: 任务ID
        :return: 执行结果
        """
        return await self.run_with_scheduler_context('run-once', job_id)

    async def pause_job(self, job_id: int) -> dict[str, Any]:
        """
        暂停指定定时任务。

        :param job_id: 任务ID
        :return: 暂停结果
        """
        return await self.run_with_scheduler_context('pause', job_id, status='1')

    async def resume_job(self, job_id: int) -> dict[str, Any]:
        """
        恢复指定定时任务。

        :param job_id: 任务ID
        :return: 恢复结果
        """
        return await self.run_with_scheduler_context('resume', job_id, status='0')


JOB_RUNTIME = JobRuntimeService()
