import asyncio
from pathlib import Path

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.runtime.capability import PluginRuntimeCapability, PluginRuntimeCapabilityResolver
from plugins.core.runtime.support import PluginPrecheckContext
from plugins.core.types import PluginStateRecord
from plugins.core.validation.manifest import PluginManifestChecker
from plugins.core.validation.menus import PluginMenuConflictChecker
from plugins.core.validation.plugin_deps import (
    PluginDependencyChecker as InterPluginDependencyChecker,
)
from plugins.core.validation.plugin_deps import (
    PluginDependencyCheckResult,
)
from plugins.core.validation.structure import PluginStructureChecker

from .dependency_container import PluginRuntimeDependencies
from .responses import PluginRuntimeBlockedPayloadDict


class PluginRuntimeContextService:
    """
    插件应用运行时上下文服务。

    集中提供插件发现、注册表构建、数据库状态读取和预检上下文构建能力，
    让 runtime facade 和组合式 use case 只关注插件操作编排。
    """

    def __init__(self, dependencies: PluginRuntimeDependencies) -> None:
        """
        初始化插件运行时上下文服务。

        :param dependencies: 插件运行时依赖容器
        """
        self.dependencies = dependencies

    def build_registry(self) -> PluginRegistry:
        """
        构建本地插件注册表。

        :return: 插件注册表
        """
        backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        return PluginRegistry.build(self.discover_plugins(backend_root))

    def get_discovered_plugin(self, plugin_id: str) -> DiscoveredPlugin | None:
        """
        根据插件 ID 获取已发现插件。

        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        return self.get_discovered_plugin_from_list(self.discover_plugins(backend_root), plugin_id)

    @staticmethod
    def get_discovered_plugin_from_list(
        discovered_plugins: list[DiscoveredPlugin],
        plugin_id: str,
    ) -> DiscoveredPlugin | None:
        """
        从已发现插件列表中查找指定插件。

        :param discovered_plugins: 已发现插件列表
        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        for discovered_plugin in discovered_plugins:
            if discovered_plugin.manifest.id == plugin_id:
                return discovered_plugin

        return None

    async def load_database_plugin_state(self, plugin_id: str) -> tuple[PluginStateRecord | None, str | None]:
        """
        读取数据库插件状态。

        :param plugin_id: 插件ID
        :return: 数据库插件状态和错误信息
        """
        try:
            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                return await plugin_service.plugin_detail_services(session, plugin_id), None
        except Exception as exc:
            return None, str(exc)

    async def load_database_plugin_states(self) -> list[PluginStateRecord]:
        """
        读取数据库插件状态列表。

        :return: 数据库插件状态列表
        """
        try:
            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                return await plugin_service.get_plugin_list_services(session)
        except Exception:
            return []

    def load_database_plugin_states_sync(self) -> list[PluginStateRecord]:
        """
        以同步方式读取数据库插件状态列表。

        :return: 数据库插件状态列表
        """
        if not self.has_plugin_dependencies():
            return []
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.load_database_plugin_states())
        return []

    def has_plugin_dependencies(self) -> bool:
        """
        判断当前本地插件是否声明了插件间依赖。

        :return: 是否存在插件间依赖声明
        """
        backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        return any(plugin.manifest.dependencies.plugins for plugin in self.discover_plugins(backend_root))

    def resolve_plugin_capability(self, discovered_plugin: DiscoveredPlugin) -> PluginRuntimeCapability:
        """
        解析插件运行时操作能力。

        :param discovered_plugin: 已发现插件
        :return: 插件运行时能力
        """
        return PluginRuntimeCapabilityResolver(
            frontend_mode=self.dependencies.runtime_environment.get_frontend_mode(),
            backend_runtime_mode=self.dependencies.runtime_environment.get_backend_runtime_mode(),
        ).resolve(discovered_plugin)

    def with_plugin_capability(
        self,
        payload: dict[str, object],
        discovered_plugin: DiscoveredPlugin | None,
    ) -> dict[str, object]:
        """
        为运行时响应负载附加插件操作能力。

        :param payload: 运行时响应负载
        :param discovered_plugin: 已发现插件
        :return: 附加能力后的响应负载
        """
        if discovered_plugin:
            payload['capability'] = self.resolve_plugin_capability(discovered_plugin).to_payload()
        return payload

    def build_operation_blocked_payload(
        self,
        discovered_plugin: DiscoveredPlugin,
        operation: str,
        *,
        dry_run: bool | None = None,
    ) -> PluginRuntimeBlockedPayloadDict | None:
        """
        构建运行模式阻断负载。

        :param discovered_plugin: 已发现插件
        :param operation: 操作类型
        :param dry_run: 是否预演
        :return: 阻断负载，不阻断时返回 None
        """
        capability = self.resolve_plugin_capability(discovered_plugin)
        if capability.allows(operation):
            return None
        payload: PluginRuntimeBlockedPayloadDict = {
            'ok': False,
            'status': 'blocked',
            'operation': operation,
            'pluginId': discovered_plugin.manifest.id,
            'message': '当前环境不允许执行该插件操作',
            'suggestion': '请在开发模式或维护窗口中执行插件变更，并重启后端或重新构建前端。',
            'capability': capability.to_payload(),
            'exit_code': 1,
        }
        if dry_run is not None:
            payload['dryRun'] = dry_run
        return payload

    async def check_inter_plugin_dependencies(
        self,
        discovered_plugin: DiscoveredPlugin,
        discovered_plugins: list[DiscoveredPlugin],
    ) -> PluginDependencyCheckResult:
        """
        检查插件间依赖。

        :param discovered_plugin: 当前已发现插件
        :param discovered_plugins: 全量已发现插件列表
        :return: 插件间依赖检查结果
        """
        if not discovered_plugin.manifest.dependencies.plugins:
            return PluginDependencyCheckResult(plugin_id=discovered_plugin.manifest.id, items=[])
        database_plugins = await self.load_database_plugin_states()
        return InterPluginDependencyChecker(discovered_plugins, database_plugins).check_manifest(
            discovered_plugin.manifest
        )

    async def build_precheck_context(
        self,
        backend_root: Path,
        discovered_plugin: DiscoveredPlugin,
        discovered_plugins: list[DiscoveredPlugin],
    ) -> PluginPrecheckContext:
        """
        构建插件操作预检上下文。

        :param backend_root: 后端项目根目录
        :param discovered_plugin: 当前插件
        :param discovered_plugins: 已发现插件列表
        :return: 插件操作预检上下文
        """
        dependency_result = self.dependencies.dependency_checker.check_manifest(discovered_plugin.manifest)
        manifest_result = PluginManifestChecker(backend_root=backend_root).check(discovered_plugin.manifest)
        plugin_dependency_result = await self.check_inter_plugin_dependencies(discovered_plugin, discovered_plugins)
        structure_result = PluginStructureChecker(backend_root).check(discovered_plugin)
        menu_conflict_result = PluginMenuConflictChecker().check(discovered_plugin, discovered_plugins)

        return PluginPrecheckContext.build(
            dependency_result,
            manifest_result,
            plugin_dependency_result,
            structure_result,
            menu_conflict_result,
        )

    @staticmethod
    def discover_plugins(backend_root: Path) -> list[DiscoveredPlugin]:
        """
        发现本地插件。

        :param backend_root: 后端项目根目录
        :return: 已发现插件列表
        """
        return PluginScanner(backend_root / 'plugins').discover()
