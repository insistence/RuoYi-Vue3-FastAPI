import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from common.constant import LockConstant
from config.scheduler.manager import SchedulerManager

EXPECTED_REACQUIRE_ATTEMPTS = 2


@pytest.mark.asyncio
async def test_scheduler_activation_failure_stops_renewal_and_releases_lease() -> None:
    """校验Scheduler启动失败时不会继续占用Application leader租约。"""
    redis = MagicMock()

    with (
        patch.object(SchedulerManager, 'start_application_lock_renewal') as start_renewal,
        patch.object(
            SchedulerManager,
            '_start_scheduler_as_leader',
            new=AsyncMock(side_effect=RuntimeError('scheduler startup failed')),
        ),
        patch.object(
            SchedulerManager,
            'stop_application_lock_renewal',
            new_callable=AsyncMock,
        ) as stop_renewal,
        patch(
            'config.scheduler.manager.StartupUtil.release_application_leader',
            new_callable=AsyncMock,
        ) as release_application_leader,
        pytest.raises(RuntimeError, match='scheduler startup failed'),
    ):
        await SchedulerManager._activate_scheduler_as_leader(redis)

    start_renewal.assert_called_once_with(redis)
    stop_renewal.assert_awaited_once_with()
    release_application_leader.assert_awaited_once_with(
        redis,
        LockConstant.APP_STARTUP_LOCK_KEY,
        SchedulerManager.get_application_lock_owner_token(),
    )
    assert SchedulerManager._is_leader is False


def test_start_application_lock_renewal_retains_redis_for_early_startup_cleanup() -> None:
    """校验Scheduler初始化前的启动失败仍可找到Redis并释放Application租约。"""
    redis = MagicMock()
    renewal_task = MagicMock()
    renewal_task.done.return_value = False
    original_redis = SchedulerManager._redis
    original_renewal_task = SchedulerManager._application_lock_renewal_task
    SchedulerManager._redis = None
    SchedulerManager._application_lock_renewal_task = renewal_task

    try:
        reused_task = SchedulerManager.start_application_lock_renewal(redis)

        assert reused_task is renewal_task
        assert SchedulerManager._redis is redis
    finally:
        SchedulerManager._redis = original_redis
        SchedulerManager._application_lock_renewal_task = original_renewal_task


@pytest.mark.asyncio
async def test_non_leader_scheduler_starts_reacquire_task() -> None:
    """校验首次获取Application锁失败后会持续参与leader竞争。"""
    redis = MagicMock()
    scheduled_task = MagicMock()
    scheduled_task.done.return_value = False
    original_state = (
        SchedulerManager._redis,
        SchedulerManager._is_leader,
        SchedulerManager._reacquire_task,
        SchedulerManager._is_closing,
    )
    SchedulerManager._redis = None
    SchedulerManager._is_leader = False
    SchedulerManager._reacquire_task = None
    SchedulerManager._is_closing = False

    def create_task(coroutine: object) -> MagicMock:
        coroutine.close()
        return scheduled_task

    try:
        with (
            patch(
                'config.scheduler.manager.StartupUtil.acquire_application_leader',
                new=AsyncMock(return_value=False),
            ) as acquire_application_leader,
            patch('config.scheduler.manager.asyncio.create_task', side_effect=create_task) as create_task_mock,
        ):
            await SchedulerManager.init_system_scheduler(redis)

        acquire_application_leader.assert_awaited_once()
        create_task_mock.assert_called_once()
        assert SchedulerManager._reacquire_task is scheduled_task
        assert SchedulerManager._is_closing is False
    finally:
        (
            SchedulerManager._redis,
            SchedulerManager._is_leader,
            SchedulerManager._reacquire_task,
            SchedulerManager._is_closing,
        ) = original_state


def test_scheduler_reacquire_task_is_idempotent_and_disabled_while_closing() -> None:
    """校验每个worker只创建一个竞争任务，关闭期不再新建任务。"""
    redis = MagicMock()
    existing_task = MagicMock()
    existing_task.done.return_value = False
    original_state = (
        SchedulerManager._redis,
        SchedulerManager._reacquire_task,
        SchedulerManager._is_closing,
    )
    SchedulerManager._redis = redis
    SchedulerManager._reacquire_task = existing_task
    SchedulerManager._is_closing = False

    try:
        with patch('config.scheduler.manager.asyncio.create_task') as create_task_mock:
            SchedulerManager._ensure_reacquire_task()
            SchedulerManager._ensure_reacquire_task()

            create_task_mock.assert_not_called()
            assert SchedulerManager._reacquire_task is existing_task

            SchedulerManager._reacquire_task = None
            SchedulerManager._is_closing = True
            SchedulerManager._ensure_reacquire_task()

            create_task_mock.assert_not_called()
            assert SchedulerManager._reacquire_task is None
    finally:
        SchedulerManager._redis, SchedulerManager._reacquire_task, SchedulerManager._is_closing = original_state


def test_scheduler_reacquire_delay_includes_jitter() -> None:
    """校验重新竞争间隔包含有界随机抖动。"""
    with patch('config.scheduler.manager.random.uniform', return_value=0.25) as uniform:
        delay = SchedulerManager._get_reacquire_delay()

    uniform.assert_called_once_with(0, SchedulerManager._reacquire_jitter_seconds)
    assert delay == SchedulerManager._reacquire_interval_seconds + 0.25


@pytest.mark.asyncio
async def test_scheduler_close_releases_owner_lease_before_forgetting_redis() -> None:
    """校验关闭Scheduler时使用进程owner token原子释放租约。"""
    redis = MagicMock()
    original_redis = SchedulerManager._redis
    original_is_leader = SchedulerManager._is_leader
    original_is_closing = SchedulerManager._is_closing
    original_tasks = (
        SchedulerManager._sync_listener_task,
        SchedulerManager._sync_task,
        SchedulerManager._reacquire_task,
        SchedulerManager._lock_lost_task,
    )
    SchedulerManager._redis = redis
    SchedulerManager._is_leader = True
    SchedulerManager._is_closing = False
    SchedulerManager._sync_listener_task = None
    SchedulerManager._sync_task = None
    reacquire_task = asyncio.create_task(asyncio.Event().wait())
    SchedulerManager._reacquire_task = reacquire_task
    SchedulerManager._lock_lost_task = None

    try:
        with (
            patch.object(
                SchedulerManager,
                'stop_application_lock_renewal',
                new_callable=AsyncMock,
            ) as stop_renewal,
            patch.object(SchedulerManager._resources, 'dispose'),
            patch('config.scheduler.manager.SchedulerManager._scheduler', running=False),
            patch(
                'config.scheduler.manager.StartupUtil.release_application_leader',
                new=AsyncMock(return_value=True),
            ) as release_application_leader,
        ):
            await SchedulerManager.close_system_scheduler()

        stop_renewal.assert_awaited_once_with()
        release_application_leader.assert_awaited_once_with(
            redis,
            LockConstant.APP_STARTUP_LOCK_KEY,
            SchedulerManager.get_application_lock_owner_token(),
        )
        assert SchedulerManager._redis is None
        assert SchedulerManager._is_leader is False
        assert SchedulerManager._is_closing is True
        assert reacquire_task.cancelled()
    finally:
        SchedulerManager._redis = original_redis
        SchedulerManager._is_leader = original_is_leader
        SchedulerManager._is_closing = original_is_closing
        (
            SchedulerManager._sync_listener_task,
            SchedulerManager._sync_task,
            SchedulerManager._reacquire_task,
            SchedulerManager._lock_lost_task,
        ) = original_tasks


def test_scheduler_lock_lost_callback_revokes_leader_state() -> None:
    """校验租约丢失回调会立即撤销Scheduler leader状态并安排降级清理。"""
    original_is_leader = SchedulerManager._is_leader
    original_lock_lost_task = SchedulerManager._lock_lost_task
    scheduled_task = MagicMock()

    def create_task(coroutine: object) -> MagicMock:
        coroutine.close()
        return scheduled_task

    SchedulerManager._is_leader = True
    SchedulerManager._lock_lost_task = None
    try:
        with patch('config.scheduler.manager.asyncio.create_task', side_effect=create_task) as create_task_mock:
            SchedulerManager.on_lock_lost()

        assert SchedulerManager._is_leader is False
        assert SchedulerManager._lock_lost_task is scheduled_task
        create_task_mock.assert_called_once()
    finally:
        SchedulerManager._is_leader = original_is_leader
        SchedulerManager._lock_lost_task = original_lock_lost_task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('acquire_results', 'activate_results'),
    [
        pytest.param([ConnectionError('redis unavailable'), True], [None], id='redis-failure'),
        pytest.param([True, True], [RuntimeError('restore failed'), None], id='restore-failure'),
    ],
)
async def test_scheduler_reacquires_after_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
    acquire_results: list[bool | Exception],
    activate_results: list[Exception | None],
) -> None:
    """Redis或调度器恢复短暂失败后，继续竞争租约并完成启动。"""
    redis = MagicMock()
    monkeypatch.setattr(SchedulerManager, '_redis', redis)
    monkeypatch.setattr(SchedulerManager, '_is_leader', False)
    monkeypatch.setattr(SchedulerManager, '_is_closing', False)
    monkeypatch.setattr(SchedulerManager, '_reacquire_task', None)
    with (
        patch(
            'config.scheduler.manager.StartupUtil.acquire_application_leader',
            new=AsyncMock(side_effect=acquire_results),
        ) as acquire,
        patch.object(
            SchedulerManager, '_activate_scheduler_as_leader', new=AsyncMock(side_effect=activate_results)
        ) as activate,
        patch.object(
            SchedulerManager, '_get_reacquire_delay', return_value=SchedulerManager._reacquire_interval_seconds
        ),
        patch('config.scheduler.manager.asyncio.sleep', new_callable=AsyncMock) as sleep,
    ):
        await SchedulerManager._run_reacquire_loop()

    assert acquire.await_count == EXPECTED_REACQUIRE_ATTEMPTS
    assert activate.await_args_list == [call(redis)] * len(activate_results)
    assert sleep.await_args_list == [call(SchedulerManager._reacquire_interval_seconds)] * EXPECTED_REACQUIRE_ATTEMPTS
