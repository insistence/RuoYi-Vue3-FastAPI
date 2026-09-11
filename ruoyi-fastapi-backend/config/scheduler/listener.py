import json

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED, SchedulerEvent

from config.scheduler.events import TimedJobExecutionEvent
from config.scheduler.resources import SchedulerResources
from module_admin.entity.vo.job_vo import JobLogModel
from module_admin.service.job_log_service import JobLogService
from utils.log_util import logger
from utils.time_util import TimezoneUtil


class SchedulerJobListener:
    """
    调度事件转换和任务执行日志持久化
    """

    def __init__(self, resources: SchedulerResources) -> None:
        """
        绑定执行日志使用的独立数据库会话资源

        :param resources: 调度数据库资源
        :return: None
        """
        self.resources = resources

    def handle_event(self, event: SchedulerEvent) -> None:
        """
        调度器事件监听器，记录任务执行日志

        :param event: APScheduler分发的任务执行事件
        :return: None
        """
        if not isinstance(event, TimedJobExecutionEvent) or (
            str(event.job_id).startswith('_') and not str(event.job_id).startswith('_manual:')
        ):
            return
        try:
            info = event.snapshot
            reason = {
                EVENT_JOB_ERROR: '执行失败',
                EVENT_JOB_MISSED: '错过执行窗口',
                EVENT_JOB_MAX_INSTANCES: '达到并发上限',
            }.get(event.code)
            message = f'任务ID: {info.job_id or event.job_id}, 执行ID: {event.execution_id}, {reason or "执行成功"}'
            if event.run_duration_ms is not None:
                message += f', 耗时：{event.run_duration_ms}毫秒'
            job_log = JobLogModel(
                jobId=info.job_id,
                executionId=event.execution_id,
                jobName=info.name,
                jobGroup=info.job_group,
                jobStore=info.jobstore,
                jobExecutor=info.executor,
                invokeTarget=info.invoke_target,
                jobArgs=json.loads(info.args) if info.args else [],
                jobKwargs=json.loads(info.kwargs),
                jobTrigger=info.trigger,
                jobMessage=message,
                status='1' if reason else '0',
                exceptionInfo=str(event.exception) if event.exception else (reason or ''),
                scheduledTime=event.scheduled_run_time,
                startTime=event.start_time,
                endTime=event.end_time,
                runDurationMs=event.run_duration_ms,
                timeZone=info.time_zone,
                createTime=TimezoneUtil.utc_now(),
            )
            self.persist_log(job_log)
        except Exception:
            logger.exception('调度任务事件监听器异常')

    def persist_log(self, job_log: JobLogModel) -> None:
        """
        使用独立同步会话保存任务执行日志

        :param job_log: 待保存的任务执行日志
        :return: None
        """
        session = self.resources.log_session_factory()()
        try:
            result = JobLogService.add_job_log_services(session, job_log)
            if not result.is_success:
                logger.error(f'记录任务执行日志失败: {result.message}')
        finally:
            session.close()
