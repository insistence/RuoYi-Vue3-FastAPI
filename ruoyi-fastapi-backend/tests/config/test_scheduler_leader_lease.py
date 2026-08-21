import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from common.constant import LockConstant
from config.get_scheduler import SchedulerUtil

EXPECTED_REACQUIRE_ATTEMPTS = 2


@pytest.mark.asyncio
async def test_scheduler_activation_failure_stops_renewal_and_releases_lease() -> None:
    """校验Scheduler启动失败时不会继续占用Application leader租约。"""
    redis = MagicMock()

    with (
        patch.object(SchedulerUtil, 'start_application_lock_renewal') as start_renewal,
        patch.object(
            SchedulerUtil,
            '_start_scheduler_as_leader',
            new=AsyncMock(side_effect=RuntimeError('scheduler startup failed')),
        ),
        patch.object(
            SchedulerUtil,
            'stop_application_lock_renewal',
            new_callable=AsyncMock,
        ) as stop_renewal,
        patch(
            'config.get_scheduler.StartupUtil.release_application_leader',
            new_callable=AsyncMock,
        ) as release_application_leader,
        pytest.raises(RuntimeError, match='scheduler startup failed'),
    ):
        await SchedulerUtil._activate_scheduler_as_leader(redis)

    start_renewal.assert_called_once_with(redis)
    stop_renewal.assert_awaited_once_with()
    release_application_leader.assert_awaited_once_with(
        redis,
        LockConstant.APP_STARTUP_LOCK_KEY,
        SchedulerUtil.get_application_lock_owner_token(),
    )
    assert SchedulerUtil._is_leader is False


def test_start_application_lock_renewal_retains_redis_for_early_startup_cleanup() -> None:
    """校验Scheduler初始化前的启动失败仍可找到Redis并释放Application租约。"""
    redis = MagicMock()
    renewal_task = MagicMock()
    renewal_task.done.return_value = False
    original_redis = SchedulerUtil._redis
    original_renewal_task = SchedulerUtil._application_lock_renewal_task
    SchedulerUtil._redis = None
    SchedulerUtil._application_lock_renewal_task = renewal_task

    try:
        reused_task = SchedulerUtil.start_application_lock_renewal(redis)

        assert reused_task is renewal_task
        assert SchedulerUtil._redis is redis
    finally:
        SchedulerUtil._redis = original_redis
        SchedulerUtil._application_lock_renewal_task = original_renewal_task


@pytest.mark.asyncio
async def test_non_leader_scheduler_starts_reacquire_task() -> None:
    """校验首次获取Application锁失败后会持续参与leader竞争。"""
    redis = MagicMock()
    scheduled_task = MagicMock()
    scheduled_task.done.return_value = False
    original_state = (
        SchedulerUtil._redis,
        SchedulerUtil._is_leader,
        SchedulerUtil._reacquire_task,
        SchedulerUtil._is_closing,
    )
    SchedulerUtil._redis = None
    SchedulerUtil._is_leader = False
    SchedulerUtil._reacquire_task = None
    SchedulerUtil._is_closing = False

    def create_task(coroutine: object) -> MagicMock:
        coroutine.close()
        return scheduled_task

    try:
        with (
            patch(
                'config.get_scheduler.StartupUtil.acquire_application_leader',
                new=AsyncMock(return_value=False),
            ) as acquire_application_leader,
            patch('config.get_scheduler.asyncio.create_task', side_effect=create_task) as create_task_mock,
        ):
            await SchedulerUtil.init_system_scheduler(redis)

        acquire_application_leader.assert_awaited_once()
        create_task_mock.assert_called_once()
        assert SchedulerUtil._reacquire_task is scheduled_task
        assert SchedulerUtil._is_closing is False
    finally:
        (
            SchedulerUtil._redis,
            SchedulerUtil._is_leader,
            SchedulerUtil._reacquire_task,
            SchedulerUtil._is_closing,
        ) = original_state


def test_scheduler_reacquire_task_is_idempotent_and_disabled_while_closing() -> None:
    """校验每个worker只创建一个竞争任务，关闭期不再新建任务。"""
    redis = MagicMock()
    existing_task = MagicMock()
    existing_task.done.return_value = False
    original_state = (
        SchedulerUtil._redis,
        SchedulerUtil._reacquire_task,
        SchedulerUtil._is_closing,
    )
    SchedulerUtil._redis = redis
    SchedulerUtil._reacquire_task = existing_task
    SchedulerUtil._is_closing = False

    try:
        with patch('config.get_scheduler.asyncio.create_task') as create_task_mock:
            SchedulerUtil._ensure_reacquire_task()
            SchedulerUtil._ensure_reacquire_task()

            create_task_mock.assert_not_called()
            assert SchedulerUtil._reacquire_task is existing_task

            SchedulerUtil._reacquire_task = None
            SchedulerUtil._is_closing = True
            SchedulerUtil._ensure_reacquire_task()

            create_task_mock.assert_not_called()
            assert SchedulerUtil._reacquire_task is None
    finally:
        SchedulerUtil._redis, SchedulerUtil._reacquire_task, SchedulerUtil._is_closing = original_state


def test_scheduler_reacquire_delay_includes_jitter() -> None:
    """校验重新竞争间隔包含有界随机抖动。"""
    with patch('config.get_scheduler.random.uniform', return_value=0.25) as uniform:
        delay = SchedulerUtil._get_reacquire_delay()

    uniform.assert_called_once_with(0, SchedulerUtil._reacquire_jitter_seconds)
    assert delay == SchedulerUtil._reacquire_interval_seconds + 0.25


@pytest.mark.asyncio
async def test_scheduler_close_releases_owner_lease_before_forgetting_redis() -> None:
    """校验关闭Scheduler时使用进程owner token原子释放租约。"""
    redis = MagicMock()
    original_redis = SchedulerUtil._redis
    original_is_leader = SchedulerUtil._is_leader
    original_is_closing = SchedulerUtil._is_closing
    original_tasks = (
        SchedulerUtil._sync_listener_task,
        SchedulerUtil._sync_task,
        SchedulerUtil._reacquire_task,
        SchedulerUtil._lock_lost_task,
    )
    SchedulerUtil._redis = redis
    SchedulerUtil._is_leader = True
    SchedulerUtil._is_closing = False
    SchedulerUtil._sync_listener_task = None
    SchedulerUtil._sync_task = None
    reacquire_task = asyncio.create_task(asyncio.Event().wait())
    SchedulerUtil._reacquire_task = reacquire_task
    SchedulerUtil._lock_lost_task = None

    try:
        with (
            patch.object(
                SchedulerUtil,
                'stop_application_lock_renewal',
                new_callable=AsyncMock,
            ) as stop_renewal,
            patch.object(SchedulerUtil, '_dispose_sync_engines'),
            patch('config.get_scheduler.scheduler', running=False),
            patch(
                'config.get_scheduler.StartupUtil.release_application_leader',
                new=AsyncMock(return_value=True),
            ) as release_application_leader,
        ):
            await SchedulerUtil.close_system_scheduler()

        stop_renewal.assert_awaited_once_with()
        release_application_leader.assert_awaited_once_with(
            redis,
            LockConstant.APP_STARTUP_LOCK_KEY,
            SchedulerUtil.get_application_lock_owner_token(),
        )
        assert SchedulerUtil._redis is None
        assert SchedulerUtil._is_leader is False
        assert SchedulerUtil._is_closing is True
        assert reacquire_task.cancelled()
    finally:
        SchedulerUtil._redis = original_redis
        SchedulerUtil._is_leader = original_is_leader
        SchedulerUtil._is_closing = original_is_closing
        (
            SchedulerUtil._sync_listener_task,
            SchedulerUtil._sync_task,
            SchedulerUtil._reacquire_task,
            SchedulerUtil._lock_lost_task,
        ) = original_tasks


def test_scheduler_lock_lost_callback_revokes_leader_state() -> None:
    """校验租约丢失回调会立即撤销Scheduler leader状态并安排降级清理。"""
    original_is_leader = SchedulerUtil._is_leader
    original_lock_lost_task = SchedulerUtil._lock_lost_task
    scheduled_task = MagicMock()

    def create_task(coroutine: object) -> MagicMock:
        coroutine.close()
        return scheduled_task

    SchedulerUtil._is_leader = True
    SchedulerUtil._lock_lost_task = None
    try:
        with patch('config.get_scheduler.asyncio.create_task', side_effect=create_task) as create_task_mock:
            SchedulerUtil.on_lock_lost()

        assert SchedulerUtil._is_leader is False
        assert SchedulerUtil._lock_lost_task is scheduled_task
        create_task_mock.assert_called_once()
    finally:
        SchedulerUtil._is_leader = original_is_leader
        SchedulerUtil._lock_lost_task = original_lock_lost_task


@pytest.mark.asyncio
async def test_scheduler_reacquire_retries_after_redis_error() -> None:
    """校验Redis短暂异常不会永久终止Application leader重新竞争。"""
    redis = MagicMock()
    original_redis = SchedulerUtil._redis
    original_is_leader = SchedulerUtil._is_leader
    original_reacquire_task = SchedulerUtil._reacquire_task
    original_is_closing = SchedulerUtil._is_closing
    SchedulerUtil._redis = redis
    SchedulerUtil._is_leader = False
    SchedulerUtil._is_closing = False

    try:
        with (
            patch(
                'config.get_scheduler.StartupUtil.acquire_application_leader',
                new=AsyncMock(side_effect=[ConnectionError('redis unavailable'), True]),
            ) as acquire_application_leader,
            patch.object(
                SchedulerUtil,
                '_activate_scheduler_as_leader',
                new_callable=AsyncMock,
            ) as activate_scheduler,
            patch.object(
                SchedulerUtil,
                '_get_reacquire_delay',
                return_value=SchedulerUtil._reacquire_interval_seconds,
            ),
            patch('config.get_scheduler.asyncio.sleep', new_callable=AsyncMock) as sleep,
        ):
            await SchedulerUtil._run_reacquire_loop()

        assert acquire_application_leader.await_count == EXPECTED_REACQUIRE_ATTEMPTS
        assert sleep.await_args_list == [
            call(SchedulerUtil._reacquire_interval_seconds),
            call(SchedulerUtil._reacquire_interval_seconds),
        ]
        activate_scheduler.assert_awaited_once_with(redis)
    finally:
        SchedulerUtil._redis = original_redis
        SchedulerUtil._is_leader = original_is_leader
        SchedulerUtil._reacquire_task = original_reacquire_task
        SchedulerUtil._is_closing = original_is_closing


@pytest.mark.asyncio
async def test_scheduler_reacquire_retries_after_scheduler_restore_error() -> None:
    """校验重新获得租约后的Scheduler恢复异常不会永久终止failover。"""
    redis = MagicMock()
    original_redis = SchedulerUtil._redis
    original_is_leader = SchedulerUtil._is_leader
    original_reacquire_task = SchedulerUtil._reacquire_task
    original_is_closing = SchedulerUtil._is_closing
    SchedulerUtil._redis = redis
    SchedulerUtil._is_leader = False
    SchedulerUtil._is_closing = False

    try:
        with (
            patch(
                'config.get_scheduler.StartupUtil.acquire_application_leader',
                new=AsyncMock(return_value=True),
            ) as acquire_application_leader,
            patch.object(
                SchedulerUtil,
                '_activate_scheduler_as_leader',
                new=AsyncMock(side_effect=[RuntimeError('restore failed'), None]),
            ) as activate_scheduler,
            patch.object(
                SchedulerUtil,
                '_get_reacquire_delay',
                return_value=SchedulerUtil._reacquire_interval_seconds,
            ),
            patch('config.get_scheduler.asyncio.sleep', new_callable=AsyncMock) as sleep,
        ):
            await SchedulerUtil._run_reacquire_loop()

        assert acquire_application_leader.await_count == EXPECTED_REACQUIRE_ATTEMPTS
        assert activate_scheduler.await_count == EXPECTED_REACQUIRE_ATTEMPTS
        assert sleep.await_args_list == [
            call(SchedulerUtil._reacquire_interval_seconds),
            call(SchedulerUtil._reacquire_interval_seconds),
        ]
    finally:
        SchedulerUtil._redis = original_redis
        SchedulerUtil._is_leader = original_is_leader
        SchedulerUtil._reacquire_task = original_reacquire_task
        SchedulerUtil._is_closing = original_is_closing
