from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from plugins.core.runtime.support import (
    BatchOperationResultPayload,
    PluginBatchReportBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)
from plugins.core.validation.plugin_deps import PluginBatchOperation, PluginDependencyPlanBuilder

if TYPE_CHECKING:
    from collections.abc import Mapping

    from plugins.core.capability import PluginRuntimeCapability
    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.types import PluginStateRecord

    from .context import PluginRuntimeContextService
    from .dependency_container import PluginRuntimeDependencies
    from .responses import PluginBatchResponse, PluginLifecycleResponse, PluginPlanResponse


class PluginBatchRuntimeOperations(Protocol):
    """
    批量工作流所需的运行时协作能力。
    """

    async def install_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        安装插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录操作日志
        :return: 插件安装负载
        """

    async def set_plugin_enabled(
        self,
        plugin_id: str,
        *,
        enabled: bool,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        设置插件启用状态。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录操作日志
        :return: 插件启停负载
        """

    async def upgrade_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        升级插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录操作日志
        :return: 插件升级负载
        """

    async def record_plugin_operation_log(
        self,
        payload: Mapping[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """
        记录插件操作审计日志。

        :param payload: 插件操作结果负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续
        :return: None
        """

    async def execute_batch_plugin_item(
        self,
        operation: PluginBatchOperation,
        plugin_id: str,
    ) -> BatchOperationResultPayload:
        """
        执行单个批量插件操作项。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 单插件操作结果负载
        """


class PluginBatchUseCase:
    """
    插件批量计划和批量执行 use case。
    """

    def __init__(
        self,
        dependencies: PluginRuntimeDependencies,
        runtime_operations: PluginBatchRuntimeOperations,
        context: PluginRuntimeContextService,
    ) -> None:
        """
        初始化插件批量 use case。

        :param dependencies: 插件运行时依赖容器
        :param runtime_operations: 批量工作流所需的运行时协作能力
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

    def _load_database_plugin_states_sync(self) -> list[PluginStateRecord]:
        """
        以同步方式读取数据库插件状态列表。

        :return: 数据库插件状态列表
        """
        return self.context.load_database_plugin_states_sync()

    def _load_database_plugin_states_sync_with_error(self) -> tuple[list[PluginStateRecord], str | None]:
        """
        以同步方式读取数据库插件状态列表，并保留失败原因。

        :return: 数据库插件状态列表和错误信息
        """
        return self.context.load_database_plugin_states_sync_with_error()

    async def _load_database_plugin_states_with_error(self) -> tuple[list[PluginStateRecord], str | None]:
        """
        以异步方式读取数据库插件状态列表，并保留失败原因。

        :return: 数据库插件状态列表和错误信息
        """
        return await self.context.load_database_plugin_states_with_error()

    def _resolve_plugin_capability(self, discovered_plugin: DiscoveredPlugin) -> PluginRuntimeCapability:
        """
        解析插件运行时操作能力。

        :param discovered_plugin: 已发现插件
        :return: 插件运行时能力
        """
        return self.context.resolve_plugin_capability(discovered_plugin)

    def plan_plugins(
        self,
        operation: PluginBatchOperation,
        plugin_ids: list[str] | None = None,
    ) -> PluginPlanResponse:
        """
        生成插件批量操作拓扑计划。

        .. note:: 本方法内部以同步方式读取数据库，禁止在异步上下文中调用，
            异步场景请使用 :meth:`plan_plugins_async`。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :return: 插件批量操作拓扑计划负载
        """
        try:
            database_plugins, database_error = self._load_database_plugin_states_sync_with_error()
            return self._build_plan_plugins_payload(operation, plugin_ids, database_plugins, database_error)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('生成插件批量操作计划失败', exc)

    async def plan_plugins_async(
        self,
        operation: PluginBatchOperation,
        plugin_ids: list[str] | None = None,
    ) -> PluginPlanResponse:
        """
        异步生成插件批量操作拓扑计划。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :return: 插件批量操作拓扑计划负载
        """
        try:
            database_plugins, database_error = await self._load_database_plugin_states_with_error()
            return self._build_plan_plugins_payload(operation, plugin_ids, database_plugins, database_error)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('生成插件批量操作计划失败', exc)

    def _build_plan_plugins_payload(
        self,
        operation: PluginBatchOperation,
        plugin_ids: list[str] | None,
        database_plugins: list[PluginStateRecord],
        database_error: str | None,
    ) -> PluginPlanResponse:
        """
        构建插件批量操作拓扑计划负载。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :param database_plugins: 数据库插件状态列表
        :param database_error: 数据库读取错误
        :return: 插件批量操作拓扑计划负载
        """
        try:
            if operation not in {'install', 'enable', 'upgrade'}:
                return PluginRuntimePayloadBuilder.build_invalid_operation_payload(
                    None,
                    operation,
                    message=f'插件计划操作不支持：{operation}',
                )

            backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            plan = PluginDependencyPlanBuilder(discovered_plugins, database_plugins).build_plan(
                operation,
                plugin_ids,
            )
            payload = PluginPayloadBuilder.build_plan_payload(plan, database_error)
            capability_blockers = self._collect_capability_blockers(
                discovered_plugins,
                operation,
                plugin_ids or plan.requested_plugin_ids,
            )
            if capability_blockers:
                payload['ok'] = False
                payload['message'] = '插件批量操作计划存在环境阻断项'
                payload['capabilityBlockers'] = capability_blockers
            return cast('PluginPlanResponse', payload)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('生成插件批量操作计划失败', exc)

    def _collect_capability_blockers(
        self,
        discovered_plugins: list[DiscoveredPlugin],
        operation: PluginBatchOperation,
        requested_plugin_ids: list[str],
    ) -> list[dict[str, object]]:
        """
        收集插件能力阻断项。

        :param discovered_plugins: 已发现插件列表
        :param operation: 批量操作类型
        :param requested_plugin_ids: 请求的插件ID列表
        :return: 能力阻断项列表
        """
        blocked_operation = f'batch_{operation}'
        target_plugin_ids = set(requested_plugin_ids)
        blockers: list[dict[str, object]] = []
        for discovered_plugin in discovered_plugins:
            if target_plugin_ids and discovered_plugin.manifest.id not in target_plugin_ids:
                continue
            capability = self._resolve_plugin_capability(discovered_plugin)
            if capability.allows(blocked_operation):
                continue
            blockers.append(
                {
                    'pluginId': discovered_plugin.manifest.id,
                    'operation': blocked_operation,
                    'message': capability.primary_reason or '当前环境不允许执行该插件操作',
                    'capability': capability.to_payload(),
                }
            )

        return blockers

    async def batch_plugins(
        self,
        operation: PluginBatchOperation,
        plugin_ids: list[str] | None = None,
        *,
        dry_run: bool = False,
        continue_on_error: bool = False,
    ) -> PluginBatchResponse:
        """
        批量执行插件安装、启用或升级。

        执行前会先生成拓扑计划；当计划存在阻塞项时不会执行任何写操作。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :param dry_run: 是否仅预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量执行结果负载
        """
        try:
            plan_payload = cast('dict[str, object]', await self.plan_plugins_async(operation, plugin_ids))
            if not plan_payload.get('ok', False):
                plan_payload = PluginBatchReportBuilder.build_plan_blocked_payload(
                    plan_payload,
                    dry_run=dry_run,
                    continue_on_error=continue_on_error,
                )
                if not dry_run:
                    await self.runtime_operations.record_plugin_operation_log(
                        plan_payload,
                        dry_run=dry_run,
                        continue_on_error=continue_on_error,
                    )
                return cast('PluginBatchResponse', plan_payload)
            if dry_run:
                return cast(
                    'PluginBatchResponse',
                    PluginBatchReportBuilder.build_dry_run_payload(
                        plan_payload,
                        continue_on_error=continue_on_error,
                    ),
                )

            reports = []
            failed = None
            executable_plugin_ids = PluginBatchReportBuilder.resolve_executable_plugin_ids(plan_payload)
            for plugin_id in executable_plugin_ids:
                report, result = await PluginBatchReportBuilder.run_item(
                    operation,
                    plugin_id,
                    self.runtime_operations.execute_batch_plugin_item,
                )
                reports.append(report)
                if not report.ok:
                    failed = failed or PluginBatchReportBuilder.build_failed_payload(report, result)
                    if not continue_on_error:
                        break

            payload = PluginBatchReportBuilder.build_execution_payload(
                plan_payload,
                reports,
                failed,
                continue_on_error=continue_on_error,
            )
            await self.runtime_operations.record_plugin_operation_log(
                payload,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )

            return cast('PluginBatchResponse', payload)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件批量操作失败', exc)

    async def execute_batch_plugin_item(
        self,
        operation: PluginBatchOperation,
        plugin_id: str,
    ) -> BatchOperationResultPayload:
        """
        执行单个批量插件操作项。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 单插件操作结果负载
        """
        if operation == 'install':
            return cast(
                'BatchOperationResultPayload',
                await self.runtime_operations.install_plugin(plugin_id, dry_run=False, record_operation_log=False),
            )
        if operation == 'enable':
            return cast(
                'BatchOperationResultPayload',
                await self.runtime_operations.set_plugin_enabled(
                    plugin_id,
                    enabled=True,
                    dry_run=False,
                    record_operation_log=False,
                ),
            )
        if operation == 'upgrade':
            return cast(
                'BatchOperationResultPayload',
                await self.runtime_operations.upgrade_plugin(plugin_id, dry_run=False, record_operation_log=False),
            )
        return PluginRuntimePayloadBuilder.build_batch_item_unsupported_payload(operation, plugin_id)
