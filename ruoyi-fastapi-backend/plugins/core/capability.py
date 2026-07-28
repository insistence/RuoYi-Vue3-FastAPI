from dataclasses import dataclass
from typing import Literal

from plugins.core.discovery.scanner import DiscoveredPlugin

PluginOperation = Literal[
    'install',
    'uninstall',
    'enable',
    'disable',
    'upgrade',
    'purge',
    'dependency_install',
    'batch_install',
    'batch_enable',
    'batch_upgrade',
]

STATE_CHANGE_OPERATIONS: set[str] = {
    'install',
    'uninstall',
    'enable',
    'disable',
    'upgrade',
    'purge',
    'dependency_install',
    'batch_install',
    'batch_enable',
    'batch_upgrade',
}

SERVICE_MODE_REASON = (
    '当前为服务运行模式，插件路由、任务和生命周期资源需要重启后激活。请在开发模式或维护窗口中执行插件变更。'
)
BUILT_FRONTEND_REASON = '当前为已构建前端环境，该插件包含前端源码资源，需要在构建前安装依赖并重新构建前端后生效。'


@dataclass(frozen=True)
class PluginRuntimeCapability:
    """
    插件运行时操作能力。
    """

    plugin_id: str
    frontend_mode: str
    backend_runtime_mode: str
    has_frontend_resources: bool
    frontend_build_required: bool
    frontend_runtime_manageable: bool
    backend_runtime_manageable: bool
    runtime_manageable: bool
    blocked_operations: list[str]
    warnings: list[str]

    @property
    def primary_reason(self) -> str:
        """
        获取首个阻断原因。

        :return: 阻断原因
        """
        return self.warnings[0] if self.warnings else ''

    def allows(self, operation: str) -> bool:
        """
        判断指定操作是否允许。

        :param operation: 操作类型
        :return: 是否允许
        """
        return operation not in self.blocked_operations

    def to_payload(self) -> dict[str, object]:
        """
        构建前后端通用能力负载。

        :return: 能力负载
        """
        return {
            'pluginId': self.plugin_id,
            'frontendMode': self.frontend_mode,
            'backendRuntimeMode': self.backend_runtime_mode,
            'hasFrontendResources': self.has_frontend_resources,
            'frontendBuildRequired': self.frontend_build_required,
            'frontendRuntimeManageable': self.frontend_runtime_manageable,
            'backendRuntimeManageable': self.backend_runtime_manageable,
            'runtimeManageable': self.runtime_manageable,
            'blockedOperations': self.blocked_operations,
            'warnings': self.warnings,
            'primaryReason': self.primary_reason,
        }


class PluginRuntimeCapabilityResolver:
    """
    插件运行时能力解析器。
    """

    def __init__(self, *, frontend_mode: str, backend_runtime_mode: str) -> None:
        """
        初始化能力解析器。

        :param frontend_mode: 前端运行模式
        :param backend_runtime_mode: 后端运行模式
        """
        self.frontend_mode = frontend_mode
        self.backend_runtime_mode = backend_runtime_mode

    def resolve(self, discovered_plugin: DiscoveredPlugin) -> PluginRuntimeCapability:
        """
        解析单个插件运行时能力。

        :param discovered_plugin: 已发现插件
        :return: 插件运行时能力
        """
        manifest = discovered_plugin.manifest
        has_frontend_resources = bool(
            manifest.frontend.menus or manifest.dependencies.npm or manifest.dependencies.npm_dev
        )
        frontend_build_required = manifest.frontend.delivery.build_required or has_frontend_resources
        frontend_runtime_manageable = not (
            self.frontend_mode == 'built' and has_frontend_resources and frontend_build_required
        )
        backend_runtime_manageable = self.backend_runtime_mode == 'dev'
        runtime_manageable = frontend_runtime_manageable and backend_runtime_manageable

        warnings = []
        if not backend_runtime_manageable:
            warnings.append(SERVICE_MODE_REASON)
        if not frontend_runtime_manageable:
            warnings.append(BUILT_FRONTEND_REASON)

        blocked_operations: list[str] = []
        if not runtime_manageable:
            blocked_operations = sorted(STATE_CHANGE_OPERATIONS)

        return PluginRuntimeCapability(
            plugin_id=manifest.id,
            frontend_mode=self.frontend_mode,
            backend_runtime_mode=self.backend_runtime_mode,
            has_frontend_resources=has_frontend_resources,
            frontend_build_required=frontend_build_required,
            frontend_runtime_manageable=frontend_runtime_manageable,
            backend_runtime_manageable=backend_runtime_manageable,
            runtime_manageable=runtime_manageable,
            blocked_operations=blocked_operations,
            warnings=warnings,
        )
