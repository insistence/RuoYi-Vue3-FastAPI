import json
import re
from apscheduler.events import EVENT_ALL
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Union
from config.database import AsyncSessionLocal, quote_plus
from config.env import DataBaseConfig, RedisConfig
from exceptions.exception import ServiceException
from module_admin.dao.job_dao import JobDao
from module_admin.entity.vo.job_vo import JobLogModel, JobModel
from module_admin.service.job_log_service import JobLogService
from utils.log_util import logger
import module_task  # noqa: F401


# 重写Cron定时
class MyCronTrigger(CronTrigger):
    @classmethod
    def from_crontab(cls, expr: str, timezone=None):
        values = expr.split()
        if len(values) != 6 and len(values) != 7:
            raise ValueError('Wrong number of fields; got {}, expected 6 or 7'.format(len(values)))

        second = values[0]
        minute = values[1]
        hour = values[2]
        if '?' in values[3]:
            day = None
        elif 'L' in values[5]:
            day = f"last {values[5].replace('L', '')}"
        elif 'W' in values[3]:
            day = cls.__find_recent_workday(int(values[3].split('W')[0]))
        else:
            day = values[3].replace('L', 'last')
        month = values[4]
        if '?' in values[5] or 'L' in values[5]:
            week = None
        elif '#' in values[5]:
            week = int(values[5].split('#')[1])
        else:
            week = values[5]
        if '#' in values[5]:
            day_of_week = int(values[5].split('#')[0]) - 1
        else:
            day_of_week = None
        year = values[6] if len(values) == 7 else None
        return cls(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            week=week,
            day_of_week=day_of_week,
            year=year,
            timezone=timezone,
        )

    @classmethod
    def __find_recent_workday(cls, day: int):
        now = datetime.now()
        date = datetime(now.year, now.month, day)
        if date.weekday() < 5:
            return date.day
        else:
            diff = 1
            while True:
                previous_day = date - timedelta(days=diff)
                if previous_day.weekday() < 5:
                    return previous_day.day
                else:
                    diff += 1


SQLALCHEMY_DATABASE_URL = (
    f'mysql+pymysql://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
    f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=DataBaseConfig.db_echo,
    max_overflow=DataBaseConfig.db_max_overflow,
    pool_size=DataBaseConfig.db_pool_size,
    pool_recycle=DataBaseConfig.db_pool_recycle,
    pool_timeout=DataBaseConfig.db_pool_timeout,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
job_stores = {
    'default': MemoryJobStore(),
    'sqlalchemy': SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URL, engine=engine),
    'redis': RedisJobStore(
        **dict(
            host=RedisConfig.redis_host,
            port=RedisConfig.redis_port,
            username=RedisConfig.redis_username,
            password=RedisConfig.redis_password,
            db=RedisConfig.redis_database,
        )
    ),
}
executors = {'default': ThreadPoolExecutor(20), 'processpool': ProcessPoolExecutor(5)}
job_defaults = {'coalesce': False, 'max_instance': 1}
scheduler = BackgroundScheduler()
scheduler.configure(jobstores=job_stores, executors=executors, job_defaults=job_defaults)


class SchedulerUtil:
    """
    定时任务相关方法
    """

    @classmethod
    async def init_system_scheduler(cls):
        """
        应用启动时初始化定时任务

        :return:
        """
        logger.info('开始启动定时任务...')
        scheduler.start()
        async with AsyncSessionLocal() as session:
            job_list = await JobDao.get_job_list_for_scheduler(session)
            for item in job_list:
                query_job = cls.get_scheduler_job(job_id=str(item.job_id))
                if query_job:
                    cls.remove_scheduler_job(job_id=str(item.job_id))
                cls.add_scheduler_job(item)
        scheduler.add_listener(cls.scheduler_event_listener, EVENT_ALL)
        logger.info('系统初始定时任务加载成功')

    @classmethod
    async def close_system_scheduler(cls):
        """
        应用关闭时关闭定时任务

        :return:
        """
        scheduler.shutdown()
        logger.info('关闭定时任务成功')

    @classmethod
    def get_scheduler_job(cls, job_id: Union[str, int]):
        """
        根据任务id获取任务对象

        :param job_id: 任务id
        :return: 任务对象
        """
        query_job = scheduler.get_job(job_id=str(job_id))

        return query_job

    @classmethod
    def add_scheduler_job(cls, job_info: JobModel):
        """
        根据输入的任务对象信息添加任务

        :param job_info: 任务对象信息
        :return:
        """
        scheduler.add_job(
            func=eval(job_info.invoke_target),
            trigger=MyCronTrigger.from_crontab(job_info.cron_expression),
            args=job_info.job_args.split(',') if job_info.job_args else None,
            kwargs=json.loads(job_info.job_kwargs) if job_info.job_kwargs else None,
            id=str(job_info.job_id),
            name=job_info.job_name,
            misfire_grace_time=1000000000000 if job_info.misfire_policy == '3' else None,
            coalesce=True if job_info.misfire_policy == '2' else False,
            max_instances=3 if job_info.concurrent == '0' else 1,
            jobstore=job_info.job_group,
            executor=job_info.job_executor,
        )

    @classmethod
    def execute_scheduler_job_once(cls, job_info: JobModel):
        """
        根据输入的任务对象执行一次任务

        :param job_info: 任务对象信息
        :return:
        """
        scheduler.add_job(
            func=eval(job_info.invoke_target),
            trigger='date',
            run_date=datetime.now() + timedelta(seconds=1),
            args=job_info.job_args.split(',') if job_info.job_args else None,
            kwargs=json.loads(job_info.job_kwargs) if job_info.job_kwargs else None,
            id=str(job_info.job_id),
            name=job_info.job_name,
            misfire_grace_time=1000000000000 if job_info.misfire_policy == '3' else None,
            coalesce=True if job_info.misfire_policy == '2' else False,
            max_instances=3 if job_info.concurrent == '0' else 1,
            jobstore=job_info.job_group,
            executor=job_info.job_executor,
        )

    @classmethod
    def remove_scheduler_job(cls, job_id: Union[str, int]):
        """
        根据任务id移除任务

        :param job_id: 任务id
        :return:
        """
        scheduler.remove_job(job_id=str(job_id))

    @classmethod
    def __valid_range(cls, search_str: str, start_range: int, end_range: int):
        match = re.match(r'^(\d+)-(\d+)$', search_str)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            return start_range <= start < end <= end_range
        return False

    @classmethod
    def __valid_sum(
        cls, search_str: str, start_range_a: int, start_range_b: int, end_range_a: int, end_range_b: int, sum_range: int
    ):
        match = re.match(r'^(\d+)/(\d+)$', search_str)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            return (
                start_range_a <= start <= start_range_b
                and end_range_a <= end <= end_range_b
                and start + end <= sum_range
            )
        return False

    @classmethod
    def __validate_second_or_minute(cls, second_or_minute: str):
        """
        校验秒或分钟值是否正确

        :param second_or_minute: 秒或分钟值
        :return: 校验结果
        """
        if (
            second_or_minute == '*'
            or ('-' in second_or_minute and cls.__valid_range(second_or_minute, 0, 59))
            or ('/' in second_or_minute and cls.__valid_sum(second_or_minute, 0, 58, 1, 59))
            or re.match(r'^(?:[0-5]?\d|59)(?:,[0-5]?\d|59)*$', second_or_minute)
        ):
            return True
        return False

    @classmethod
    def __validate_hour(cls, hour: str):
        """
        校验小时值是否正确
        :param hour: 小时值
        :return: 校验结果
        """
        if (
            hour == '*'
            or ('-' in hour and cls.__valid_range(hour, 0, 23))
            or ('/' in hour and cls.__valid_sum(hour, 0, 22, 1, 23, 23))
            or re.match(r'^(?:0|[1-9]|1\d|2[0-3])(?:,(?:0|[1-9]|1\d|2[0-3]))*$', hour)
        ):
            return True
        return False

    @classmethod
    def __validate_day(cls, day: str):
        """
        校验日值是否正确
        :param day: 日值
        :return: 校验结果
        """
        if (
            day in ['*', '?', 'L']
            or ('-' in day and cls.__valid_range(day, 1, 31))
            or ('/' in day and cls.__valid_sum(day, 1, 30, 1, 30, 31))
            or ('W' in day and re.match(r'^(?:[1-9]|1\d|2\d|3[01])W$', day))
            or re.match(r'^(?:0|[1-9]|1\d|2[0-9]|3[0-1])(?:,(?:0|[1-9]|1\d|2[0-9]|3[0-1]))*$', day)
        ):
            return True
        return False

    @classmethod
    def __validate_month(cls, month: str):
        """
        校验月值是否正确
        :param month: 月值
        :return: 校验结果
        """
        if (
            month == '*'
            or ('-' in month and cls.__valid_range(month, 1, 12))
            or ('/' in month and cls.__valid_sum(month, 1, 11, 1, 11, 12))
            or re.match(r'^(?:0|[1-9]|1[0-2])(?:,(?:0|[1-9]|1[0-2]))*$', month)
        ):
            return True
        return False

    @classmethod
    def __validate_week(cls, week: str):
        """
        校验周值是否正确
        :param week: 周值
        :return: 校验结果
        """
        if (
            week in ['*', '?']
            or ('-' in week and cls.__valid_range(week, 1, 7))
            or re.match(r'^[1-7]#[1-4]$', week)
            or re.match(r'^[1-7]L$', week)
            or re.match(r'^[1-7](?:(,[1-7]))*$', week)
        ):
            return True
        return False

    @classmethod
    def __validate_year(cls, year: str):
        """
        校验年值是否正确
        :param year: 年值
        :return: 校验结果
        """
        current_year = int(datetime.now().year)
        if (
            year == '*'
            or ('-' in year and cls.__valid_range(year, current_year, 2099))
            or ('/' in year and cls.__valid_sum(year, current_year, 2098, 1, 2099 - current_year, 2099))
            or re.match(r'^[1-7]#[1-4]$', year)
            or re.match(r'^[1-7]L$', year)
        ):
            return True
        return False

    @classmethod
    def validate_cron_expression(cls, cron_expression: str):
        """
        校验Cron表达式是否正确

        :param cron_expression: Cron表达式
        :return: 校验结果
        """
        values = cron_expression.split()
        if len(values) != 6 and len(values) != 7:
            return False
        second_validation = cls.__validate_second_or_minute(values[0])
        minute_validation = cls.__validate_second_or_minute(values[1])
        hour_validation = cls.__validate_hour(values[2])
        day_validation = cls.__validate_day(values[3])
        month_validation = cls.__validate_month(values[4])
        week_validation = cls.__validate_week(values[5])
        validation = (
            second_validation
            and minute_validation
            and hour_validation
            and day_validation
            and month_validation
            and week_validation
        )
        if len(values) == 6:
            return validation
        if len(values) == 7:
            year_validation = cls.__validate_year(values[6])
            return validation and year_validation

    @classmethod
    def scheduler_event_listener(cls, event):
        # 获取事件类型和任务ID
        event_type = event.__class__.__name__
        # 获取任务执行异常信息
        status = '0'
        exception_info = ''
        if event_type == 'JobExecutionEvent' and event.exception:
            exception_info = str(event.exception)
            status = '1'
        job_id = event.job_id
        query_job = cls.get_scheduler_job(job_id=job_id)
        if query_job:
            query_job_info = query_job.__getstate__()
            # 获取任务名称
            job_name = query_job_info.get('name')
            # 获取任务组名
            job_group = query_job._jobstore_alias
            # 获取任务执行器
            job_executor = query_job_info.get('executor')
            # 获取调用目标字符串
            invoke_target = query_job_info.get('func')
            # 获取调用函数位置参数
            job_args = ','.join(query_job_info.get('args'))
            # 获取调用函数关键字参数
            job_kwargs = json.dumps(query_job_info.get('kwargs'))
            # 获取任务触发器
            job_trigger = str(query_job_info.get('trigger'))
            # 构造日志消息
            job_message = f"事件类型: {event_type}, 任务ID: {job_id}, 任务名称: {job_name}, 执行于{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            job_log = JobLogModel(
                jobName=job_name,
                jobGroup=job_group,
                jobExecutor=job_executor,
                invokeTarget=invoke_target,
                jobArgs=job_args,
                jobKwargs=job_kwargs,
                jobTrigger=job_trigger,
                jobMessage=job_message,
                status=status,
                exceptionInfo=exception_info,
                createTime=datetime.now(),
            )
            session = SessionLocal()
            JobLogService.add_job_log_services(session, job_log)
            session.close()
