from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.support import (
    PluginDocumentationBuilder,
    PluginDocumentationPayloadDict,
    PluginNotFoundPayloadDict,
    PluginPayloadBuilder,
    PluginRuntimeExceptionPayloadDict,
    PluginRuntimePayloadBuilder,
)

from .context import PluginRuntimeContextService
from .dependency_container import PluginRuntimeDependencies


class PluginToolUseCase:
    """
    插件运行时工具 use case。
    """

    def __init__(self, dependencies: PluginRuntimeDependencies, context: PluginRuntimeContextService) -> None:
        """
        初始化插件运行时工具 use case。

        :param dependencies: 插件运行时依赖容器
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.context = context

    def _get_discovered_plugin(self, plugin_id: str) -> DiscoveredPlugin | None:
        """
        根据插件 ID 获取已发现插件。

        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin(plugin_id)

    def generate_plugin_docs(
        self, plugin_id: str
    ) -> PluginDocumentationPayloadDict | PluginNotFoundPayloadDict | PluginRuntimeExceptionPayloadDict:
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
