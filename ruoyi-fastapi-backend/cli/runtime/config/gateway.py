from importlib import import_module
from typing import Any


class ConfigInfrastructureGateway:
    """
    参数配置基础设施网关。

    该对象负责延迟加载数据库会话、Redis、DAO、Service 与脱敏工具依赖，
    供参数配置运行时 facade 和其协作对象统一复用。
    """

    @staticmethod
    def get_redis_error_class() -> type[Exception]:
        """
        获取 Redis 异常类型。

        :return: Redis 异常类型
        """
        return import_module('redis.exceptions').RedisError

    @staticmethod
    def get_common_constant() -> Any:
        """
        获取公共常量定义。

        :return: 公共常量定义模块
        """
        return import_module('common.constant').CommonConstant

    @staticmethod
    def get_redis_init_key_config() -> Any:
        """
        获取 Redis 初始化键枚举。

        :return: Redis 初始化键枚举
        """
        return import_module('common.enums').RedisInitKeyConfig

    @staticmethod
    def get_page_model() -> Any:
        """
        获取分页模型类型。

        :return: 分页模型类型
        """
        return import_module('common.vo').PageModel

    @staticmethod
    def get_async_session_local() -> Any:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        """
        return import_module('config.database').AsyncSessionLocal

    @staticmethod
    def get_redis_util() -> Any:
        """
        获取 Redis 工具类。

        :return: Redis 工具类
        """
        return import_module('config.get_redis').RedisUtil

    @staticmethod
    def get_config_dao() -> Any:
        """
        获取参数配置 DAO。

        :return: 参数配置 DAO
        """
        return import_module('module_admin.dao.config_dao').ConfigDao

    @staticmethod
    def get_config_vo_module() -> Any:
        """
        获取参数配置 VO 模块。

        :return: 参数配置 VO 模块
        """
        return import_module('module_admin.entity.vo.config_vo')

    @staticmethod
    def get_config_service() -> Any:
        """
        获取参数配置服务类。

        :return: 参数配置服务类
        """
        return import_module('module_admin.service.config_service').ConfigService

    @staticmethod
    def get_log_sanitizer() -> Any:
        """
        获取日志脱敏工具类。

        :return: 日志脱敏工具类
        """
        return import_module('utils.log_util').LogSanitizer
