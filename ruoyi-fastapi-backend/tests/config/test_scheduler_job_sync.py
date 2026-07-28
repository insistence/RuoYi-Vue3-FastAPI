from unittest.mock import patch

import pytest
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.get_scheduler import SchedulerUtil
from module_admin.entity.vo.job_vo import JobModel


def _build_file_retention_job() -> JobModel:
    """构建与初始化SQL一致的文件保留期限提醒任务。"""
    return JobModel(
        jobId=4,
        jobName='文件保留期限提醒',
        jobGroup='default',
        jobExecutor='default',
        invokeTarget='module_task.file_task.scan_retention_reminders',
        jobArgs=None,
        jobKwargs='{"remind_days": 7, "batch_size": 500}',
        cronExpression='0 0 1 * * ?',
        misfirePolicy='3',
        concurrent='1',
        status='0',
        updateTime=None,
    )


def _build_memory_scheduler() -> AsyncIOScheduler:
    """构建不依赖数据库、Redis和进程池的测试调度器。"""
    return AsyncIOScheduler(
        jobstores={'default': MemoryJobStore()},
        executors={'default': AsyncIOExecutor()},
    )


@pytest.mark.asyncio
async def test_default_file_retention_job_is_in_sync_after_add() -> None:
    """校验默认启用任务添加后与数据库配置一致。"""
    job_info = _build_file_retention_job()
    test_scheduler = _build_memory_scheduler()
    test_scheduler.start(paused=True)

    try:
        test_scheduler.add_job(**SchedulerUtil._prepare_scheduler_job_add(job_info))
        scheduler_job = test_scheduler.get_job(str(job_info.job_id))

        assert SchedulerUtil._is_job_config_in_sync(scheduler_job, job_info) is True
    finally:
        test_scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_null_update_time_job_is_compared_once_without_rebuild() -> None:
    """校验更新时间为空的任务不会在每轮同步时重复移除和添加。"""
    job_info = _build_file_retention_job()
    job_id = str(job_info.job_id)
    test_scheduler = _build_memory_scheduler()
    test_scheduler.start(paused=True)
    original_cache = SchedulerUtil._job_update_time_cache
    SchedulerUtil._job_update_time_cache = {}

    try:
        with patch('config.get_scheduler.scheduler', test_scheduler):
            SchedulerUtil._add_job_to_scheduler(job_info)
            scheduler_job = test_scheduler.get_job(job_id)

            with patch.object(
                SchedulerUtil,
                '_is_job_config_in_sync',
                wraps=SchedulerUtil._is_job_config_in_sync,
            ) as compare_job_config:
                SchedulerUtil._sync_update_job(job_id, job_info, scheduler_job, None)
                SchedulerUtil._sync_update_job(job_id, job_info, test_scheduler.get_job(job_id), None)

            assert compare_job_config.call_count == 1
            assert test_scheduler.get_job(job_id) is scheduler_job
            assert job_id in SchedulerUtil._job_update_time_cache
            assert SchedulerUtil._job_update_time_cache[job_id] is None
    finally:
        SchedulerUtil._job_update_time_cache = original_cache
        test_scheduler.shutdown(wait=False)


def test_job_update_cache_distinguishes_cached_null_from_missing() -> None:
    """校验空更新时间可被缓存，同时仍支持显式失效。"""
    job_id = '4'
    original_cache = SchedulerUtil._job_update_time_cache
    SchedulerUtil._job_update_time_cache = {}

    try:
        assert SchedulerUtil._should_skip_job_update(job_id, None) is False

        SchedulerUtil._refresh_job_update_cache(job_id, None)

        assert SchedulerUtil._should_skip_job_update(job_id, None) is True

        SchedulerUtil._invalidate_job_update_cache(job_id)

        assert SchedulerUtil._should_skip_job_update(job_id, None) is False
    finally:
        SchedulerUtil._job_update_time_cache = original_cache
