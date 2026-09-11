import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from apscheduler.events import JobExecutionEvent
from apscheduler.job import Job

from config.scheduler.triggers import trigger_timezone
from utils.time_util import TimezoneUtil


@dataclass(frozen=True)
class JobSnapshot:
    """
    任务提交时的不可变配置快照
    """

    name: str
    jobstore: str
    executor: str
    invoke_target: str
    args: str
    kwargs: str
    trigger: str
    time_zone: str | None
    job_group: str = 'default'
    job_id: int | None = None
    execution_id: str | None = None
    dispatch_token: str | None = None
    managed: bool = False

    @classmethod
    def from_job(cls, job: Job, *, managed: bool = False) -> 'JobSnapshot':
        """
        从调度器任务提取执行日志所需的配置

        :param job: 调度器任务对象
        :param managed: 是否启用持久化执行管理
        :return: 与后续任务变更无关的配置快照
        """
        return cls(
            name=job.name,
            jobstore=job._jobstore_alias,
            executor=job.executor,
            invoke_target=job.func_ref or str(job.func),
            args=json.dumps(list(job.args), ensure_ascii=False, default=str) if job.args else '',
            kwargs=json.dumps(job.kwargs, ensure_ascii=False, default=str),
            trigger=str(job.trigger),
            time_zone=trigger_timezone(job.trigger),
            job_group=getattr(job.trigger, 'task_job_group', 'default'),
            job_id=getattr(job.trigger, 'task_job_id', None) or (int(job.id) if job.id.isdecimal() else None),
            execution_id=getattr(job.trigger, 'execution_id', None),
            dispatch_token=getattr(job.trigger, 'dispatch_token', None),
            managed=managed and (job.id.isdecimal() or job.id.startswith('_manual:')),
        )

    def execution_snapshot(self) -> dict[str, Any]:
        """
        生成跨进程执行记录需要的可序列化配置快照

        :return: 可序列化的任务配置快照
        """
        return {
            'jobId': self.job_id,
            'jobName': self.name,
            'jobGroup': self.job_group,
            'jobStore': self.jobstore,
            'jobExecutor': self.executor,
            'invokeTarget': self.invoke_target,
            'jobArgs': json.loads(self.args) if self.args else [],
            'jobKwargs': json.loads(self.kwargs),
            'timeZone': self.time_zone,
        }


class TimedJobExecutionEvent(JobExecutionEvent):
    """
    包含任务快照、真实起止时刻和耗时的执行事件
    """

    def __init__(self, code: int, job: Job, run_time: datetime, snapshot: JobSnapshot, **kwargs) -> None:
        """
        初始化任务执行事件

        :param code: APScheduler事件类型
        :param job: 调度器任务对象
        :param run_time: 本次计划执行时刻
        :param snapshot: 提交任务时的配置快照
        :param kwargs: 传递给标准执行事件的附加参数
        :return: None
        """
        super().__init__(code, job.id, snapshot.jobstore, run_time, **kwargs)
        self.snapshot = snapshot
        self.execution_id = snapshot.execution_id or (
            uuid5(NAMESPACE_URL, f'ruoyi-job:{snapshot.job_id}:{TimezoneUtil.to_utc(run_time).isoformat()}').hex
            if snapshot.managed
            else uuid4().hex
        )
        self.execution_key = (snapshot.jobstore, job.id, TimezoneUtil.to_utc(run_time))
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.run_duration_ms: int | None = None
        self.execution_status: str | None = None
