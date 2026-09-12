import asyncio
import pickle
from datetime import timedelta
from pathlib import Path

import pytest
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from pydantic import ValidationError
from sqlalchemy import Integer, MetaData, select, update
from sqlalchemy.exc import IntegrityError

from config.scheduler.manager import SchedulerManager
from exceptions.exception import ServiceException
from module_admin.dao.job_log_dao import JobLogDao
from module_admin.entity.do.job_do import SysJob, SysJobLog
from module_admin.entity.do.job_runtime_do import SysJobSync
from module_admin.entity.vo.job_vo import DeleteJobModel, EditJobModel, JobLogPageQueryModel, JobModel
from module_admin.service.job_service import JobService
from tests.scheduler_helpers import CALLS, Runtime, job_info
from utils.time_util import TimezoneUtil


@pytest.mark.parametrize(
    'change',
    [
        {'jobArgs': 'one,two'},
        {'jobArgs': {'value': 1}},
        {'jobKwargs': '[]'},
        {'jobKwargs': []},
        {'maxInstances': 0},
        {'maxInstances': True},
        {'maxInstances': 1.5},
        {'misfireGraceTime': 0},
        {'misfireGraceTime': -1},
        {'misfireGraceTime': True},
        {'coalesce': 'false'},
        {'misfirePolicy': '3'},
        {'concurrent': '0'},
    ],
)
def test_job_fields_reject_ambiguous_or_invalid_configuration(change: dict) -> None:
    with pytest.raises(ValidationError):
        JobModel(**change)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('grace', 'coalesce', 'expected_calls', 'expected_events'),
    [
        (None, False, 3, 3),
        (None, True, 1, 1),
        (1, False, 0, 3),
        (1, True, 0, 1),
    ],
)
async def test_real_scheduler_applies_misfire_window_and_backlog_policy(
    runtime: Runtime,
    grace: int | None,
    coalesce: bool,
    expected_calls: int,
    expected_events: int,
) -> None:
    await runtime.save(
        job_info(cronExpression='0 0 0 * * ?', timeZone='UTC', misfireGraceTime=grace, coalesce=coalesce)
    )
    await SchedulerManager._sync_jobs_from_database()
    now = TimezoneUtil.utc_now()
    # 选择明确早于当前时刻的每日计划，避免测试依赖秒级执行速度。
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now - midnight < timedelta(seconds=10):
        pytest.skip('UTC午夜边界不适合固定三次积压的测试')
    runtime.scheduler.modify_job('42', next_run_time=midnight - timedelta(days=2))
    events = []
    complete = asyncio.Event()

    def collect(event: object) -> None:
        events.append(event)
        if len(events) == expected_events:
            complete.set()

    runtime.scheduler.add_listener(collect, EVENT_JOB_EXECUTED | EVENT_JOB_MISSED)
    runtime.scheduler.resume()
    await asyncio.wait_for(complete.wait(), timeout=5)
    assert len(CALLS) == expected_calls
    assert all(event.code == (EVENT_JOB_EXECUTED if grace is None else EVENT_JOB_MISSED) for event in events)
    if grace is not None:
        assert all(event.start_time is None and event.run_duration_ms is None for event in events)


@pytest.mark.asyncio
async def test_json_parameters_and_unlimited_delay_survive_database_roundtrip(runtime: Runtime) -> None:
    value = {'text': 'x' * 600, 'flags': [True, None, 3.25], 'name': 'tenant,a'}
    saved = await runtime.save(job_info(jobArgs=[value], misfireGraceTime=None))
    async with runtime.sessions() as db:
        result = await JobService.job_detail_services(db, saved.job_id)
    assert result.job_args == [value]
    assert result.misfire_grace_time is None
    async with runtime.sessions() as db:
        submitted = await JobService.execute_job_once_services(db, saved)
    runtime.scheduler.resume()
    await runtime.wait_execution(submitted.result['executionId'], {'success'})
    assert [value] == CALLS


@pytest.mark.asyncio
async def test_group_changes_preserve_storage_and_schedule_progress(runtime: Runtime, tmp_path: Path) -> None:
    runtime.scheduler.add_jobstore(SQLAlchemyJobStore(url=f'sqlite:///{tmp_path / "jobstore.db"}'), 'sqlalchemy')
    await runtime.save(job_info(jobGroup='报表', jobStore='sqlalchemy'))
    await SchedulerManager._sync_jobs_from_database()
    previous_time = TimezoneUtil.utc_now() - timedelta(minutes=5)
    runtime.scheduler.modify_job('42', jobstore='sqlalchemy', next_run_time=previous_time)
    async with runtime.sessions() as db:
        await JobService.edit_job_services(db, EditJobModel(jobId=42, jobGroup='财务', coalesce=True))
    current = runtime.scheduler.get_job('42', jobstore='sqlalchemy')
    assert current.next_run_time == previous_time
    assert current.trigger.task_job_group == '财务'
    assert pickle.loads(pickle.dumps(current.trigger)).task_job_group == '财务'
    assert runtime.scheduler.get_job('42', jobstore='default') is None
    async with runtime.sessions() as db:
        await JobService.edit_job_services(db, EditJobModel(jobId=42, jobStore='default'))
    current = runtime.scheduler.get_job('42', jobstore='default')
    assert current.next_run_time == previous_time
    assert current.trigger.task_job_group == '财务'
    assert runtime.scheduler.get_job('42', jobstore='sqlalchemy') is None


@pytest.mark.asyncio
async def test_id_is_unique_and_name_is_unique_within_business_group(runtime: Runtime) -> None:
    await runtime.save()
    assert list(SysJob.__table__.primary_key.columns.keys()) == ['job_id']
    async with runtime.sessions() as db:
        with pytest.raises(ServiceException) as error:
            await JobService.add_job_services(db, job_info(jobArgs=['different']))
        assert '已存在' in error.value.message
    async with runtime.sessions() as db:
        db.add(
            SysJob(
                **job_info(jobName='another', jobGroup='another').model_dump(
                    include=set(SysJob.__table__.columns.keys())
                )
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
    async with runtime.sessions() as db:
        result = await JobService.add_job_services(db, job_info(jobGroup='another'))
    assert result.result['saved']


@pytest.mark.asyncio
async def test_actual_schedule_is_observed_from_leader_and_separate_from_preview(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await runtime.save()
    await SchedulerManager._sync_jobs_from_database()
    actual = TimezoneUtil.utc_now() + timedelta(minutes=2)
    actual = actual.replace(microsecond=actual.microsecond // 1000 * 1000)
    runtime.scheduler.modify_job('42', next_run_time=actual)
    await SchedulerManager._dispatcher.refresh_observations(is_leader=SchedulerManager.is_application_leader)
    monkeypatch.setattr(SchedulerManager, '_is_leader', False)
    async with runtime.sessions() as db:
        result = await JobService.job_detail_services(db, 42)
    assert result.next_run_time == actual
    assert result.cron_next_time > actual
    async with runtime.sessions() as db:
        await db.execute(
            update(SysJobSync).values(schedule_observed_time=TimezoneUtil.utc_now() - timedelta(minutes=1))
        )
        await db.commit()
        stale = await JobService.job_detail_services(db, 42)
    assert stale.next_run_time is None
    assert stale.cron_next_time is not None
    monkeypatch.setattr(SchedulerManager, '_is_leader', True)
    async with runtime.sessions() as db:
        await JobService.edit_job_services(db, EditJobModel(jobId=42, status='1', type='status'))
        disabled = await JobService.job_detail_services(db, 42)
    assert disabled.next_run_time is None
    assert disabled.cron_next_time is not None


@pytest.mark.asyncio
async def test_log_ids_keep_history_queryable_after_rename_and_delete(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = MetaData()
    logs = SysJobLog.__table__.to_metadata(metadata)
    logs.c.job_log_id.type = Integer()
    metadata.create_all(runtime.engine)
    recorded = []
    logged = asyncio.Event()

    def record(log: object) -> None:
        recorded.append(log)
        logged.set()

    monkeypatch.setattr(SchedulerManager._listener, 'persist_log', record)
    runtime.scheduler.add_listener(SchedulerManager.scheduler_event_listener)
    job = await runtime.save(job_info(jobGroup='业务分组', jobArgs=['tenant,a']))
    async with runtime.sessions() as db:
        submitted = await JobService.execute_job_once_services(db, job)
    runtime.scheduler.resume()
    await runtime.wait_execution(submitted.result['executionId'], {'success'})
    # 执行结果先提交、事件随后分发，等待事件循环完成日志通知。
    await asyncio.wait_for(logged.wait(), timeout=5)
    assert len(recorded) == 1
    log = recorded[0]
    assert log.job_id == job.job_id
    assert log.execution_id == submitted.result['executionId']
    assert log.job_group == '业务分组'
    assert log.job_store == 'default'
    assert log.job_args == ['tenant,a']
    async with runtime.sessions() as db:
        db.add(SysJobLog(**log.model_dump(exclude={'job_log_id'})))
        await db.commit()
        await JobService.edit_job_services(db, EditJobModel(jobId=42, jobName='改名后'))
        await JobService.delete_job_services(db, DeleteJobModel(jobIds='42'))
        result = await JobLogDao.get_job_log_list(db, JobLogPageQueryModel(jobId=42), is_page=True)
        assert result.total == 1
        assert result.rows[0]['jobName'] == job.job_name
        by_execution = await JobLogDao.get_job_log_list(
            db, JobLogPageQueryModel(executionId=log.execution_id), is_page=True
        )
        assert by_execution.rows[0]['jobId'] == job.job_id
        assert (await db.scalars(select(SysJob))).first() is None
