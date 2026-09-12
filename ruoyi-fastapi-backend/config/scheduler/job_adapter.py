import hashlib
import importlib
import json
import pickle
from collections.abc import Callable
from typing import Any

from apscheduler.job import Job
from apscheduler.util import iscoroutinefunction_partial, obj_to_ref

from common.constant import CommonConstant, JobConstant
from module_admin.entity.vo.job_vo import JobModel
from utils.cron_util import MyCronTrigger
from utils.string_util import StringUtil


class JobAdapter:
    """
    统一任务默认值、参数解析和调度配置校验
    """

    JOB_STORES = frozenset({'default', 'sqlalchemy', 'redis'})
    EXECUTORS = frozenset({'default', 'processpool'})
    CONFIG_FIELDS = (
        'job_name',
        'job_group',
        'job_store',
        'job_executor',
        'invoke_target',
        'job_args',
        'job_kwargs',
        'cron_expression',
        'time_zone',
        'misfire_grace_time',
        'coalesce',
        'max_instances',
        'status',
    )

    @staticmethod
    def from_record(record: Any) -> JobModel:
        """
        读取已保存配置，不在读取阶段阻断无效配置的诊断和停用

        :param record: 数据库记录或任务对象
        :return: 任务对象信息
        """
        if isinstance(record, JobModel):
            return record
        return JobModel.model_construct(
            **{name: getattr(record, name) for name in JobModel.model_fields if hasattr(record, name)}
        )

    @staticmethod
    def normalize(job: JobModel) -> JobModel:
        """
        补齐保存和注册共用的默认值，保留显式填写的配置

        :param job: 任务对象信息
        :return: 补齐默认值后的任务对象
        """
        defaults = {
            'job_group': 'default',
            'job_executor': 'default',
            'status': '1',
        }
        values = {key: value for key, value in defaults.items() if getattr(job, key) is None}
        for name in ('job_name', 'job_group'):
            if isinstance(value := getattr(job, name), str):
                values[name] = value.strip()
        return job.model_copy(update=values)

    @staticmethod
    def parse_args(value: list[Any]) -> list[Any]:
        """
        校验位置参数为JSON数组，保留数组内的值类型

        :param value: 待解析的位置参数
        :return: 位置参数列表
        """
        if not isinstance(value, list):
            raise ValueError('位置参数必须是 JSON 数组')
        return value

    @staticmethod
    def import_function(target: str) -> Callable[..., Any]:
        """
        导入任务函数，明确拒绝不存在和不可调用的目标

        :param target: 调用目标字符串
        :return: 任务函数
        """
        try:
            module_name, name = target.rsplit('.', 1)
            function = getattr(importlib.import_module(module_name), name)
        except (AttributeError, ImportError, TypeError, ValueError) as exc:
            raise ValueError(f'调用目标不存在或无法导入：{target}') from exc
        if not callable(function):
            raise ValueError(f'调用目标不可调用：{target}')
        return function

    @staticmethod
    def validate_allowed_target(target: str | None) -> None:
        """
        校验管理接口允许保存的调用模块，按完整模块前缀匹配

        :param target: 调用目标字符串
        :return: None
        """
        if not target:
            raise ValueError('调用目标不能为空')
        forbidden = [
            CommonConstant.LOOKUP_RMI,
            CommonConstant.LOOKUP_LDAP,
            CommonConstant.LOOKUP_LDAPS,
            CommonConstant.HTTP,
            CommonConstant.HTTPS,
        ]
        if StringUtil.contains_any_ignore_case(target, forbidden) or StringUtil.startswith_any_case(
            target, JobConstant.JOB_ERROR_LIST
        ):
            raise ValueError('调用目标包含禁止使用的模块或协议')
        if not any(
            target.lower().startswith(f'{prefix.rstrip(".").lower()}.') for prefix in JobConstant.JOB_WHITE_LIST
        ):
            raise ValueError('调用目标字符串不在白名单内')

    @classmethod
    def prepare(cls, job: JobModel, *, function: Callable[..., Any] | None = None) -> dict[str, Any]:
        """
        校验完整配置并构造注册参数，不写数据库或改变调度器

        :param job: 任务对象信息
        :param function: 已导入的任务函数，未指定时根据调用目标导入
        :return: 调度器任务注册参数
        """
        job = JobModel.model_validate(cls.normalize(job).model_dump(by_alias=True))
        if not job.job_name or not job.job_name.strip():
            raise ValueError('任务名称不能为空')
        for name, limit in {
            'job_name': 64,
            'job_group': 64,
            'invoke_target': 500,
            'cron_expression': 255,
        }.items():
            value = getattr(job, name)
            if value is not None and len(value) > limit:
                raise ValueError(f'{name} 长度不能超过 {limit} 个字符')
        if not job.job_group:
            raise ValueError('业务分组不能为空')
        if job.job_store not in cls.JOB_STORES:
            raise ValueError(f'任务存储未注册：{job.job_store}')
        if job.job_executor not in cls.EXECUTORS:
            raise ValueError(f'任务执行器未注册：{job.job_executor}')
        if not job.invoke_target:
            raise ValueError('调用目标不能为空')
        function = function if function is not None else cls.import_function(job.invoke_target)
        if not callable(function):
            raise ValueError('调用目标不可调用')
        kwargs = job.job_kwargs
        # 禁止非有限数值进入JSON列，避免数据库与执行器对同一参数产生不同解释。
        json.dumps([job.job_args, kwargs], allow_nan=False)
        executor = 'default' if iscoroutinefunction_partial(function) else job.job_executor
        trigger = MyCronTrigger.from_crontab(job.cron_expression, job.time_zone)
        trigger.task_job_group = job.job_group
        options = {
            'func': function,
            'trigger': trigger,
            'args': cls.parse_args(job.job_args),
            'kwargs': kwargs,
            'id': str(job.job_id) if job.job_id is not None else 'validation',
            'name': job.job_name,
            'misfire_grace_time': job.misfire_grace_time,
            'coalesce': job.coalesce,
            'max_instances': job.max_instances,
            'jobstore': job.job_store,
            'executor': executor,
        }
        try:
            # Job 构造器执行与真实注册相同的函数签名和参数校验，但不会注册任务。
            Job(None, **{key: value for key, value in options.items() if key != 'jobstore'})
            obj_to_ref(function)
            if executor == 'processpool' or job.job_store != 'default':
                pickle.dumps((obj_to_ref(function), options['args'], kwargs, options['trigger']))
        except (AttributeError, TypeError, ValueError, pickle.PickleError) as exc:
            raise ValueError(f'任务函数或参数不符合调度要求：{exc}') from exc
        return options

    @classmethod
    def config_hash(cls, job: JobModel | None) -> str:
        """
        计算调度配置摘要，供版本跟踪和插件变更校准使用

        :param job: 任务对象信息
        :return: 任务配置摘要
        """
        data = None if job is None else cls.normalize(job).model_dump(include=set(cls.CONFIG_FIELDS), mode='json')
        value = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(value.encode()).hexdigest()
