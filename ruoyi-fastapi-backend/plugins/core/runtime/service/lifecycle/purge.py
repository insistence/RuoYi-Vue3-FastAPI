from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginEnablePayloadBuilder,
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginPurgePayloadBuilder,
    PluginRuntimePayloadBuilder,
)

from ..context import PluginRuntimeContextService
from ..dependency_container import PluginRuntimeDependencies
from ..responses import PluginLifecycleResponse, PluginRuntimeBlockedPayloadDict
from .operations import PluginLifecycleRuntimeOperations
from .runner import PluginLifecycleStep, PluginLifecycleStepFailed, PluginLifecycleStepRunner


@dataclass(slots=True)
class PluginPurgeLifecycleContext:
    """
    插件物理清理声明式生命周期上下文。
    """

    plugin_id: str
    dry_run: bool
    backend_root: Path | None = None
    discovered_plugins: list[DiscoveredPlugin] | None = None
    discovered_plugin: DiscoveredPlugin | None = None
    precheck: PluginPrecheckContext | None = None
    dependency_payload: dict[str, object] | None = None
    actions: list[dict[str, object]] | None = None
    plan: Any | None = None
    hook_result: Any | None = None
    session: Any | None = None
    plugin_service: Any | None = None
    session_context: Any | None = None


class PluginPurgeUseCase:
    """
    插件物理清理 use case。
    """

    def __init__(
        self,
        dependencies: PluginRuntimeDependencies,
        runtime_operations: PluginLifecycleRuntimeOperations,
        context: PluginRuntimeContextService,
    ) -> None:
        """
        初始化插件物理清理 use case。

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

    def _discover_plugins(self, backend_root: Path) -> list[DiscoveredPlugin]:
        """
        发现本地插件。

        :param backend_root: 后端项目根目录
        :return: 已发现插件列表
        """
        return self.context.discover_plugins(backend_root)

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

        :param plugin_id: 被物理清理的插件ID
        :param discovered_plugins: 已发现插件列表
        :return: 依赖方检查负载
        """
        dependent_result = await self.context.check_enabled_plugin_dependents(plugin_id, discovered_plugins)
        return cast('dict[str, object]', PluginEnablePayloadBuilder.build_dependency_payload(dependent_result))

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

    async def purge_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        物理清理插件平台元数据并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件物理清理结果负载
        """
        payload = await self._purge_plugin(plugin_id, dry_run=dry_run)
        payload_view = cast('dict[str, object]', payload)
        payload_view['operation'] = 'purge'
        if record_operation_log and not dry_run:
            await self.runtime_operations.record_plugin_operation_log(
                payload_view,
                dry_run=dry_run,
                continue_on_error=False,
            )

        return payload

    async def _purge_plugin(self, plugin_id: str, *, dry_run: bool = False) -> PluginLifecycleResponse:
        """
        物理清理插件平台元数据。

        purge 与 uninstall 语义隔离：uninstall 只停用插件，purge 会删除平台拥有的插件状态、
        菜单关联、配置、migration 历史和插件任务。业务数据只能通过插件显式声明的 on_purge 钩子清理。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件物理清理结果负载
        """
        context = PluginPurgeLifecycleContext(plugin_id=plugin_id, dry_run=dry_run)
        try:
            result = await PluginLifecycleStepRunner(self._build_purge_steps()).run(context)
            if result.stop:
                await self._close_purge_session(result.context)
                return result.stop.payload
            payload = PluginPurgePayloadBuilder.build_success_payload(
                result.context.plugin_id,
                result.context.plan,
                result.context.hook_result,
            )
            return self._with_plugin_capability(payload, result.context.discovered_plugin)
        except PluginLifecycleStepFailed as exc:
            await self._close_purge_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件物理清理失败',
                exc.original_error,
                plugin_id=plugin_id,
                failed_step=exc.step_name,
            )
        except Exception as exc:
            await self._close_purge_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件物理清理失败',
                exc,
                plugin_id=plugin_id,
                failed_step='prepare_purge',
            )

    def _build_purge_steps(self) -> list[PluginLifecycleStep[PluginPurgeLifecycleContext]]:
        """
        构建插件物理清理声明式生命周期步骤。

        :return: 插件物理清理步骤列表
        """
        return [
            PluginLifecycleStep('discover_plugin', self._purge_step_discover_plugin),
            PluginLifecycleStep('discover_plugins', self._purge_step_discover_plugins),
            PluginLifecycleStep('build_precheck', self._purge_step_build_precheck),
            PluginLifecycleStep('check_enabled_dependents', self._purge_step_check_enabled_dependents),
            PluginLifecycleStep('build_purge_plan', self._purge_step_build_purge_plan),
            PluginLifecycleStep('check_purge_blockers', self._purge_step_check_purge_blockers),
            PluginLifecycleStep('run_purge_hook', self._purge_step_run_purge_hook),
            PluginLifecycleStep('purge_metadata', self._purge_step_purge_metadata),
            PluginLifecycleStep('commit', self._purge_step_commit),
        ]

    async def _purge_step_discover_plugin(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        发现物理清理目标插件。

        :param context: 插件物理清理上下文
        :return: 阻断 payload 或 None
        """
        context.discovered_plugin = self._get_discovered_plugin(context.plugin_id)
        if not context.discovered_plugin:
            return PluginPayloadBuilder.build_plugin_not_found_payload(
                context.plugin_id,
                operation='purge',
                dry_run=context.dry_run,
            )

        return self._build_operation_blocked_payload(
            context.discovered_plugin,
            'purge',
            dry_run=context.dry_run,
        )

    async def _purge_step_discover_plugins(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        发现本地插件列表。

        :param context: 插件物理清理上下文
        :return: None
        """
        context.backend_root = context.discovered_plugin.backend_path.parent.parent
        context.discovered_plugins = self._discover_plugins(context.backend_root)

        return None

    async def _purge_step_build_precheck(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        构建物理清理预检。

        :param context: 插件物理清理上下文
        :return: None
        """
        context.precheck = await self._build_precheck_context(
            cast('Path', context.backend_root),
            cast('DiscoveredPlugin', context.discovered_plugin),
            context.discovered_plugins or [],
        )
        context.actions = PluginRuntimePayloadBuilder.build_precheck_actions(
            'purge',
            context.discovered_plugin,
            context.precheck,
        )

        return None

    async def _purge_step_check_enabled_dependents(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        检查物理清理目标的已启用依赖方。

        :param context: 插件物理清理上下文
        :return: None
        """
        context.dependency_payload = await self._build_enabled_dependents_payload(
            context.plugin_id,
            context.discovered_plugins or [],
        )

        return None

    async def _purge_step_build_purge_plan(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        构建物理清理计划。

        :param context: 插件物理清理上下文
        :return: None
        """
        gateway = self.dependencies.state_gateway
        async_session_local = gateway.get_async_session_local()
        context.session_context = async_session_local()
        context.session = await context.session_context.__aenter__()
        context.plugin_service = gateway.get_plugin_service()
        context.plan = await context.plugin_service.build_plugin_purge_plan_services(
            context.session,
            context.discovered_plugin,
        )

        return None

    async def _purge_step_check_purge_blockers(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        检查物理清理 dry-run 和依赖阻断。

        :param context: 插件物理清理上下文
        :return: dry-run 或阻断 payload
        """
        if context.dry_run:
            payload = PluginLifecyclePayloadBuilder.build_operation_dry_run_payload(
                context.plugin_id,
                operation='purge',
                message='插件物理清理演练完成，未执行实际删除',
                actions=context.actions or [],
                precheck=cast('PluginPrecheckContext', context.precheck),
                extra_payload={
                    'safeMode': False,
                    'removesSource': context.plan.removes_source,
                    'plan': PluginPayloadBuilder.build_purge_plan(context.plan),
                    **(context.dependency_payload or {}),
                },
                ok_from_precheck=False,
            )
            return self._with_plugin_capability(payload, context.discovered_plugin)
        if bool((context.dependency_payload or {}).get('pluginDependencyOk', True)):
            return None

        payload = PluginEnablePayloadBuilder.build_dependency_blocker_payload(
            context.plugin_id,
            operation='purge',
            enabled=False,
            dependency_payload=context.dependency_payload or {},
            message='插件仍被已启用插件依赖，物理清理已中止',
        )
        return self._with_plugin_capability(payload, context.discovered_plugin)

    async def _purge_step_run_purge_hook(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        执行物理清理钩子。

        :param context: 插件物理清理上下文
        :return: None
        """
        context.hook_result = await PluginHookRunner(context.discovered_plugin).run(
            'on_purge',
            query_db=context.session,
        )

        return None

    async def _purge_step_purge_metadata(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        清理插件平台元数据。

        :param context: 插件物理清理上下文
        :return: None
        """
        await context.plugin_service.purge_plugin_services(context.session, context.discovered_plugin)

        return None

    async def _purge_step_commit(
        self,
        context: PluginPurgeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        提交物理清理事务。

        :param context: 插件物理清理上下文
        :return: None
        """
        await context.session.commit()
        await self._close_purge_session(context)

        return None

    async def _close_purge_session(self, context: PluginPurgeLifecycleContext) -> None:
        """
        关闭物理清理数据库会话。

        :param context: 插件物理清理上下文
        :return: None
        """
        if context.session_context is None:
            return
        await context.session_context.__aexit__(None, None, None)
        context.session_context = None
        context.session = None
