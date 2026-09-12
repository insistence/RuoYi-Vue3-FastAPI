from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import timezone

from apscheduler.events import SchedulerEvent
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from config.database import DataSourceRegistry, create_sync_db_engine
from config.env import DataBaseConfig, RedisConfig
from config.scheduler.executors import TimedAsyncIOExecutor, TimedProcessPoolExecutor

redis_config = {
    'host': RedisConfig.redis_host,
    'port': RedisConfig.redis_port,
    'username': RedisConfig.redis_username,
    'password': RedisConfig.redis_password,
    'db': RedisConfig.redis_database,
}
job_defaults = {'coalesce': False, 'max_instances': 1}


class SchedulerResources:
    """
    调度器存储、执行器和数据库资源管理
    """

    def __init__(self) -> None:
        """
        初始化当前进程的调度资源引用，数据库引擎按需创建

        :return: None
        """
        self._jobstore_engine: Engine | None = None
        self._listener_engine: Engine | None = None
        self._session_local: sessionmaker[Session] | None = None
        self._configured = False
        self._disposed = False

    def jobstore_engine(self) -> Engine:
        """
        懒加载获取 jobstore 使用的同步 Engine

        :return: 同步 Engine
        """
        if self._jobstore_engine is None:
            # JobStore 使用独立 Engine，避免 APScheduler 关闭时释放 Registry 共享的 Engine。
            self._jobstore_engine = create_sync_db_engine(echo=False, config=DataBaseConfig.get_source())
        return self._jobstore_engine

    def listener_engine(self) -> Engine:
        """
        懒加载获取 listener 使用的同步 Engine

        :return: 同步 Engine
        """
        if self._listener_engine is None:
            self._listener_engine = DataSourceRegistry.get_sync_engine(DataBaseConfig.db_default_source)
        return self._listener_engine

    def log_session_factory(self) -> sessionmaker[Session]:
        """
        懒加载获取同步 SessionLocal

        :return: SessionLocal
        """
        if self._session_local is None:
            self._session_local = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.listener_engine(),
            )
        return self._session_local

    def configure(self, scheduler: AsyncIOScheduler, on_event: Callable[[SchedulerEvent], None]) -> None:
        """
        配置 scheduler（懒加载 jobstore）

        :param scheduler: 当前进程的调度器
        :param on_event: 任务执行事件回调
        :return: None
        """
        if self._configured:
            return
        self._disposed = False
        job_stores = {
            'default': MemoryJobStore(),
            'sqlalchemy': SQLAlchemyJobStore(engine=self.jobstore_engine()),
            'redis': RedisJobStore(**redis_config),
        }
        executors = {
            'default': TimedAsyncIOExecutor(on_rejected=on_event, manage_executions=True),
            'processpool': TimedProcessPoolExecutor(5, on_rejected=on_event, manage_executions=True),
        }
        scheduler.configure(jobstores=job_stores, executors=executors, job_defaults=job_defaults, timezone=timezone.utc)
        self._configured = True

    @staticmethod
    def session() -> AbstractAsyncContextManager[AsyncSession]:
        """
        获取内部调度使用的异步 Session，过滤轮询和事务的常规SQL日志

        :return: 异步 Session
        """
        # 日志标记只作用于此会话的连接，不随异步任务上下文传播到业务任务。
        return DataSourceRegistry.session(DataBaseConfig.db_default_source, log_sql=False)

    def dispose(self) -> None:
        """
        释放 Scheduler 使用的同步 Engine

        :return: None
        """
        if self._disposed:
            return
        self._configured = False
        if self._jobstore_engine:
            self._jobstore_engine.dispose()
            self._jobstore_engine = None
        # Listener 使用 Registry 共享的 Engine，此处只清理引用，避免影响其他服务。
        self._listener_engine = None
        self._session_local = None
        self._disposed = True
