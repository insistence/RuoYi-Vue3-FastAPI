from pathlib import Path
from typing import Any

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.purge import PluginPurgePlan
from plugins.core.runtime.support import PluginPayloadBuilder, PluginPrecheckContext, PluginRuntimePayloadBuilder
from plugins.core.validation.plugin_deps import PluginBatchOperation

from .context import PluginRuntimeContextService
from .dependency_container import PluginRuntimeDependencies


class PluginPrecheckUseCase:
    """
    插件预检 use case。
    """

    def __init__(self, dependencies: PluginRuntimeDependencies, context: PluginRuntimeContextService) -> None:
        """
        初始化插件预检 use case。

        :param dependencies: 插件运行时依赖容器
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.context = context

    def _discover_plugins(self, backend_root: Path) -> list[DiscoveredPlugin]:
        """
        发现本地插件。

        :param backend_root: 后端项目根目录
        :return: 已发现插件列表
        """
        return self.context.discover_plugins(backend_root)

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

    async def _load_database_plugin_state(self, plugin_id: str) -> tuple[Any | None, str | None]:
        """
        读取数据库插件状态。

        :param plugin_id: 插件ID
        :return: 数据库插件状态和错误信息
        """
        return await self.context.load_database_plugin_state(plugin_id)

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
        payload: dict[str, Any],
        discovered_plugin: DiscoveredPlugin | None,
    ) -> dict[str, Any]:
        """
        为运行时响应负载附加插件操作能力。

        :param payload: 运行时响应负载
        :param discovered_plugin: 已发现插件
        :return: 附加能力后的响应负载
        """
        return self.context.with_plugin_capability(payload, discovered_plugin)

    async def precheck_plugin_operation(self, plugin_id: str, operation: PluginBatchOperation) -> dict[str, Any]:
        """
        执行插件操作预检。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :return: 插件操作预检负载
        """
        if operation not in ('install', 'enable', 'upgrade', 'uninstall', 'purge'):
            return PluginRuntimePayloadBuilder.build_invalid_operation_payload(
                plugin_id,
                operation,
                message='插件预检操作只支持 install、enable、upgrade、uninstall 或 purge',
            )

        try:
            backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id, operation=operation)

            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            database_plugin, database_error = await self._load_database_plugin_state(plugin_id)
            actions = PluginRuntimePayloadBuilder.build_precheck_actions(operation, discovered_plugin, precheck)
            version_state = PluginPayloadBuilder.build_upgrade_version_state(discovered_plugin, database_plugin)
            purge_plan = await self._build_precheck_purge_plan(discovered_plugin) if operation == 'purge' else None
            payload = PluginRuntimePayloadBuilder.build_precheck_payload(
                plugin_id,
                operation,
                precheck=precheck,
                version_state=version_state,
                actions=actions,
                database_error=database_error,
                purge_plan=purge_plan,
            )
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件操作预检失败', exc)

    async def _build_precheck_purge_plan(self, discovered_plugin: DiscoveredPlugin) -> PluginPurgePlan | None:
        """
        构建插件预检物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划，构建失败时返回 None
        """
        try:
            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                return await plugin_service.build_plugin_purge_plan_services(session, discovered_plugin)
        except Exception:
            return None
