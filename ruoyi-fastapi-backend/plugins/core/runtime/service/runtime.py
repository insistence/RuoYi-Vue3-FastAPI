from plugins.core.validation.dependencies import PluginDependencyChecker

from .audit import PluginAuditOperationMixin
from .batch import PluginBatchOperationMixin
from .config import PluginConfigOperationMixin
from .context import PluginRuntimeContextMixin
from .dependencies import PluginDependencyOperationMixin
from .dependency_container import PluginRuntimeDependencies
from .environment import PLUGIN_RUNTIME_ENVIRONMENT, PluginRuntimeEnvironmentService
from .gateway import DefaultPluginInfrastructureGateway, PluginInfrastructureGateway
from .lifecycle import PluginLifecycleOperationMixin
from .precheck import PluginPrecheckOperationMixin
from .query import PluginQueryOperationMixin
from .tools import PluginToolOperationMixin


class PluginRuntimeService(
    PluginQueryOperationMixin,
    PluginBatchOperationMixin,
    PluginAuditOperationMixin,
    PluginDependencyOperationMixin,
    PluginToolOperationMixin,
    PluginPrecheckOperationMixin,
    PluginLifecycleOperationMixin,
    PluginConfigOperationMixin,
    PluginRuntimeContextMixin,
):
    """
    插件应用运行时服务。

    使用 Facade + Mixin 组合管理插件查询、检查、生命周期、配置、测试和模板等核心能力。
    数据库、VO 和命令执行等外部依赖通过 `PluginInfrastructureGateway` 注入。
    """

    def __init__(
        self,
        *,
        runtime_environment: PluginRuntimeEnvironmentService | None = None,
        dependency_checker: PluginDependencyChecker | None = None,
        infrastructure_gateway: PluginInfrastructureGateway | None = None,
    ) -> None:
        """
        初始化插件应用运行时服务。

        :param runtime_environment: 插件运行时环境服务
        :param dependency_checker: 插件依赖检查器
        :param infrastructure_gateway: 插件基础设施网关
        :return: None
        """
        resolved_environment = runtime_environment or PLUGIN_RUNTIME_ENVIRONMENT
        resolved_dependency_checker = dependency_checker or PluginDependencyChecker(
            frontend_mode=resolved_environment.get_frontend_mode(),
        )
        resolved_gateway = infrastructure_gateway or DefaultPluginInfrastructureGateway()
        self.dependencies = PluginRuntimeDependencies(
            runtime_environment=resolved_environment,
            dependency_checker=resolved_dependency_checker,
            infrastructure_gateway=resolved_gateway,
        )
        self.runtime_environment = self.dependencies.runtime_environment
        self.dependency_checker = self.dependencies.dependency_checker
        self.infrastructure_gateway = self.dependencies.infrastructure_gateway
