from typing import Any

from plugins.core.runtime.support import (
    PluginDocumentationBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)


class PluginToolOperationMixin:
    """
    插件运行时工具操作。
    """

    def generate_plugin_docs(self, plugin_id: str) -> dict[str, Any]:
        """
        生成插件 Markdown 文档片段。

        :param plugin_id: 插件ID
        :return: 插件文档生成负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)

            return PluginDocumentationBuilder.build_payload(plugin_id, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件文档生成失败', exc)
