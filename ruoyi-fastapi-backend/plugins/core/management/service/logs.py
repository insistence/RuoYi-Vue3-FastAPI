import json
from collections.abc import Mapping
from typing import cast

from plugins.core.management.entity.vo.schemas import PluginOperationLogDetailModel, PluginOperationLogModel
from utils.log_util import logger


class PluginOperationLogBuilder:
    """
    插件操作审计日志构建器。

    使用 Builder 模式集中处理操作结果 payload 与审计日志模型、详情模型和导出行之间的转换。
    """

    @staticmethod
    def build_export_row(
        operation_log: PluginOperationLogDetailModel,
        operation_dict: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """
        构建插件批量操作审计日志导出行。

        :param operation_log: 插件批量操作审计日志详情
        :param operation_dict: 插件操作类型字典
        :return: 插件批量操作审计日志导出行
        """
        operation_dict = operation_dict or {}

        return {
            'operationId': operation_log.operation_id,
            'operation': operation_dict.get(operation_log.operation, operation_log.operation),
            'pluginIds': ','.join(operation_log.plugin_ids),
            'dryRun': '是' if operation_log.dry_run else '否',
            'continueOnError': '是' if operation_log.continue_on_error else '否',
            'status': operation_log.status,
            'summary': json.dumps(operation_log.summary, ensure_ascii=False),
            'remark': operation_log.remark,
            'createTime': operation_log.create_time,
        }

    @classmethod
    def build_detail(cls, operation_log: Mapping[str, object]) -> PluginOperationLogDetailModel:
        """
        构建插件批量操作审计日志详情。

        :param operation_log: 插件批量操作审计日志字典
        :return: 插件批量操作审计日志详情
        """
        return PluginOperationLogDetailModel(
            operationId=operation_log.get('operationId'),
            operation=operation_log.get('operation') or '-',
            pluginIds=cls.deserialize_json_list(operation_log.get('pluginIds')),
            dryRun=operation_log.get('dryRun') == '0',
            continueOnError=operation_log.get('continueOnError') == '0',
            status=operation_log.get('status') or '-',
            summary=cls.deserialize_json_dict(operation_log.get('summary')),
            result=cls.deserialize_json_dict(operation_log.get('result')),
            createTime=operation_log.get('createTime'),
            remark=operation_log.get('remark'),
        )

    @staticmethod
    def deserialize_json_dict(value: object) -> dict[str, object]:
        """
        反序列化 JSON 字典。

        :param value: JSON 字符串
        :return: 字典对象
        """
        if not isinstance(value, str) or not value:
            return {}
        try:
            result = json.loads(value)
        except json.JSONDecodeError as exc:
            logger.warning(f'插件操作审计日志 JSON 字典解析失败：{exc}')
            return {'parseError': 'JSON 解析失败'}

        if not isinstance(result, dict):
            logger.warning('插件操作审计日志 JSON 内容不是对象')
            return {'parseError': 'JSON 内容不是对象'}

        return cast('dict[str, object]', result)

    @staticmethod
    def deserialize_json_list(value: object) -> list[str]:
        """
        反序列化 JSON 字符串列表。

        :param value: JSON 字符串
        :return: 字符串列表
        """
        if not isinstance(value, str) or not value:
            return []
        try:
            result = json.loads(value)
        except json.JSONDecodeError:
            return []

        return [str(item) for item in result] if isinstance(result, list) else []

    @classmethod
    def build_model(
        cls,
        payload: Mapping[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> PluginOperationLogModel:
        """
        根据插件操作结果构建审计日志模型。

        :param payload: 插件操作结果负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件操作审计日志模型
        """
        summary_value = payload.get('summary')
        summary = cast('dict[str, object]', summary_value) if isinstance(summary_value, dict) else {}
        plugin_ids = cls.resolve_plugin_ids(payload)

        return PluginOperationLogModel(
            operation=str(payload.get('operation', 'unknown')),
            pluginIds=json.dumps(plugin_ids, ensure_ascii=False),
            dryRun='0' if dry_run else '1',
            continueOnError='0' if continue_on_error else '1',
            status=cls.resolve_status(payload),
            summary=json.dumps(summary, ensure_ascii=False),
            result=json.dumps(dict(payload), ensure_ascii=False, default=str),
            remark=str(payload.get('message', ''))[:500] or None,
        )

    @staticmethod
    def resolve_plugin_ids(payload: Mapping[str, object]) -> list[str]:
        """
        解析插件操作审计日志的目标插件 ID。

        :param payload: 插件操作结果负载
        :return: 目标插件 ID 列表
        """
        plan_value = payload.get('plan')
        plan = cast('dict[str, object]', plan_value) if isinstance(plan_value, dict) else {}
        ordered_plugin_ids = plan.get('orderedPluginIds') if isinstance(plan.get('orderedPluginIds'), list) else []
        if ordered_plugin_ids:
            return [str(plugin_id) for plugin_id in ordered_plugin_ids]
        plugin_id = payload.get('pluginId')
        if plugin_id:
            return [str(plugin_id)]

        return []

    @staticmethod
    def resolve_status(payload: Mapping[str, object]) -> str:
        """
        解析插件操作审计状态。

        :param payload: 插件操作结果负载
        :return: 审计状态
        """
        if payload.get('dryRun'):
            return 'dry_run'
        plan_value = payload.get('plan')
        plan = cast('dict[str, object]', plan_value) if isinstance(plan_value, dict) else {}
        if plan.get('blockerCount', 0):
            return 'blocked'
        summary_value = payload.get('summary')
        summary = cast('dict[str, object]', summary_value) if isinstance(summary_value, dict) else {}
        if summary.get('failed', 0):
            return 'failed'

        return 'success' if payload.get('ok', False) else 'failed'
