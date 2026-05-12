from contextlib import asynccontextmanager
from typing import Any

from cli.exit_codes import REDIS_ERROR, RUNTIME_ERROR

from .gateway import CacheInfrastructureGateway


class CacheDomainSupport:
    """
    缓存领域支持对象。

    该对象负责缓存名称列表构建、键范围解析和 TTL 结果判定等
    局部缓存规则，避免主运行时服务继续承载细碎领域判断。

    :param infrastructure_gateway: 缓存基础设施网关
    """

    def __init__(self, infrastructure_gateway: CacheInfrastructureGateway) -> None:
        """
        初始化缓存领域支持对象。

        :param infrastructure_gateway: 缓存基础设施网关
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway

    def build_cache_name_items(self) -> list[dict[str, Any]]:
        """
        构建系统内置缓存名称列表。

        :return: 缓存名称列表
        """
        redis_init_key_config = self.infrastructure_gateway.get_redis_init_key_config()
        return [
            {
                'cacheName': key_config.key,
                'remark': key_config.remark,
            }
            for key_config in redis_init_key_config
        ]

    @staticmethod
    def build_full_cache_key(cache_name: str, cache_key: str) -> str:
        """
        构建缓存完整键名。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名
        :return: 完整缓存键名
        """
        return f'{cache_name}:{cache_key}'

    def build_missing_cache_result(self, cache_name: str, cache_key: str) -> dict[str, Any]:
        """
        构建缓存不存在的统一结果。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名
        :return: 缓存不存在结果
        """
        full_cache_key = self.build_full_cache_key(cache_name, cache_key)
        return {
            'ok': False,
            'message': f'缓存不存在：{full_cache_key}',
            'cacheName': cache_name,
            'cacheKey': cache_key,
            'fullCacheKey': full_cache_key,
            'exit_code': RUNTIME_ERROR,
        }

    @staticmethod
    def build_cache_name_pattern(cache_name: str) -> str:
        """
        构建按缓存名称扫描时使用的 Redis 键模式。

        :param cache_name: 缓存名称
        :return: Redis 键匹配模式
        """
        return f'{cache_name}:*'

    @staticmethod
    def extract_cache_key_items(cache_name: str, cache_keys: list[str]) -> list[str]:
        """
        从缓存完整键名列表中提取相对键名。

        :param cache_name: 缓存名称
        :param cache_keys: 完整缓存键名列表
        :return: 相对键名列表
        """
        return [key.split(':', 1)[1] for key in sorted(cache_keys) if key.startswith(f'{cache_name}:')]

    @staticmethod
    def build_clear_scope(
        *,
        cache_name: str,
        cache_key: str,
        clear_all: bool,
    ) -> dict[str, str]:
        """
        构建缓存清理范围定义。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名片段
        :param clear_all: 是否清理全部缓存
        :return: 清理范围定义
        """
        if clear_all:
            return {'mode': 'all'}
        if cache_name:
            return {'mode': 'cacheName', 'cacheName': cache_name}
        return {'mode': 'cacheKey', 'cacheKey': cache_key}


class CacheRedisSupport:
    """
    缓存 Redis 访问支持对象。

    该对象负责 Redis 连接生命周期、错误结果规整和缓存键模式拼装，
    避免主运行时服务继续承载基础设施桥接细节。

    :param infrastructure_gateway: 缓存基础设施网关
    :param domain_support: 缓存领域支持对象
    """

    def __init__(
        self,
        infrastructure_gateway: CacheInfrastructureGateway,
        domain_support: CacheDomainSupport,
    ) -> None:
        """
        初始化缓存 Redis 访问支持对象。

        :param infrastructure_gateway: 缓存基础设施网关
        :param domain_support: 缓存领域支持对象
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway
        self.domain_support = domain_support

    @asynccontextmanager
    async def redis_session(self) -> Any:
        """
        创建并托管 Redis 会话。

        :return: `(redis, redis_util)` 元组
        """
        redis = None
        redis_util = self.infrastructure_gateway.get_redis_util()
        try:
            redis = await redis_util.create_redis_pool(log_enabled=False)
            yield redis, redis_util
        finally:
            if redis is not None:
                await redis.close()

    @staticmethod
    def build_redis_error_result(message: str, exc: Exception) -> dict[str, Any]:
        """
        构建统一 Redis 异常结果。

        :param message: 失败消息
        :param exc: 原始异常
        :return: 标准失败结果
        """
        return {
            'ok': False,
            'message': message,
            'error': str(exc),
            'exit_code': REDIS_ERROR,
        }

    def build_cache_name_keys_pattern(self, cache_name: str) -> str:
        """
        构建按缓存名称读取键列表时使用的模式。

        :param cache_name: 缓存名称
        :return: Redis 键匹配模式
        """
        return self.domain_support.build_cache_name_pattern(cache_name)

    def build_clear_target_pattern(
        self,
        *,
        cache_name: str,
        cache_key: str,
        clear_all: bool,
    ) -> str | None:
        """
        构建缓存清理目标的 Redis 键匹配模式。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名片段
        :param clear_all: 是否清理全部缓存
        :return: Redis 键匹配模式；全部清理时返回 `None`
        """
        if clear_all:
            return None
        if cache_name:
            return self.domain_support.build_cache_name_pattern(cache_name)
        return f'*{cache_key}'
