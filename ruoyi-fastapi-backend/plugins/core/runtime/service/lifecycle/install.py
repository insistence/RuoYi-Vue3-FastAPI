from pathlib import Path
from typing import Any

from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.lifecycle.seed import PluginSeedRunner
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)

from ..migration_store import PluginDatabaseMigrationHistoryStore


class PluginInstallOperationMixin:
    """
    插件安装操作。
    """

    async def install_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> dict[str, Any]:
        """
        安装插件并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件安装结果负载
        """
        payload = await self._install_plugin(plugin_id, dry_run=dry_run)
        payload['operation'] = 'install'
        if not dry_run:
            await self._record_plugin_failure_state(payload, '插件安装失败')
        if record_operation_log and not dry_run:
            await self._record_plugin_operation_log(payload, dry_run=dry_run, continue_on_error=False)

        return payload

    async def _install_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        安装插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件安装结果负载
        """
        try:
            backend_root = Path(self.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)
            blocked_payload = self._build_operation_blocked_payload(discovered_plugin, 'install', dry_run=dry_run)
            if blocked_payload:
                return blocked_payload

            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            actions = PluginPayloadBuilder.build_install_actions(
                discovered_plugin,
                precheck.dependency_result.ok,
                precheck.plugin_dependency_result.ok,
                precheck.structure_result.ok,
                precheck.menu_conflict_result.ok,
            )
            if dry_run:
                payload = PluginLifecyclePayloadBuilder.build_install_dry_run_payload(plugin_id, actions, precheck)
                payload['operation'] = 'install'
                return self._with_plugin_capability(payload, discovered_plugin)
            blocker_payload = PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
                plugin_id,
                operation='install',
                actions=actions,
                precheck=precheck,
            )
            if blocker_payload:
                return blocker_payload
            dependency_install_payload = self._install_plugin_dependencies_from_result(
                plugin_id,
                precheck.dependency_result,
                dry_run=False,
                discovered_plugin=discovered_plugin,
            )
            if not dependency_install_payload.get('ok', False):
                return PluginLifecyclePayloadBuilder.build_precheck_blocker_payload(
                    plugin_id,
                    message='插件依赖安装失败，安装已中止',
                    actions=actions,
                    precheck=precheck,
                    extra_payload={'dependencyInstall': dependency_install_payload},
                )
            self._refresh_dependency_checker()
            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            dependency_install_payload['postCheck'] = PluginPayloadBuilder.build_dependency_check_payload(
                plugin_id,
                precheck.dependency_result,
            )
            actions = PluginPayloadBuilder.build_install_actions(
                discovered_plugin,
                precheck.dependency_result.ok,
                precheck.plugin_dependency_result.ok,
                precheck.structure_result.ok,
                precheck.menu_conflict_result.ok,
            )
            dependency_blocker_payload = PluginLifecyclePayloadBuilder.build_dependency_blocker_payload(
                plugin_id,
                actions=actions,
                precheck=precheck,
                dependency_install_payload=dependency_install_payload,
            )
            if dependency_blocker_payload:
                return dependency_blocker_payload

            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
            async with async_session_local() as session:
                installed_menu_conflicts = await plugin_service.check_installed_menu_conflict_services(
                    session,
                    discovered_plugin,
                )
                if installed_menu_conflicts:
                    return PluginLifecyclePayloadBuilder.build_installed_menu_conflict_payload(
                        plugin_id,
                        message='插件菜单与已安装菜单存在冲突，安装已中止',
                        actions=actions,
                        precheck=precheck,
                        installed_menu_conflicts=installed_menu_conflicts,
                    )
                plugin = await plugin_service.upsert_discovered_plugin_services(
                    session,
                    discovered_plugin,
                    backend_root / 'plugins',
                    backend_root.parent / 'ruoyi-fastapi-frontend' / 'plugins',
                )
                plugin_enabled = getattr(plugin, 'enabled', '0') == '0'
                await plugin_service.install_plugin_menu_services(session, discovered_plugin, enabled=plugin_enabled)
                installed_configs = await plugin_service.install_plugin_default_config_services(
                    session,
                    discovered_plugin,
                )
                migration_results = await PluginMigrationRunner(
                    discovered_plugin,
                    PluginDatabaseMigrationHistoryStore.with_gateway(plugin_service, self.infrastructure_gateway),
                ).run(session)
                seed_results = await PluginSeedRunner(discovered_plugin).run(session)
                hook_result = await PluginHookRunner(discovered_plugin).run('on_install', query_db=session)
                plugin = await plugin_service.mark_plugin_installed_services(session, discovered_plugin)
                await session.commit()

            payload = PluginLifecyclePayloadBuilder.build_success_payload(
                plugin_id,
                message='插件安装完成',
                actions=actions,
                precheck=precheck,
                plugin=plugin,
                installed_configs=installed_configs,
                migration_results=migration_results,
                seed_results=seed_results,
                hook_result=hook_result,
                extra_payload={'dependencyInstall': dependency_install_payload},
            )
            payload['operation'] = 'install'
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件安装失败', exc)
