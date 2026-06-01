from pathlib import Path
from typing import Any

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.lifecycle.seed import PluginSeedRunner
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)

from ..migration_store import PluginDatabaseMigrationHistoryStore


class PluginUpgradeOperationMixin:
    """
    插件升级操作。
    """

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
            await self._record_plugin_failure_state(payload, '插件升级失败')
        if record_operation_log and not dry_run:
            await self._record_plugin_operation_log(payload, dry_run=dry_run, continue_on_error=False)

        return payload

    async def _upgrade_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        升级插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件升级结果负载
        """
        try:
            backend_root = Path(self.runtime_environment.get_backend_dir())
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

            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
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
                    PluginDatabaseMigrationHistoryStore.with_gateway(plugin_service, self.infrastructure_gateway),
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
