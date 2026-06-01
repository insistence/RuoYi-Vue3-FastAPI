from pathlib import Path
from typing import Any

from plugins.core.runtime.support import (
    PluginBatchReportBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)
from plugins.core.validation.plugin_deps import PluginBatchOperation, PluginDependencyPlanBuilder


class PluginBatchOperationMixin:
    """
    插件批量计划和批量执行操作。
    """

    def plan_plugins(
        self,
        operation: PluginBatchOperation,
        plugin_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        生成插件批量操作拓扑计划。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :return: 插件批量操作拓扑计划负载
        """
        try:
            if operation not in {'install', 'enable', 'upgrade'}:
                return PluginRuntimePayloadBuilder.build_invalid_operation_payload(
                    None,
                    operation,
                    message=f'插件计划操作不支持：{operation}',
                )

            backend_root = Path(self.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            database_plugins = self._load_database_plugin_states_sync()
            plan = PluginDependencyPlanBuilder(discovered_plugins, database_plugins).build_plan(
                operation,
                plugin_ids,
            )
            payload = PluginPayloadBuilder.build_plan_payload(plan)
            blocked_operation = f'batch_{operation}'
            capability_blockers = []
            target_plugin_ids = set(plugin_ids or plan.requested_plugin_ids)
            for discovered_plugin in discovered_plugins:
                if target_plugin_ids and discovered_plugin.manifest.id not in target_plugin_ids:
                    continue
                capability = self._resolve_plugin_capability(discovered_plugin)
                if capability.allows(blocked_operation):
                    continue
                capability_blockers.append(
                    {
                        'pluginId': discovered_plugin.manifest.id,
                        'operation': blocked_operation,
                        'message': capability.primary_reason or '当前环境不允许执行该插件操作',
                        'capability': capability.to_payload(),
                    }
                )
            if capability_blockers:
                payload['ok'] = False
                payload['message'] = '插件批量操作计划存在环境阻断项'
                payload['capabilityBlockers'] = capability_blockers
                payload['exit_code'] = 1
            return payload
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('生成插件批量操作计划失败', exc)

    async def batch_plugins(
        self,
        operation: PluginBatchOperation,
        plugin_ids: list[str] | None = None,
        *,
        dry_run: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
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
            plan_payload = self.plan_plugins(operation, plugin_ids)
            if not plan_payload.get('ok', False):
                plan_payload = PluginBatchReportBuilder.build_plan_blocked_payload(
                    plan_payload,
                    dry_run=dry_run,
                    continue_on_error=continue_on_error,
                )
                if not dry_run:
                    await self._record_plugin_operation_log(
                        plan_payload,
                        dry_run=dry_run,
                        continue_on_error=continue_on_error,
                    )
                return plan_payload
            if dry_run:
                return PluginBatchReportBuilder.build_dry_run_payload(
                    plan_payload,
                    continue_on_error=continue_on_error,
                )

            reports = []
            failed = None
            executable_plugin_ids = PluginBatchReportBuilder.resolve_executable_plugin_ids(plan_payload)
            for plugin_id in executable_plugin_ids:
                report, result = await PluginBatchReportBuilder.run_item(
                    operation,
                    plugin_id,
                    self._execute_batch_plugin_item,
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
            await self._record_plugin_operation_log(
                payload,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )

            return payload
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件批量操作失败', exc)

    async def _execute_batch_plugin_item(self, operation: PluginBatchOperation, plugin_id: str) -> dict[str, Any]:
        """
        执行单个批量插件操作项。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 单插件操作结果负载
        """
        if operation == 'install':
            return await self.install_plugin(plugin_id, dry_run=False, record_operation_log=False)
        if operation == 'enable':
            return await self.set_plugin_enabled(plugin_id, enabled=True, dry_run=False, record_operation_log=False)
        if operation == 'upgrade':
            return await self.upgrade_plugin(plugin_id, dry_run=False, record_operation_log=False)
        return PluginRuntimePayloadBuilder.build_batch_item_unsupported_payload(operation, plugin_id)
