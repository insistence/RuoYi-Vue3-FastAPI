from typing import Any

from plugins.core.runtime.exit_codes import RUNTIME_ERROR


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
    ) -> dict[str, Any]:
        """
        构建插件不存在负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param dry_run: 是否预演
        :param enabled: 是否启用
        :return: 插件不存在负载
        """
        payload: dict[str, Any] = {
            'ok': False,
            'message': f'插件不存在：{plugin_id}',
            'pluginId': plugin_id,
            'exit_code': RUNTIME_ERROR,
        }
        if operation is not None:
            payload['operation'] = operation
        if dry_run is not None:
            payload['dryRun'] = dry_run
        if enabled is not None:
            payload['enabled'] = enabled

        return payload
