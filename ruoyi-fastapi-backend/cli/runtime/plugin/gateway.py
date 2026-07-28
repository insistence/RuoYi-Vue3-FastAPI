from importlib import import_module
from typing import Any


class PluginRuntimeGateway:
    """
    插件 CLI 运行时网关。

    该对象负责延迟加载插件核心运行时与管理适配器，避免导入
    `cli.runtime.plugin` 时立即加载 `plugins.core`。
    """

    @staticmethod
    def get_core_runtime_service_class() -> Any:
        """
        获取插件核心运行时服务类。

        :return: 插件核心运行时服务类
        """
        return import_module('plugins.core.runtime.service').PluginRuntimeService

    @staticmethod
    def get_core_runtime_gateway_overrides_class() -> Any:
        """
        获取插件核心运行时窄端口覆盖项类。

        :return: 插件核心运行时窄端口覆盖项类
        """
        return import_module('plugins.core.runtime.service.dependency_container').PluginRuntimeGatewayOverrides

    @staticmethod
    def get_management_runtime_gateway() -> Any:
        """
        获取插件管理运行时适配器。

        :return: 插件管理运行时适配器实例
        """
        gateway_class = import_module('plugins.core.management.service.gateway').PluginManagementRuntimeGateway
        return gateway_class()

    @staticmethod
    def get_core_runtime_environment() -> Any:
        """
        获取插件核心运行时环境服务。

        :return: 插件核心运行时环境服务
        """
        return import_module('plugins.core.environment').PLUGIN_RUNTIME_ENVIRONMENT

    @staticmethod
    def get_core_lifecycle_lock() -> Any:
        """
        获取插件核心生命周期分布式锁。

        :return: 插件核心生命周期分布式锁
        """
        lock_class = import_module('plugins.core.runtime.service.lifecycle_lock').RedisPluginLifecycleLock
        return lock_class()

    @staticmethod
    def build_exception_payload(message: str, exc: Exception) -> dict[str, object]:
        """
        构建插件核心异常负载。

        :param message: 异常场景提示
        :param exc: 异常对象
        :return: 异常负载
        """
        payload_builder = import_module('plugins.core.runtime.support').PluginRuntimePayloadBuilder
        return payload_builder.build_exception_payload(message, exc)
