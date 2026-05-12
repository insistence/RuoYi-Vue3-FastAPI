from importlib import import_module
from typing import Any

REDIS_TTL_KEY_NOT_FOUND = -2
REDIS_TTL_PERSISTENT = -1


class CacheInfrastructureGateway:
    """
    缓存基础设施网关。

    该对象负责延迟加载 Redis 相关基础设施依赖，
    供缓存运行时 facade 和其协作对象统一复用。
    """

    @staticmethod
    def get_redis_error_class() -> type[Exception]:
        """
        获取 Redis 异常类型。

        :return: Redis 异常类型
        """
        return import_module('redis.exceptions').RedisError

    @staticmethod
    def get_redis_init_key_config() -> Any:
        """
        获取系统缓存初始化键枚举。

        :return: 缓存初始化键枚举
        """
        return import_module('common.enums').RedisInitKeyConfig

    @staticmethod
    def get_redis_util() -> Any:
        """
        获取 Redis 工具类。

        :return: Redis 工具类
        """
        return import_module('config.get_redis').RedisUtil
