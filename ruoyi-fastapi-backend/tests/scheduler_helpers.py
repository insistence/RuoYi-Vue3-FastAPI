import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import MetaData, create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

import module_task.scheduler_test as task_module
from config.scheduler.dispatcher import SchedulerDispatcher
from config.scheduler.executors import TimedAsyncIOExecutor
from config.scheduler.job_adapter import JobAdapter
from config.scheduler.job_execution import JobExecutionStore
from config.scheduler.jobs import SchedulerJobs
from config.scheduler.listener import SchedulerJobListener
from config.scheduler.manager import SchedulerManager
from config.scheduler.resources import SchedulerResources
from config.scheduler.synchronization import SchedulerSynchronizer
from module_admin.dao.job_dao import JobDao
from module_admin.dao.job_runtime_dao import JobRuntimeDao
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.job_runtime_do import SysJobExecution, SysJobSync
from module_admin.entity.vo.job_vo import JobModel
from utils.time_util import TimezoneUtil

STARTED: asyncio.Event | None = None
RELEASE: asyncio.Event | None = None
CALLS: list[str] = []


def init_execution_process(database_url: str) -> None:
    """
    子进程只使用测试库，禁止回退到项目开发数据源

    :param database_url: 隔离测试数据库连接地址
    :return: None
    """
    engine = create_engine(database_url)
    JobExecutionStore.session = staticmethod(lambda: Session(engine, expire_on_commit=False))


def held_process_job(directory: str) -> int:
    """
    通过临时文件协调真实进程任务，带超时避免失败后遗留任务

    :param directory: 进程测试使用的临时目录
    :return: 执行任务的进程ID
    """
    Path(directory, 'started.json').write_text(json.dumps({'pid': os.getpid()}), encoding='utf-8')
    deadline = time.monotonic() + 20
    while not Path(directory, 'release').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('process test was not released')
        time.sleep(0.02)
    return os.getpid()


def claim_in_process(execution_id: str, job: dict) -> bool:
    """
    不同进程同时尝试占用同一任务，保留占用供父进程断言

    :param execution_id: 执行ID
    :param job: 任务对象信息
    :return: 是否获得执行占用
    """
    return JobExecutionStore.claim(execution_id, job['jobId'], job, TimezoneUtil.utc_now()).accepted


def harmless_job(value: str = 'done') -> str:
    """
    隔离测试任务，只记录调用并返回参数

    :param value: 用于记录调用和返回的测试参数
    :return: 任务输入参数
    """
    CALLS.append(value)
    return value


async def held_job() -> None:
    """
    保持一次异步执行，用于验证手动与 Cron 共享并发上限

    :return: None
    """
    CALLS.append('held')
    STARTED.set()
    await RELEASE.wait()


def job_info(**changes) -> JobModel:
    """
    构造使用未来 Cron 的无业务副作用任务

    :param changes: 需要覆盖的任务字段
    :return: 测试任务对象
    """
    return JobModel(
        **{
            'jobId': 42,
            'jobName': 'runtime verification',
            'jobGroup': 'default',
            'jobExecutor': 'default',
            'invokeTarget': 'module_task.scheduler_test.runtime_harmless',
            'cronExpression': '0 0 0 1 1 ? 2099',
            'timeZone': 'America/New_York',
            'misfireGraceTime': 1,
            'coalesce': False,
            'maxInstances': 1,
            'status': '0',
            **changes,
        }
    )


@dataclass
class Runtime:
    """
    使用文件 SQLite 和真实 APScheduler 的隔离测试环境
    """

    engine: Engine
    sessions: async_sessionmaker[AsyncSession]
    scheduler: AsyncIOScheduler
    started: asyncio.Event
    release: asyncio.Event

    async def save(self, job: JobModel | None = None) -> JobModel:
        """
        保存测试定义和初始同步状态

        :param job: 任务对象信息
        :return: 已保存的任务对象
        """
        job = job or job_info()
        async with self.sessions() as db:
            row = await JobDao.add_job_dao(db, job)
            await JobRuntimeDao.record_configuration(db, row.job_id, job)
            await db.commit()
            return JobAdapter.from_record(row)

    async def execution(self, execution_id: str) -> dict:
        """
        读取当前执行状态

        :param execution_id: 执行ID
        :return: 当前执行状态
        """
        async with self.sessions() as db:
            result = await JobRuntimeDao.get_execution(db, execution_id)
            return JobRuntimeDao.execution_result(result)

    async def wait_execution(self, execution_id: str, expected: set[str]) -> dict:
        """
        等待执行进入预期状态，失败时打印最后观察到的状态

        :param execution_id: 执行ID
        :param expected: 预期的执行状态集合
        :return: 符合预期的执行状态
        """
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            result = await self.execution(execution_id)
            if result['status'] in expected:
                return result
            await asyncio.sleep(0.01)
        raise AssertionError(result)


@pytest_asyncio.fixture
async def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Runtime]:
    """
    只访问临时 SQLite，调度器执行日志不会连接开发数据库

    :param tmp_path: 临时目录
    :param monkeypatch: 测试替换对象
    :return: 隔离测试运行环境
    """
    global STARTED, RELEASE
    STARTED, RELEASE = asyncio.Event(), asyncio.Event()
    CALLS.clear()
    path = tmp_path / 'scheduler-runtime.db'
    engine = create_engine(f'sqlite:///{path}')
    metadata = MetaData()
    definition = SysJob.__table__.to_metadata(metadata)
    # SQLite仅为INTEGER主键分配自增ID；测试副本关闭BIGINT自增并使用插入事件模拟。
    definition.c.job_id.autoincrement = False
    SysJobSync.__table__.to_metadata(metadata)
    SysJobExecution.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    def assign_sqlite_id(_mapper: object, connection: object, target: SysJob) -> None:
        """
        为 SQLite 测试模拟真实 MySQL/PostgreSQL 的数据库任务 ID 分配

        :param _mapper: 任务模型映射器
        :param connection: 数据库连接
        :param target: 任务模型实例
        :return: None
        """
        if target.job_id is None:
            target.job_id = connection.scalar(select(func.coalesce(func.max(SysJob.job_id), 0) + 1))

    event.listen(SysJob, 'before_insert', assign_sqlite_id)
    async_engine = create_async_engine(f'sqlite+aiosqlite:///{path}')
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    scheduler = AsyncIOScheduler(
        timezone=timezone.utc,
        executors={
            'default': TimedAsyncIOExecutor(manage_executions=True),
        },
    )
    scheduler.start(paused=True)
    patch_runtime_globals(monkeypatch, scheduler, sessions, engine)
    try:
        yield Runtime(engine, sessions, scheduler, STARTED, RELEASE)
    finally:
        RELEASE.set()
        pending = list(scheduler._executors['default']._pending_futures)
        if pending:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=5)
        if SchedulerManager._sync_task:
            SchedulerManager._sync_task.cancel()
            await asyncio.gather(SchedulerManager._sync_task, return_exceptions=True)
        scheduler.shutdown(wait=False)
        await asyncio.sleep(0)
        event.remove(SysJob, 'before_insert', assign_sqlite_id)
        await async_engine.dispose()
        engine.dispose()


def patch_scheduler_components(monkeypatch: pytest.MonkeyPatch, scheduler: AsyncIOScheduler) -> None:
    """
    为隔离调度器创建完整的功能类实例及依赖关系

    :param monkeypatch: 测试替换对象
    :param scheduler: 隔离测试调度器
    :return: None
    """
    resources = SchedulerResources()
    jobs = SchedulerJobs(scheduler)
    synchronizer = SchedulerSynchronizer(jobs, resources)
    dispatcher = SchedulerDispatcher(jobs, resources, synchronizer)
    listener = SchedulerJobListener(resources)
    monkeypatch.setattr(SchedulerManager, '_scheduler', scheduler)
    monkeypatch.setattr(SchedulerManager, '_resources', resources)
    monkeypatch.setattr(SchedulerManager, '_jobs', jobs)
    monkeypatch.setattr(SchedulerManager, '_synchronizer', synchronizer)
    monkeypatch.setattr(SchedulerManager, '_dispatcher', dispatcher)
    monkeypatch.setattr(SchedulerManager, '_listener', listener)


def patch_runtime_globals(
    monkeypatch: pytest.MonkeyPatch,
    scheduler: AsyncIOScheduler,
    sessions: async_sessionmaker[AsyncSession],
    engine: Engine,
) -> None:
    """
    隔离调度器单例和数据库工厂，测试结束由 monkeypatch 逐项恢复

    :param monkeypatch: 测试替换对象
    :param scheduler: 隔离测试调度器
    :param sessions: 异步数据库会话工厂
    :param engine: 隔离测试数据库引擎
    :return: None
    """
    monkeypatch.setattr(task_module, 'runtime_harmless', harmless_job, raising=False)
    monkeypatch.setattr(task_module, 'runtime_held', held_job, raising=False)
    patch_scheduler_components(monkeypatch, scheduler)
    monkeypatch.setattr(SchedulerManager, '_is_leader', True)
    monkeypatch.setattr(SchedulerManager, '_redis', SimpleNamespace(publish=AsyncMock()))
    monkeypatch.setattr(SchedulerManager, '_sync_lock', asyncio.Lock())
    monkeypatch.setattr(SchedulerManager, '_sync_pending_ids', set())
    monkeypatch.setattr(SchedulerManager, '_sync_full_pending', False)
    monkeypatch.setattr(SchedulerManager, '_sync_pending', False)
    monkeypatch.setattr(SchedulerManager, '_sync_task', None)
    monkeypatch.setattr(SchedulerManager, '_last_sync_at', None)
    monkeypatch.setattr(SchedulerManager._resources, 'session', sessions)
    monkeypatch.setattr(SchedulerManager._listener, 'persist_log', lambda _log: None)
    monkeypatch.setattr(JobExecutionStore, 'session', staticmethod(lambda: Session(engine, expire_on_commit=False)))
