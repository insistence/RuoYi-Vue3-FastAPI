from dataclasses import dataclass
from typing import Any

from plugins.core.validation.dependencies import PluginDependencyChecker

from .environment import PluginRuntimeEnvironmentService
from .gateway import PluginInfrastructureGateway


@dataclass(frozen=True)
class PluginRuntimeDependencies:
    """
    插件运行时基础依赖集合。
    """

    runtime_environment: PluginRuntimeEnvironmentService
    dependency_checker: PluginDependencyChecker
    infrastructure_gateway: PluginInfrastructureGateway | Any
