from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


class RateLimitExceeded(ValueError):
    """
    请求超过 Redis 原子窗口限额
    """

    def __init__(self, retry_after: int) -> None:
        """
        创建限流异常

        :param retry_after: 建议重试等待秒数
        :return: None
        """

        super().__init__('请求过于频繁，请稍后重试')
        self.retry_after = max(1, retry_after)


class RateLimitUnavailable(RuntimeError):
    """
    Redis 限流依赖不可用，调用方必须 fail closed
    """


class OidcRateLimiter:
    """
    认证限流模块服务层
    """

    _SCRIPT = """
local value = redis.call('INCR', KEYS[1])
if value == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {value, ttl}
"""

    @classmethod
    async def enforce(cls, redis: Redis, key: str, *, limit: int, window_seconds: int) -> None:
        """
        原子增加计数，超限或 Redis 故障均不静默放行

        :param redis: Redis 客户端
        :param key: 不含 Token、Secret 或用户名原文的限流 Key
        :param limit: 窗口最大请求数
        :param window_seconds: 窗口秒数
        :return: None
        :raises RateLimitExceeded: 请求超过限额
        :raises RateLimitUnavailable: Redis 执行失败
        """

        try:
            result = await redis.eval(cls._SCRIPT, 1, key, window_seconds)
            count, ttl = int(result[0]), max(1, int(result[1]))
        except Exception as exc:
            raise RateLimitUnavailable('认证限流服务暂不可用') from exc
        if count > limit:
            raise RateLimitExceeded(ttl)


AfterCommitCallback = Callable[[], Awaitable[None]]


class AfterCommitCoordinator:
    """
    提交后副作用协调模块服务层

    ``register`` 只登记闭包，不会执行；生产调用方必须使用 ``commit`` 或
    ``rollback`` 完成事务，避免在数据库事实落盘前修改缓存
    """

    def __init__(self) -> None:
        """
        创建空的提交后回调队列

        :return: None
        """

        self._callbacks: list[AfterCommitCallback] = []
        self._callback_errors: list[Exception] = []

    @property
    def pending_count(self) -> int:
        """
        返回尚未处理的回调数量

        :return: 尚未执行的回调数量
        """

        return len(self._callbacks)

    @property
    def callback_errors(self) -> tuple[Exception, ...]:
        """
        返回已记录的提交后回调异常

        :return: 提交后回调异常元组
        """

        return tuple(self._callback_errors)

    async def register(self, callback: AfterCommitCallback) -> None:
        """
        登记一个只应在数据库提交成功后运行的异步闭包

        :param callback: 不读取可变 ORM 状态的异步副作用闭包
        :return: None
        :raises TypeError: callback 不是可调用对象
        """

        if not callable(callback):
            raise TypeError('事务提交后回调必须为可调用对象')
        self._callbacks.append(callback)

    async def commit(self, db: AsyncSession) -> None:
        """
        先提交数据库，再按登记顺序执行副作用

        :param db: 要提交的异步数据库会话
        :return: None
        :raises Exception: 数据库提交失败
        """

        callbacks, self._callbacks = self._callbacks, []
        try:
            await db.commit()
        except Exception:
            callbacks.clear()
            raise
        for callback in callbacks:
            try:
                await callback()
            except Exception as exc:  # noqa: PERF203
                self._callback_errors.append(exc)
        callbacks.clear()

    async def rollback(self, db: AsyncSession) -> None:
        """
        回滚数据库并丢弃全部提交后副作用

        :param db: 要回滚的异步数据库会话
        :return: None
        """

        self._callbacks.clear()
        await db.rollback()
