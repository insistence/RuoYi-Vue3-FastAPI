from pathlib import Path
from typing import Any

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.runtime.health import PluginHealthChecker
from plugins.core.runtime.support import (
    PluginAuditPayloadBuilder,
    PluginConfigPayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginRuntimePayloadBuilder,
)
from plugins.core.validation.manifest import PluginManifestChecker
from plugins.core.validation.menus import PluginMenuConflictChecker
from plugins.core.validation.plugin_deps import (
    PluginDependencyChecker as InterPluginDependencyChecker,
)
from plugins.core.validation.structure import PluginStructureChecker


class PluginQueryOperationMixin:
    """
    插件查询、检查、诊断和健康检查操作。
    """

    def list_plugins(self) -> dict[str, Any]:
        """
        获取本地插件列表。

        :return: 插件列表负载
        """
        try:
            registry = self._build_registry()
            payload = PluginPayloadBuilder.build_plugin_list_payload(registry.list_plugins())
            for item, plugin in zip(payload['plugins'], registry.list_plugins(), strict=False):
                self._with_plugin_capability(item, plugin.discovered_plugin)
            return payload
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('读取插件列表失败', exc)

    def get_plugin_info(self, plugin_id: str) -> dict[str, Any]:
        """
        获取插件详情。

        :param plugin_id: 插件ID
        :return: 插件详情负载
        """
        try:
            registry = self._build_registry()
            plugin = registry.get_plugin(plugin_id)
            if not plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)
            dependency_result = self.dependency_checker.check_manifest(plugin.discovered_plugin.manifest)
            return PluginPayloadBuilder.build_plugin_info_payload(
                plugin,
                dependency_result.items,
                capability=self._resolve_plugin_capability(plugin.discovered_plugin),
            )
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('读取插件详情失败', exc)

    async def get_plugin_info_with_state(self, plugin_id: str) -> dict[str, Any]:
        """
        获取包含数据库状态的插件详情。

        :param plugin_id: 插件ID
        :return: 插件详情负载
        """
        try:
            registry = self._build_registry()
            plugin = registry.get_plugin(plugin_id)
            if not plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)

            database_plugin, database_error = await self._load_database_plugin_state(plugin_id)
            if database_plugin:
                plugin = PluginRegistry.build([plugin.discovered_plugin], [database_plugin]).get_plugin(plugin_id)

            dependency_result = self.dependency_checker.check_manifest(plugin.discovered_plugin.manifest)
            return PluginPayloadBuilder.build_plugin_info_payload(
                plugin,
                dependency_result.items,
                database_error=database_error,
                capability=self._resolve_plugin_capability(plugin.discovered_plugin),
            )
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('读取插件详情失败', exc)

    async def diagnose_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        生成插件诊断包。

        诊断包只读聚合 manifest、依赖检查、结构检查、菜单冲突、配置脱敏快照和审计预留信息。

        :param plugin_id: 插件ID
        :return: 插件诊断包负载
        """
        info_payload = await self.get_plugin_info_with_state(plugin_id)
        if not info_payload.get('ok', False):
            return PluginRuntimePayloadBuilder.build_diagnose_failure_payload(plugin_id, info_payload)

        check_payload = self.check_plugin(plugin_id)
        config_payload = await self.get_plugin_config(plugin_id, reveal_secret=False)
        config_payload['summary'] = PluginConfigPayloadBuilder.build_diagnostic_summary(config_payload.get('configs'))
        audit_payload = await self._build_recent_audit_snapshot(plugin_id)
        discovered_plugin = self._get_discovered_plugin(plugin_id)
        menu_plan = (
            PluginPayloadBuilder.build_menu_diagnostic_plan(discovered_plugin)
            if discovered_plugin
            else PluginRuntimePayloadBuilder.build_empty_menu_plan()
        )

        return PluginRuntimePayloadBuilder.build_diagnose_payload(
            plugin_id,
            info_payload=info_payload,
            check_payload=check_payload,
            menu_plan=menu_plan,
            config_payload=config_payload,
            audit_payload=audit_payload,
        )

    async def _build_recent_audit_snapshot(self, plugin_id: str, *, audit_limit: int = 5) -> dict[str, Any]:
        """
        构建最近审计记录快照。

        :param plugin_id: 插件ID
        :param audit_limit: 最近审计记录数量
        :return: 最近审计记录快照
        """
        try:
            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
            async with async_session_local() as session:
                operation_logs = await plugin_service.get_plugin_operation_log_export_list_services(
                    session,
                    self.infrastructure_gateway.build_operation_log_export_query(
                        export_limit=max(audit_limit * 3, audit_limit),
                    ),
                )
        except Exception as exc:
            return PluginAuditPayloadBuilder.build_recent_snapshot_failure(exc)

        return PluginAuditPayloadBuilder.build_recent_snapshot_payload(
            plugin_id,
            operation_logs,
            audit_limit=audit_limit,
        )

    def check_plugin(self, plugin_id: str | None = None) -> dict[str, Any]:
        """
        检查插件依赖状态。

        :param plugin_id: 插件ID，未传入时检查全部插件
        :return: 插件检查负载
        """
        try:
            backend_root = Path(self.runtime_environment.get_backend_dir())
            registry = self._build_registry()
            plugins = registry.list_plugins()
            if plugin_id:
                plugin = registry.get_plugin(plugin_id)
                if not plugin:
                    return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)
                plugins = [plugin]

            checks = []
            all_discovered_plugins = [plugin.discovered_plugin for plugin in registry.list_plugins()]
            database_plugins = self._load_database_plugin_states_sync()
            plugin_dependency_checker = InterPluginDependencyChecker(all_discovered_plugins, database_plugins)
            for plugin in plugins:
                dependency_result = self.dependency_checker.check_manifest(plugin.discovered_plugin.manifest)
                manifest_result = PluginManifestChecker(backend_root=backend_root).check(
                    plugin.discovered_plugin.manifest
                )
                plugin_dependency_result = plugin_dependency_checker.check_manifest(plugin.discovered_plugin.manifest)
                structure_result = PluginStructureChecker(backend_root).check(plugin.discovered_plugin)
                menu_conflict_result = PluginMenuConflictChecker().check(
                    plugin.discovered_plugin,
                    all_discovered_plugins,
                )
                precheck = PluginPrecheckContext.build(
                    dependency_result,
                    manifest_result,
                    plugin_dependency_result,
                    structure_result,
                    menu_conflict_result,
                )
                check_item = PluginPayloadBuilder.build_check_item(plugin.plugin_id, precheck)
                checks.append(self._with_plugin_capability(check_item, plugin.discovered_plugin))

            return PluginPayloadBuilder.build_check_payload(checks)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件检查失败', exc)

    def check_plugin_dependencies(self, plugin_id: str) -> dict[str, Any]:
        """
        检查插件依赖状态。

        :param plugin_id: 插件ID
        :return: 插件依赖检查负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)

            dependency_result = self.dependency_checker.check_manifest(discovered_plugin.manifest)
            payload = PluginPayloadBuilder.build_dependency_check_payload(plugin_id, dependency_result)
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('检查插件依赖失败', exc)

    async def health_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        执行插件健康检查。

        :param plugin_id: 插件ID
        :return: 插件健康检查负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)

            health_result = await PluginHealthChecker(discovered_plugin).check()
            return PluginRuntimePayloadBuilder.build_health_response_payload(plugin_id, health_result)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件健康检查失败', exc)
