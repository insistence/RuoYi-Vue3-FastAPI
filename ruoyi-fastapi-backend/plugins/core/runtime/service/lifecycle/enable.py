from pathlib import Path
from typing import cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.support import (
    PluginEnablePayloadBuilder,
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginRuntimePayloadBuilder,
)

from ..context import PluginRuntimeContextService
from ..dependency_container import PluginRuntimeDependencies
from ..responses import PluginLifecycleResponse, PluginRuntimeBlockedPayloadDict
from .operations import PluginLifecycleRuntimeOperations


class PluginEnableUseCase:
    """
    插件启停和安全卸载 use case。
    """

    def __init__(
        self,
        dependencies: PluginRuntimeDependencies,
        runtime_operations: PluginLifecycleRuntimeOperations,
        context: PluginRuntimeContextService,
    ) -> None:
        """
        初始化插件启停 use case。

        :param dependencies: 插件运行时依赖容器
        :param runtime_operations: 生命周期工作流所需的运行时协作能力
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.runtime_operations = runtime_operations
        self.context = context

    def _get_discovered_plugin(self, plugin_id: str) -> DiscoveredPlugin | None:
        """
        根据插件 ID 获取已发现插件。

        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin(plugin_id)

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
    ) -> PluginRuntimeBlockedPayloadDict | None:
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

    async def _build_enabled_dependents_payload(
        self,
        plugin_id: str,
        discovered_plugins: list[DiscoveredPlugin],
    ) -> dict[str, object]:
        """
        构建已启用依赖方检查负载。

        :param plugin_id: 被停用或卸载的插件ID
        :param discovered_plugins: 已发现插件列表
        :return: 依赖方检查负载
        """
        dependent_result = await self.context.check_enabled_plugin_dependents(plugin_id, discovered_plugins)
        return cast('dict[str, object]', PluginEnablePayloadBuilder.build_dependency_payload(dependent_result))

    async def _disable_plugin(
        self,
        plugin_id: str,
        discovered_plugin: DiscoveredPlugin | None,
        discovered_plugins: list[DiscoveredPlugin],
        *,
        dry_run: bool = False,
    ) -> PluginLifecycleResponse:
        """
        停用插件并在写库前检查已启用依赖方。

        :param plugin_id: 插件ID
        :param discovered_plugin: 已发现插件
        :param discovered_plugins: 已发现插件列表
        :param dry_run: 是否仅预演
        :return: 插件停用结果负载
        """
        operation = 'disable'
        dependency_payload = await self._build_enabled_dependents_payload(plugin_id, discovered_plugins)
        if dry_run:
            payload = PluginEnablePayloadBuilder.build_dry_run_payload(
                plugin_id,
                operation=operation,
                enabled=False,
                dependency_payload=dependency_payload,
            )
            return self._with_plugin_capability(payload, discovered_plugin)
        if not bool(dependency_payload.get('pluginDependencyOk', True)):
            payload = PluginEnablePayloadBuilder.build_dependency_blocker_payload(
                plugin_id,
                operation=operation,
                enabled=False,
                dependency_payload=dependency_payload,
            )
            return self._with_plugin_capability(payload, discovered_plugin)

        gateway = self.dependencies.state_gateway
        async_session_local = gateway.get_async_session_local()
        plugin_service = gateway.get_plugin_service()
        async with async_session_local() as session:
            response = await plugin_service.update_plugin_enabled_services(session, plugin_id, False)
            if not response.is_success:
                return PluginEnablePayloadBuilder.build_update_failure_payload(
                    plugin_id,
                    operation=operation,
                    enabled=False,
                    message=response.message,
                )
            await session.commit()

        payload = PluginEnablePayloadBuilder.build_success_payload(
            plugin_id,
            operation=operation,
            enabled=False,
            message=response.message,
            dependency_payload=dependency_payload,
        )
        return self._with_plugin_capability(payload, discovered_plugin)

    def _with_plugin_capability(
        self,
        payload: PluginLifecycleResponse,
        discovered_plugin: DiscoveredPlugin | None,
    ) -> PluginLifecycleResponse:
        """
        为运行时响应负载附加插件操作能力。

        :param payload: 运行时响应负载
        :param discovered_plugin: 已发现插件
        :return: 附加能力后的响应负载
        """
        return cast(
            'PluginLifecycleResponse',
            self.context.with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
        )

    async def set_plugin_enabled(
        self,
        plugin_id: str,
        *,
        enabled: bool,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        更新插件启停状态并按需记录审计日志。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件启停结果负载
        """
        payload = await self._set_plugin_enabled(plugin_id, enabled=enabled, dry_run=dry_run)
        payload_view = cast('dict[str, object]', payload)
        if enabled and not dry_run:
            await self.runtime_operations.record_plugin_failure_state(payload_view, '插件启用失败')
        if record_operation_log and not dry_run:
            await self.runtime_operations.record_plugin_operation_log(
                payload_view,
                dry_run=dry_run,
                continue_on_error=False,
            )

        return payload

    async def _set_plugin_enabled(
        self, plugin_id: str, *, enabled: bool, dry_run: bool = False
    ) -> PluginLifecycleResponse:
        """
        更新插件启停状态。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :return: 插件启停结果负载
        """
        operation = 'enable' if enabled else 'disable'
        try:
            backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if discovered_plugin:
                blocked_payload = self._build_operation_blocked_payload(discovered_plugin, operation, dry_run=dry_run)
                if blocked_payload:
                    return blocked_payload
            if not enabled:
                return await self._disable_plugin(
                    plugin_id,
                    discovered_plugin,
                    discovered_plugins,
                    dry_run=dry_run,
                )

            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(
                    plugin_id,
                    operation=operation,
                    enabled=enabled,
                    dry_run=dry_run,
                )
            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            actions = PluginPayloadBuilder.build_enabled_actions(enabled, precheck.plugin_dependency_result.ok)
            dependency_payload = cast(
                'dict[str, object]',
                PluginEnablePayloadBuilder.build_dependency_payload(precheck.plugin_dependency_result),
            )
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

            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
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
    ) -> PluginLifecycleResponse:
        """
        安全卸载插件。

        卸载不删除源码和业务数据，但会移除插件菜单及平台菜单归属数据。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件卸载结果负载
        """
        result = await self._uninstall_plugin(plugin_id, dry_run=dry_run)
        result = PluginEnablePayloadBuilder.build_uninstall_payload(cast('dict[str, object]', result), dry_run=dry_run)
        result_view = cast('dict[str, object]', result)
        if record_operation_log and not dry_run:
            await self.runtime_operations.record_plugin_operation_log(
                result_view,
                dry_run=dry_run,
                continue_on_error=False,
            )

        return result

    async def _uninstall_plugin(self, plugin_id: str, *, dry_run: bool = False) -> PluginLifecycleResponse:
        """
        标记插件卸载并停用关联运行资源。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件卸载结果负载
        """
        try:
            backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                dependency_payload = await self._build_enabled_dependents_payload(plugin_id, discovered_plugins)
                if dry_run:
                    return PluginEnablePayloadBuilder.build_dry_run_payload(
                        plugin_id,
                        operation='uninstall',
                        enabled=False,
                        dependency_payload=dependency_payload,
                    )
                if not bool(dependency_payload.get('pluginDependencyOk', True)):
                    return PluginEnablePayloadBuilder.build_dependency_blocker_payload(
                        plugin_id,
                        operation='uninstall',
                        enabled=False,
                        dependency_payload=dependency_payload,
                    )
                gateway = self.dependencies.state_gateway
                async_session_local = gateway.get_async_session_local()
                plugin_service = gateway.get_plugin_service()
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
                    dependency_payload=dependency_payload,
                )
            blocked_payload = self._build_operation_blocked_payload(discovered_plugin, 'uninstall', dry_run=dry_run)
            if blocked_payload:
                return blocked_payload
            dependency_payload = await self._build_enabled_dependents_payload(plugin_id, discovered_plugins)
            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            plugin_dependency_ok = bool(dependency_payload.get('pluginDependencyOk', True))
            actions = PluginPayloadBuilder.build_enabled_actions(False, plugin_dependency_ok)
            if dry_run:
                payload = PluginLifecyclePayloadBuilder.build_operation_dry_run_payload(
                    plugin_id,
                    operation='uninstall',
                    message='插件卸载演练完成，未执行实际写入',
                    actions=actions,
                    precheck=precheck,
                    extra_payload={
                        'enabled': False,
                        **dependency_payload,
                    },
                    ok_from_precheck=False,
                )
                return self._with_plugin_capability(payload, discovered_plugin)
            if not plugin_dependency_ok:
                payload = PluginEnablePayloadBuilder.build_dependency_blocker_payload(
                    plugin_id,
                    operation='uninstall',
                    enabled=False,
                    dependency_payload=dependency_payload,
                )
                return self._with_plugin_capability(payload, discovered_plugin)

            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
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
                dependency_payload=dependency_payload,
            )
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件卸载失败', exc)
