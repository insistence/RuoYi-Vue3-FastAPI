import asyncio
from pathlib import Path
from time import monotonic

from plugins.core.capability import PluginRuntimeCapability, PluginRuntimeCapabilityResolver
from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import (
    DiscoveredPlugin,
    PluginDiscoveryError,
    PluginDiscoveryResult,
    PluginScanner,
)
from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.lifecycle.precheck import PluginLifecycleScriptPrechecker
from plugins.core.runtime.support import PluginPrecheckContext
from plugins.core.types import PluginStateRecord
from plugins.core.validation.manifest import PluginManifestChecker, PluginManifestCheckResult
from plugins.core.validation.menus import PluginMenuConflictChecker
from plugins.core.validation.plugin_deps import (
    PluginDependencyChecker as InterPluginDependencyChecker,
)
from plugins.core.validation.plugin_deps import (
    PluginDependencyCheckResult,
)
from plugins.core.validation.result import PluginValidationIssue
from plugins.core.validation.structure import PluginStructureChecker
from utils.log_util import logger

from .dependency_container import PluginRuntimeDependencies
from .migration_store import PluginMigrationHistoryGatewayStore
from .responses import PluginRuntimeBlockedPayload, PluginRuntimeBlockedPayloadDict

PLUGIN_DISCOVERY_CACHE_TTL_SECONDS = 2.0
DATABASE_PLUGIN_STATE_SYNC_LOOP_ERROR = '当前事件循环内不能同步读取数据库插件状态，已返回空列表'


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
        self._discovered_plugins_cache: dict[Path, tuple[float, list[DiscoveredPlugin]]] = {}
        self._discovery_errors_cache: dict[Path, list[PluginDiscoveryError]] = {}

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
            return await self.dependencies.state_query_gateway.get_plugin_state(plugin_id), None
        except Exception as exc:
            logger.exception(f'读取数据库插件状态失败：{plugin_id}，{exc}')
            return None, str(exc)

    async def load_database_plugin_states_with_error(self) -> tuple[list[PluginStateRecord], str | None]:
        """
        读取数据库插件状态列表，并保留失败原因。

        :return: 数据库插件状态列表和错误信息
        """
        try:
            return await self.dependencies.state_query_gateway.list_plugin_states(), None
        except Exception as exc:
            logger.exception(f'读取数据库插件状态列表失败：{exc}')
            return [], str(exc)

    async def load_database_plugin_states(self) -> list[PluginStateRecord]:
        """
        读取数据库插件状态列表。

        :return: 数据库插件状态列表
        """
        database_plugins, _database_error = await self.load_database_plugin_states_with_error()
        return database_plugins

    def load_database_plugin_states_sync_with_error(self) -> tuple[list[PluginStateRecord], str | None]:
        """
        以同步方式读取数据库插件状态列表，并保留失败原因。

        :return: 数据库插件状态列表和错误信息
        """
        if not self.has_plugin_dependencies():
            return [], None
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.load_database_plugin_states_with_error())
        logger.warning(DATABASE_PLUGIN_STATE_SYNC_LOOP_ERROR)
        return [], DATABASE_PLUGIN_STATE_SYNC_LOOP_ERROR

    def load_database_plugin_states_sync(self) -> list[PluginStateRecord]:
        """
        以同步方式读取数据库插件状态列表。

        :return: 数据库插件状态列表
        """
        database_plugins, _database_error = self.load_database_plugin_states_sync_with_error()
        return database_plugins

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
        return PluginRuntimeBlockedPayload(
            ok=False,
            status='blocked',
            operation=operation,
            plugin_id=discovered_plugin.manifest.id,
            message='当前环境不允许执行该插件操作',
            suggestion='请在开发模式或维护窗口中执行插件变更，并重启后端或重新构建前端。',
            capability=capability.to_payload(),
            dry_run=dry_run,
            exit_code=1,
        ).to_payload(exclude_none=True)

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

    async def check_enabled_plugin_dependents(
        self,
        plugin_id: str,
        discovered_plugins: list[DiscoveredPlugin],
    ) -> PluginDependencyCheckResult:
        """
        检查指定插件是否仍被已启用插件依赖。

        :param plugin_id: 被停用或卸载的插件ID
        :param discovered_plugins: 全量已发现插件列表
        :return: 被依赖方检查结果
        """
        has_direct_dependents = any(
            dependency.id == plugin_id
            for discovered_plugin in discovered_plugins
            for dependency in discovered_plugin.manifest.dependencies.plugins
        )
        if not has_direct_dependents:
            return PluginDependencyCheckResult(plugin_id=plugin_id, items=[])

        database_plugins = await self.load_database_plugin_states()
        return InterPluginDependencyChecker(discovered_plugins, database_plugins).check_enabled_dependents(plugin_id)

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
        frontend_root = Path(self.dependencies.runtime_environment.get_frontend_dir())
        frontend_plugins_root = Path(self.dependencies.runtime_environment.get_frontend_plugins_dir())
        dependency_result = self.dependencies.dependency_checker.check_manifest(discovered_plugin.manifest)
        manifest_result = PluginManifestChecker(backend_root=backend_root, frontend_root=frontend_root).check(
            discovered_plugin.manifest
        )
        manifest_result = await self._check_lifecycle_scripts(discovered_plugin, manifest_result)
        plugin_dependency_result = await self.check_inter_plugin_dependencies(discovered_plugin, discovered_plugins)
        structure_result = PluginStructureChecker(backend_root, frontend_plugins_root).check(discovered_plugin)
        menu_conflict_result = PluginMenuConflictChecker().check(discovered_plugin, discovered_plugins)

        return PluginPrecheckContext.build(
            dependency_result,
            manifest_result,
            plugin_dependency_result,
            structure_result,
            menu_conflict_result,
        )

    async def _check_lifecycle_scripts(
        self,
        discovered_plugin: DiscoveredPlugin,
        manifest_result: PluginManifestCheckResult,
    ) -> PluginManifestCheckResult:
        """
        检查 migration 历史和 seed 执行计划，并合并到 manifest 预检结果。

        :param discovered_plugin: 当前插件
        :param manifest_result: 原始 manifest 检查结果
        :return: 合并生命周期脚本预检后的 manifest 检查结果
        """
        if not discovered_plugin.manifest.backend.migrations and not discovered_plugin.manifest.backend.seeds:
            return manifest_result
        try:
            migration_runner = PluginMigrationRunner(
                discovered_plugin,
                PluginMigrationHistoryGatewayStore(self.dependencies.migration_history_gateway),
            )
            script_result = await PluginLifecycleScriptPrechecker(discovered_plugin, migration_runner).check(object())
        except Exception as exc:
            logger.exception(f'插件生命周期脚本预检失败：{discovered_plugin.manifest.id}，{exc}')
            return PluginManifestCheckResult(
                plugin_id=manifest_result.plugin_id,
                issues=[
                    *manifest_result.issues,
                    PluginRuntimeContextService._build_lifecycle_script_precheck_issue(exc),
                ],
            )

        return PluginManifestCheckResult(
            plugin_id=manifest_result.plugin_id,
            issues=[*manifest_result.issues, *script_result.issues],
        )

    @staticmethod
    def _build_lifecycle_script_precheck_issue(exc: Exception) -> PluginValidationIssue:
        """
        构建生命周期脚本预检异常问题。

        :param exc: 原始异常
        :return: 统一校验问题
        """
        return PluginValidationIssue(
            level='error',
            category='lifecycle',
            kind='lifecycle_script_precheck_failed',
            path='backend',
            message=f'插件生命周期脚本预检失败：{exc}',
            suggestion='请检查 migration/seed 声明和脚本文件',
        )

    def discover_plugins(self, backend_root: Path) -> list[DiscoveredPlugin]:
        """
        发现本地插件。

        使用容错扫描，单个损坏插件不会影响其他插件。损坏插件的错误明细可通过
        :meth:`get_discovery_errors` 获取。

        :param backend_root: 后端项目根目录
        :return: 已发现插件列表
        """
        return self.discover_plugins_with_errors(backend_root).plugins

    def discover_plugins_with_errors(self, backend_root: Path) -> PluginDiscoveryResult:
        """
        发现本地插件并返回错误明细。

        :param backend_root: 后端项目根目录
        :return: 插件发现结果
        """
        resolved_backend_root = backend_root.resolve()
        cached_entry = self._discovered_plugins_cache.get(resolved_backend_root)
        if cached_entry is not None:
            cached_at, cached_plugins = cached_entry
            if monotonic() - cached_at <= PLUGIN_DISCOVERY_CACHE_TTL_SECONDS:
                cached_errors = self._discovery_errors_cache.get(resolved_backend_root, [])
                return PluginDiscoveryResult(plugins=list(cached_plugins), errors=list(cached_errors))

        discovery_result = PluginScanner(resolved_backend_root / 'plugins').discover_with_errors()
        self._discovered_plugins_cache[resolved_backend_root] = (monotonic(), discovery_result.plugins)
        self._discovery_errors_cache[resolved_backend_root] = list(discovery_result.errors)
        for error in discovery_result.errors:
            logger.warning(f'插件扫描失败，已隔离损坏插件：目录={error.plugin_dir}，错误：{error.error_message}')
        return discovery_result

    def get_discovery_errors(self, backend_root: Path) -> list[PluginDiscoveryError]:
        """
        获取本地插件扫描错误明细。

        :param backend_root: 后端项目根目录
        :return: 扫描错误明细列表
        """
        self.discover_plugins_with_errors(backend_root)
        return list(self._discovery_errors_cache.get(backend_root.resolve(), []))
