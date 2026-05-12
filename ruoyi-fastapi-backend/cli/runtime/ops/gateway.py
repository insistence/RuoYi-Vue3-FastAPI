from importlib import import_module
from typing import Any


class OperationsInfrastructureGateway:
    """
    运维基础设施网关。

    该对象负责延迟加载 Redis、调度器、服务器监控与系统工具依赖，
    供运维运行时 facade 和其协作对象统一复用。
    """

    @staticmethod
    def get_redis_util() -> Any:
        """
        获取 Redis 工具类。

        :return: Redis 工具类
        """
        return import_module('config.get_redis').RedisUtil

    @staticmethod
    def get_redis_error_class() -> type[Exception]:
        """
        获取 Redis 异常类型。

        :return: Redis 异常类型
        """
        return import_module('redis.exceptions').RedisError

    @staticmethod
    def get_scheduler_util() -> Any:
        """
        获取调度器工具类。

        :return: 调度器工具类
        """
        return import_module('config.get_scheduler').SchedulerUtil

    @staticmethod
    def get_server_service() -> Any:
        """
        获取服务器监控服务类。

        :return: 服务器监控服务类
        """
        return import_module('module_admin.service.server_service').ServerService

    @staticmethod
    def get_psutil_module() -> Any:
        """
        获取 `psutil` 模块。

        :return: `psutil` 模块
        """
        return import_module('psutil')

    @staticmethod
    def get_bytes2human() -> Any:
        """
        获取字节数转可读文本函数。

        :return: `bytes2human` 函数
        """
        return import_module('utils.common_util').bytes2human
