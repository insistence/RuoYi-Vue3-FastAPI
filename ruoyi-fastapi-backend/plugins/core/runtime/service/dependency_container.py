from dataclasses import dataclass

from plugins.core.validation.dependencies import PluginDependencyChecker

from .environment import PluginRuntimeEnvironmentService
from .gateway import PluginCommandRunnerGateway, PluginManagementModelGateway, PluginStateGateway


@dataclass(frozen=True)
class PluginRuntimeDependencies:
    """
    插件运行时基础依赖集合。
    """

    runtime_environment: PluginRuntimeEnvironmentService
    dependency_checker: PluginDependencyChecker
    state_gateway: PluginStateGateway
    model_gateway: PluginManagementModelGateway
    command_gateway: PluginCommandRunnerGateway
