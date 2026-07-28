import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from plugins.core.runtime.service import PluginRuntimeService
from plugins.core.runtime.service.lifecycle_lock import (
    PluginLifecycleLockLost,
    PluginLifecycleLockResult,
    RedisPluginLifecycleLock,
)


class DeniedLifecycleLock:
    """
    测试用拒绝插件生命周期锁。
    """

    def __init__(self) -> None:
        """初始化测试锁。"""
        self.calls: list[tuple[str, str]] = []

    @asynccontextmanager
    async def lock(self, plugin_id: str, operation: str) -> AsyncIterator[PluginLifecycleLockResult]:
        """返回未获取锁结果。"""
        self.calls.append((plugin_id, operation))
        yield PluginLifecycleLockResult(acquired=False, message='插件正在操作中')


class FailingLifecycleLock:
    """
    测试用失败插件生命周期锁。
    """

    @asynccontextmanager
    async def lock(self, plugin_id: str, operation: str) -> AsyncIterator[PluginLifecycleLockResult]:
        """不应被调用的锁。"""
        raise AssertionError('dry_run 不应获取生命周期锁')
        yield PluginLifecycleLockResult(acquired=True)


def test_lifecycle_operation_returns_failure_when_lock_denied() -> None:
    """校验生命周期锁未获取时不会执行真实插件安装。"""
    lifecycle_lock = DeniedLifecycleLock()
    runtime = PluginRuntimeService(lifecycle_lock=lifecycle_lock)
    runtime.install.install_plugin = AsyncMock(return_value={'ok': True, 'message': 'installed'})

    payload = asyncio.run(runtime.install_plugin('demo'))

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['operation'] == 'install'
    assert payload['message'] == '插件正在操作中'
    assert lifecycle_lock.calls == [('demo', 'install')]
    runtime.install.install_plugin.assert_not_awaited()


def test_redis_lifecycle_lock_uses_global_key() -> None:
    """校验 Redis 生命周期锁串行化所有插件写操作。"""
    assert RedisPluginLifecycleLock._build_lock_key() == 'plugin:lifecycle:lock:global'


@pytest.mark.asyncio
async def test_redis_lifecycle_lock_renews_until_lock_lost() -> None:
    """校验 Redis 生命周期锁会在持锁期间续期，并在锁不属于当前持有者时退出续期。"""
    redis = AsyncMock()
    redis.eval = AsyncMock(side_effect=[1, 0])
    lifecycle_lock = RedisPluginLifecycleLock(expire_seconds=3)
    expected_renew_attempts = 2

    with (
        patch('plugins.core.runtime.service.lifecycle_lock.asyncio.sleep', new_callable=AsyncMock) as sleep,
        patch('plugins.core.runtime.service.lifecycle_lock.logger') as mocked_logger,
        pytest.raises(PluginLifecycleLockLost, match='生命周期操作锁已丢失'),
    ):
        await lifecycle_lock._renew_lock_loop(redis, 'plugin:lifecycle:lock:global', 'demo:install:value')

    assert sleep.await_count == expected_renew_attempts
    redis.eval.assert_any_await(
        RedisPluginLifecycleLock._RENEW_SCRIPT,
        1,
        'plugin:lifecycle:lock:global',
        'demo:install:value',
        3,
    )
    mocked_logger.error.assert_called_once_with('❌ 插件生命周期操作锁已丢失，操作已中断')


@pytest.mark.asyncio
async def test_redis_lifecycle_lock_raises_when_renew_fails() -> None:
    """校验 Redis 生命周期锁续期失败时会中断持锁操作。"""
    redis = AsyncMock()
    redis.eval = AsyncMock(side_effect=RedisError('renew failed'))
    lifecycle_lock = RedisPluginLifecycleLock(expire_seconds=3)

    with (
        patch('plugins.core.runtime.service.lifecycle_lock.asyncio.sleep', new_callable=AsyncMock),
        patch('plugins.core.runtime.service.lifecycle_lock.logger') as mocked_logger,
        pytest.raises(PluginLifecycleLockLost, match='续期失败'),
    ):
        await lifecycle_lock._renew_lock_loop(redis, 'plugin:lifecycle:lock:global', 'demo:install:value')

    mocked_logger.error.assert_called_once_with('❌ 插件生命周期操作锁续期失败，操作已中断：renew failed')


@pytest.mark.asyncio
async def test_redis_lifecycle_lock_preserves_body_redis_error() -> None:
    """校验持锁代码块抛 RedisError 时不会被锁获取失败分支吞掉。"""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock(return_value=1)
    redis.close = AsyncMock()
    lifecycle_lock = RedisPluginLifecycleLock(expire_seconds=3)

    with (
        patch('plugins.core.runtime.service.lifecycle_lock.RedisUtil.create_redis_pool', AsyncMock(return_value=redis)),
        patch.object(lifecycle_lock, '_start_lock_renewal', return_value=None),
        pytest.raises(RedisError, match='body failed'),
    ):
        async with lifecycle_lock.lock('demo', 'install') as lock_result:
            assert lock_result.acquired is True
            raise RedisError('body failed')

    redis.eval.assert_awaited_once()
    redis.close.assert_awaited_once()


def test_lifecycle_dry_run_skips_lock() -> None:
    """校验 dry_run 生命周期操作不会获取分布式锁。"""
    runtime = PluginRuntimeService(lifecycle_lock=FailingLifecycleLock())
    runtime.install.install_plugin = AsyncMock(return_value={'ok': True, 'message': 'dry-run'})

    payload = asyncio.run(runtime.install_plugin('demo', dry_run=True))

    assert payload == {'ok': True, 'message': 'dry-run'}
    runtime.install.install_plugin.assert_awaited_once_with(
        'demo',
        dry_run=True,
        record_operation_log=True,
        operated_by=None,
    )
