from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from redis.exceptions import RedisError

from common.constant import LockConstant
from config.get_redis import RedisUtil

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from redis import asyncio as aioredis


@dataclass(frozen=True)
class PluginLifecycleLockResult:
    """
    插件生命周期操作锁获取结果。
    """

    acquired: bool
    message: str = ''


class PluginLifecycleLock(Protocol):
    """
    插件生命周期操作锁接口。
    """

    def lock(self, plugin_id: str, operation: str) -> AsyncIterator[PluginLifecycleLockResult]:
        """
        获取插件生命周期操作锁。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :return: 锁获取结果上下文
        """


class NoopPluginLifecycleLock:
    """
    空插件生命周期锁，用于测试和离线运行时。
    """

    @asynccontextmanager
    async def lock(self, plugin_id: str, operation: str) -> AsyncIterator[PluginLifecycleLockResult]:
        """
        返回已获取锁结果。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :return: 锁获取结果上下文
        """
        yield PluginLifecycleLockResult(acquired=True)


class RedisPluginLifecycleLock:
    """
    基于 Redis 的插件生命周期操作分布式锁。

    插件生命周期操作会写入菜单、任务、配置等共享资源，因此生产环境使用全局锁串行化
    写操作，避免不同插件并发安装/升级时绕过应用层幂等检查。
    """

    _RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    end
    return 0
    """
    _RENEW_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    end
    return 0
    """

    def __init__(self, expire_seconds: int | None = None) -> None:
        """
        初始化 Redis 插件生命周期锁。

        :param expire_seconds: 锁自动过期时间
        :return: None
        """
        self.expire_seconds = expire_seconds or LockConstant.PLUGIN_LIFECYCLE_LOCK_EXPIRE_SECONDS

    @asynccontextmanager
    async def lock(self, plugin_id: str, operation: str) -> AsyncIterator[PluginLifecycleLockResult]:
        """
        获取插件生命周期操作锁。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :return: 锁获取结果上下文
        """
        redis: aioredis.Redis | None = None
        lock_key = self._build_lock_key()
        lock_value = f'{plugin_id}:{operation}:{uuid4()}'
        acquired = False
        renewal_task: asyncio.Task | None = None
        try:
            try:
                redis = await RedisUtil.create_redis_pool(log_enabled=False)
                acquired = bool(await redis.set(lock_key, lock_value, nx=True, ex=self.expire_seconds))
                if not acquired:
                    yield PluginLifecycleLockResult(
                        acquired=False,
                        message='插件生命周期操作正在执行中，请稍后重试',
                    )
                    return
                renewal_task = self._start_lock_renewal(redis, lock_key, lock_value)
            except RedisError as exc:
                yield PluginLifecycleLockResult(
                    acquired=False,
                    message=f'插件生命周期操作锁不可用：{exc}',
                )
                return

            yield PluginLifecycleLockResult(acquired=True)
        finally:
            if redis is not None:
                if renewal_task is not None:
                    renewal_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await renewal_task
                if acquired:
                    with suppress(RedisError):
                        await redis.eval(self._RELEASE_SCRIPT, 1, lock_key, lock_value)
                await redis.close()

    def _start_lock_renewal(
        self,
        redis: aioredis.Redis,
        lock_key: str,
        lock_value: str,
    ) -> asyncio.Task:
        """
        启动生命周期锁续期任务。

        :param redis: Redis 连接对象
        :param lock_key: 锁 key
        :param lock_value: 锁值
        :return: 续期任务
        """
        return asyncio.create_task(self._renew_lock_loop(redis, lock_key, lock_value))

    async def _renew_lock_loop(self, redis: aioredis.Redis, lock_key: str, lock_value: str) -> None:
        """
        周期性续期生命周期锁。

        :param redis: Redis 连接对象
        :param lock_key: 锁 key
        :param lock_value: 锁值
        :return: None
        """
        interval_seconds = self._renew_interval_seconds()
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                renewed = await redis.eval(self._RENEW_SCRIPT, 1, lock_key, lock_value, self.expire_seconds)
                if not renewed:
                    return
            except RedisError:
                continue

    def _renew_interval_seconds(self) -> int:
        """
        计算锁续期间隔。

        :return: 续期间隔秒数
        """
        return max(1, self.expire_seconds // 3)

    @staticmethod
    def _build_lock_key() -> str:
        """
        构建插件生命周期操作锁 key。

        :return: 锁 key
        """
        return f'{LockConstant.PLUGIN_LIFECYCLE_LOCK_PREFIX}:global'
