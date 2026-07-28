from pathlib import Path
from typing import Any, Protocol, cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.support import PluginPrecheckContext

from ..context import PluginRuntimeContextService
from ..responses import PluginLifecycleResponse, PluginRuntimeBlockedPayloadDict


class PluginLifecycleSessionContext(Protocol):
    """
    带数据库会话的生命周期上下文。
    """

    session_context: Any | None
    session: Any | None


class PluginLifecycleUseCaseSupport:
    """
    生命周期 use case 公共协作能力。
    """

    context: PluginRuntimeContextService

    def _discover_plugins(self, backend_root: Path) -> list[DiscoveredPlugin]:
        """
        发现本地插件。

        :param backend_root: 后端项目根目录
        :return: 已发现插件列表
        """
        return self.context.discover_plugins(backend_root)

    def _get_discovered_plugin(self, plugin_id: str) -> DiscoveredPlugin | None:
        """
        根据插件 ID 获取已发现插件。

        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin(plugin_id)

    def _get_discovered_plugin_from_list(
        self,
        discovered_plugins: list[DiscoveredPlugin],
        plugin_id: str,
    ) -> DiscoveredPlugin | None:
        """
        从已发现插件列表中查找指定插件。

        :param discovered_plugins: 已发现插件列表
        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin_from_list(discovered_plugins, plugin_id)

    def _build_operation_blocked_payload(
        self,
        discovered_plugin: DiscoveredPlugin,
        operation: str,
        *,
        dry_run: bool | None = None,
    ) -> PluginRuntimeBlockedPayloadDict | None:
        """
        构建运行模式阻断负载。

        :param discovered_plugin: 已发现插件
        :param operation: 操作类型
        :param dry_run: 是否预演
        :return: 阻断负载，不阻断时返回 None
        """
        return self.context.build_operation_blocked_payload(discovered_plugin, operation, dry_run=dry_run)

    async def _build_precheck_context(
        self,
        backend_root: Path,
        discovered_plugin: DiscoveredPlugin,
        discovered_plugins: list[DiscoveredPlugin],
    ) -> PluginPrecheckContext:
        """
        构建插件操作预检上下文。

        :param backend_root: 后端项目根目录
        :param discovered_plugin: 当前插件
        :param discovered_plugins: 已发现插件列表
        :return: 插件操作预检上下文
        """
        return await self.context.build_precheck_context(backend_root, discovered_plugin, discovered_plugins)

    def _with_plugin_capability(
        self,
        payload: PluginLifecycleResponse,
        discovered_plugin: DiscoveredPlugin | None,
    ) -> PluginLifecycleResponse:
        """
        为运行时响应负载附加插件操作能力。

        :param payload: 运行时响应负载
        :param discovered_plugin: 已发现插件
        :return: 附加能力后的响应负载
        """
        return cast(
            'PluginLifecycleResponse',
            self.context.with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
        )

    async def _close_lifecycle_session(self, context: object) -> None:
        """
        关闭生命周期上下文中的数据库会话。

        :param context: 生命周期上下文
        :return: None
        """
        lifecycle_context = cast('PluginLifecycleSessionContext', context)
        session_context = lifecycle_context.session_context
        if session_context is None:
            return
        await session_context.__aexit__(None, None, None)
        lifecycle_context.session_context = None
        lifecycle_context.session = None
