from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.server_util import StartupUtil

RENEWED_LEASE_SECONDS = 120


class FakeLeaseRedis:
    """支持Application leader租约语义的内存Redis。"""

    def __init__(self) -> None:
        """初始化内存锁状态。"""
        self.values: dict[str, str] = {}
        self.expires: dict[str, int] = {}

    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        """模拟SET NX EX。"""
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expires[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        """读取锁值。"""
        return self.values.get(key)

    async def eval(self, script: str, _key_count: int, key: str, *args: object) -> int:
        """模拟compare-and-expire和compare-and-delete脚本。"""
        owner_token = str(args[0])
        if self.values.get(key) != owner_token:
            return 0
        if 'expire' in script:
            self.expires[key] = int(args[1])
            return 1
        if 'del' in script:
            self.values.pop(key, None)
            self.expires.pop(key, None)
            return 1
        raise AssertionError('unexpected lease script')


def test_application_lock_owner_token_is_stable_in_process_and_unique_between_processes() -> None:
    """校验固定展示worker ID不会成为跨进程共享的锁owner。"""
    original_token = StartupUtil._application_lock_owner_token
    original_pid = StartupUtil._application_lock_owner_pid
    try:
        StartupUtil._application_lock_owner_token = None
        StartupUtil._application_lock_owner_pid = None
        with (
            patch('utils.server_util.os.getpid', return_value=1001),
            patch('utils.server_util.uuid.uuid4', return_value=SimpleNamespace(hex='first')),
        ):
            first = StartupUtil.get_application_lock_owner_token('configured-worker')
            repeated = StartupUtil.get_application_lock_owner_token('configured-worker')

        with (
            patch('utils.server_util.os.getpid', return_value=1002),
            patch('utils.server_util.uuid.uuid4', return_value=SimpleNamespace(hex='second')),
        ):
            second = StartupUtil.get_application_lock_owner_token('configured-worker')

        assert first == repeated
        assert first != second
        assert first == 'configured-worker:1001:first'
        assert second == 'configured-worker:1002:second'
    finally:
        StartupUtil._application_lock_owner_token = original_token
        StartupUtil._application_lock_owner_pid = original_pid


@pytest.mark.asyncio
async def test_application_leader_lease_only_accepts_current_owner() -> None:
    """校验不同owner token无法同时获得同一Application leader租约。"""
    redis = FakeLeaseRedis()

    first_acquired = await StartupUtil.acquire_application_leader(redis, 'app:leader', 'owner-1', 60)
    repeated_acquired = await StartupUtil.acquire_application_leader(redis, 'app:leader', 'owner-1', 60)
    second_acquired = await StartupUtil.acquire_application_leader(redis, 'app:leader', 'owner-2', 60)

    assert first_acquired is True
    assert repeated_acquired is True
    assert second_acquired is False


@pytest.mark.asyncio
async def test_application_leader_renew_and_release_are_owner_safe() -> None:
    """校验非owner不能续期或删除已换主的Application leader租约。"""
    redis = FakeLeaseRedis()
    redis.values['app:leader'] = 'owner-2'
    redis.expires['app:leader'] = 60

    stale_renewed = await StartupUtil.renew_application_leader(
        redis,
        'app:leader',
        'owner-1',
        RENEWED_LEASE_SECONDS,
    )
    stale_released = await StartupUtil.release_application_leader(redis, 'app:leader', 'owner-1')
    owner_renewed = await StartupUtil.renew_application_leader(
        redis,
        'app:leader',
        'owner-2',
        RENEWED_LEASE_SECONDS,
    )

    assert stale_renewed is False
    assert stale_released is False
    assert owner_renewed is True
    assert redis.expires['app:leader'] == RENEWED_LEASE_SECONDS

    owner_released = await StartupUtil.release_application_leader(redis, 'app:leader', 'owner-2')

    assert owner_released is True
    assert 'app:leader' not in redis.values


@pytest.mark.asyncio
async def test_application_leader_renewal_reports_lock_loss() -> None:
    """校验owner不再匹配时续期任务会退出并通知Scheduler降级。"""
    redis = FakeLeaseRedis()
    redis.values['app:leader'] = 'new-owner'
    on_lock_lost = MagicMock()

    renewal_task = StartupUtil.start_application_leader_renewal(
        redis,
        'app:leader',
        'stale-owner',
        RENEWED_LEASE_SECONDS,
        interval_seconds=1,
        on_lock_lost=on_lock_lost,
    )
    await renewal_task

    on_lock_lost.assert_called_once_with()


@pytest.mark.asyncio
async def test_application_leader_renewal_fails_closed_on_redis_error() -> None:
    """校验无法确认续期成功时主动撤销leader身份，不在TTL后继续运行。"""
    redis = MagicMock()
    redis.eval = AsyncMock(side_effect=ConnectionError('redis unavailable'))
    on_lock_lost = MagicMock()

    renewal_task = StartupUtil.start_application_leader_renewal(
        redis,
        'app:leader',
        'owner',
        RENEWED_LEASE_SECONDS,
        interval_seconds=1,
        on_lock_lost=on_lock_lost,
    )
    await renewal_task

    on_lock_lost.assert_called_once_with()
