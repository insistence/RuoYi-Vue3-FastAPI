from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PluginAuditItemPayload:
    """
    插件审计单项结构化负载。
    """

    operation_log: Any

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件审计单项 payload 契约。

        :return: 插件审计单项 payload
        """
        return {
            'operationId': getattr(self.operation_log, 'operation_id', None),
            'operation': getattr(self.operation_log, 'operation', '-'),
            'pluginIds': list(getattr(self.operation_log, 'plugin_ids', [])),
            'dryRun': bool(getattr(self.operation_log, 'dry_run', False)),
            'continueOnError': bool(getattr(self.operation_log, 'continue_on_error', False)),
            'status': getattr(self.operation_log, 'status', '-'),
            'summary': getattr(self.operation_log, 'summary', {}),
            'createTime': getattr(self.operation_log, 'create_time', None),
            'remark': getattr(self.operation_log, 'remark', None),
        }


@dataclass(frozen=True)
class PluginAuditSnapshotPayload:
    """
    插件最近审计快照结构化负载。
    """

    plugin_id: str
    operation_logs: list[Any]
    audit_limit: int

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件最近审计快照 payload 契约。

        :return: 插件最近审计快照 payload
        """
        recent_logs = [
            operation_log
            for operation_log in self.operation_logs
            if self.plugin_id in getattr(operation_log, 'plugin_ids', [])
        ][: self.audit_limit]
        return {
            'available': True,
            'count': len(recent_logs),
            'items': [
                operation_log.model_dump(by_alias=True)
                if hasattr(operation_log, 'model_dump')
                else PluginAuditItemPayload(operation_log).to_payload()
                for operation_log in recent_logs
            ],
        }


@dataclass(frozen=True)
class PluginAuditSnapshotFailurePayload:
    """
    插件最近审计快照读取失败结构化负载。
    """

    error: Exception

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件最近审计快照读取失败 payload 契约。

        :return: 插件最近审计快照读取失败 payload
        """
        return {
            'available': False,
            'message': f'最近审计快照读取失败：{self.error}',
            'items': [],
        }


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
        return PluginAuditSnapshotFailurePayload(error).to_payload()

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
        return PluginAuditSnapshotPayload(plugin_id, operation_logs, audit_limit).to_payload()

    @staticmethod
    def build_item_payload(operation_log: Any) -> dict[str, Any]:
        """
        构建审计记录负载。

        :param operation_log: 审计记录对象
        :return: 审计记录负载
        """
        return PluginAuditItemPayload(operation_log).to_payload()
