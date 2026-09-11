import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from apscheduler.job import Job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.util import obj_to_ref

from config.scheduler.job_adapter import JobAdapter
from config.scheduler.triggers import TaskDateTrigger
from module_admin.entity.vo.job_vo import JobModel
from utils.log_util import logger


class SchedulerJobs:
    """
    任务注册、配置比较和本地调度进度管理
    """

    def __init__(self, scheduler: AsyncIOScheduler) -> None:
        """
        绑定当前进程的调度器并初始化任务更新时间缓存

        :param scheduler: 当前进程的调度器
        :return: None
        """
        self.scheduler = scheduler
        self.update_time_cache: dict[str, datetime | None] = {}

    @staticmethod
    def parse_args(job_args: list[Any] | None) -> list[Any] | None:
        """
        解析任务位置参数。

        :param job_args: 数据库中的任务位置参数
        :return: 位置参数列表
        """
        return JobAdapter.parse_args(job_args) if job_args else None

    @staticmethod
    def dump_args(args: tuple[Any, ...] | list[Any] | None) -> str:
        """
        序列化任务位置参数。

        :param args: 调度器任务位置参数
        :return: 数据库存储字符串
        """
        return json.dumps(list(args), ensure_ascii=False) if args else ''

    @classmethod
    def import_function(cls, func_path: str) -> Callable[..., Any]:
        """
        动态导入函数

        :param func_path: 函数字符串，如module_task.scheduler_test.job
        :return: 导入的函数对象
        """
        return JobAdapter.import_function(func_path)

    @classmethod
    def prepare_job(cls, job_info: JobModel) -> dict[str, Any]:
        """
        构建调度器任务参数

        :param job_info: 任务对象信息
        :return: 调度器任务参数
        """
        return JobAdapter.prepare(job_info, function=cls.import_function(job_info.invoke_target))

    @classmethod
    def trigger_signature(cls, trigger: Any) -> tuple[Any, ...]:
        """
        提取用于比较触发器配置的完整签名

        :param trigger: 待比较的触发器对象
        :return: 包含时区、起止边界和子触发器信息的签名
        """
        if isinstance(trigger, CronTrigger):
            return (
                type(trigger).__module__,
                type(trigger).__qualname__,
                tuple((field.name, str(field)) for field in trigger.fields),
                str(trigger.timezone),
                trigger.start_date,
                trigger.end_date,
                trigger.jitter,
            )
        if isinstance(trigger, DateTrigger):
            return ('date', trigger.run_date)
        if isinstance(trigger, OrTrigger):
            return ('or', tuple(cls.trigger_signature(item) for item in trigger.triggers), trigger.jitter)
        return (type(trigger), trigger)

    @classmethod
    def is_config_current(cls, scheduler_job: Job, job_info: JobModel) -> bool:
        """
        判断任务配置是否一致

        :param scheduler_job: 调度器任务对象
        :param job_info: 数据库任务对象
        :return: 是否一致
        """
        job_state = scheduler_job.__getstate__()
        options = cls.prepare_job(job_info)
        expected = {
            'name': options['name'],
            'executor': options['executor'],
            'jobstore': options['jobstore'],
            'job_group': getattr(options['trigger'], 'task_job_group', 'default'),
            'misfire_grace_time': options['misfire_grace_time'],
            'coalesce': options['coalesce'],
            'max_instances': options['max_instances'],
            'trigger': cls.trigger_signature(options['trigger']),
            'args': tuple(options['args']),
            'kwargs': options['kwargs'],
            'func': obj_to_ref(options['func']),
        }
        current = {
            'name': job_state.get('name'),
            'executor': job_state.get('executor'),
            'jobstore': scheduler_job._jobstore_alias,
            'job_group': getattr(scheduler_job.trigger, 'task_job_group', 'default'),
            'misfire_grace_time': job_state.get('misfire_grace_time'),
            'coalesce': job_state.get('coalesce'),
            'max_instances': job_state.get('max_instances'),
            'trigger': cls.trigger_signature(job_state.get('trigger')),
            'args': tuple(job_state.get('args') or ()),
            'kwargs': dict(job_state.get('kwargs') or {}),
            'func': job_state.get('func'),
        }
        return expected == current

    def register_job(self, job_info: JobModel) -> bool:
        """
        注册或更新调度任务，保留未发生变化的调度进度

        :param job_info: 任务对象信息
        :return: 是否成功注册任务
        """
        existing_job = self.scheduler.get_job(job_id=str(job_info.job_id))
        options = self.prepare_job(job_info)
        if (
            existing_job
            and hasattr(existing_job, 'next_run_time')
            and self.trigger_signature(existing_job.trigger) == self.trigger_signature(options['trigger'])
        ):
            # 仅修改参数、策略、分组或存储时保留计划进度，让过期规则处理已到期计划。
            options['next_run_time'] = existing_job.next_run_time
        self.scheduler.add_job(**options, replace_existing=True)
        if existing_job and existing_job._jobstore_alias != job_info.job_store:
            self.scheduler.remove_job(job_id=str(job_info.job_id), jobstore=existing_job._jobstore_alias)
        return True

    def get_job(self, job_id: str | int) -> Job | None:
        """
        根据任务id获取任务对象

        :param job_id: 任务id
        :return: 任务对象
        """
        query_job = self.scheduler.get_job(job_id=str(job_id))

        return query_job

    def add_job(self, job_info: JobModel) -> None:
        """
        根据输入的任务对象信息添加任务

        :param job_info: 任务对象信息
        :return: None
        """
        self.scheduler.add_job(**self.prepare_job(job_info))
        self.record_update_time(str(job_info.job_id), job_info.update_time)

    def execute_once(self, job_info: JobModel, *, execution_id: str, dispatch_token: str) -> None:
        """
        将已持久化并领取的手动请求注册为独立单次任务

        :param job_info: 任务对象信息
        :param execution_id: 已持久化的执行请求 ID
        :param dispatch_token: 本次派发持有的领取凭据
        :return: None
        """
        options = self.prepare_job(job_info)
        options.update(
            id=f'_manual:{execution_id}',
            trigger=TaskDateTrigger(
                job_info.time_zone,
                task_job_id=job_info.job_id,
                task_job_group=job_info.job_group,
                execution_id=execution_id,
                dispatch_token=dispatch_token,
                timezone=timezone.utc,
            ),
            misfire_grace_time=None,
            coalesce=False,
            max_instances=1,
        )
        self.scheduler.add_job(**options, replace_existing=True)

    def remove_job(self, job_id: str | int) -> None:
        """
        根据任务id移除任务

        :param job_id: 任务id
        :return: None
        """
        job_id = str(job_id)
        query_job = self.get_job(job_id=job_id)
        if query_job:
            self.scheduler.remove_job(job_id=job_id)
        self.forget_update_time(job_id)

    def update_job(
        self, job_id: str, job_info: JobModel | None, scheduler_job: Job | None, job_update_time: datetime | None
    ) -> None:
        """
        同步更新任务配置

        :param job_id: 任务ID
        :param job_info: 数据库任务对象
        :param scheduler_job: 调度器任务对象
        :param job_update_time: 任务更新时间
        :return: None
        """
        if not job_info or not scheduler_job:
            return
        if self.has_update_time(job_id, job_update_time):
            return
        if not self.is_config_current(scheduler_job, job_info):
            if not self.register_job(job_info):
                return
            logger.info(f'♻️ 同步更新任务: {job_info.job_name}')
        self.record_update_time(job_id, job_update_time)

    def has_update_time(self, job_id: str, job_update_time: datetime | None) -> bool:
        """
        判断是否跳过同步更新

        :param job_id: 任务ID
        :param job_update_time: 任务更新时间
        :return: 是否跳过
        """
        return job_id in self.update_time_cache and self.update_time_cache[job_id] == job_update_time

    def record_update_time(self, job_id: str, job_update_time: datetime | None) -> None:
        """
        刷新任务更新时间缓存

        :param job_id: 任务ID
        :param job_update_time: 任务更新时间
        :return: None
        """
        self.update_time_cache[job_id] = job_update_time

    def forget_update_time(self, job_id: str) -> None:
        """
        移除任务更新时间缓存

        :param job_id: 任务ID
        :return: None
        """
        self.update_time_cache.pop(job_id, None)
