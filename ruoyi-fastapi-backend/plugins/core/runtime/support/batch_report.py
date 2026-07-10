from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import TypeAlias

from pydantic import Field

from plugins.core.runtime.support.payload.base import PluginPayloadModel
from plugins.core.validation.plugin_deps import PluginBatchOperation


class BatchOperationResult(PluginPayloadModel):
    """
    批量单项运行时结果 payload。
    """

    ok: bool | None = None
    message: str | None = None
    plugin_dependency_errors: object | None = Field(default=None, alias='pluginDependencyErrors')
    structure_errors: object | None = Field(default=None, alias='structureErrors')
    menu_conflicts: object | None = Field(default=None, alias='menuConflicts')
    error: object | None = None


class BatchSummary(PluginPayloadModel):
    """
    批量执行汇总 payload。
    """

    total: int
    succeeded: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class PluginBatchItemReport:
    """
    插件批量执行单项报告。

    :param plugin_id: 插件ID
    :param operation: 批量操作类型
    :param ok: 是否执行成功
    :param status: 执行状态
    :param message: 执行消息
    :param duration_ms: 耗时毫秒数
    :param suggestion: 失败建议
    """

    plugin_id: str
    operation: PluginBatchOperation
    ok: bool
    status: str
    message: str
    duration_ms: int
    suggestion: str


class BatchFailedItem(PluginPayloadModel):
    """
    批量失败项 payload。
    """

    plugin_id: str = Field(alias='pluginId')
    operation: str | None = None
    ok: bool | None = None
    status: str | None = None
    message: str | None = None
    duration_ms: int | None = Field(default=None, alias='durationMs')
    suggestion: str | None = None
    result: dict[str, object]


class PluginBatchRunPayload(PluginPayloadModel):
    """
    插件批量执行响应 payload。
    """

    ok: bool | None = None
    message: str
    operation: str | None = None
    database_available: bool | None = Field(default=None, alias='databaseAvailable')
    database_error: str | None = Field(default=None, alias='databaseError')
    plan: dict[str, object] | None = None
    dry_run: bool = Field(alias='dryRun')
    continue_on_error: bool = Field(alias='continueOnError')
    executed: list[dict[str, object]]
    failed: dict[str, object] | None
    summary: dict[str, object]


BatchOperationResultPayload: TypeAlias = dict[str, object]
BatchSummaryPayload: TypeAlias = dict[str, object]
BatchItemReportPayload: TypeAlias = dict[str, object]
BatchFailedPayload: TypeAlias = dict[str, object]
BatchPlanPayload: TypeAlias = Mapping[str, object]
BatchItemRunner: TypeAlias = Callable[[PluginBatchOperation, str], Awaitable[BatchOperationResultPayload]]


class PluginBatchReportBuilder:
    """
    插件批量执行报告构建器。

    使用 Builder 模式统一生成批量执行单项报告和汇总信息。
    """

    @classmethod
    async def run_item(
        cls,
        operation: PluginBatchOperation,
        plugin_id: str,
        runner: BatchItemRunner,
    ) -> tuple[PluginBatchItemReport, BatchOperationResultPayload]:
        """
        执行单个插件批量操作并构建报告。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :param runner: 异步执行函数
        :return: 单项报告和原始执行结果
        """
        started_at = perf_counter()
        result = await runner(operation, plugin_id)
        duration_ms = int((perf_counter() - started_at) * 1000)
        report = cls.build_item_report(operation, plugin_id, result, duration_ms)

        return report, result

    @classmethod
    def build_item_report(
        cls,
        operation: PluginBatchOperation,
        plugin_id: str,
        result: BatchOperationResultPayload,
        duration_ms: int,
    ) -> PluginBatchItemReport:
        """
        构建单个插件批量操作报告。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :param result: 原始执行结果
        :param duration_ms: 耗时毫秒数
        :return: 单项报告
        """
        ok = bool(result.get('ok', False))

        return PluginBatchItemReport(
            plugin_id=plugin_id,
            operation=operation,
            ok=ok,
            status='success' if ok else 'failed',
            message=str(result.get('message', '-')),
            duration_ms=duration_ms,
            suggestion='' if ok else cls.build_failure_suggestion(operation, plugin_id, result),
        )

    @staticmethod
    def build_summary(reports: list[PluginBatchItemReport], total: int) -> BatchSummaryPayload:
        """
        构建插件批量执行汇总。

        :param reports: 单项报告列表
        :param total: 计划执行总数
        :return: 汇总负载
        """
        failed = len([report for report in reports if not report.ok])
        succeeded = len([report for report in reports if report.ok])

        return BatchSummary(
            total=total,
            succeeded=succeeded,
            failed=failed,
            skipped=max(total - succeeded - failed, 0),
        ).to_payload()

    @staticmethod
    def resolve_executable_plugin_ids(plan_payload: BatchPlanPayload) -> list[str]:
        """
        从批量计划负载中解析实际执行插件 ID。

        计划会展示目标插件的依赖闭包，但执行阶段只执行用户显式请求的插件，避免依赖插件状态影响
        用户本次选择的插件安装或升级。

        :param plan_payload: 插件批量计划负载
        :return: 实际执行插件 ID 列表
        """
        plan = plan_payload.get('plan', {})
        if not isinstance(plan, Mapping):
            return []
        requested_plugin_ids = plan.get('requestedPluginIds')
        ordered_plugin_ids = plan.get('orderedPluginIds')
        if not isinstance(requested_plugin_ids, list) or not requested_plugin_ids:
            return ordered_plugin_ids if isinstance(ordered_plugin_ids, list) else []
        if not isinstance(ordered_plugin_ids, list):
            return requested_plugin_ids

        requested_plugin_id_set = set(requested_plugin_ids)
        return [plugin_id for plugin_id in ordered_plugin_ids if plugin_id in requested_plugin_id_set]

    @classmethod
    def build_plan_blocked_payload(
        cls,
        plan_payload: BatchPlanPayload,
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> dict[str, object]:
        """
        构建插件批量计划阻断负载。

        :param plan_payload: 插件批量计划负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量计划阻断负载
        """
        total = cls._count_planned_items(plan_payload)
        return PluginBatchRunPayload.model_validate(
            {
                **plan_payload,
                'dryRun': dry_run,
                'continueOnError': continue_on_error,
                'executed': [],
                'failed': None,
                'summary': cls.build_summary([], total),
                'message': '插件批量操作计划存在阻塞项，未执行任何写操作',
            }
        ).to_payload()

    @classmethod
    def build_dry_run_payload(
        cls,
        plan_payload: BatchPlanPayload,
        *,
        continue_on_error: bool,
    ) -> dict[str, object]:
        """
        构建插件批量执行预演负载。

        :param plan_payload: 插件批量计划负载
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量执行预演负载
        """
        total = cls._count_planned_items(plan_payload)
        return PluginBatchRunPayload.model_validate(
            {
                **plan_payload,
                'message': '插件批量操作演练完成，未执行实际写入',
                'dryRun': True,
                'continueOnError': continue_on_error,
                'executed': [],
                'failed': None,
                'summary': cls.build_summary([], total),
            }
        ).to_payload()

    @classmethod
    def build_failed_payload(
        cls,
        report: PluginBatchItemReport,
        result: BatchOperationResultPayload,
    ) -> BatchFailedPayload:
        """
        构建插件批量执行失败项负载。

        :param report: 单项报告
        :param result: 单项原始执行结果
        :return: 失败项负载
        """
        return BatchFailedItem.model_validate({**cls.dump_item_report(report), 'result': result}).to_payload(
            exclude_none=True
        )

    @classmethod
    def build_execution_payload(
        cls,
        plan_payload: BatchPlanPayload,
        reports: list[PluginBatchItemReport],
        failed: BatchFailedPayload | None,
        *,
        continue_on_error: bool,
    ) -> dict[str, object]:
        """
        构建插件批量执行结果负载。

        :param plan_payload: 插件批量计划负载
        :param reports: 单项执行报告列表
        :param failed: 首个失败项负载
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量执行结果负载
        """
        ok = failed is None
        return PluginBatchRunPayload.model_validate(
            {
                **plan_payload,
                'ok': ok,
                'message': cls.build_batch_message(ok, continue_on_error),
                'dryRun': False,
                'continueOnError': continue_on_error,
                'executed': [cls.dump_item_report(report) for report in reports],
                'failed': failed,
                'summary': cls.build_summary(reports, cls._count_planned_items(plan_payload)),
            }
        ).to_payload()

    @staticmethod
    def build_batch_message(ok: bool, continue_on_error: bool) -> str:
        """
        构建批量执行结果消息。

        :param ok: 批量执行是否全部成功
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 批量执行结果消息
        """
        if ok:
            return '插件批量操作完成'
        if continue_on_error:
            return '插件批量操作完成，存在失败项'

        return '插件批量操作中止'

    @staticmethod
    def dump_item_report(report: PluginBatchItemReport) -> BatchItemReportPayload:
        """
        转换单项报告为插件运行时负载。

        :param report: 单项报告
        :return: 单项报告负载
        """
        return {
            'pluginId': report.plugin_id,
            'operation': report.operation,
            'ok': report.ok,
            'status': report.status,
            'message': report.message,
            'durationMs': report.duration_ms,
            'suggestion': report.suggestion,
        }

    @staticmethod
    def build_failure_suggestion(
        operation: PluginBatchOperation,
        plugin_id: str,
        result: BatchOperationResultPayload,
    ) -> str:
        """
        构建插件批量执行失败建议。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :param result: 原始执行结果
        :return: 失败建议
        """
        if result.get('pluginDependencyErrors'):
            return f'先执行 ruoyi plugin plan {operation} {plugin_id} 查看插件依赖阻塞项'
        if result.get('structureErrors'):
            return f'先执行 ruoyi plugin check {plugin_id} 修复插件目录结构问题'
        if result.get('menuConflicts'):
            return f'先执行 ruoyi plugin check {plugin_id} 查看菜单或权限冲突'
        if result.get('error'):
            return '查看错误详情并修复后重新执行批量命令'

        return f'先单独执行 ruoyi plugin {operation} {plugin_id} --dry-run 定位失败原因'

    @staticmethod
    def _count_planned_items(plan_payload: BatchPlanPayload) -> int:
        """
        统计插件批量计划项数量。

        :param plan_payload: 插件批量计划负载
        :return: 计划项数量
        """
        plan = plan_payload.get('plan', {})
        if not isinstance(plan, Mapping):
            return 0
        requested_plugin_ids = plan.get('requestedPluginIds')
        if isinstance(requested_plugin_ids, list) and requested_plugin_ids:
            return len(requested_plugin_ids)

        ordered_plugin_ids = plan.get('orderedPluginIds')
        return len(ordered_plugin_ids) if isinstance(ordered_plugin_ids, list) else 0
