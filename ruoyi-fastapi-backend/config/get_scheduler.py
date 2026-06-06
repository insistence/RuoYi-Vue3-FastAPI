import asyncio
import importlib
import json
from asyncio import iscoroutinefunction
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import module_task  # noqa: F401
from apscheduler.events import EVENT_ALL, SchedulerEvent
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.job import Job
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from common.constant import LockConstant
from config.database import (
    SYNC_SQLALCHEMY_DATABASE_URL,
    create_async_db_engine,
    create_async_session_local,
    create_sync_db_engine,
    create_sync_session_local,
)
from config.env import AppConfig, LogConfig, RedisConfig
from module_admin.dao.job_dao import JobDao
from module_admin.entity.vo.job_vo import JobLogModel, JobModel
from module_admin.service.job_log_service import JobLogService
from redis import asyncio as aioredis
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine
from utils.log_util import logger
from utils.server_util import StartupUtil, WorkerIdUtil


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


redis_config = {
    'host': RedisConfig.redis_host,
    'port': RedisConfig.redis_port,
    'username': RedisConfig.redis_username,
    'password': RedisConfig.redis_password,
    'db': RedisConfig.redis_database,
}
job_defaults = {'coalesce': False, 'max_instance': 1}
scheduler = AsyncIOScheduler()


class SchedulerUtil:
    """
    定时任务相关方法
    """

    # 分布式锁相关类变量
    _is_leader: bool = False
    _worker_id: str = WorkerIdUtil.get_worker_id(LogConfig.log_worker_id)
    _redis: aioredis.Redis | None = None
    _job_update_time_cache: dict[str, datetime] = {}
    _sync_channel: str = 'scheduler:sync:request'
    _sync_listener_task: asyncio.Task | None = None
    _lock_lost_task: asyncio.Task | None = None
    _sync_task: asyncio.Task | None = None
    _sync_pending: bool = False
    _sync_lock: asyncio.Lock = asyncio.Lock()
    _last_sync_at: datetime | None = None
    _sync_debounce_seconds: float = 0.5
    _sync_min_interval_seconds: float = 2.0
    _reacquire_task: asyncio.Task | None = None
    _reacquire_interval_seconds: float = 5.0
    _sync_async_engine: AsyncEngine | None = None
    _sync_async_sessionmaker: Any | None = None
    _disposed_sync_engines: bool = False
    _run_once_job_id_prefix: str = '_run_once_'
    _run_once_job_log_cache: dict[str, dict[str, Any]] = {}

    # 懒加载的同步 Engine 和 SessionLocal
    _jobstore_engine: Engine | None = None
    _listener_engine: Engine | None = None
    _session_local: Any | None = None
    _scheduler_configured: bool = False

    @classmethod
    def _get_jobstore_engine(cls) -> Engine:
        """
        懒加载获取 jobstore 使用的同步 Engine

        :return: 同步 Engine
        """
        if cls._jobstore_engine is None:
            cls._jobstore_engine = create_sync_db_engine(echo=False)
        return cls._jobstore_engine

    @classmethod
    def _get_listener_engine(cls) -> Engine:
        """
        懒加载获取 listener 使用的同步 Engine

        :return: 同步 Engine
        """
        if cls._listener_engine is None:
            cls._listener_engine = create_sync_db_engine()
        return cls._listener_engine

    @classmethod
    def _get_session_local(cls) -> Any:
        """
        懒加载获取同步 SessionLocal

        :return: SessionLocal
        """
        if cls._session_local is None:
            cls._session_local = create_sync_session_local(cls._get_listener_engine())
        return cls._session_local

    @classmethod
    def _configure_scheduler(cls) -> None:
        """
        配置 scheduler（懒加载 jobstore）

        :return: None
        """
        if cls._scheduler_configured:
            return
        job_stores = {
            'default': MemoryJobStore(),
            'sqlalchemy': SQLAlchemyJobStore(url=SYNC_SQLALCHEMY_DATABASE_URL, engine=cls._get_jobstore_engine()),
            'redis': RedisJobStore(**redis_config),
        }
        executors = {'default': AsyncIOExecutor(), 'processpool': ProcessPoolExecutor(5)}
        scheduler.configure(jobstores=job_stores, executors=executors, job_defaults=job_defaults)
        cls._scheduler_configured = True

    @classmethod
    def _should_enable_scheduler_sync(cls) -> bool:
        """
        判断是否需要启用多 worker 的任务状态同步机制

        :return: 是否开启定时同步与监听
        """
        return not AppConfig.app_reload and AppConfig.app_workers > 1

    @classmethod
    async def init_system_scheduler(cls, redis: aioredis.Redis) -> None:
        """
        应用启动时初始化定时任务（使用分布式锁确保只有一个worker启动scheduler）

        :param redis: Redis连接对象
        :return:
        """
        cls._redis = redis
        logger.info(f'🔎 Worker {cls._worker_id} 尝试获取 Application 锁...')

        acquired = await StartupUtil.acquire_startup_log_gate(
            redis=redis,
            lock_key=LockConstant.APP_STARTUP_LOCK_KEY,
            worker_id=cls._worker_id,
            lock_expire_seconds=LockConstant.LOCK_EXPIRE_SECONDS,
        )

        if acquired:
            await cls._start_scheduler_as_leader(redis)
        else:
            cls._is_leader = False
            logger.info(f'⏸️ Worker {cls._worker_id} 未持有 Application 锁，跳过 Scheduler 启动')

    @classmethod
    async def _start_scheduler_as_leader(cls, redis: aioredis.Redis) -> None:
        """
        以 Leader 身份启动 Scheduler（内部方法，调用前需确保已持有锁）

        :param redis: Redis连接对象
        :return: None
        """
        cls._is_leader = True
        cls._disposed_sync_engines = False
        logger.info(f'🎯 Worker {cls._worker_id} 持有 Application 锁，开始启动定时任务...')
        # 懒加载配置 scheduler
        cls._configure_scheduler()
        scheduler.start()

        # 加载数据库中的定时任务
        async with cls._get_sync_async_session() as session:
            job_list = await JobDao.get_job_list_for_scheduler(session)
            for item in job_list:
                cls._add_job_to_scheduler(item)

        # 添加事件监听器
        scheduler.add_listener(cls.scheduler_event_listener, EVENT_ALL)

        if cls._should_enable_scheduler_sync():
            # 添加任务状态同步任务（每30秒从数据库同步一次任务状态）
            scheduler.add_job(
                func=cls.request_scheduler_sync,
                trigger='interval',
                seconds=30,
                id='_scheduler_job_sync',
                name='Scheduler任务同步',
                replace_existing=True,
            )
            cls._sync_listener_task = asyncio.create_task(cls._listen_sync_channel(redis))

        logger.info('✅️ 系统初始定时任务加载成功')

    @classmethod
    def on_lock_lost(cls) -> None:
        """
        锁丢失处理入口

        :return: None
        """
        if not cls._is_leader:
            return
        cls._is_leader = False
        logger.warning(f'⚠️ Worker {cls._worker_id} 失去 Application 锁')
        if cls._lock_lost_task:
            cls._lock_lost_task.cancel()
        cls._lock_lost_task = asyncio.create_task(cls._handle_lock_lost())

    @classmethod
    async def _handle_lock_lost(cls) -> None:
        """
        处理锁丢失后的资源释放

        :return: None
        """
        if cls._sync_listener_task:
            cls._sync_listener_task.cancel()
            try:
                await cls._sync_listener_task
            except asyncio.CancelledError:
                pass
            cls._sync_listener_task = None
        if cls._sync_task:
            cls._sync_task.cancel()
            try:
                await cls._sync_task
            except asyncio.CancelledError:
                pass
            cls._sync_task = None
            cls._sync_pending = False
        if getattr(scheduler, 'running', False):
            scheduler.shutdown()
        await cls._dispose_sync_async_engine()
        cls._dispose_sync_engines()
        cls._ensure_reacquire_task()

    @classmethod
    async def _sync_jobs_from_database(cls) -> None:
        """
        从数据库同步任务状态，确保多worker环境下任务状态一致
        """
        if not cls._is_leader:
            return

        try:
            async with cls._get_sync_async_session() as session:
                db_jobs_all = await JobDao.get_all_job_list_for_scheduler(session)
                db_jobs_enabled = [job for job in db_jobs_all if job.status == '0']
                db_enabled_ids = {str(job.job_id) for job in db_jobs_enabled}
                db_job_map = {str(job.job_id): job for job in db_jobs_enabled}
                db_job_update_time_map = {
                    str(job.job_id): job.update_time for job in db_jobs_enabled if job.update_time is not None
                }
                scheduler_jobs = scheduler.get_jobs()
                scheduler_job_map = {
                    job.id: job
                    for job in scheduler_jobs
                    if not cls._is_internal_scheduler_job(job.id) and not cls._is_run_once_job_id(job.id)
                }
                scheduler_job_ids = set(scheduler_job_map.keys())

                jobs_to_remove = scheduler_job_ids - db_enabled_ids
                for job_id in jobs_to_remove:
                    scheduler.remove_job(job_id=job_id)
                    logger.info(f'🗑️ 同步移除任务: {job_id}')
                    cls._refresh_job_update_cache(job_id, None)

                jobs_to_add = db_enabled_ids - scheduler_job_ids
                for job_id in jobs_to_add:
                    job_info = db_job_map.get(job_id)
                    if job_info:
                        cls._add_job_to_scheduler(job_info)
                        logger.info(f'➕ 同步添加任务: {job_info.job_name}')
                        cls._refresh_job_update_cache(job_id, job_info.update_time)

                jobs_to_update = db_enabled_ids & scheduler_job_ids
                for job_id in jobs_to_update:
                    job_info = db_job_map.get(job_id)
                    scheduler_job = scheduler_job_map.get(job_id)
                    job_update_time = db_job_update_time_map.get(job_id)
                    cls._sync_update_job(job_id, job_info, scheduler_job, job_update_time)

        except Exception as e:
            logger.error(f'❌ 任务同步异常: {e}')

    @classmethod
    def _is_job_config_in_sync(cls, scheduler_job: Job, job_info: JobModel) -> bool:
        """
        判断任务配置是否一致

        :param scheduler_job: 调度器任务对象
        :param job_info: 数据库任务对象
        :return: 是否一致
        """
        job_state = scheduler_job.__getstate__()
        job_kwargs = json.loads(job_info.job_kwargs) if job_info.job_kwargs else None
        job_args = job_info.job_args.split(',') if job_info.job_args else None
        job_executor = job_info.job_executor
        if iscoroutinefunction(cls._import_function(job_info.invoke_target)):
            job_executor = 'default'
        expected = {
            'name': job_info.job_name,
            'executor': job_executor,
            'jobstore': job_info.job_group,
            'misfire_grace_time': 1000000000000 if job_info.misfire_policy == '3' else None,
            'coalesce': job_info.misfire_policy == '2',
            'max_instances': 3 if job_info.concurrent == '0' else 1,
            'trigger': str(MyCronTrigger.from_crontab(job_info.cron_expression)),
            'args': tuple(job_args) if job_args else None,
            'kwargs': job_kwargs if job_kwargs else None,
            'func': str(cls._import_function(job_info.invoke_target)),
        }
        current = {
            'name': job_state.get('name'),
            'executor': job_state.get('executor'),
            'jobstore': scheduler_job._jobstore_alias,
            'misfire_grace_time': job_state.get('misfire_grace_time'),
            'coalesce': job_state.get('coalesce'),
            'max_instances': job_state.get('max_instances'),
            'trigger': str(job_state.get('trigger')),
            'args': job_state.get('args'),
            'kwargs': job_state.get('kwargs'),
            'func': str(job_state.get('func')),
        }
        return expected == current

    @classmethod
    def _sync_update_job(
        cls, job_id: str, job_info: JobModel | None, scheduler_job: Job | None, job_update_time: datetime | None
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
        if cls._should_skip_job_update(job_id, job_update_time):
            return
        if not cls._is_job_config_in_sync(scheduler_job, job_info):
            scheduler.remove_job(job_id=job_id)
            cls._add_job_to_scheduler(job_info)
            logger.info(f'♻️ 同步更新任务: {job_info.job_name}')
        cls._refresh_job_update_cache(job_id, job_update_time)

    @classmethod
    def _should_skip_job_update(cls, job_id: str, job_update_time: datetime | None) -> bool:
        """
        判断是否跳过同步更新

        :param job_id: 任务ID
        :param job_update_time: 任务更新时间
        :return: 是否跳过
        """
        if job_update_time is None:
            return False
        return cls._job_update_time_cache.get(job_id) == job_update_time

    @classmethod
    def _refresh_job_update_cache(cls, job_id: str, job_update_time: datetime | None) -> None:
        """
        刷新任务更新时间缓存

        :param job_id: 任务ID
        :param job_update_time: 任务更新时间
        :return: None
        """
        if job_update_time is not None:
            cls._job_update_time_cache[job_id] = job_update_time
        else:
            cls._job_update_time_cache.pop(job_id, None)

    @classmethod
    async def request_scheduler_sync(cls) -> None:
        """
        请求调度器同步任务状态

        :return: None
        """
        if cls._is_leader:
            cls._sync_pending = True
            cls._ensure_sync_task()
            return
        if cls._redis:
            await cls._redis.publish(cls._sync_channel, cls._worker_id)

    @classmethod
    def _ensure_sync_task(cls) -> None:
        """
        启动同步调度任务

        :return: None
        """
        if cls._sync_task and not cls._sync_task.done():
            return
        cls._sync_task = asyncio.create_task(cls._run_sync_loop())

    @classmethod
    def _get_sync_async_session(cls) -> Any:
        """
        获取同步任务使用的异步 Session

        :return: 异步 Session
        """
        if not cls._sync_async_sessionmaker:
            cls._sync_async_engine = create_async_db_engine(echo=False)
            cls._sync_async_sessionmaker = create_async_session_local(cls._sync_async_engine)
        return cls._sync_async_sessionmaker()

    @classmethod
    async def _dispose_sync_async_engine(cls) -> None:
        """
        释放同步任务使用的异步 Engine

        :return: None
        """
        if cls._sync_async_engine:
            await cls._sync_async_engine.dispose()
            cls._sync_async_engine = None
            cls._sync_async_sessionmaker = None

    @classmethod
    def _dispose_sync_engines(cls) -> None:
        """
        释放 Scheduler 使用的同步 Engine

        :return: None
        """
        if cls._disposed_sync_engines:
            return
        if cls._jobstore_engine:
            cls._jobstore_engine.dispose()
            cls._jobstore_engine = None
        if cls._listener_engine:
            cls._listener_engine.dispose()
            cls._listener_engine = None
        cls._session_local = None
        cls._disposed_sync_engines = True

    @classmethod
    def _ensure_reacquire_task(cls) -> None:
        """
        启动锁重新竞争任务

        :return: None
        """
        if not cls._redis:
            return
        if cls._reacquire_task and not cls._reacquire_task.done():
            return
        cls._reacquire_task = asyncio.create_task(cls._run_reacquire_loop())

    @classmethod
    async def _run_reacquire_loop(cls) -> None:
        """
        循环尝试重新获取锁并恢复调度器

        :return: None
        """
        try:
            while not cls._is_leader:
                if not cls._redis:
                    await asyncio.sleep(cls._reacquire_interval_seconds)
                    continue
                acquired = await StartupUtil.acquire_startup_log_gate(
                    redis=cls._redis,
                    lock_key=LockConstant.APP_STARTUP_LOCK_KEY,
                    worker_id=cls._worker_id,
                    lock_expire_seconds=LockConstant.LOCK_EXPIRE_SECONDS,
                )
                if acquired:
                    # 直接调用 _start_scheduler_as_leader，避免重复获取锁
                    await cls._start_scheduler_as_leader(cls._redis)
                    return
                await asyncio.sleep(cls._reacquire_interval_seconds)
        except asyncio.CancelledError:
            raise
        finally:
            cls._reacquire_task = None

    @classmethod
    async def _run_sync_loop(cls) -> None:
        """
        执行同步调度循环

        :return: None
        """
        try:
            while True:
                if not cls._sync_pending:
                    break
                cls._sync_pending = False
                await asyncio.sleep(cls._sync_debounce_seconds)
                await cls._sync_with_throttle()
        except asyncio.CancelledError:
            raise
        finally:
            cls._sync_task = None

    @classmethod
    async def _sync_with_throttle(cls) -> None:
        """
        按节流规则执行同步

        :return: None
        """
        async with cls._sync_lock:
            if not cls._is_leader:
                return
            if cls._last_sync_at:
                elapsed = datetime.now() - cls._last_sync_at
                min_interval = timedelta(seconds=cls._sync_min_interval_seconds)
                if elapsed < min_interval:
                    await asyncio.sleep((min_interval - elapsed).total_seconds())
            await cls._sync_jobs_from_database()
            cls._last_sync_at = datetime.now()

    @classmethod
    async def _listen_sync_channel(cls, redis: aioredis.Redis) -> None:
        """
        监听同步请求通道

        :param redis: Redis连接对象
        :return: None
        """
        while True:
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe(cls._sync_channel)
                async for message in pubsub.listen():
                    if not cls._is_leader:
                        continue
                    if message.get('type') != 'message':
                        continue
                    await cls.request_scheduler_sync()
            except asyncio.CancelledError:
                await pubsub.unsubscribe(cls._sync_channel)
                await pubsub.close()
                raise
            except Exception as e:
                logger.error(f'❌ Scheduler 同步监听异常: {e}，5秒后重试...')
                await pubsub.close()
                await asyncio.sleep(5)
            finally:
                try:
                    await pubsub.close()
                except Exception:
                    pass

    @classmethod
    async def _execute_async_job_with_log(
        cls, job_func: Callable[..., Any], job_info: JobModel, args: list, kwargs: dict
    ) -> None:
        """
        执行异步任务并记录日志

        :param job_func: 任务函数
        :param job_info: 任务对象信息
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: None
        """
        status = '0'
        exception_info = ''
        job_executor = job_info.job_executor
        if iscoroutinefunction(job_func):
            job_executor = 'default'
        try:
            await job_func(*args, **kwargs)
        except Exception as e:
            status = '1'
            exception_info = str(e)
            logger.error(f'❌ 异步执行任务 {job_info.job_name} 失败: {e}')
        finally:
            cls._record_job_execution_log(job_info, job_executor, status, exception_info)

    @classmethod
    def _record_job_execution_log(cls, job_info: JobModel, job_executor: str, status: str, exception_info: str) -> None:
        """
        记录任务执行日志（用于非 Leader Worker 直接执行任务时）

        :param job_info: 任务对象信息
        :param job_executor: 任务执行器
        :param status: 执行状态 0-成功 1-失败
        :param exception_info: 异常信息
        :return: None
        """
        try:
            job_args = job_info.job_args if job_info.job_args else ''
            job_kwargs = job_info.job_kwargs if job_info.job_kwargs else '{}'
            job_trigger = str(MyCronTrigger.from_crontab(job_info.cron_expression)) if job_info.cron_expression else ''
            job_message = (
                f'事件类型: DirectExecution(非Leader), 任务ID: {job_info.job_id}, '
                f'任务名称: {job_info.job_name}, 执行于{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
            )
            job_log = JobLogModel(
                jobName=job_info.job_name,
                jobGroup=job_info.job_group,
                jobExecutor=job_executor,
                invokeTarget=job_info.invoke_target,
                jobArgs=job_args,
                jobKwargs=job_kwargs,
                jobTrigger=job_trigger,
                jobMessage=job_message,
                status=status,
                exceptionInfo=exception_info,
                createTime=datetime.now(),
            )
            session = cls._get_session_local()()
            try:
                JobLogService.add_job_log_services(session, job_log)
            finally:
                session.close()
        except Exception as e:
            logger.error(f'❌ 记录任务执行日志失败: {e}')

    @classmethod
    def _is_run_once_job_id(cls, job_id: str | int) -> bool:
        """
        判断是否为执行一次产生的临时任务ID

        :param job_id: 任务ID
        :return: 是否为执行一次临时任务
        """
        return str(job_id).startswith(cls._run_once_job_id_prefix)

    @classmethod
    def _is_internal_scheduler_job(cls, job_id: str | int) -> bool:
        """
        判断是否为系统内部调度任务

        :param job_id: 任务ID
        :return: 是否为系统内部任务
        """
        return str(job_id).startswith('_') and not cls._is_run_once_job_id(job_id)

    @classmethod
    def _build_run_once_job_id(cls, job_info: JobModel) -> str:
        """
        构建执行一次临时任务ID

        :param job_info: 任务对象信息
        :return: 临时任务ID
        """
        return f'{cls._run_once_job_id_prefix}{job_info.job_id}_{uuid4().hex}'

    @classmethod
    def _build_job_log_cache_from_job_info(
        cls, job_info: JobModel, job_executor: str, job_trigger: DateTrigger
    ) -> dict[str, Any]:
        """
        根据任务信息构建执行日志缓存

        :param job_info: 任务对象信息
        :param job_executor: 任务执行器
        :param job_trigger: 任务触发器
        :return: 执行日志缓存
        """
        return {
            'job_name': job_info.job_name,
            'job_group': job_info.job_group,
            'job_executor': job_executor,
            'invoke_target': job_info.invoke_target,
            'job_args': job_info.job_args if job_info.job_args else '',
            'job_kwargs': job_info.job_kwargs if job_info.job_kwargs else '{}',
            'job_trigger': str(job_trigger),
        }

    @classmethod
    def _get_scheduler_job_log_cache(cls, query_job: Job) -> dict[str, Any]:
        """
        根据调度器任务构建执行日志缓存

        :param query_job: 调度器任务
        :return: 执行日志缓存
        """
        query_job_info = query_job.__getstate__()
        args = query_job_info.get('args')
        kwargs = query_job_info.get('kwargs')
        return {
            'job_name': query_job_info.get('name'),
            'job_group': query_job._jobstore_alias,
            'job_executor': query_job_info.get('executor'),
            'invoke_target': query_job_info.get('func'),
            'job_args': ','.join(str(arg) for arg in args) if args else '',
            'job_kwargs': json.dumps(kwargs) if kwargs else '{}',
            'job_trigger': str(query_job_info.get('trigger')),
        }

    @classmethod
    def _prepare_scheduler_job_add(cls, job_info: JobModel) -> dict[str, Any]:
        """
        构建调度器任务参数

        :param job_info: 任务对象信息
        :return: 调度器任务参数
        """
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
        内部方法：将任务添加到调度器（不检查应用锁状态，仅供内部使用）

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
        if cls._sync_listener_task:
            cls._sync_listener_task.cancel()
            try:
                await cls._sync_listener_task
            except asyncio.CancelledError:
                pass
            cls._sync_listener_task = None
        if cls._sync_task:
            cls._sync_task.cancel()
            try:
                await cls._sync_task
            except asyncio.CancelledError:
                pass
            cls._sync_task = None
            cls._sync_pending = False
        if cls._reacquire_task:
            cls._reacquire_task.cancel()
            try:
                await cls._reacquire_task
            except asyncio.CancelledError:
                pass
            cls._reacquire_task = None
        await cls._dispose_sync_async_engine()
        cls._dispose_sync_engines()
        if cls._lock_lost_task:
            cls._lock_lost_task.cancel()
            try:
                await cls._lock_lost_task
            except asyncio.CancelledError:
                pass
            cls._lock_lost_task = None
        if getattr(scheduler, 'running', False):
            scheduler.shutdown()
            logger.info('✅️ 关闭定时任务成功')
        # 释放锁
        if cls._redis:
            current_holder = await cls._redis.get(LockConstant.APP_STARTUP_LOCK_KEY)
            if current_holder == cls._worker_id:
                await cls._redis.delete(LockConstant.APP_STARTUP_LOCK_KEY)
                logger.info(f'🔓 Worker {cls._worker_id} 释放 Application 锁')

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
        # 非应用锁 worker 跳过操作（数据库状态是持久化的，持有应用锁时会加载）
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

        # 非应用锁 worker：直接执行函数（不通过 scheduler）
        if not cls._is_leader:
            logger.info(f'📍 当前 Worker 未持有 Application 锁，直接执行任务 {job_info.job_name}')
            args = job_info.job_args.split(',') if job_info.job_args else []
            kwargs = json.loads(job_info.job_kwargs) if job_info.job_kwargs else {}
            status = '0'
            exception_info = ''
            try:
                if iscoroutinefunction(job_func):
                    asyncio.create_task(cls._execute_async_job_with_log(job_func, job_info, args, kwargs))  # noqa: RUF006
                else:
                    job_func(*args, **kwargs)
            except Exception as e:
                status = '1'
                exception_info = str(e)
                logger.error(f'❌ 直接执行任务 {job_info.job_name} 失败: {e}')
            finally:
                # 同步任务记录日志（异步任务在 _execute_async_job_with_log 中记录）
                if not iscoroutinefunction(job_func):
                    cls._record_job_execution_log(job_info, job_executor, status, exception_info)
            return

        # 应用锁 worker：添加独立的一次性任务，不覆盖原有 Cron 任务
        job_trigger = DateTrigger()
        run_once_job_id = cls._build_run_once_job_id(job_info)
        cls._run_once_job_log_cache[run_once_job_id] = cls._build_job_log_cache_from_job_info(
            job_info, job_executor, job_trigger
        )
        try:
            scheduler.add_job(
                func=job_func,
                trigger=job_trigger,
                args=job_info.job_args.split(',') if job_info.job_args else None,
                kwargs=json.loads(job_info.job_kwargs) if job_info.job_kwargs else None,
                id=run_once_job_id,
                name=job_info.job_name,
                misfire_grace_time=1000000000000 if job_info.misfire_policy == '3' else None,
                coalesce=job_info.misfire_policy == '2',
                max_instances=3 if job_info.concurrent == '0' else 1,
                jobstore='default',
                executor=job_executor,
            )
        except Exception:
            cls._run_once_job_log_cache.pop(run_once_job_id, None)
            raise

    @classmethod
    def remove_scheduler_job(cls, job_id: str | int) -> None:
        """
        根据任务id移除任务

        :param job_id: 任务id
        :return:
        """
        # 非应用锁 worker 跳过操作（数据库状态是持久化的，持有应用锁时会根据状态加载）
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
                # 跳过内部系统任务，不记录日志；执行一次的临时任务需要保留日志
                if cls._is_internal_scheduler_job(job_id):
                    return
                if cls._is_run_once_job_id(job_id):
                    job_log_cache = cls._run_once_job_log_cache.get(str(job_id))
                else:
                    query_job = cls.get_scheduler_job(job_id=job_id)
                    job_log_cache = cls._get_scheduler_job_log_cache(query_job) if query_job else None
                if job_log_cache:
                    # 构造日志消息
                    job_message = (
                        f'事件类型: {event_type}, 任务ID: {job_id}, '
                        f'任务名称: {job_log_cache.get("job_name")}, '
                        f'执行于{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                    )
                    job_log = JobLogModel(
                        jobName=job_log_cache.get('job_name'),
                        jobGroup=job_log_cache.get('job_group'),
                        jobExecutor=job_log_cache.get('job_executor'),
                        invokeTarget=job_log_cache.get('invoke_target'),
                        jobArgs=job_log_cache.get('job_args'),
                        jobKwargs=job_log_cache.get('job_kwargs'),
                        jobTrigger=job_log_cache.get('job_trigger'),
                        jobMessage=job_message,
                        status=status,
                        exceptionInfo=exception_info,
                        createTime=datetime.now(),
                    )
                    session = cls._get_session_local()()
                    try:
                        JobLogService.add_job_log_services(session, job_log)
                    finally:
                        session.close()
                if event_type == 'JobExecutionEvent':
                    cls._run_once_job_log_cache.pop(str(job_id), None)
        except Exception as e:
            logger.error(f'❌ 调度任务事件监听器异常: {e}')
