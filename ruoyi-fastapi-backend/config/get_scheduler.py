import asyncio
import importlib
import json
import uuid
from asyncio import iscoroutinefunction
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from apscheduler.events import EVENT_ALL, SchedulerEvent
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.job import Job
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from redis import asyncio as aioredis
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker

import module_task  # noqa: F401
from config.database import AsyncSessionLocal, quote_plus
from config.env import DataBaseConfig, RedisConfig
from module_admin.dao.job_dao import JobDao
from module_admin.entity.vo.job_vo import JobLogModel, JobModel
from module_admin.service.job_log_service import JobLogService
from utils.log_util import logger

# 分布式锁配置
SCHEDULER_LOCK_KEY = 'scheduler:leader_lock'
LOCK_EXPIRE_SECONDS = 60  # 锁过期时间（秒）
LOCK_RENEWAL_INTERVAL = 20  # 锁续期间隔（秒）


# 重写Cron定时
class MyCronTrigger(CronTrigger):
    CRON_EXPRESSION_LENGTH_MIN = 6
    CRON_EXPRESSION_LENGTH_MAX = 7
    WEEKDAY_COUNT = 5

    @classmethod
    def from_crontab(cls, expr: str, timezone: str | None = None) -> 'MyCronTrigger':
        values = expr.split()
        if len(values) != cls.CRON_EXPRESSION_LENGTH_MIN and len(values) != cls.CRON_EXPRESSION_LENGTH_MAX:
            raise ValueError(f'Wrong number of fields; got {len(values)}, expected 6 or 7')

        second = values[0]
        minute = values[1]
        hour = values[2]
        if '?' in values[3]:
            day = None
        elif 'L' in values[5]:
            day = f'last {values[5].replace("L", "")}'
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
        day_of_week = int(values[5].split('#')[0]) - 1 if '#' in values[5] else None
        year = values[6] if len(values) == cls.CRON_EXPRESSION_LENGTH_MAX else None
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
    def __find_recent_workday(cls, day: int) -> int:
        now = datetime.now()
        date = datetime(now.year, now.month, day)
        if date.weekday() < cls.WEEKDAY_COUNT:
            return date.day
        diff = 1
        while True:
            previous_day = date - timedelta(days=diff)
            if previous_day.weekday() < cls.WEEKDAY_COUNT:
                return previous_day.day
            diff += 1


SQLALCHEMY_DATABASE_URL = (
    f'mysql+pymysql://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
    f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
)
if DataBaseConfig.db_type == 'postgresql':
    SQLALCHEMY_DATABASE_URL = (
        f'postgresql+psycopg2://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
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
redis_config = {
    'host': RedisConfig.redis_host,
    'port': RedisConfig.redis_port,
    'username': RedisConfig.redis_username,
    'password': RedisConfig.redis_password,
    'db': RedisConfig.redis_database,
}
job_stores = {
    'default': MemoryJobStore(),
    'sqlalchemy': SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URL, engine=engine),
    'redis': RedisJobStore(**redis_config),
}
executors = {'default': AsyncIOExecutor(), 'processpool': ProcessPoolExecutor(5)}
job_defaults = {'coalesce': False, 'max_instance': 1}
scheduler = AsyncIOScheduler()
scheduler.configure(jobstores=job_stores, executors=executors, job_defaults=job_defaults)


class SchedulerUtil:
    """
    定时任务相关方法
    """

    # 分布式锁相关类变量
    _is_leader: bool = False
    _worker_id: str = str(uuid.uuid4())
    _redis: aioredis.Redis | None = None

    @classmethod
    async def init_system_scheduler(cls, redis: aioredis.Redis) -> None:
        """
        应用启动时初始化定时任务（使用分布式锁确保只有一个worker启动scheduler）

        :param redis: Redis连接对象
        :return:
        """
        cls._redis = redis
        logger.info(f'🔎 Worker {cls._worker_id[:8]} 尝试获取 Scheduler Leader 锁...')

        # 尝试获取分布式锁 (SET NX EX)
        acquired = await redis.set(
            SCHEDULER_LOCK_KEY,
            cls._worker_id,
            nx=True,
            ex=LOCK_EXPIRE_SECONDS,
        )

        if acquired:
            cls._is_leader = True
            logger.info(f'🎯 Worker {cls._worker_id[:8]} 成为 Scheduler Leader，开始启动定时任务...')
            scheduler.start()

            # 加载数据库中的定时任务
            async with AsyncSessionLocal() as session:
                job_list = await JobDao.get_job_list_for_scheduler(session)
                for item in job_list:
                    cls._add_job_to_scheduler(item)

            # 添加事件监听器
            scheduler.add_listener(cls.scheduler_event_listener, EVENT_ALL)

            # 添加锁续期任务
            scheduler.add_job(
                func=cls._renew_scheduler_lock,
                trigger='interval',
                seconds=LOCK_RENEWAL_INTERVAL,
                id='_scheduler_lock_renewal',
                name='Scheduler锁续期任务',
                replace_existing=True,
            )

            # 添加任务状态同步任务（每30秒从数据库同步一次任务状态）
            scheduler.add_job(
                func=cls._sync_jobs_from_database,
                trigger='interval',
                seconds=30,
                id='_scheduler_job_sync',
                name='Scheduler任务同步',
                replace_existing=True,
            )

            logger.info('✅️ 系统初始定时任务加载成功')
        else:
            cls._is_leader = False
            logger.info(f'⏸️ Worker {cls._worker_id[:8]} 不是 Leader，跳过 Scheduler 启动')

    @classmethod
    async def _renew_scheduler_lock(cls) -> None:
        """
        续期分布式锁，确保leader身份不丢失
        """
        if cls._redis and cls._is_leader:
            # 检查锁是否仍属于当前worker
            current_holder = await cls._redis.get(SCHEDULER_LOCK_KEY)
            if current_holder == cls._worker_id:
                await cls._redis.expire(SCHEDULER_LOCK_KEY, LOCK_EXPIRE_SECONDS)
                logger.debug('🔄 Scheduler Leader 锁续期成功')
            else:
                # 锁被其他worker获取，当前worker不再是leader
                cls._is_leader = False
                logger.warning(f'⚠️ Worker {cls._worker_id[:8]} 失去 Leader 身份')

    @classmethod
    async def _sync_jobs_from_database(cls) -> None:
        """
        从数据库同步任务状态，确保多worker环境下任务状态一致
        """
        if not cls._is_leader:
            return

        try:
            async with AsyncSessionLocal() as session:
                # 获取数据库中所有启用的任务
                db_jobs = await JobDao.get_job_list_for_scheduler(session)
                db_job_ids = {str(job.job_id) for job in db_jobs}
                db_job_map = {str(job.job_id): job for job in db_jobs}

                # 获取调度器中当前运行的任务（排除内部任务）
                scheduler_jobs = scheduler.get_jobs()
                scheduler_job_ids = {job.id for job in scheduler_jobs if not job.id.startswith('_')}

                # 找出需要移除的任务（调度器中有但数据库中没有启用的）
                jobs_to_remove = scheduler_job_ids - db_job_ids
                for job_id in jobs_to_remove:
                    scheduler.remove_job(job_id=job_id)
                    logger.info(f'🗑️ 同步移除任务: {job_id}')

                # 找出需要添加的任务（数据库中有但调度器中没有的）
                jobs_to_add = db_job_ids - scheduler_job_ids
                for job_id in jobs_to_add:
                    job_info = db_job_map.get(job_id)
                    if job_info:
                        cls._add_job_to_scheduler(job_info)
                        logger.info(f'➕ 同步添加任务: {job_info.job_name}')

        except Exception as e:
            logger.error(f'❌ 任务同步异常: {e}')

    @classmethod
    def _prepare_scheduler_job_add(cls, job_info: JobModel) -> dict[str, Any]:
        job_func = cls._import_function(job_info.invoke_target)
        job_executor = job_info.job_executor
        if iscoroutinefunction(job_func):
            job_executor = 'default'
        return {
            'func': job_func,
            'trigger': MyCronTrigger.from_crontab(job_info.cron_expression),
            'args': job_info.job_args.split(',') if job_info.job_args else None,
            'kwargs': json.loads(job_info.job_kwargs) if job_info.job_kwargs else None,
            'id': str(job_info.job_id),
            'name': job_info.job_name,
            'misfire_grace_time': 1000000000000 if job_info.misfire_policy == '3' else None,
            'coalesce': job_info.misfire_policy == '2',
            'max_instances': 3 if job_info.concurrent == '0' else 1,
            'jobstore': job_info.job_group,
            'executor': job_executor,
        }

    @classmethod
    def _add_job_to_scheduler(cls, job_info: JobModel) -> None:
        """
        内部方法：将任务添加到调度器（不检查 Leader 状态，仅供内部使用）

        :param job_info: 任务对象信息
        """
        try:
            # 先移除已存在的同ID任务
            existing_job = scheduler.get_job(job_id=str(job_info.job_id))
            if existing_job:
                scheduler.remove_job(job_id=str(job_info.job_id))
            scheduler.add_job(**cls._prepare_scheduler_job_add(job_info))
        except Exception as e:
            logger.error(f'❌ 添加任务 {job_info.job_name} 失败: {e}')

    @classmethod
    async def close_system_scheduler(cls) -> None:
        """
        应用关闭时关闭定时任务

        :return:
        """
        if cls._is_leader:
            scheduler.shutdown()
            # 释放锁
            if cls._redis:
                current_holder = await cls._redis.get(SCHEDULER_LOCK_KEY)
                if current_holder == cls._worker_id:
                    await cls._redis.delete(SCHEDULER_LOCK_KEY)
                    logger.info(f'🔓 Worker {cls._worker_id[:8]} 释放 Scheduler Leader 锁')
            logger.info('✅️ 关闭定时任务成功')
        else:
            logger.info(f'⏸️ Worker {cls._worker_id[:8]} 不是 Leader，无需关闭 Scheduler')

    @classmethod
    def _import_function(cls, func_path: str) -> Callable[..., Any]:
        """
        动态导入函数

        :param func_path: 函数字符串，如module_task.scheduler_test.job
        :return: 导入的函数对象
        """
        module_path, func_name = func_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)

    @classmethod
    def get_scheduler_job(cls, job_id: str | int) -> Job:
        """
        根据任务id获取任务对象

        :param job_id: 任务id
        :return: 任务对象
        """
        query_job = scheduler.get_job(job_id=str(job_id))

        return query_job

    @classmethod
    def add_scheduler_job(cls, job_info: JobModel) -> None:
        """
        根据输入的任务对象信息添加任务

        :param job_info: 任务对象信息
        :return:
        """
        # 非 Leader worker 跳过操作（数据库状态是持久化的，Leader 启动时会加载）
        if not cls._is_leader:
            return
        scheduler.add_job(**cls._prepare_scheduler_job_add(job_info))

    @classmethod
    def execute_scheduler_job_once(cls, job_info: JobModel) -> None:
        """
        根据输入的任务对象执行一次任务

        :param job_info: 任务对象信息
        :return:
        """
        job_func = cls._import_function(job_info.invoke_target)
        job_executor = job_info.job_executor
        if iscoroutinefunction(job_func):
            job_executor = 'default'

        # 非 Leader worker：直接执行函数（不通过 scheduler）
        if not cls._is_leader:
            logger.info(f'📍 当前 Worker 不是 Leader，直接执行任务 {job_info.job_name}')
            try:
                args = job_info.job_args.split(',') if job_info.job_args else []
                kwargs = json.loads(job_info.job_kwargs) if job_info.job_kwargs else {}
                if iscoroutinefunction(job_func):
                    asyncio.create_task(job_func(*args, **kwargs))  # noqa: RUF006
                else:
                    job_func(*args, **kwargs)
            except Exception as e:
                logger.error(f'❌ 直接执行任务 {job_info.job_name} 失败: {e}')
            return

        # Leader worker：通过 scheduler 执行
        job_trigger = DateTrigger()
        if job_info.status == '0':
            job_trigger = OrTrigger(triggers=[DateTrigger(), MyCronTrigger.from_crontab(job_info.cron_expression)])
        scheduler.add_job(
            func=job_func,
            trigger=job_trigger,
            args=job_info.job_args.split(',') if job_info.job_args else None,
            kwargs=json.loads(job_info.job_kwargs) if job_info.job_kwargs else None,
            id=str(job_info.job_id),
            name=job_info.job_name,
            misfire_grace_time=1000000000000 if job_info.misfire_policy == '3' else None,
            coalesce=job_info.misfire_policy == '2',
            max_instances=3 if job_info.concurrent == '0' else 1,
            jobstore=job_info.job_group,
            executor=job_executor,
        )

    @classmethod
    def remove_scheduler_job(cls, job_id: str | int) -> None:
        """
        根据任务id移除任务

        :param job_id: 任务id
        :return:
        """
        # 非 Leader worker 跳过操作（数据库状态是持久化的，Leader 启动时会根据状态加载）
        if not cls._is_leader:
            return
        query_job = cls.get_scheduler_job(job_id=job_id)
        if query_job:
            scheduler.remove_job(job_id=str(job_id))

    @classmethod
    def scheduler_event_listener(cls, event: SchedulerEvent) -> None:
        """
        调度器事件监听器，记录任务执行日志
        """
        try:
            # 获取事件类型和任务ID
            event_type = event.__class__.__name__
            # 获取任务执行异常信息
            status = '0'
            exception_info = ''
            if event_type == 'JobExecutionEvent' and event.exception:
                exception_info = str(event.exception)
                status = '1'
            if hasattr(event, 'job_id'):
                job_id = event.job_id
                # 跳过内部系统任务（以 _ 开头的任务ID），不记录日志
                if str(job_id).startswith('_'):
                    return
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
                    # 获取调用函数位置参数（安全处理）
                    args = query_job_info.get('args')
                    job_args = ','.join(str(arg) for arg in args) if args else ''
                    # 获取调用函数关键字参数
                    kwargs = query_job_info.get('kwargs')
                    job_kwargs = json.dumps(kwargs) if kwargs else '{}'
                    # 获取任务触发器
                    job_trigger = str(query_job_info.get('trigger'))
                    # 构造日志消息
                    job_message = f'事件类型: {event_type}, 任务ID: {job_id}, 任务名称: {job_name}, 执行于{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
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
                    try:
                        JobLogService.add_job_log_services(session, job_log)
                    finally:
                        session.close()
        except Exception as e:
            logger.error(f'❌ 调度任务事件监听器异常: {e}')
