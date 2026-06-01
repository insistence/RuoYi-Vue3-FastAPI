import asyncio
from typing import Any

from cli.runtime.base import RUNTIME_ENVIRONMENT, RuntimeEnvironmentService

from .gateway import AppInfrastructureGateway
from .support import AppSnapshotSupport


class AppRuntimeService:
    """
    应用运行时服务。

    该服务作为应用运行时 facade，对外统一暴露应用实例构建、
    应用配置快照与环境信息快照入口。

    :param runtime_environment: 运行时环境服务
    :param infrastructure_gateway: 应用基础设施网关
    :param snapshot_support: 应用快照支持对象
    """

    def __init__(
        self,
        *,
        runtime_environment: RuntimeEnvironmentService | None = None,
        infrastructure_gateway: AppInfrastructureGateway | None = None,
        snapshot_support: AppSnapshotSupport | None = None,
    ) -> None:
        """
        初始化应用运行时服务。

        :param runtime_environment: 运行时环境服务
        :param infrastructure_gateway: 应用基础设施网关
        :param snapshot_support: 应用快照支持对象
        :return: None
        """
        self.runtime_environment = runtime_environment or RUNTIME_ENVIRONMENT
        self.infrastructure_gateway = infrastructure_gateway or AppInfrastructureGateway()
        self.snapshot_support = snapshot_support or AppSnapshotSupport(
            self.infrastructure_gateway,
            self.runtime_environment,
        )

    def build_app_instance(self) -> Any:
        """
        构建当前环境下的 FastAPI 应用实例。

        :return: FastAPI 应用实例
        """
        server_module = self.infrastructure_gateway.get_server_module()
        app = server_module.create_app()
        self._register_application_routers(server_module, app)

        return app

    @staticmethod
    def _register_application_routers(server_module: Any, app: Any) -> None:
        """
        为 CLI 路由查看场景注册应用路由。

        :param server_module: server 模块
        :param app: FastAPI 应用实例
        :return: None
        """
        register_application_routers = getattr(server_module, '_register_application_routers', None)
        if register_application_routers is None:
            return
        asyncio.run(register_application_routers(app))

    def get_app_config_snapshot(self) -> dict[str, Any]:
        """
        读取当前运行环境的应用配置快照。

        :return: 应用配置快照
        """
        return self.snapshot_support.build_app_config_snapshot()

    def get_app_env_snapshot(self) -> dict[str, Any]:
        """
        读取当前 CLI 进程的环境解析结果快照。

        :return: 环境解析结果快照
        """
        return self.snapshot_support.build_app_env_snapshot()


APP_RUNTIME = AppRuntimeService()
