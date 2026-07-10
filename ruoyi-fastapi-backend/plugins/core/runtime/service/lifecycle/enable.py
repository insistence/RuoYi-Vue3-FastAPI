from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from plugins.core.runtime.support import (
    PluginEnablePayloadBuilder,
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginRuntimePayloadBuilder,
)

from .common import PluginLifecycleUseCaseSupport
from .runner import PluginLifecycleStep, PluginLifecycleStepFailed, PluginLifecycleStepRunner

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from plugins.core.discovery.scanner import DiscoveredPlugin

    from ..context import PluginRuntimeContextService
    from ..dependency_container import PluginRuntimeDependencies
    from ..responses import PluginLifecycleResponse
    from .operations import PluginLifecycleRuntimeOperations


@dataclass(slots=True)
class PluginEnabledLifecycleContext:
    """
    插件启停声明式生命周期上下文。
    """

    plugin_id: str
    enabled: bool
    dry_run: bool
    operation: str
    backend_root: Path | None = None
    discovered_plugins: list[DiscoveredPlugin] | None = None
    discovered_plugin: DiscoveredPlugin | None = None
    precheck: PluginPrecheckContext | None = None
    actions: list[dict[str, object]] | None = None
    dependency_payload: dict[str, object] | None = None
    response: dict[str, object] | None = None
    session: AsyncSession | None = None
    plugin_service: object | None = None
    session_context: object | None = None


@dataclass(slots=True)
class PluginUninstallLifecycleContext:
    """
    插件卸载声明式生命周期上下文。
    """

    plugin_id: str
    dry_run: bool
    backend_root: Path | None = None
    discovered_plugins: list[DiscoveredPlugin] | None = None
    discovered_plugin: DiscoveredPlugin | None = None
    precheck: PluginPrecheckContext | None = None
    actions: list[dict[str, object]] | None = None
    dependency_payload: dict[str, object] | None = None
    response: dict[str, object] | None = None
    session: AsyncSession | None = None
    plugin_service: object | None = None
    session_context: object | None = None


class PluginEnableUseCase(PluginLifecycleUseCaseSupport):
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
        context = PluginEnabledLifecycleContext(
            plugin_id=plugin_id,
            enabled=False,
            dry_run=dry_run,
            operation='disable',
            discovered_plugin=discovered_plugin,
            discovered_plugins=discovered_plugins,
        )
        try:
            result = await PluginLifecycleStepRunner(self._build_disable_steps()).run(context)
            if result.stop:
                await self._close_enabled_session(result.context)
                return result.stop.payload
            return self._build_enabled_success_payload(result.context)
        except PluginLifecycleStepFailed as exc:
            await self._close_enabled_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '更新插件启停状态失败',
                exc.original_error,
                plugin_id=plugin_id,
                failed_step=exc.step_name,
            )
        except Exception as exc:
            await self._close_enabled_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '更新插件启停状态失败',
                exc,
                plugin_id=plugin_id,
                failed_step='check_enabled_dependents',
            )

    def _build_disable_steps(self) -> list[PluginLifecycleStep[PluginEnabledLifecycleContext]]:
        """
        构建插件停用声明式生命周期步骤。

        :return: 插件停用步骤列表
        """
        return [
            PluginLifecycleStep('check_enabled_dependents', self._enabled_step_check_enabled_dependents),
            PluginLifecycleStep('update_enabled_state', self._enabled_step_update_enabled_state),
        ]

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
        payload_view['operation'] = 'enable' if enabled else 'disable'
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
        context = PluginEnabledLifecycleContext(
            plugin_id=plugin_id,
            enabled=enabled,
            dry_run=dry_run,
            operation=operation,
        )
        try:
            result = await PluginLifecycleStepRunner(self._build_enabled_steps(enabled)).run(context)
            if result.stop:
                await self._close_enabled_session(result.context)
                return result.stop.payload
            if not result.context.enabled:
                return await self._disable_plugin(
                    result.context.plugin_id,
                    result.context.discovered_plugin,
                    result.context.discovered_plugins or [],
                    dry_run=result.context.dry_run,
                )
            return self._build_enabled_success_payload(result.context)
        except PluginLifecycleStepFailed as exc:
            await self._close_enabled_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '更新插件启停状态失败',
                exc.original_error,
                plugin_id=plugin_id,
                failed_step=exc.step_name,
            )
        except Exception as exc:
            await self._close_enabled_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '更新插件启停状态失败',
                exc,
                plugin_id=plugin_id,
                failed_step=f'prepare_{operation}',
            )

    def _build_enabled_steps(self, enabled: bool) -> list[PluginLifecycleStep[PluginEnabledLifecycleContext]]:
        """
        构建插件启停声明式生命周期步骤。

        :param enabled: 是否启用
        :return: 插件启停步骤列表
        """
        steps = [PluginLifecycleStep('discover_plugin', self._enabled_step_discover_plugin)]
        if enabled:
            steps.extend(
                [
                    PluginLifecycleStep('build_precheck', self._enabled_step_build_precheck),
                    PluginLifecycleStep('update_enabled_state', self._enabled_step_update_enabled_state),
                ]
            )

        return steps

    async def _enabled_step_discover_plugin(
        self,
        context: PluginEnabledLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        发现插件并检查运行模式阻断。

        :param context: 插件启停上下文
        :return: 阻断 payload 或 None
        """
        context.backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        context.discovered_plugins = self._discover_plugins(context.backend_root)
        context.discovered_plugin = self._get_discovered_plugin_from_list(
            context.discovered_plugins,
            context.plugin_id,
        )
        if context.discovered_plugin:
            return self._build_operation_blocked_payload(
                context.discovered_plugin,
                context.operation,
                dry_run=context.dry_run,
            )
        if context.enabled:
            return PluginPayloadBuilder.build_plugin_not_found_payload(
                context.plugin_id,
                operation=context.operation,
                enabled=context.enabled,
                dry_run=context.dry_run,
            )

        return None

    async def _enabled_step_build_precheck(
        self,
        context: PluginEnabledLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        构建启用预检。

        :param context: 插件启停上下文
        :return: dry-run 或阻断 payload
        """
        context.precheck = await self._build_precheck_context(
            cast('Path', context.backend_root),
            cast('DiscoveredPlugin', context.discovered_plugin),
            context.discovered_plugins or [],
        )
        context.actions = PluginPayloadBuilder.build_enabled_actions(
            context.enabled,
            context.precheck.plugin_dependency_result.ok,
        )
        context.dependency_payload = cast(
            'dict[str, object]',
            PluginEnablePayloadBuilder.build_dependency_payload(context.precheck.plugin_dependency_result),
        )
        if not context.dry_run:
            return PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
                context.plugin_id,
                operation=context.operation,
                actions=context.actions,
                precheck=context.precheck,
                extra_payload={'operation': context.operation, 'enabled': context.enabled},
            )

        payload = PluginLifecyclePayloadBuilder.build_operation_dry_run_payload(
            context.plugin_id,
            operation=context.operation,
            message='插件启停演练完成，未执行实际写入',
            actions=context.actions,
            precheck=context.precheck,
            extra_payload={
                'enabled': context.enabled,
                **(context.dependency_payload or {}),
            },
        )
        return self._with_plugin_capability(payload, context.discovered_plugin)

    async def _enabled_step_check_enabled_dependents(
        self,
        context: PluginEnabledLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        检查已启用依赖方。

        :param context: 插件启停上下文
        :return: dry-run 或依赖阻断 payload
        """
        context.dependency_payload = await self._build_enabled_dependents_payload(
            context.plugin_id,
            context.discovered_plugins or [],
        )
        if context.dry_run:
            payload = PluginEnablePayloadBuilder.build_dry_run_payload(
                context.plugin_id,
                operation=context.operation,
                enabled=context.enabled,
                dependency_payload=context.dependency_payload,
            )
            return self._with_plugin_capability(payload, context.discovered_plugin)
        if bool(context.dependency_payload.get('pluginDependencyOk', True)):
            return None

        payload = PluginEnablePayloadBuilder.build_dependency_blocker_payload(
            context.plugin_id,
            operation=context.operation,
            enabled=context.enabled,
            dependency_payload=context.dependency_payload,
        )
        return self._with_plugin_capability(payload, context.discovered_plugin)

    async def _enabled_step_update_enabled_state(
        self,
        context: PluginEnabledLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        更新插件启用状态。

        :param context: 插件启停上下文
        :return: 更新失败 payload 或 None
        """
        context.response = await self.dependencies.lifecycle_state_gateway.set_plugin_enabled_state(
            context.plugin_id,
            context.enabled,
            context.discovered_plugin,
        )
        if not context.response.is_success:
            return PluginEnablePayloadBuilder.build_update_failure_payload(
                context.plugin_id,
                operation=context.operation,
                enabled=context.enabled,
                message=context.response.message,
            )

        return None

    def _build_enabled_success_payload(
        self,
        context: PluginEnabledLifecycleContext,
    ) -> PluginLifecycleResponse:
        """
        构建插件启停成功负载。

        :param context: 插件启停上下文
        :return: 插件启停成功负载
        """
        payload = PluginEnablePayloadBuilder.build_success_payload(
            context.plugin_id,
            operation=context.operation,
            enabled=context.enabled,
            message=context.response.message,
            dependency_payload=context.dependency_payload or {},
        )
        return self._with_plugin_capability(payload, context.discovered_plugin)

    async def _close_enabled_session(self, context: PluginEnabledLifecycleContext) -> None:
        """
        关闭插件启停数据库会话。

        :param context: 插件启停上下文
        :return: None
        """
        await self._close_lifecycle_session(context)

    async def uninstall_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
        operated_by: str | None = None,
    ) -> PluginLifecycleResponse:
        """
        安全卸载插件。

        卸载不删除源码和业务数据，但会移除插件菜单及平台菜单归属数据。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :param operated_by: 操作者用户名，非预演时写入审计日志
        :return: 插件卸载结果负载
        """
        result = await self._uninstall_plugin(plugin_id, dry_run=dry_run)
        result = PluginEnablePayloadBuilder.build_uninstall_payload(cast('dict[str, object]', result), dry_run=dry_run)
        result_view = cast('dict[str, object]', result)
        if record_operation_log and not dry_run:
            if operated_by is not None:
                result_view['operatedBy'] = operated_by
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
        context = PluginUninstallLifecycleContext(plugin_id=plugin_id, dry_run=dry_run)
        try:
            result = await PluginLifecycleStepRunner(self._build_uninstall_steps()).run(context)
            if result.stop:
                await self._close_uninstall_session(result.context)
                return result.stop.payload
            return self._build_uninstall_success_payload(result.context)
        except PluginLifecycleStepFailed as exc:
            await self._close_uninstall_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件卸载失败',
                exc.original_error,
                plugin_id=plugin_id,
                failed_step=exc.step_name,
            )
        except Exception as exc:
            await self._close_uninstall_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件卸载失败',
                exc,
                plugin_id=plugin_id,
                failed_step='prepare_uninstall',
            )

    def _build_uninstall_steps(self) -> list[PluginLifecycleStep[PluginUninstallLifecycleContext]]:
        """
        构建插件卸载声明式生命周期步骤。

        :return: 插件卸载步骤列表
        """
        return [
            PluginLifecycleStep('discover_plugin', self._uninstall_step_discover_plugin),
            PluginLifecycleStep('check_enabled_dependents', self._uninstall_step_check_enabled_dependents),
            PluginLifecycleStep('build_precheck', self._uninstall_step_build_precheck),
            PluginLifecycleStep('mark_uninstalled', self._uninstall_step_mark_uninstalled),
        ]

    async def _uninstall_step_discover_plugin(
        self,
        context: PluginUninstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        发现卸载目标插件。

        :param context: 插件卸载上下文
        :return: 阻断 payload 或 None
        """
        context.backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        context.discovered_plugins = self._discover_plugins(context.backend_root)
        context.discovered_plugin = self._get_discovered_plugin_from_list(
            context.discovered_plugins,
            context.plugin_id,
        )
        if not context.discovered_plugin:
            return None

        return self._build_operation_blocked_payload(
            context.discovered_plugin,
            'uninstall',
            dry_run=context.dry_run,
        )

    async def _uninstall_step_check_enabled_dependents(
        self,
        context: PluginUninstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        检查卸载目标的已启用依赖方。

        :param context: 插件卸载上下文
        :return: dry-run 或依赖阻断 payload
        """
        context.dependency_payload = await self._build_enabled_dependents_payload(
            context.plugin_id,
            context.discovered_plugins or [],
        )
        plugin_dependency_ok = bool(context.dependency_payload.get('pluginDependencyOk', True))
        if context.dry_run and not context.discovered_plugin:
            return PluginEnablePayloadBuilder.build_dry_run_payload(
                context.plugin_id,
                operation='uninstall',
                enabled=False,
                dependency_payload=context.dependency_payload,
            )
        if not context.dry_run and not plugin_dependency_ok:
            payload = PluginEnablePayloadBuilder.build_dependency_blocker_payload(
                context.plugin_id,
                operation='uninstall',
                enabled=False,
                dependency_payload=context.dependency_payload,
            )
            return self._with_plugin_capability(payload, context.discovered_plugin)

        return None

    async def _uninstall_step_build_precheck(
        self,
        context: PluginUninstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        构建卸载预检。

        :param context: 插件卸载上下文
        :return: dry-run payload 或 None
        """
        if not context.discovered_plugin:
            return None
        context.precheck = await self._build_precheck_context(
            cast('Path', context.backend_root),
            context.discovered_plugin,
            context.discovered_plugins or [],
        )
        plugin_dependency_ok = bool((context.dependency_payload or {}).get('pluginDependencyOk', True))
        context.actions = PluginPayloadBuilder.build_enabled_actions(False, plugin_dependency_ok)
        if not context.dry_run:
            return None

        payload = PluginLifecyclePayloadBuilder.build_operation_dry_run_payload(
            context.plugin_id,
            operation='uninstall',
            message='插件卸载演练完成，未执行实际写入',
            actions=context.actions,
            precheck=context.precheck,
            extra_payload={
                'enabled': False,
                **(context.dependency_payload or {}),
            },
            ok_from_precheck=False,
        )
        return self._with_plugin_capability(payload, context.discovered_plugin)

    async def _uninstall_step_mark_uninstalled(
        self,
        context: PluginUninstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        标记插件卸载。

        :param context: 插件卸载上下文
        :return: 更新失败 payload 或 None
        """
        context.response = await self.dependencies.lifecycle_state_gateway.mark_plugin_uninstalled_state(
            context.plugin_id,
        )
        if context.response.is_success:
            return None

        return PluginEnablePayloadBuilder.build_update_failure_payload(
            context.plugin_id,
            operation='uninstall',
            enabled=False,
            message=context.response.message,
        )

    def _build_uninstall_success_payload(
        self,
        context: PluginUninstallLifecycleContext,
    ) -> PluginLifecycleResponse:
        """
        构建插件卸载成功负载。

        :param context: 插件卸载上下文
        :return: 插件卸载成功负载
        """
        payload = PluginEnablePayloadBuilder.build_success_payload(
            context.plugin_id,
            operation='uninstall',
            enabled=False,
            message=context.response.message,
            dependency_payload=context.dependency_payload or {},
        )
        return self._with_plugin_capability(payload, context.discovered_plugin)

    async def _close_uninstall_session(self, context: PluginUninstallLifecycleContext) -> None:
        """
        关闭插件卸载数据库会话。

        :param context: 插件卸载上下文
        :return: None
        """
        await self._close_lifecycle_session(context)
