from pathlib import Path
from typing import Any

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.lifecycle.seed import PluginSeedRunner
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginRuntimePayloadBuilder,
)

from ..context import PluginRuntimeContextService
from ..dependency_container import PluginRuntimeDependencies
from ..migration_store import PluginDatabaseMigrationHistoryStore
from .operations import PluginLifecycleRuntimeOperations


class PluginUpgradeUseCase:
    """
    插件升级 use case。
    """

    def __init__(
        self,
        dependencies: PluginRuntimeDependencies,
        runtime_operations: PluginLifecycleRuntimeOperations,
        context: PluginRuntimeContextService,
    ) -> None:
        """
        初始化插件升级 use case。

        :param dependencies: 插件运行时依赖容器
        :param runtime_operations: 生命周期工作流所需的运行时协作能力
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.runtime_operations = runtime_operations
        self.context = context

    def _discover_plugins(self, backend_root: Path) -> list[DiscoveredPlugin]:
        """
        发现本地插件。

        :param backend_root: 后端项目根目录
        :return: 已发现插件列表
        """
        return self.context.discover_plugins(backend_root)

    def _get_discovered_plugin_from_list(
        self,
        discovered_plugins: list[DiscoveredPlugin],
        plugin_id: str,
    ) -> DiscoveredPlugin | None:
        """
        从已发现插件列表中查找指定插件。

        :param discovered_plugins: 已发现插件列表
        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin_from_list(discovered_plugins, plugin_id)

    def _build_operation_blocked_payload(
        self,
        discovered_plugin: DiscoveredPlugin,
        operation: str,
        *,
        dry_run: bool | None = None,
    ) -> dict[str, Any] | None:
        """
        构建运行模式阻断负载。

        :param discovered_plugin: 已发现插件
        :param operation: 操作类型
        :param dry_run: 是否预演
        :return: 阻断负载，不阻断时返回 None
        """
        return self.context.build_operation_blocked_payload(discovered_plugin, operation, dry_run=dry_run)

    async def _build_precheck_context(
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
        return await self.context.build_precheck_context(backend_root, discovered_plugin, discovered_plugins)

    async def _load_database_plugin_state(self, plugin_id: str) -> tuple[Any | None, str | None]:
        """
        读取数据库插件状态。

        :param plugin_id: 插件ID
        :return: 数据库插件状态和错误信息
        """
        return await self.context.load_database_plugin_state(plugin_id)

    def _with_plugin_capability(
        self,
        payload: dict[str, Any],
        discovered_plugin: DiscoveredPlugin | None,
    ) -> dict[str, Any]:
        """
        为运行时响应负载附加插件操作能力。

        :param payload: 运行时响应负载
        :param discovered_plugin: 已发现插件
        :return: 附加能力后的响应负载
        """
        return self.context.with_plugin_capability(payload, discovered_plugin)

    async def upgrade_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> dict[str, Any]:
        """
        升级插件并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件升级结果负载
        """
        payload = await self._upgrade_plugin(plugin_id, dry_run=dry_run)
        payload['operation'] = 'upgrade'
        if not dry_run:
            await self.runtime_operations._record_plugin_failure_state(payload, '插件升级失败')
        if record_operation_log and not dry_run:
            await self.runtime_operations._record_plugin_operation_log(
                payload,
                dry_run=dry_run,
                continue_on_error=False,
            )

        return payload

    async def _upgrade_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        升级插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件升级结果负载
        """
        try:
            backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)
            blocked_payload = self._build_operation_blocked_payload(discovered_plugin, 'upgrade', dry_run=dry_run)
            if blocked_payload:
                return blocked_payload

            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            actions = PluginPayloadBuilder.build_upgrade_actions(
                discovered_plugin,
                precheck.dependency_result.ok,
                precheck.plugin_dependency_result.ok,
                precheck.structure_result.ok,
                precheck.menu_conflict_result.ok,
            )
            if dry_run:
                database_plugin, database_error = await self._load_database_plugin_state(plugin_id)
                version_state = PluginPayloadBuilder.build_upgrade_version_state(discovered_plugin, database_plugin)
                payload = PluginPayloadBuilder.build_upgrade_dry_run_payload(
                    plugin_id,
                    {
                        'versionState': version_state,
                        'dependencyResult': precheck.dependency_result,
                        'pluginDependencyResult': precheck.plugin_dependency_result,
                        'structureResult': precheck.structure_result,
                        'menuConflictResult': precheck.menu_conflict_result,
                        'actions': actions,
                        'manifestOk': precheck.manifest_result.ok,
                        'manifestIssues': precheck.manifest_issues,
                        'manifestWarnings': precheck.manifest_warnings,
                        'pluginDependencyErrors': precheck.plugin_dependency_errors,
                        'structureErrors': precheck.structure_errors,
                        'menuConflicts': precheck.menu_conflicts,
                    },
                    database_error=database_error,
                )
                payload['operation'] = 'upgrade'
                return self._with_plugin_capability(payload, discovered_plugin)

            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                database_plugin = await plugin_service.plugin_detail_services(session, plugin_id)
                version_state = PluginPayloadBuilder.build_upgrade_version_state(discovered_plugin, database_plugin)
                blocker_payload = PluginRuntimePayloadBuilder.build_upgrade_pre_execution_blocker(
                    plugin_id,
                    version_state,
                    actions,
                    precheck,
                )
                if blocker_payload:
                    return blocker_payload
                if not version_state['needsUpgrade']:
                    payload = PluginLifecyclePayloadBuilder.build_upgrade_latest_payload(
                        plugin_id,
                        version_state,
                        precheck,
                    )
                    payload['operation'] = 'upgrade'
                    return self._with_plugin_capability(payload, discovered_plugin)
                blocker_payload = PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
                    plugin_id,
                    operation='upgrade',
                    actions=actions,
                    precheck=precheck,
                    extra_payload=version_state,
                )
                if blocker_payload:
                    return blocker_payload

                installed_menu_conflicts = await plugin_service.check_installed_menu_conflict_services(
                    session,
                    discovered_plugin,
                )
                if installed_menu_conflicts:
                    return PluginLifecyclePayloadBuilder.build_installed_menu_conflict_payload(
                        plugin_id,
                        message='插件菜单与已安装菜单存在冲突，升级已中止',
                        actions=actions,
                        precheck=precheck,
                        installed_menu_conflicts=installed_menu_conflicts,
                        extra_payload=version_state,
                    )

                await plugin_service.upsert_discovered_plugin_services(
                    session,
                    discovered_plugin,
                    backend_root / 'plugins',
                    backend_root.parent / 'ruoyi-fastapi-frontend' / 'plugins',
                )
                registry = PluginRegistry.build([discovered_plugin], [database_plugin])
                await plugin_service.install_enabled_plugin_menu_services(session, registry)
                installed_configs = await plugin_service.install_plugin_default_config_services(
                    session,
                    discovered_plugin,
                )
                migration_results = await PluginMigrationRunner(
                    discovered_plugin,
                    PluginDatabaseMigrationHistoryStore.with_model_gateway(
                        plugin_service,
                        self.dependencies.model_gateway,
                    ),
                ).run(session)
                seed_results = await PluginSeedRunner(discovered_plugin).run(session)
                hook_result = await PluginHookRunner(discovered_plugin).run('on_upgrade', query_db=session)
                plugin = await plugin_service.mark_plugin_installed_services(session, discovered_plugin)
                await session.commit()

            payload = PluginLifecyclePayloadBuilder.build_success_payload(
                plugin_id,
                message='插件升级完成',
                actions=actions,
                precheck=precheck,
                plugin=plugin,
                installed_configs=installed_configs,
                migration_results=migration_results,
                seed_results=seed_results,
                hook_result=hook_result,
                extra_payload=version_state,
            )
            payload['operation'] = 'upgrade'
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件升级失败', exc)
