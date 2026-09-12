import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.scheduler.jobs import SchedulerJobs
from config.scheduler.manager import SchedulerManager
from module_admin.dao.job_dao import JobDao
from tests.scheduler_helpers import Runtime, job_info


@pytest_asyncio.fixture
async def jobs() -> AsyncIterator[SchedulerJobs]:
    """每个用例使用独立的内存调度器和同步缓存。"""
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.start(paused=True)
    try:
        yield SchedulerJobs(scheduler)
    finally:
        scheduler.shutdown(wait=False)
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_null_update_time_job_is_compared_once_without_rebuild(jobs: SchedulerJobs) -> None:
    """空更新时间不会导致重复比较配置或重建任务。"""
    info = job_info(
        invokeTarget='module_task.file_task.scan_retention_reminders',
        jobKwargs={'remind_days': 7, 'batch_size': 500},
        updateTime=None,
    )
    job_id = str(info.job_id)
    jobs.register_job(info)
    original = jobs.get_job(job_id)

    with patch.object(jobs, 'is_config_current', wraps=jobs.is_config_current) as compare:
        jobs.update_job(job_id, info, original, None)
        jobs.update_job(job_id, info, jobs.get_job(job_id), None)

    compare.assert_called_once()
    assert jobs.get_job(job_id) is original


@pytest.mark.asyncio
async def test_timezone_only_update_rebuilds_trigger_and_failure_remains_retryable(jobs: SchedulerJobs) -> None:
    """存储故障保留旧触发器，重试后应用新时区。"""
    info = job_info(invokeTarget='module_task.scheduler_test.job', timeZone='Asia/Shanghai')
    job_id = str(info.job_id)
    jobs.register_job(info)
    original = jobs.get_job(job_id)
    changed_at = datetime(2026, 9, 9, tzinfo=timezone.utc)
    changed = info.model_copy(update={'time_zone': 'UTC', 'update_time': changed_at})

    with (
        patch.object(jobs.scheduler, 'add_job', side_effect=RuntimeError('store unavailable')),
        pytest.raises(RuntimeError, match='store unavailable'),
    ):
        jobs.update_job(job_id, changed, original, changed_at)

    assert jobs.get_job(job_id) is original
    assert str(original.trigger.timezone) == 'Asia/Shanghai'
    jobs.update_job(job_id, changed, original, changed_at)
    assert str(jobs.get_job(job_id).trigger.timezone) == 'UTC'
    assert jobs.is_config_current(jobs.get_job(job_id), changed)


@pytest.mark.asyncio
@pytest.mark.parametrize('immediate', [False, True])
@pytest.mark.parametrize('publish_fails', [False, True])
async def test_non_leader_only_notifies_ids_and_tolerates_notification_failure(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, immediate: bool, publish_fails: bool
) -> None:
    monkeypatch.setattr(SchedulerManager, '_is_leader', False)
    publish = SchedulerManager._redis.publish
    publish.side_effect = RuntimeError('offline') if publish_fails else None
    sync = AsyncMock()
    monkeypatch.setattr(SchedulerManager, '_sync_jobs_from_database', sync)
    result = await SchedulerManager.request_scheduler_sync({42, 43}, immediate=immediate)
    assert result['syncStatus'] == 'pending'
    assert json.loads(publish.await_args.args[1]) == {'jobIds': [42, 43]}
    sync.assert_not_awaited()
    assert SchedulerManager._sync_task is None


@pytest.mark.asyncio
async def test_immediate_sync_notifies_new_leader_if_lease_is_lost_waiting_for_lock(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = SchedulerManager._sync_lock
    await lock.acquire()
    sync = AsyncMock()
    monkeypatch.setattr(SchedulerManager, '_sync_jobs_from_database', sync)
    task = asyncio.create_task(SchedulerManager.request_scheduler_sync({42}, immediate=True))
    await asyncio.sleep(0)
    assert not task.done()
    monkeypatch.setattr(SchedulerManager, '_is_leader', False)
    lock.release()
    result = await asyncio.wait_for(task, timeout=1)
    assert result['syncStatus'] == 'pending'
    sync.assert_not_awaited()
    assert json.loads(SchedulerManager._redis.publish.await_args.args[1]) == {'jobIds': [42]}


@pytest.mark.asyncio
async def test_immediate_sync_stops_local_updates_if_lease_is_lost_during_read(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    await runtime.save()
    await SchedulerManager._sync_jobs_from_database()
    original = runtime.scheduler.get_job('42')

    async def read_jobs(_session: object) -> list:
        monkeypatch.setattr(SchedulerManager, '_is_leader', False)
        return []

    monkeypatch.setattr(JobDao, 'get_all_job_list_for_scheduler', read_jobs)
    result = await SchedulerManager.request_scheduler_sync(immediate=True)
    assert result['syncStatus'] == 'pending'
    assert runtime.scheduler.get_job('42') is original
    assert json.loads(SchedulerManager._redis.publish.await_args.args[1]) == {'jobIds': None}
