from pathlib import Path
from typing import cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.purge import PluginPurgePlan
from plugins.core.runtime.support import PluginPayloadBuilder, PluginPrecheckContext, PluginRuntimePayloadBuilder
from plugins.core.types import PluginStateRecord
from plugins.core.validation.plugin_deps import PluginBatchOperation
from utils.log_util import logger

from .context import PluginRuntimeContextService
from .dependency_container import PluginRuntimeDependencies
from .responses import PluginPrecheckResponse


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

    async def _load_database_plugin_state(self, plugin_id: str) -> tuple[PluginStateRecord | None, str | None]:
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
        payload: dict[str, object],
        discovered_plugin: DiscoveredPlugin | None,
    ) -> dict[str, object]:
        """
        为运行时响应负载附加插件操作能力。

        :param payload: 运行时响应负载
        :param discovered_plugin: 已发现插件
        :return: 附加能力后的响应负载
        """
        return cast('dict[str, object]', self.context.with_plugin_capability(payload, discovered_plugin))

    async def precheck_plugin_operation(
        self, plugin_id: str, operation: PluginBatchOperation
    ) -> PluginPrecheckResponse:
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
            purge_plan = None
            purge_plan_error = None
            if operation == 'purge':
                purge_plan, purge_plan_error = await self._build_precheck_purge_plan(discovered_plugin)
            payload = PluginRuntimePayloadBuilder.build_precheck_payload(
                plugin_id,
                operation,
                precheck=precheck,
                version_state=version_state,
                actions=actions,
                database_error=database_error,
                purge_plan=purge_plan,
                purge_plan_error=purge_plan_error,
            )
            return cast(
                'PluginPrecheckResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件操作预检失败', exc)

    async def _build_precheck_purge_plan(
        self,
        discovered_plugin: DiscoveredPlugin,
    ) -> tuple[PluginPurgePlan | None, str | None]:
        """
        构建插件预检物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划和构建错误
        """
        try:
            return await self.dependencies.purge_plan_gateway.build_plugin_purge_plan(discovered_plugin), None
        except Exception as exc:
            logger.warning(f'插件 {discovered_plugin.manifest.id} 预检物理清理计划构建失败：{exc}')
            return None, str(exc)
