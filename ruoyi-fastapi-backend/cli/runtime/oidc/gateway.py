from importlib import import_module
from typing import Any


class OidcInfrastructureGateway:
    """
    OIDC 基础设施网关

    该对象负责延迟加载 OIDC CLI 所需的数据库、Redis、运行时检查
    与签名密钥管理依赖。
    """

    @staticmethod
    def get_data_source_registry() -> Any:
        """
        获取数据源注册表

        :return: 数据源注册表
        """
        return import_module('config.database').DataSourceRegistry

    @staticmethod
    def get_oidc_config() -> Any:
        """
        获取 OIDC 配置对象

        :return: OIDC 配置对象
        """
        return import_module('config.env').OidcConfig

    @staticmethod
    def get_redis_util() -> Any:
        """
        获取 Redis 工具类

        :return: Redis 工具类
        """
        return import_module('config.get_redis').RedisUtil

    @staticmethod
    def get_runtime_service() -> Any:
        """
        获取 OIDC 运行时服务

        :return: OIDC 运行时服务类
        """
        return import_module('module_identity.service.runtime_service').OidcRuntimeService

    @staticmethod
    def get_key_management_service() -> Any:
        """
        获取 OIDC 签名密钥管理服务

        :return: OIDC 签名密钥管理服务类
        """
        return import_module('module_identity.service.key_service').OidcKeyManagementService
