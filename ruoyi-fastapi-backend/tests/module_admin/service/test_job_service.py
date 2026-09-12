from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from config.scheduler.manager import SchedulerManager
from exceptions.exception import ServiceException
from module_admin.dao.job_dao import JobDao
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.job_runtime_do import SysJobSync
from module_admin.entity.vo.job_vo import DeleteJobModel, EditJobModel, JobModel
from module_admin.service.job_service import JobService
from tests.scheduler_helpers import Runtime, job_info


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['add', 'edit', 'disable', 'delete'])
@pytest.mark.parametrize('commit_fails', [False, True])
async def test_job_mutations_only_request_targeted_sync_after_commit(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, action: str, commit_fails: bool
) -> None:
    if action != 'add':
        await runtime.save()
        await SchedulerManager._sync_jobs_from_database()
    original = runtime.scheduler.get_job('42')
    events = []
    async with runtime.sessions() as db:
        commit = db.commit

        async def committing() -> None:
            assert runtime.scheduler.get_job('42') is original
            events.append('commit')
            if commit_fails:
                raise RuntimeError('transaction failed')
            await commit()

        async def sync(job_ids: set[int], *, immediate: bool) -> dict:
            assert immediate
            assert events == ['commit']
            events.append('sync')
            return await SchedulerManager._sync_jobs_from_database(job_ids)

        monkeypatch.setattr(db, 'commit', committing)
        monkeypatch.setattr(SchedulerManager, 'request_scheduler_sync', sync)
        method, argument = {
            'add': (JobService.add_job_services, job_info()),
            'edit': (JobService.edit_job_services, EditJobModel(jobId=42, timeZone='UTC')),
            'disable': (JobService.edit_job_services, EditJobModel(jobId=42, status='1', type='status')),
            'delete': (JobService.delete_job_services, DeleteJobModel(jobIds='42')),
        }[action]
        if commit_fails:
            with pytest.raises(RuntimeError, match='transaction failed'):
                await method(db, argument)
            assert events == ['commit']
            assert runtime.scheduler.get_job('42') is original
        else:
            result = await method(db, argument)
            assert result.result['saved']
            assert result.result['syncStatus'] == 'applied'
            assert events == ['commit', 'sync']
            state = result.result['jobs'][0]
            assert state['configVersion'] == state['appliedVersion']
            if action == 'add':
                assert state['configVersion'] == 1
            job_id = state['jobId']
            assert (runtime.scheduler.get_job(str(job_id)) is None) == (action in ('disable', 'delete'))
    async with runtime.sessions() as db:
        job = (await db.scalars(select(SysJob))).first()
        if commit_fails and action == 'add':
            assert job is None
            assert await db.scalar(select(func.count()).select_from(SysJobSync)) == 0
            assert runtime.scheduler.get_jobs() == []
        if action == 'disable' and not commit_fails:
            assert job.time_zone == 'America/New_York'
        if commit_fails and action != 'add':
            assert job.time_zone == 'America/New_York'
            assert job.status == '0'


@pytest.mark.asyncio
async def test_sync_failure_after_commit_reports_saved_and_keeps_retryable_state(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    await runtime.save()
    monkeypatch.setattr(
        SchedulerManager, 'request_scheduler_sync', AsyncMock(side_effect=RuntimeError('sync unavailable'))
    )
    async with runtime.sessions() as db:
        result = await JobService.delete_job_services(db, DeleteJobModel(jobIds='42'))
    assert result.result['saved'] is True
    assert result.result['syncStatus'] == 'failed'
    assert '删除已提交' in result.message
    async with runtime.sessions() as db:
        assert (await db.scalars(select(SysJob))).first() is None
        state = await db.get(SysJobSync, 42)
        assert state.deleted
        assert state.sync_status == 'pending'


@pytest.mark.asyncio
async def test_disable_broken_target_remains_possible_but_enable_is_rejected(runtime: Runtime) -> None:
    await runtime.save(job_info(invokeTarget='module_task.scheduler_test.missing'))
    async with runtime.sessions() as db:
        result = await JobService.edit_job_services(db, EditJobModel(jobId=42, status='1', type='status'))
    assert result.result['syncStatus'] == 'applied'
    async with runtime.sessions() as db:
        with pytest.raises(ServiceException):
            await JobService.edit_job_services(db, EditJobModel(jobId=42, status='0', type='status'))
        assert (await JobDao.get_job_detail_by_id(db, 42)).status == '1'


@pytest.mark.asyncio
async def test_add_job_rejects_plugin_invoke_target_from_system_job_form() -> None:
    """
    校验系统定时任务入口不会放开到整个 plugins 包。

    :return: None
    """
    job = JobModel(
        jobName='plugin-core-task',
        jobGroup='default',
        jobExecutor='default',
        invokeTarget='plugins.core.lifecycle.jobs.PluginJobInstaller.pause_plugin_jobs',
        cronExpression='0/5 * * * * ?',
        misfireGraceTime=1,
        maxInstances=1,
        status='1',
    )

    with pytest.raises(ServiceException) as exc_info:
        await JobService.add_job_services(object(), job)

    assert '目标字符串不在白名单内' in exc_info.value.message
