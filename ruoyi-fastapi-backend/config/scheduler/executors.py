import asyncio
import logging
import sys
import time
import traceback
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from datetime import datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.executors.base import MaxInstancesReachedError
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.job import Job
from apscheduler.util import iscoroutinefunction_partial

from config.scheduler.events import JobSnapshot, TimedJobExecutionEvent
from config.scheduler.job_execution import ExecutionHeartbeat, JobExecutionStore
from utils.time_util import TimezoneUtil


def _missed_event(job: Job, run_time: datetime, snapshot: JobSnapshot) -> TimedJobExecutionEvent | None:
    """
    判断本次计划是否已超过允许的延迟执行时限

    :param job: 调度器任务对象
    :param run_time: 本次计划执行时刻
    :param snapshot: 提交任务时的配置快照
    :return: 过期事件，仍可执行时返回None
    """
    if job.misfire_grace_time is not None and TimezoneUtil.utc_now() - run_time > timedelta(
        seconds=job.misfire_grace_time
    ):
        return TimedJobExecutionEvent(EVENT_JOB_MISSED, job, run_time, snapshot)
    return None


@contextmanager
def _execution(
    job: Job,
    run_time: datetime,
    snapshot: JobSnapshot,
    events: list[TimedJobExecutionEvent],
    logger_name: str,
    *,
    event: TimedJobExecutionEvent | None = None,
) -> Iterator[TimedJobExecutionEvent]:
    """
    在实际调用边界记录任务起止时刻和单调耗时

    保留APScheduler对BaseException的捕获行为，异常通过执行事件回传。

    :param job: 调度器任务对象
    :param run_time: 本次计划执行时刻
    :param snapshot: 提交任务时的配置快照
    :param events: 接收执行事件的结果列表
    :param logger_name: 调度器日志名称
    :param event: 已创建的执行事件，未指定时自动创建
    :return: 供调用方写入任务返回值的执行事件
    """
    logger = logging.getLogger(logger_name)
    event = event or TimedJobExecutionEvent(EVENT_JOB_EXECUTED, job, run_time, snapshot)
    # 内部周期任务正常执行时不输出日志，避免每秒派发和定期同步刷屏。
    log_execution = not job.id.startswith('_scheduler_')
    if log_execution:
        logger.info('▶️ 开始执行任务“%s”，计划执行时间：%s', job, run_time)
    event.start_time = TimezoneUtil.utc_now()
    started_at = time.perf_counter()
    try:
        yield event
    except BaseException as exc:
        event.code = EVENT_JOB_ERROR
        event.exception = exc
    finally:
        event.run_duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        event.end_time = TimezoneUtil.utc_now()
        events.append(event)
    if event.exception is not None:
        exc = event.exception
        event.traceback = ''.join(traceback.format_tb(exc.__traceback__))
        logger.error('❌ 任务“%s”执行异常', job, exc_info=(type(exc), exc, exc.__traceback__))
        traceback.clear_frames(exc.__traceback__)
    if event.code == EVENT_JOB_EXECUTED and log_execution:
        logger.info('✅ 任务“%s”执行成功', job)


def _claim_execution(event: TimedJobExecutionEvent) -> str | None:
    """
    在实际调用前检查持久化并发约束，失败时生成未执行事件

    :param event: 任务执行事件
    :return: 执行占用凭据，未获得占用时返回None
    """
    snapshot = event.snapshot
    try:
        claim = JobExecutionStore.claim(
            event.execution_id,
            snapshot.job_id,
            snapshot.execution_snapshot(),
            event.scheduled_run_time,
            dispatch_token=snapshot.dispatch_token,
        )
    except Exception as exc:
        event.code = EVENT_JOB_ERROR
        event.execution_status = 'failed'
        event.exception = RuntimeError(f'无法确认任务执行占用，本次未调用：{exc}')
        return None
    if claim.accepted:
        return claim.token
    event.code = EVENT_JOB_MAX_INSTANCES if claim.status == 'rejected' else EVENT_JOB_ERROR
    event.execution_status = claim.status
    event.exception = RuntimeError(claim.message)
    return None


def _finish_execution(event: TimedJobExecutionEvent, token: str) -> None:
    """
    保存已执行任务的终态，存储故障保留未确认占用供恢复流程处理

    :param event: 任务执行事件
    :param token: 当前执行占用凭据
    :return: None
    """
    try:
        JobExecutionStore.finish(
            event.execution_id,
            token,
            failed=event.code != EVENT_JOB_EXECUTED,
            message=str(event.exception) if event.exception else None,
            start_time=event.start_time,
            end_time=event.end_time,
            run_duration_ms=event.run_duration_ms,
        )
    except Exception:
        logging.getLogger(__name__).exception('❌ 保存任务执行结果失败：%s', event.execution_id)


def _record_unstarted_execution(event: TimedJobExecutionEvent) -> None:
    """
    保存过期和执行器拒绝记录，不覆盖已经开始的执行

    :param event: 任务执行事件
    :return: None
    """
    if not event.snapshot.managed:
        return
    try:
        JobExecutionStore.record_unstarted(
            event.execution_id,
            event.snapshot.job_id,
            event.snapshot.execution_snapshot(),
            event.scheduled_run_time,
            'missed' if event.code == EVENT_JOB_MISSED else 'rejected',
            '错过执行窗口' if event.code == EVENT_JOB_MISSED else '达到执行器并发上限',
            dispatch_token=event.snapshot.dispatch_token,
        )
    except Exception:
        logging.getLogger(__name__).exception('❌ 保存任务未执行记录失败：%s', event.execution_id)


def run_timed_job(
    job: Job, run_times: list[datetime], snapshot: JobSnapshot, logger_name: str
) -> list[TimedJobExecutionEvent]:
    """
    执行同步任务并收集带测时信息的事件

    :param job: 调度器任务对象
    :param run_times: 本次提交需要处理的计划执行时刻列表
    :param snapshot: 提交任务时的配置快照
    :param logger_name: 调度器日志名称
    :return: 本次提交产生的执行事件列表
    """
    events = []
    for run_time in run_times:
        if missed := _missed_event(job, run_time, snapshot):
            _record_unstarted_execution(missed)
            events.append(missed)
            continue
        event = TimedJobExecutionEvent(EVENT_JOB_EXECUTED, job, run_time, snapshot)
        token = _claim_execution(event) if snapshot.managed else None
        if snapshot.managed and token is None:
            events.append(event)
            continue
        heartbeat = ExecutionHeartbeat(event.execution_id, token) if token else None
        if heartbeat:
            heartbeat.start()
        try:
            with _execution(job, run_time, snapshot, events, logger_name, event=event):
                event.retval = job.func(*job.args, **job.kwargs)
            if token:
                _finish_execution(event, token)
        finally:
            if heartbeat:
                heartbeat.stop()
    return events


async def run_timed_coroutine_job(
    job: Job, run_times: list[datetime], snapshot: JobSnapshot, logger_name: str
) -> list[TimedJobExecutionEvent]:
    """
    执行异步任务并收集带测时信息的事件

    :param job: 调度器任务对象
    :param run_times: 本次提交需要处理的计划执行时刻列表
    :param snapshot: 提交任务时的配置快照
    :param logger_name: 调度器日志名称
    :return: 本次提交产生的执行事件列表
    """
    events = []
    for run_time in run_times:
        if missed := _missed_event(job, run_time, snapshot):
            await asyncio.to_thread(_record_unstarted_execution, missed)
            events.append(missed)
            continue
        event = TimedJobExecutionEvent(EVENT_JOB_EXECUTED, job, run_time, snapshot)
        token = await asyncio.to_thread(_claim_execution, event) if snapshot.managed else None
        if snapshot.managed and token is None:
            events.append(event)
            continue
        heartbeat = ExecutionHeartbeat(event.execution_id, token) if token else None
        if heartbeat:
            heartbeat.start()
        try:
            with _execution(job, run_time, snapshot, events, logger_name, event=event):
                event.retval = await job.func(*job.args, **job.kwargs)
            if token:
                await asyncio.to_thread(_finish_execution, event, token)
        finally:
            if heartbeat:
                heartbeat.stop()
    return events


class JobSubmission:
    """
    任务提交和并发拒绝事件处理
    """

    def __init__(
        self,
        on_rejected: Callable[[TimedJobExecutionEvent], None] | None = None,
        manage_executions: bool = False,
    ) -> None:
        """
        初始化提交配置和拒绝事件回调

        :param on_rejected: 并发拒绝事件回调
        :param manage_executions: 是否启用持久化执行管理
        :return: None
        """
        self._on_rejected = on_rejected
        self.manage_executions = manage_executions

    def submit_job(
        self,
        submit: Callable[[Job, list[datetime]], None],
        job: Job,
        run_times: list[datetime],
        job_logger: logging.Logger,
    ) -> None:
        """
        调用执行器提交任务，达到并发上限时记录未执行事件

        :param submit: 执行器的原始提交方法
        :param job: 调度器任务对象
        :param run_times: 本次提交的计划执行时刻
        :param job_logger: 执行器日志对象
        :return: None
        """
        try:
            submit(job, run_times)
        except MaxInstancesReachedError:
            if self._on_rejected is not None or self.manage_executions:
                try:
                    snapshot = JobSnapshot.from_job(job, managed=self.manage_executions)
                    for run_time in run_times:
                        event = TimedJobExecutionEvent(EVENT_JOB_MAX_INSTANCES, job, run_time, snapshot)
                        _record_unstarted_execution(event)
                        if self._on_rejected is not None:
                            self._on_rejected(event)
                except Exception:
                    job_logger.exception('❌ 记录任务并发拒绝日志失败')
            # 标准JobSubmissionEvent仍由调度器捕获此异常后统一发送。
            raise


class TimedAsyncIOExecutor(AsyncIOExecutor):
    """
    记录真实执行耗时的异步及线程执行器
    """

    def __init__(
        self,
        *args,
        on_rejected: Callable[[TimedJobExecutionEvent], None] | None = None,
        manage_executions: bool = False,
        **kwargs,
    ) -> None:
        """
        初始化执行器和任务提交处理对象

        :param args: 执行器的位置参数
        :param on_rejected: 并发拒绝事件回调
        :param manage_executions: 是否启用持久化执行管理
        :param kwargs: 执行器的关键字参数
        :return: None
        """
        super().__init__(*args, **kwargs)
        self._submission = JobSubmission(on_rejected, manage_executions)

    def submit_job(self, job: Job, run_times: list[datetime]) -> None:
        """
        通过提交处理对象执行原始提交并记录并发拒绝事件

        :param job: 调度器任务对象
        :param run_times: 本次提交的计划执行时刻
        :return: None
        """
        self._submission.submit_job(super().submit_job, job, run_times, self._logger)

    def _do_submit_job(self, job: Job, run_times: list[datetime]) -> None:
        """
        提交携带配置快照的任务并注册完成回调

        :param job: 调度器任务对象
        :param run_times: 本次提交需要处理的计划执行时刻列表
        :return: None
        """
        snapshot = JobSnapshot.from_job(job, managed=self._submission.manage_executions)

        def callback(future: Future) -> None:
            """
            将任务执行结果交回APScheduler处理

            :param future: 任务执行产生的Future对象
            :return: None
            """
            self._pending_futures.discard(future)
            try:
                events = future.result()
            except BaseException:
                self._run_job_error(job.id, *sys.exc_info()[1:])
            else:
                self._run_job_success(job.id, events)

        if iscoroutinefunction_partial(job.func):
            future = self._eventloop.create_task(run_timed_coroutine_job(job, run_times, snapshot, self._logger.name))
        else:
            future = self._eventloop.run_in_executor(None, run_timed_job, job, run_times, snapshot, self._logger.name)
        future.add_done_callback(callback)
        self._pending_futures.add(future)


class TimedProcessPoolExecutor(ProcessPoolExecutor):
    """
    记录真实执行耗时的进程池执行器
    """

    def __init__(
        self,
        *args,
        on_rejected: Callable[[TimedJobExecutionEvent], None] | None = None,
        manage_executions: bool = False,
        **kwargs,
    ) -> None:
        """
        初始化执行器和任务提交处理对象

        :param args: 执行器的位置参数
        :param on_rejected: 并发拒绝事件回调
        :param manage_executions: 是否启用持久化执行管理
        :param kwargs: 执行器的关键字参数
        :return: None
        """
        super().__init__(*args, **kwargs)
        self._submission = JobSubmission(on_rejected, manage_executions)

    def submit_job(self, job: Job, run_times: list[datetime]) -> None:
        """
        通过提交处理对象执行原始提交并记录并发拒绝事件

        :param job: 调度器任务对象
        :param run_times: 本次提交的计划执行时刻
        :return: None
        """
        self._submission.submit_job(super().submit_job, job, run_times, self._logger)

    def _do_submit_job(self, job: Job, run_times: list[datetime]) -> None:
        """
        提交携带配置快照的任务并注册完成回调

        :param job: 调度器任务对象
        :param run_times: 本次提交需要处理的计划执行时刻列表
        :return: None
        """
        snapshot = JobSnapshot.from_job(job, managed=self._submission.manage_executions)

        def callback(future: Future) -> None:
            """
            将任务执行结果交回APScheduler处理

            :param future: 任务执行产生的Future对象
            :return: None
            """
            exc = future.exception()
            if exc:
                self._run_job_error(job.id, exc, exc.__traceback__)
            else:
                self._run_job_success(job.id, future.result())

        try:
            future = self._pool.submit(run_timed_job, job, run_times, snapshot, self._logger.name)
        except BrokenProcessPool:
            self._logger.warning('⚠️ 进程池异常，正在重建进程池')
            self._pool = self._pool.__class__(self._pool._max_workers, **self.pool_kwargs)
            future = self._pool.submit(run_timed_job, job, run_times, snapshot, self._logger.name)
        future.add_done_callback(callback)
