from pathlib import Path
from typing import Any

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.purge import PluginPurgePlan
from plugins.core.runtime.support import PluginPayloadBuilder, PluginRuntimePayloadBuilder
from plugins.core.validation.plugin_deps import PluginBatchOperation


class PluginPrecheckOperationMixin:
    """
    插件操作预检操作。
    """

    async def precheck_plugin_operation(self, plugin_id: str, operation: PluginBatchOperation) -> dict[str, Any]:
        """
        执行插件操作预检。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :return: 插件操作预检负载
        """
        if operation not in ('install', 'enable', 'upgrade', 'uninstall', 'purge'):
            return PluginRuntimePayloadBuilder.build_invalid_operation_payload(
                plugin_id,
                operation,
                message='插件预检操作只支持 install、enable、upgrade、uninstall 或 purge',
            )

        try:
            backend_root = Path(self.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id, operation=operation)

            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            database_plugin, database_error = await self._load_database_plugin_state(plugin_id)
            actions = PluginRuntimePayloadBuilder.build_precheck_actions(operation, discovered_plugin, precheck)
            version_state = PluginPayloadBuilder.build_upgrade_version_state(discovered_plugin, database_plugin)
            purge_plan = await self._build_precheck_purge_plan(discovered_plugin) if operation == 'purge' else None
            payload = PluginRuntimePayloadBuilder.build_precheck_payload(
                plugin_id,
                operation,
                precheck=precheck,
                version_state=version_state,
                actions=actions,
                database_error=database_error,
                purge_plan=purge_plan,
            )
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件操作预检失败', exc)

    async def _build_precheck_purge_plan(self, discovered_plugin: DiscoveredPlugin) -> PluginPurgePlan | None:
        """
        构建插件预检物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划，构建失败时返回 None
        """
        try:
            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
            async with async_session_local() as session:
                return await plugin_service.build_plugin_purge_plan_services(session, discovered_plugin)
        except Exception:
            return None
