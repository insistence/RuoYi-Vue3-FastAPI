from dataclasses import dataclass
from typing import TypedDict

from plugins.core.runtime.exit_codes import RUNTIME_ERROR


class PluginNotFoundPayloadDict(TypedDict, total=False):
    """
    插件不存在 payload。
    """

    ok: bool
    message: str
    pluginId: str
    exit_code: int
    operation: str
    dryRun: bool
    enabled: bool


@dataclass(frozen=True)
class PluginNotFoundPayload:
    """
    插件不存在结构化负载。
    """

    plugin_id: str
    operation: str | None = None
    dry_run: bool | None = None
    enabled: bool | None = None

    def to_payload(self) -> PluginNotFoundPayloadDict:
        """
        序列化为现有插件不存在 payload 契约。

        :return: 插件不存在 payload
        """
        payload: PluginNotFoundPayloadDict = {
            'ok': False,
            'message': f'插件不存在：{self.plugin_id}',
            'pluginId': self.plugin_id,
            'exit_code': RUNTIME_ERROR,
        }
        if self.operation is not None:
            payload['operation'] = self.operation
        if self.dry_run is not None:
            payload['dryRun'] = self.dry_run
        if self.enabled is not None:
            payload['enabled'] = self.enabled

        return payload


class PluginPayloadBuilder:
    """
    插件运行时通用负载构建器。
    """

    @staticmethod
    def build_plugin_not_found_payload(
        plugin_id: str,
        *,
        operation: str | None = None,
        dry_run: bool | None = None,
        enabled: bool | None = None,
    ) -> PluginNotFoundPayloadDict:
        """
        构建插件不存在负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param dry_run: 是否预演
        :param enabled: 是否启用
        :return: 插件不存在负载
        """
        return PluginNotFoundPayload(
            plugin_id,
            operation=operation,
            dry_run=dry_run,
            enabled=enabled,
        ).to_payload()
