from pathlib import Path
from typing import Any

from plugins.core.runtime.support import (
    PluginEnablePayloadBuilder,
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)


class PluginEnableOperationMixin:
    """
    插件启停和安全卸载操作。
    """

    async def set_plugin_enabled(
        self,
        plugin_id: str,
        *,
        enabled: bool,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> dict[str, Any]:
        """
        更新插件启停状态并按需记录审计日志。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件启停结果负载
        """
        payload = await self._set_plugin_enabled(plugin_id, enabled=enabled, dry_run=dry_run)
        if enabled and not dry_run:
            await self._record_plugin_failure_state(payload, '插件启用失败')
        if record_operation_log and not dry_run:
            await self._record_plugin_operation_log(payload, dry_run=dry_run, continue_on_error=False)

        return payload

    async def _set_plugin_enabled(self, plugin_id: str, *, enabled: bool, dry_run: bool = False) -> dict[str, Any]:
        """
        更新插件启停状态。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :return: 插件启停结果负载
        """
        operation = 'enable' if enabled else 'disable'
        try:
            dependency_payload: dict[str, Any] = {}
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if discovered_plugin:
                blocked_payload = self._build_operation_blocked_payload(discovered_plugin, operation, dry_run=dry_run)
                if blocked_payload:
                    return blocked_payload
            if not enabled:
                if dry_run:
                    return PluginEnablePayloadBuilder.build_dry_run_payload(
                        plugin_id,
                        operation=operation,
                        enabled=enabled,
                        dependency_payload=dependency_payload,
                    )

                async_session_local = self.infrastructure_gateway.get_async_session_local()
                plugin_service = self.infrastructure_gateway.get_plugin_service()
                async with async_session_local() as session:
                    response = await plugin_service.update_plugin_enabled_services(session, plugin_id, enabled)
                    if not response.is_success:
                        return PluginEnablePayloadBuilder.build_update_failure_payload(
                            plugin_id,
                            operation=operation,
                            enabled=enabled,
                            message=response.message,
                        )
                    await session.commit()

                return PluginEnablePayloadBuilder.build_success_payload(
                    plugin_id,
                    operation=operation,
                    enabled=enabled,
                    message=response.message,
                    dependency_payload=dependency_payload,
                )

            backend_root = Path(self.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(
                    plugin_id,
                    operation=operation,
                    enabled=enabled,
                    dry_run=dry_run,
                )
            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            actions = PluginPayloadBuilder.build_enabled_actions(enabled, precheck.plugin_dependency_result.ok)
            dependency_payload = PluginEnablePayloadBuilder.build_dependency_payload(precheck.plugin_dependency_result)
            if not dry_run:
                blocker_payload = PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
                    plugin_id,
                    operation=operation,
                    actions=actions,
                    precheck=precheck,
                    extra_payload={'operation': operation, 'enabled': enabled},
                )
                if blocker_payload:
                    return blocker_payload
            if dry_run:
                payload = PluginLifecyclePayloadBuilder.build_operation_dry_run_payload(
                    plugin_id,
                    operation=operation,
                    message='插件启停演练完成，未执行实际写入',
                    actions=actions,
                    precheck=precheck,
                    extra_payload={
                        'enabled': enabled,
                        **dependency_payload,
                    },
                )
                return self._with_plugin_capability(payload, discovered_plugin)

            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
            async with async_session_local() as session:
                response = await plugin_service.update_plugin_enabled_services(session, plugin_id, enabled)
                if not response.is_success:
                    return PluginEnablePayloadBuilder.build_update_failure_payload(
                        plugin_id,
                        operation=operation,
                        enabled=enabled,
                        message=response.message,
                    )
                if enabled:
                    await plugin_service.install_plugin_menu_services(session, discovered_plugin, enabled=True)
                await session.commit()

            payload = PluginEnablePayloadBuilder.build_success_payload(
                plugin_id,
                operation=operation,
                enabled=enabled,
                message=response.message,
                dependency_payload=dependency_payload,
            )
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('更新插件启停状态失败', exc)

    async def uninstall_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> dict[str, Any]:
        """
        安全卸载插件。

        卸载不删除源码和业务数据，但会移除插件菜单及平台菜单归属数据。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件卸载结果负载
        """
        result = await self._uninstall_plugin(plugin_id, dry_run=dry_run)
        result = PluginEnablePayloadBuilder.build_uninstall_payload(result, dry_run=dry_run)
        if record_operation_log and not dry_run:
            await self._record_plugin_operation_log(result, dry_run=dry_run, continue_on_error=False)

        return result

    async def _uninstall_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        标记插件卸载并停用关联运行资源。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件卸载结果负载
        """
        try:
            backend_root = Path(self.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                if dry_run:
                    return PluginEnablePayloadBuilder.build_dry_run_payload(
                        plugin_id,
                        operation='uninstall',
                        enabled=False,
                        dependency_payload={},
                    )
                async_session_local = self.infrastructure_gateway.get_async_session_local()
                plugin_service = self.infrastructure_gateway.get_plugin_service()
                async with async_session_local() as session:
                    response = await plugin_service.mark_plugin_uninstalled_services(session, plugin_id)
                    if not response.is_success:
                        return PluginEnablePayloadBuilder.build_update_failure_payload(
                            plugin_id,
                            operation='uninstall',
                            enabled=False,
                            message=response.message,
                        )
                    await session.commit()

                return PluginEnablePayloadBuilder.build_success_payload(
                    plugin_id,
                    operation='uninstall',
                    enabled=False,
                    message=response.message,
                    dependency_payload={},
                )
            blocked_payload = self._build_operation_blocked_payload(discovered_plugin, 'uninstall', dry_run=dry_run)
            if blocked_payload:
                return blocked_payload
            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            actions = PluginPayloadBuilder.build_enabled_actions(False, True)
            if dry_run:
                payload = PluginLifecyclePayloadBuilder.build_operation_dry_run_payload(
                    plugin_id,
                    operation='uninstall',
                    message='插件卸载演练完成，未执行实际写入',
                    actions=actions,
                    precheck=precheck,
                    extra_payload={
                        'enabled': False,
                    },
                    ok_from_precheck=False,
                )
                return self._with_plugin_capability(payload, discovered_plugin)

            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
            async with async_session_local() as session:
                response = await plugin_service.mark_plugin_uninstalled_services(session, plugin_id)
                if not response.is_success:
                    return PluginEnablePayloadBuilder.build_update_failure_payload(
                        plugin_id,
                        operation='uninstall',
                        enabled=False,
                        message=response.message,
                    )
                await session.commit()

            payload = PluginEnablePayloadBuilder.build_success_payload(
                plugin_id,
                operation='uninstall',
                enabled=False,
                message=response.message,
                dependency_payload={},
            )
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件卸载失败', exc)
