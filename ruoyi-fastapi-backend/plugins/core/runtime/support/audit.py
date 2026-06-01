from typing import Any


class PluginAuditPayloadBuilder:
    """
    插件审计负载构建器。
    """

    @staticmethod
    def build_recent_snapshot_failure(error: Exception) -> dict[str, Any]:
        """
        构建最近审计快照读取失败负载。

        :param error: 异常对象
        :return: 最近审计快照读取失败负载
        """
        return {
            'available': False,
            'message': f'最近审计快照读取失败：{error}',
            'items': [],
        }

    @classmethod
    def build_recent_snapshot_payload(
        cls,
        plugin_id: str,
        operation_logs: list[Any],
        *,
        audit_limit: int,
    ) -> dict[str, Any]:
        """
        构建最近审计快照负载。

        :param plugin_id: 插件ID
        :param operation_logs: 审计记录列表
        :param audit_limit: 最近审计记录数量
        :return: 最近审计快照负载
        """
        recent_logs = [
            operation_log for operation_log in operation_logs if plugin_id in getattr(operation_log, 'plugin_ids', [])
        ][:audit_limit]
        return {
            'available': True,
            'count': len(recent_logs),
            'items': [
                operation_log.model_dump(by_alias=True)
                if hasattr(operation_log, 'model_dump')
                else cls.build_item_payload(operation_log)
                for operation_log in recent_logs
            ],
        }

    @staticmethod
    def build_item_payload(operation_log: Any) -> dict[str, Any]:
        """
        构建审计记录负载。

        :param operation_log: 审计记录对象
        :return: 审计记录负载
        """
        return {
            'operationId': getattr(operation_log, 'operation_id', None),
            'operation': getattr(operation_log, 'operation', '-'),
            'pluginIds': list(getattr(operation_log, 'plugin_ids', [])),
            'dryRun': bool(getattr(operation_log, 'dry_run', False)),
            'continueOnError': bool(getattr(operation_log, 'continue_on_error', False)),
            'status': getattr(operation_log, 'status', '-'),
            'summary': getattr(operation_log, 'summary', {}),
            'createTime': getattr(operation_log, 'create_time', None),
            'remark': getattr(operation_log, 'remark', None),
        }
