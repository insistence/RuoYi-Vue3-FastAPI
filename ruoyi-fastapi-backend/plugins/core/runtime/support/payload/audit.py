from collections.abc import Mapping
from typing import Protocol, TypeAlias, cast

from pydantic import Field

from .base import PluginPayloadModel


class PluginAuditItemPayload(PluginPayloadModel):
    """
    插件审计单项 payload。
    """

    operation_id: object = Field(alias='operationId')
    operation: object
    plugin_ids: list[object] = Field(alias='pluginIds')
    dry_run: bool = Field(alias='dryRun')
    continue_on_error: bool = Field(alias='continueOnError')
    status: object
    summary: object
    create_time: object = Field(alias='createTime')
    remark: object


class PluginAuditSnapshotPayload(PluginPayloadModel):
    """
    插件最近审计快照 payload。
    """

    available: bool
    count: int
    items: list[Mapping[str, object]]


class PluginAuditSnapshotFailurePayload(PluginPayloadModel):
    """
    插件最近审计快照读取失败 payload。
    """

    available: bool
    message: str
    items: list[Mapping[str, object]]


PluginAuditItemPayloadDict: TypeAlias = dict[str, object]
PluginAuditSnapshotPayloadDict: TypeAlias = dict[str, object]
PluginAuditSnapshotFailurePayloadDict: TypeAlias = dict[str, object]


class SupportsAuditModelDump(Protocol):
    """
    支持审计记录别名序列化的对象协议。
    """

    def model_dump(self, *, by_alias: bool = False) -> Mapping[str, object]:
        """
        序列化审计记录。

        :param by_alias: 是否使用字段别名
        :return: 审计记录 payload
        """
        ...


class PluginAuditPayloadBuilder:
    """
    插件审计负载构建器。
    """

    @staticmethod
    def build_recent_snapshot_failure(error: Exception) -> PluginAuditSnapshotFailurePayloadDict:
        """
        构建最近审计快照读取失败负载。

        :param error: 异常对象
        :return: 最近审计快照读取失败负载
        """
        return PluginAuditSnapshotFailurePayload(
            available=False,
            message=f'最近审计快照读取失败：{error}',
            items=[],
        ).to_payload()

    @classmethod
    def build_recent_snapshot_payload(
        cls,
        plugin_id: str,
        operation_logs: list[object],
        *,
        audit_limit: int,
    ) -> PluginAuditSnapshotPayloadDict:
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
        return PluginAuditSnapshotPayload(
            available=True,
            count=len(recent_logs),
            items=[
                cast('SupportsAuditModelDump', operation_log).model_dump(by_alias=True)
                if hasattr(operation_log, 'model_dump')
                else cls.build_item_payload(operation_log)
                for operation_log in recent_logs
            ],
        ).to_payload()

    @staticmethod
    def build_item_payload(operation_log: object) -> PluginAuditItemPayloadDict:
        """
        构建审计记录负载。

        :param operation_log: 审计记录对象
        :return: 审计记录负载
        """
        return PluginAuditItemPayload(
            operation_id=getattr(operation_log, 'operation_id', None),
            operation=getattr(operation_log, 'operation', '-'),
            plugin_ids=list(cast('list[object]', getattr(operation_log, 'plugin_ids', []))),
            dry_run=bool(getattr(operation_log, 'dry_run', False)),
            continue_on_error=bool(getattr(operation_log, 'continue_on_error', False)),
            status=getattr(operation_log, 'status', '-'),
            summary=getattr(operation_log, 'summary', {}),
            create_time=getattr(operation_log, 'create_time', None),
            remark=getattr(operation_log, 'remark', None),
        ).to_payload()
