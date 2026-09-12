import asyncio
import math
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobSubmissionEvent,
)
from apscheduler.executors.base import MaxInstancesReachedError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler

from config.scheduler.events import JobSnapshot, TimedJobExecutionEvent
from config.scheduler.executors import TimedAsyncIOExecutor, TimedProcessPoolExecutor, run_timed_job
from config.scheduler.manager import SchedulerManager
from config.scheduler.triggers import TaskDateTrigger
from utils.time_util import TimezoneUtil

EXPECTED_DURATION_MS = 250
EXPECTED_RETURN_VALUE = 8


def test_runner_keeps_scheduled_time_and_monotonic_duration_on_clock_rollback() -> None:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    try:
        job = scheduler.add_job(pow, args=[2, 3], misfire_grace_time=None)
        start = TimezoneUtil.utc_now()
        end = start - timedelta(hours=1)
        scheduled = start - timedelta(hours=2)
        with (
            patch('config.scheduler.executors.TimezoneUtil.utc_now', side_effect=[start, end]),
            patch('config.scheduler.executors.time.perf_counter', side_effect=[10, 10.25]),
        ):
            event = run_timed_job(job, [scheduled], JobSnapshot.from_job(job), 'test')[0]
        assert event.scheduled_run_time == scheduled
        assert event.start_time == start
        assert event.end_time == end
        assert event.run_duration_ms == EXPECTED_DURATION_MS
        assert event.retval == EXPECTED_RETURN_VALUE
        restored = pickle.loads(pickle.dumps(event))
        assert restored.execution_key == event.execution_key
        assert restored.snapshot == event.snapshot
        assert restored.start_time == event.start_time
        assert restored.end_time == event.end_time
        assert restored.run_duration_ms == event.run_duration_ms
    finally:
        scheduler.shutdown()


def test_failure_and_misfire_have_distinct_execution_metadata() -> None:
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    try:
        job = scheduler.add_job(math.sqrt, args=[-1], misfire_grace_time=1)
        now = TimezoneUtil.utc_now()
        missed, failed = run_timed_job(job, [now - timedelta(hours=1), now], JobSnapshot.from_job(job), 'test')
        assert missed.code == EVENT_JOB_MISSED
        assert missed.start_time is missed.end_time is missed.run_duration_ms is None
        assert failed.code == EVENT_JOB_ERROR
        assert isinstance(failed.exception, ValueError)
        assert failed.run_duration_ms >= 0
        assert 'job.func' in failed.traceback
        assert missed.execution_id != failed.execution_id
    finally:
        scheduler.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['thread', 'async', 'process'])
async def test_executors_preserve_return_value_and_log_deleted_one_shot(kind: str) -> None:
    loop = asyncio.get_running_loop()
    completed = loop.create_future()
    executor = TimedProcessPoolExecutor(1) if kind == 'process' else TimedAsyncIOExecutor()
    scheduler = AsyncIOScheduler(executors={'default': executor})

    def receive(event: TimedJobExecutionEvent) -> None:
        if isinstance(event, TimedJobExecutionEvent):
            loop.call_soon_threadsafe(completed.set_result, event)

    scheduler.add_listener(receive, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    scheduler.start(paused=True)
    try:
        function, args = (asyncio.sleep, [0, 8]) if kind == 'async' else (pow, [2, 3])
        # 执行结果测试不依赖子进程冷启动速度，过期策略由独立用例验证。
        job = scheduler.add_job(
            function,
            args=args,
            id='execution-test',
            name='原始名称',
            misfire_grace_time=None,
            trigger=TaskDateTrigger('Asia/Shanghai', run_date=TimezoneUtil.utc_now()),
        )
        scheduler.resume()
        event = await asyncio.wait_for(completed, 20)
        assert event.retval == EXPECTED_RETURN_VALUE
        assert event.snapshot.name == '原始名称'
        assert event.snapshot.time_zone == 'Asia/Shanghai'
        assert event.snapshot.invoke_target == job.func_ref
        assert scheduler.get_job(job.id) is None
        assert event.scheduled_run_time.utcoffset() == timedelta(0)
        assert event.start_time.tzinfo is timezone.utc
        assert event.end_time.tzinfo is timezone.utc
        assert event.start_time >= event.scheduled_run_time
        assert event.end_time >= event.start_time
        assert event.run_duration_ms >= 0
        with patch.object(SchedulerManager._listener, 'persist_log') as persist:
            SchedulerManager.scheduler_event_listener(event)
        persist.assert_called_once()
        log = persist.call_args.args[0]
        assert log.scheduled_time == TimezoneUtil.to_utc_milliseconds(event.scheduled_run_time)
        assert log.start_time == TimezoneUtil.to_utc_milliseconds(event.start_time)
        assert log.end_time == TimezoneUtil.to_utc_milliseconds(event.end_time)
        assert log.run_duration_ms == event.run_duration_ms
        assert log.time_zone == 'Asia/Shanghai'
        payload = log.model_dump(mode='json', by_alias=True)
        assert payload['startTime'] == TimezoneUtil.format_rfc3339(event.start_time)
        assert payload['endTime'] == TimezoneUtil.format_rfc3339(event.end_time)
        assert payload['jobArgs'] == args
        assert payload['jobKwargs'] == {}
    finally:
        scheduler.shutdown()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_thread_queue_wait_does_not_become_execution_start() -> None:
    loop = asyncio.get_running_loop()
    pool = ThreadPoolExecutor(1)
    release = threading.Event()
    pool.submit(release.wait)
    completed = loop.create_future()
    submitted = asyncio.Event()
    scheduler = AsyncIOScheduler(executors={'default': TimedAsyncIOExecutor()})

    def receive(event: object) -> None:
        if isinstance(event, TimedJobExecutionEvent):
            completed.set_result(event)
        elif event.code == EVENT_JOB_SUBMITTED:
            submitted.set()

    scheduler.add_listener(receive, EVENT_JOB_EXECUTED | EVENT_JOB_SUBMITTED)
    scheduler.start(paused=True)
    scheduler.add_job(pow, args=[2, 3])
    original_run_in_executor = loop.run_in_executor

    def use_single_worker(executor: object, function: object, *args) -> asyncio.Future:
        return original_run_in_executor(pool, function, *args)

    try:
        with patch.object(loop, 'run_in_executor', side_effect=use_single_worker):
            scheduler.resume()
            await asyncio.wait_for(submitted.wait(), 5)
            assert not completed.done()
            released_at = TimezoneUtil.utc_now()
            release.set()
            event = await asyncio.wait_for(completed, 5)
        assert event.start_time >= released_at
        assert event.run_duration_ms >= 0
    finally:
        release.set()
        scheduler.shutdown()
        await asyncio.sleep(0)
        pool.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['async', 'process'])
@pytest.mark.parametrize('one_shot', [True, False])
async def test_scheduler_emits_one_standard_max_instances_event_and_preserves_rejected_logs(
    kind: str, one_shot: bool
) -> None:
    executor = (
        TimedProcessPoolExecutor(1, on_rejected=SchedulerManager.scheduler_event_listener)
        if kind == 'process'
        else TimedAsyncIOExecutor(on_rejected=SchedulerManager.scheduler_event_listener)
    )
    scheduler = AsyncIOScheduler(executors={'default': executor}, timezone=timezone.utc)
    events = []
    rejected = asyncio.Event()

    def receive(event: JobSubmissionEvent) -> None:
        events.append(event)
        rejected.set()

    scheduler.add_listener(receive, EVENT_JOB_MAX_INSTANCES)
    scheduler.add_listener(SchedulerManager.scheduler_event_listener, EVENT_JOB_MAX_INSTANCES)
    scheduler.start(paused=True)
    scheduled = TimezoneUtil.utc_now() - timedelta(hours=2)
    if one_shot:
        trigger_options = {'trigger': TaskDateTrigger('Asia/Shanghai', run_date=scheduled)}
        expected_run_times = [scheduled]
    else:
        trigger_options = {'trigger': 'interval', 'hours': 1, 'next_run_time': scheduled}
        expected_run_times = [scheduled + timedelta(hours=index) for index in range(3)]
    job = scheduler.add_job(
        pow,
        args=[2, 3],
        id='rejected-job',
        name='并发拒绝测试',
        max_instances=1,
        coalesce=False,
        **trigger_options,
    )
    try:
        # 占用一个实例；拒绝由真实 Scheduler 提交流程触发，不需要启动长时间运行的工作任务。
        with patch.object(executor, '_do_submit_job'):
            executor.submit_job(job, [scheduled])
        with patch.object(SchedulerManager._listener, 'persist_log') as persist:
            scheduler.resume()
            await asyncio.wait_for(rejected.wait(), timeout=5)
        assert len(events) == 1
        assert isinstance(events[0], JobSubmissionEvent)
        assert events[0].scheduled_run_times == expected_run_times
        assert persist.call_count == len(expected_run_times)
        logs = [call.args[0] for call in persist.call_args_list]
        assert [log.scheduled_time for log in logs] == [
            TimezoneUtil.to_utc_milliseconds(value) for value in expected_run_times
        ]
        for log in logs:
            assert log.job_name == '并发拒绝测试'
            assert log.status == '1'
            assert log.start_time is log.end_time is log.run_duration_ms is None
        if one_shot:
            assert scheduler.get_job(job.id) is None
            assert logs[0].time_zone == 'Asia/Shanghai'
    finally:
        scheduler.shutdown()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_max_instances_event_does_not_invent_execution_times() -> None:
    rejected = []
    executor = TimedAsyncIOExecutor(on_rejected=rejected.append)
    scheduler = AsyncIOScheduler(executors={'default': executor})
    events = []
    scheduler.add_listener(events.append, EVENT_JOB_MAX_INSTANCES)
    scheduler.start(paused=True)
    try:
        job = scheduler.add_job(asyncio.sleep, args=[60], max_instances=1)
        executor.submit_job(job, [TimezoneUtil.utc_now()])
        with pytest.raises(MaxInstancesReachedError):
            executor.submit_job(job, [TimezoneUtil.utc_now()])
        assert events == []
        assert len(rejected) == 1
        assert rejected[0].start_time is rejected[0].end_time is rejected[0].run_duration_ms is None
    finally:
        scheduler.shutdown()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_rejection_log_failure_preserves_max_instances_error() -> None:
    on_rejected = Mock(side_effect=RuntimeError('log unavailable'))
    executor = TimedAsyncIOExecutor(on_rejected=on_rejected)
    scheduler = AsyncIOScheduler(executors={'default': executor})
    scheduler.start(paused=True)
    try:
        job = scheduler.add_job(pow, args=[2, 3], max_instances=1)
        with patch.object(executor, '_do_submit_job'):
            executor.submit_job(job, [TimezoneUtil.utc_now()])
        with pytest.raises(MaxInstancesReachedError):
            executor.submit_job(job, [TimezoneUtil.utc_now()])
        on_rejected.assert_called_once()
    finally:
        scheduler.shutdown()
        await asyncio.sleep(0)
