from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginEnablePayloadBuilder,
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginPurgePayloadBuilder,
    PluginRuntimePayloadBuilder,
)

from .common import PluginLifecycleUseCaseSupport
from .runner import PluginLifecycleStep, PluginLifecycleStepFailed, PluginLifecycleStepRunner

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.runtime.hooks import PluginHookResult

    from ..context import PluginRuntimeContextService
    from ..dependency_container import PluginRuntimeDependencies
    from ..responses import PluginLifecycleResponse
    from .operations import PluginLifecycleRuntimeOperations


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
    plan: object | None = None
    hook_result: PluginHookResult | None = None
    session: AsyncSession | None = None
    lifecycle_uow: object | None = None
    session_context: object | None = None


class PluginPurgeUseCase(PluginLifecycleUseCaseSupport):
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

    async def purge_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
        operated_by: str | None = None,
    ) -> PluginLifecycleResponse:
        """
        物理清理插件平台元数据并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :param operated_by: 操作者用户名，非预演时写入审计日志
        :return: 插件物理清理结果负载
        """
        payload = await self._purge_plugin(plugin_id, dry_run=dry_run)
        payload_view = cast('dict[str, object]', payload)
        payload_view['operation'] = 'purge'
        if record_operation_log and not dry_run:
            if operated_by is not None:
                payload_view['operatedBy'] = operated_by
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
            if not self._get_discovered_plugin(plugin_id):
                return await self._purge_orphan_plugin_metadata(plugin_id, dry_run=dry_run)
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

    async def _purge_orphan_plugin_metadata(
        self,
        plugin_id: str,
        *,
        dry_run: bool,
    ) -> PluginLifecycleResponse:
        """
        在插件源码缺失时按 ID 清理平台可确认归属的孤儿元数据。

        源码缺失意味着无法执行 onPurge，也无法推断插件业务表和文件资源；
        因此该路径只处理插件状态、菜单、配置、migration 历史和平台托管任务。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件物理清理结果负载
        """
        backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        discovered_plugins = self._discover_plugins(backend_root)
        dependency_payload = await self._build_enabled_dependents_payload(plugin_id, discovered_plugins)
        session_context = self.dependencies.lifecycle_uow_gateway.open_lifecycle_unit_of_work()
        lifecycle_uow = await session_context.__aenter__()
        try:
            plan = await lifecycle_uow.build_plugin_purge_plan_by_id(plugin_id)
            if not any(item.enabled for item in plan.items):
                return PluginPayloadBuilder.build_plugin_not_found_payload(
                    plugin_id,
                    operation='purge',
                    dry_run=dry_run,
                )

            if dry_run:
                payload = PluginPurgePayloadBuilder.build_dry_run_payload(plugin_id, plan)
                payload.update(
                    {
                        'metadataOnly': True,
                        'warnings': ['插件源码不存在，无法执行 onPurge 或清理插件自有业务资源'],
                        **dependency_payload,
                    }
                )
                return cast('PluginLifecycleResponse', payload)

            if not bool(dependency_payload.get('pluginDependencyOk', True)):
                return PluginEnablePayloadBuilder.build_dependency_blocker_payload(
                    plugin_id,
                    operation='purge',
                    enabled=False,
                    dependency_payload=dependency_payload,
                    message='插件仍被已启用插件依赖，孤儿元数据清理已中止',
                )

            await lifecycle_uow.purge_plugin_metadata_by_id(plugin_id)
            await lifecycle_uow.commit()
            payload = PluginPurgePayloadBuilder.build_success_payload(plugin_id, plan, None)
            payload.update(
                {
                    'metadataOnly': True,
                    'warnings': ['插件源码不存在，已跳过 onPurge；插件自有业务资源需人工确认'],
                }
            )
            return cast('PluginLifecycleResponse', payload)
        finally:
            await session_context.__aexit__(None, None, None)

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
        context.session_context = self.dependencies.lifecycle_uow_gateway.open_lifecycle_unit_of_work()
        context.lifecycle_uow = await context.session_context.__aenter__()
        context.session = context.lifecycle_uow.session
        context.plan = await context.lifecycle_uow.build_plugin_purge_plan(
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
        await context.lifecycle_uow.purge_plugin_metadata(context.discovered_plugin)

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
        await context.lifecycle_uow.commit()
        await self._close_purge_session(context)

        return None

    async def _close_purge_session(self, context: PluginPurgeLifecycleContext) -> None:
        """
        关闭物理清理数据库会话。

        :param context: 插件物理清理上下文
        :return: None
        """
        await self._close_lifecycle_session(context)
