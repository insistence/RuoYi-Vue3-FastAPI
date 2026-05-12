from importlib import import_module
from types import ModuleType


class AppInfrastructureGateway:
    """
    应用基础设施网关。

    该对象负责延迟加载应用实例构建和环境配置模块，
    供应用运行时 facade 与其协作对象统一复用。
    """

    @staticmethod
    def get_server_module() -> ModuleType:
        """
        获取应用 server 模块。

        :return: server 模块
        """
        return import_module('server')

    @staticmethod
    def get_env_module() -> ModuleType:
        """
        获取环境配置模块。

        :return: 环境配置模块
        """
        return import_module('config.env')
