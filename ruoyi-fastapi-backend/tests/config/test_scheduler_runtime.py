import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update

from config.scheduler.manager import SchedulerManager
from exceptions.exception import ServiceException
from module_admin.dao.job_dao import JobDao
from module_admin.dao.job_runtime_dao import JobRuntimeDao
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.job_runtime_do import SysJobExecution, SysJobSync
from module_admin.entity.vo.job_runtime_vo import JobExecutionQueryModel, JobSyncQueryModel
from module_admin.entity.vo.job_vo import DeleteJobModel, EditJobModel
from module_admin.service.job_service import JobService
from tests.scheduler_helpers import CALLS, Runtime, job_info
from utils.time_util import TimezoneUtil

UPDATED_CONFIG_VERSION = 2
TWICE_UPDATED_CONFIG_VERSION = 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'change',
    [
        {'invokeTarget': 'module_task.scheduler_test.does_not_exist'},
        {'jobStore': 'missing'},
        {'jobExecutor': 'missing'},
        {'jobArgs': [1, 2]},
    ],
)
async def test_invalid_configuration_is_rejected_before_save(runtime: Runtime, change: dict) -> None:
    async with runtime.sessions() as db:
        with pytest.raises((ServiceException, ValidationError)):
            await JobService.add_job_services(db, job_info(**change))
        assert await db.scalar(select(func.count()).select_from(SysJob)) == 0
        assert await db.scalar(select(func.count()).select_from(SysJobSync)) == 0
    assert runtime.scheduler.get_jobs() == []


@pytest.mark.asyncio
async def test_registration_error_is_saved_and_can_be_retried(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_add = runtime.scheduler.add_job
    monkeypatch.setattr(
        runtime.scheduler, 'add_job', lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('store offline'))
    )
    async with runtime.sessions() as db:
        result = await JobService.add_job_services(db, job_info())
    state = result.result['jobs'][0]
    assert result.result['saved'] is True
    assert result.result['syncStatus'] == 'failed'
    assert state['appliedVersion'] == 0
    assert 'store offline' in state['syncError']
    async with runtime.sessions() as db:
        assert await db.get(SysJobSync, state['jobId']) is not None
        assert await db.scalar(select(func.count()).select_from(SysJob)) == 1
    monkeypatch.setattr(runtime.scheduler, 'add_job', original_add)
    async with runtime.sessions() as db:
        result = await JobService.retry_sync_services(db, state['jobId'])
    assert result.result['syncStatus'] == 'applied'
    assert runtime.scheduler.get_job(str(state['jobId'])) is not None


@pytest.mark.asyncio
async def test_edit_is_targeted_and_invalid_edit_preserves_both_states(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = await runtime.save()
    await runtime.save(job_info(jobId=43, jobName='unrelated'))
    await SchedulerManager._sync_jobs_from_database()
    original = runtime.scheduler.get_job('42')
    unrelated = runtime.scheduler.get_job('43')
    monkeypatch.setattr(
        JobDao, 'get_all_job_list_for_scheduler', AsyncMock(side_effect=AssertionError('must not scan all'))
    )
    async with runtime.sessions() as db:
        with pytest.raises(ValidationError):
            await JobService.edit_job_services(db, EditJobModel(jobId=42, jobKwargs='[1]'))
    assert runtime.scheduler.get_job('42') is original
    async with runtime.sessions() as db:
        result = await JobService.edit_job_services(db, EditJobModel(jobId=42, timeZone='Asia/Shanghai'))
    assert result.result['jobs'][0]['configVersion'] == UPDATED_CONFIG_VERSION
    assert result.result['jobs'][0]['appliedVersion'] == UPDATED_CONFIG_VERSION
    assert str(runtime.scheduler.get_job('42').trigger.timezone) == 'Asia/Shanghai'
    assert runtime.scheduler.get_job('43') is unrelated
    assert job.time_zone == 'America/New_York'


@pytest.mark.asyncio
async def test_one_registration_failure_does_not_block_other_jobs(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    await runtime.save()
    await runtime.save(job_info(jobId=43, jobName='second'))
    add = runtime.scheduler.add_job

    def fail_first(**kwargs) -> object:
        """
        模拟一个任务的存储故障，其余任务正常注册

        :param kwargs: 关键字参数
        :return: 注册后的任务对象
        """
        if kwargs['id'] == '42':
            raise RuntimeError('first failed')
        return add(**kwargs)

    monkeypatch.setattr(runtime.scheduler, 'add_job', fail_first)
    result = await SchedulerManager._sync_jobs_from_database(raise_errors=True)
    assert result['syncStatus'] == 'failed'
    assert runtime.scheduler.get_job('43') is not None
    assert {row['jobId']: row['syncStatus'] for row in result['jobs']} == {42: 'failed', 43: 'applied'}


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['0', '1'])
async def test_manual_request_survives_sync_without_changing_cron(runtime: Runtime, status: str) -> None:
    job = await runtime.save(job_info(status=status))
    await SchedulerManager._sync_jobs_from_database()
    original = runtime.scheduler.get_job('42')
    async with runtime.sessions() as db:
        submitted = await JobService.execute_job_once_services(db, job, requested_by='tester')
    execution_id = submitted.result['executionId']
    assert submitted.result['status'] == 'pending'
    assert runtime.scheduler.get_job(f'_manual:{execution_id}') is not None
    await SchedulerManager._sync_jobs_from_database()
    assert runtime.scheduler.get_job('42') is original
    assert runtime.scheduler.get_job(f'_manual:{execution_id}') is not None
    runtime.scheduler.resume()
    finished = await runtime.wait_execution(execution_id, {'success'})
    assert finished['requestedBy'] == 'tester'
    assert finished['runDurationMs'] >= 0
    assert CALLS == ['done']
    assert runtime.scheduler.get_job('42') is original


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [1, 2])
async def test_cron_and_manual_share_the_same_concurrency_limit(runtime: Runtime, limit: int) -> None:
    job = await runtime.save(job_info(invokeTarget='module_task.scheduler_test.runtime_held', maxInstances=limit))
    await SchedulerManager._sync_jobs_from_database()
    runtime.scheduler.modify_job('42', next_run_time=TimezoneUtil.utc_now())
    runtime.scheduler.resume()
    await asyncio.wait_for(runtime.started.wait(), timeout=5)
    for _ in range(limit - 1):
        async with runtime.sessions() as db:
            accepted = await JobService.execute_job_once_services(db, job)
        await runtime.wait_execution(accepted.result['executionId'], {'running'})
    async with runtime.sessions() as db:
        submitted = await JobService.execute_job_once_services(db, job)
    rejected = await runtime.wait_execution(submitted.result['executionId'], {'rejected'})
    assert f'并发上限 {limit}' in rejected['message']
    assert rejected['startTime'] is None
    assert rejected['endTime'] is None
    assert rejected['runDurationMs'] is None
    assert ['held'] * limit == CALLS
    runtime.release.set()


@pytest.mark.asyncio
async def test_lost_notification_is_recovered_and_duplicate_wakeup_does_not_repeat(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = await runtime.save()
    monkeypatch.setattr(SchedulerManager, '_is_leader', False)
    SchedulerManager._redis.publish.side_effect = RuntimeError('offline')
    async with runtime.sessions() as db:
        pending = await JobService.execute_job_once_services(db, job)
    assert runtime.scheduler.get_jobs() == []
    assert (await runtime.execution(pending.result['executionId']))['status'] == 'pending'
    monkeypatch.setattr(SchedulerManager, '_is_leader', True)
    await SchedulerManager._drain_execution_requests()
    await SchedulerManager._drain_execution_requests()
    assert len(runtime.scheduler.get_jobs()) == 1
    runtime.scheduler.resume()
    await runtime.wait_execution(pending.result['executionId'], {'success'})
    await SchedulerManager._drain_execution_requests()
    assert CALLS == ['done']


@pytest.mark.asyncio
async def test_delete_cancels_unstarted_requests_and_keeps_queryable_tombstone(runtime: Runtime) -> None:
    job = await runtime.save()
    async with runtime.sessions() as db:
        submitted = await JobService.execute_job_once_services(db, job)
    async with runtime.sessions() as db:
        result = await JobService.delete_job_services(db, DeleteJobModel(jobIds='42'))
    assert result.result['jobs'][0]['deleted'] is True
    assert result.result['syncStatus'] == 'applied'
    runtime.scheduler.resume()
    state = await runtime.wait_execution(submitted.result['executionId'], {'cancelled'})
    assert state['startTime'] is None
    assert state['endTime'] is None
    assert state['runDurationMs'] is None
    assert CALLS == []
    async with runtime.sessions() as db:
        page = await JobService.sync_list_services(db, JobSyncQueryModel())
        assert page.rows[0]['deleted'] is True
        page = await JobService.execution_list_services(db, JobExecutionQueryModel(jobId=42))
        assert page.rows[0]['status'] == 'cancelled'
        assert 'ownerToken' not in page.rows[0]
        assert 'jobSnapshot' not in page.rows[0]


@pytest.mark.asyncio
async def test_expired_started_request_is_not_replayed_but_unstarted_request_is_reclaimed(runtime: Runtime) -> None:
    job = await runtime.save()
    async with runtime.sessions() as db:
        first = await JobRuntimeDao.create_request(db, job, None)
        second = await JobRuntimeDao.create_request(db, job, None)
        await db.commit()
        await db.execute(
            update(SysJobExecution)
            .where(SysJobExecution.execution_id == first.execution_id)
            .values(
                status='running', owner_token='old-owner', lease_until=TimezoneUtil.utc_now() - timedelta(seconds=1)
            )
        )
        await db.execute(
            update(SysJobExecution)
            .where(SysJobExecution.execution_id == second.execution_id)
            .values(
                status='submitted',
                owner_token='old-dispatch',
                lease_until=TimezoneUtil.utc_now() - timedelta(seconds=1),
            )
        )
        await db.commit()
    await SchedulerManager._drain_execution_requests()
    assert (await runtime.execution(first.execution_id))['status'] == 'unknown'
    assert (await runtime.execution(second.execution_id))['status'] == 'submitted'
    assert runtime.scheduler.get_job(f'_manual:{first.execution_id}') is None
    runtime.scheduler.resume()
    await runtime.wait_execution(second.execution_id, {'rejected'})
    assert CALLS == []


@pytest.mark.asyncio
async def test_overlapping_edits_and_late_notifications_apply_latest_version(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await runtime.save()
    await SchedulerManager._sync_jobs_from_database()
    committed_ids = []
    both_committed = asyncio.Event()
    sync = SchedulerManager.request_scheduler_sync

    async def delayed_notification(job_ids: set[int], *, immediate: bool) -> dict:
        committed_ids.append(job_ids)
        if len(committed_ids) == UPDATED_CONFIG_VERSION:
            both_committed.set()
        await asyncio.wait_for(both_committed.wait(), timeout=5)
        return await sync(job_ids, immediate=immediate)

    async def edit(change: dict) -> dict:
        async with runtime.sessions() as db:
            return (await JobService.edit_job_services(db, EditJobModel(jobId=42, **change))).result

    monkeypatch.setattr(SchedulerManager, 'request_scheduler_sync', delayed_notification)
    results = await asyncio.gather(edit({'timeZone': 'UTC'}), edit({'jobName': 'changed name'}))
    for result in results:
        state = result['jobs'][0]
        assert state['configVersion'] == state['appliedVersion'] == TWICE_UPDATED_CONFIG_VERSION
    current = runtime.scheduler.get_job('42')
    assert current.name == 'changed name'
    assert str(current.trigger.timezone) == 'UTC'
    await sync({42}, immediate=True)
    assert runtime.scheduler.get_job('42') is current


@pytest.mark.asyncio
async def test_deleted_configuration_remains_retryable_when_removal_fails(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await runtime.save()
    await SchedulerManager._sync_jobs_from_database()
    remove = runtime.scheduler.remove_job
    monkeypatch.setattr(
        runtime.scheduler, 'remove_job', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('store offline'))
    )
    async with runtime.sessions() as db:
        result = await JobService.delete_job_services(db, DeleteJobModel(jobIds='42'))
    assert result.result['saved']
    assert result.result['syncStatus'] == 'failed'
    assert result.result['jobs'][0]['deleted']
    monkeypatch.setattr(runtime.scheduler, 'remove_job', remove)
    async with runtime.sessions() as db:
        retried = await JobService.retry_sync_services(db, 42)
    assert retried.result['syncStatus'] == 'applied'
    assert runtime.scheduler.get_job('42') is None
