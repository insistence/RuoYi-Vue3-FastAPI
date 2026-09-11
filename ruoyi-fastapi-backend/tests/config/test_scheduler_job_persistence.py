import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from apscheduler.events import EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from config.scheduler.executors import TimedAsyncIOExecutor
from config.scheduler.job_execution import JobExecutionStore
from config.scheduler.manager import SchedulerManager
from module_admin.dao.job_dao import JobDao
from module_admin.dao.job_runtime_dao import JobRuntimeDao
from module_admin.entity.vo.job_vo import JobModel
from module_admin.service.job_service import JobService
from tests.scheduler_helpers import Runtime, patch_scheduler_components
from utils.cron_util import MyCronTrigger
from utils.time_util import TimezoneUtil


async def persisted_callable() -> str:
    """
    无副作用的持久化任务

    :return: 执行结果标记
    """
    return 'executed'


async def verify_persistent_scheduler(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
    execution_engine: Engine | None = None,
) -> None:
    """
    验证真实任务仓库重启校准及独立手动请求，全部访问调用方的隔离库

    :param engine: 隔离测试数据库引擎
    :param monkeypatch: 测试替换对象
    :param sessions: 异步数据库会话工厂
    :param execution_engine: 执行记录使用的数据库引擎，未指定时使用任务仓库引擎
    :return: None
    """
    info = JobModel(
        jobId=81,
        jobName='persistent timezone check',
        jobGroup='default',
        jobExecutor='default',
        invokeTarget=f'{__name__}.persisted_callable',
        cronExpression='0 30 2 * * ?',
        timeZone='America/New_York',
        status='0',
        misfireGraceTime=1,
        maxInstances=1,
    )
    async with sessions() as db:
        assert await JobDao.get_job_detail_by_id(db, 81) is None
        await JobDao.add_job_dao(db, info)
        await JobRuntimeDao.record_configuration(db, 81, info)
        await db.commit()

    def build_scheduler() -> AsyncIOScheduler:
        return AsyncIOScheduler(
            timezone=timezone.utc,
            jobstores={'default': SQLAlchemyJobStore(engine=engine, tablename='apscheduler_timezone_verify')},
            executors={'default': TimedAsyncIOExecutor(manage_executions=True)},
        )

    previous = build_scheduler()
    previous.start(paused=True)
    previous.add_job(**SchedulerManager._prepare_scheduler_job_add(info))
    previous.add_job(**SchedulerManager._prepare_scheduler_job_add(info.model_copy(update={'job_id': 82})))
    old_signature = SchedulerManager._jobs.trigger_signature(previous.get_job('81').trigger)
    previous.shutdown(wait=False)
    await asyncio.sleep(0)

    current = build_scheduler()
    updated = info.model_copy(update={'time_zone': 'Asia/Shanghai', 'update_time': TimezoneUtil.utc_now()})
    async with sessions() as db:
        await JobDao.edit_job_dao(db, {'job_id': 81, 'time_zone': updated.time_zone}, info)
        await JobRuntimeDao.record_configuration(db, 81, updated)
        await db.commit()
    patch_scheduler_components(monkeypatch, current)
    monkeypatch.setattr(SchedulerManager, '_is_leader', False)
    monkeypatch.setattr(SchedulerManager._synchronizer, 'applied_jobs', {})
    monkeypatch.setattr(SchedulerManager._jobs, 'update_time_cache', {'81': updated.update_time})
    monkeypatch.setattr(SchedulerManager._dispatcher, 'lock', asyncio.Lock())
    monkeypatch.setattr(SchedulerManager, '_configure_scheduler', lambda: None)
    monkeypatch.setattr(SchedulerManager._resources, 'session', sessions)
    monkeypatch.setattr(SchedulerManager, '_should_enable_scheduler_sync', lambda: False)
    monkeypatch.setattr(JobDao, 'get_all_job_list_for_scheduler', AsyncMock(return_value=[updated]))
    monkeypatch.setattr(SchedulerManager._listener, 'persist_log', lambda _log: None)
    monkeypatch.setattr(
        JobExecutionStore, 'session', staticmethod(lambda: Session(execution_engine or engine, expire_on_commit=False))
    )
    try:
        await SchedulerManager._start_scheduler_as_leader(None)
        current.pause()
        assert current.get_job('82') is None
        restored = current.get_job('81')
        assert SchedulerManager._jobs.is_config_current(restored, updated)
        assert old_signature != SchedulerManager._jobs.trigger_signature(restored.trigger)
        expected = MyCronTrigger.from_crontab(updated.cron_expression, updated.time_zone)
        start = datetime(2026, 11, 1, tzinfo=timezone.utc)
        assert restored.trigger.get_next_fire_time(None, start) == expected.get_next_fire_time(None, start)

        await assert_independent_manual_request(current, updated, sessions)
    finally:
        current.remove_all_jobs()
        current.shutdown(wait=False)
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_persistent_restart_reconciles_timezone_and_preserves_cron_during_manual_run(
    runtime: Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # SQLite 全库写锁与真实数据库的行锁不同，任务仓库使用另一文件以免伪造行锁死锁。
    engine = create_engine(f'sqlite:///{tmp_path / "aps-jobs.db"}')
    try:
        await verify_persistent_scheduler(engine, monkeypatch, runtime.sessions, runtime.engine)
    finally:
        engine.dispose()


UPDATED_CONFIG_VERSION = 2


async def assert_independent_manual_request(
    current: AsyncIOScheduler,
    updated: JobModel,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """
    断言手动请求和周期校准都不改写原 Cron，且真实结果可查询

    :param current: 当前测试调度器
    :param updated: 更新后的任务配置
    :param sessions: 异步数据库会话工厂
    :return: None
    """
    finished = asyncio.get_running_loop().create_future()

    def on_complete(event: JobExecutionEvent) -> None:
        if event.job_id.startswith('_manual:') and not finished.done():
            finished.set_result(event)

    current.add_listener(on_complete, EVENT_JOB_EXECUTED)
    async with sessions() as db:
        response = await JobService.execute_job_once_services(db, updated)
    execution_id = response.result['executionId']
    original_next = current.get_job('81').next_run_time
    original_trigger = SchedulerManager._jobs.trigger_signature(current.get_job('81').trigger)
    assert current.get_job(f'_manual:{execution_id}') is not None
    await SchedulerManager._sync_jobs_from_database(raise_errors=True)
    assert current.get_job('81').next_run_time == original_next
    assert SchedulerManager._jobs.trigger_signature(current.get_job('81').trigger) == original_trigger
    current.resume()
    event = await asyncio.wait_for(finished, timeout=10)
    current.pause()
    assert event.retval == 'executed'
    assert event.execution_id == execution_id
    assert current.get_job(f'_manual:{execution_id}') is None
    assert SchedulerManager._jobs.is_config_current(current.get_job('81'), updated)
    async with sessions() as db:
        execution = await JobRuntimeDao.get_execution(db, execution_id)
        assert execution.status == 'success'
        assert execution.run_duration_ms >= 0
        state = (await JobRuntimeDao.get_states(db, [81]))[81]
        assert state['configVersion'] == state['appliedVersion'] == UPDATED_CONFIG_VERSION
