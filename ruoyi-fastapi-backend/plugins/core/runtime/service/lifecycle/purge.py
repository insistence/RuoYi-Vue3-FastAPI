from pathlib import Path
from typing import cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginPurgePayloadBuilder,
    PluginRuntimePayloadBuilder,
)

from ..context import PluginRuntimeContextService
from ..dependency_container import PluginRuntimeDependencies
from ..responses import PluginLifecycleResponse, PluginRuntimeBlockedPayloadDict
from .operations import PluginLifecycleRuntimeOperations


class PluginPurgeUseCase:
    """
    插件物理清理 use case。
    """

    def __init__(
        self,
        dependencies: PluginRuntimeDependencies,
        runtime_operations: PluginLifecycleRuntimeOperations,
        context: PluginRuntimeContextService,
    ) -> None:
        """
        初始化插件物理清理 use case。

        :param dependencies: 插件运行时依赖容器
        :param runtime_operations: 生命周期工作流所需的运行时协作能力
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.runtime_operations = runtime_operations
        self.context = context

    def _get_discovered_plugin(self, plugin_id: str) -> DiscoveredPlugin | None:
        """
        根据插件 ID 获取已发现插件。

        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin(plugin_id)

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

    def _discover_plugins(self, backend_root: Path) -> list[DiscoveredPlugin]:
        """
        发现本地插件。

        :param backend_root: 后端项目根目录
        :return: 已发现插件列表
        """
        return self.context.discover_plugins(backend_root)

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

    async def purge_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        物理清理插件平台元数据并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件物理清理结果负载
        """
        payload = await self._purge_plugin(plugin_id, dry_run=dry_run)
        payload_view = cast('dict[str, object]', payload)
        if record_operation_log and not dry_run:
            await self.runtime_operations._record_plugin_operation_log(
                payload_view,
                dry_run=dry_run,
                continue_on_error=False,
            )

        return payload

    async def _purge_plugin(self, plugin_id: str, *, dry_run: bool = False) -> PluginLifecycleResponse:
        """
        物理清理插件平台元数据。

        purge 与 uninstall 语义隔离：uninstall 只停用插件，purge 会删除平台拥有的插件状态、
        菜单关联、配置、migration 历史和插件任务。业务数据只能通过插件显式声明的 on_purge 钩子清理。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件物理清理结果负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(
                    plugin_id,
                    operation='purge',
                    dry_run=dry_run,
                )
            blocked_payload = self._build_operation_blocked_payload(discovered_plugin, 'purge', dry_run=dry_run)
            if blocked_payload:
                return blocked_payload
            backend_root = discovered_plugin.backend_path.parent.parent
            discovered_plugins = self._discover_plugins(backend_root)
            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            actions = PluginRuntimePayloadBuilder.build_precheck_actions('purge', discovered_plugin, precheck)

            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                plan = await plugin_service.build_plugin_purge_plan_services(session, discovered_plugin)
                if dry_run:
                    payload = PluginLifecyclePayloadBuilder.build_operation_dry_run_payload(
                        plugin_id,
                        operation='purge',
                        message='插件物理清理演练完成，未执行实际删除',
                        actions=actions,
                        precheck=precheck,
                        extra_payload={
                            'safeMode': False,
                            'removesSource': plan.removes_source,
                            'plan': PluginPayloadBuilder.build_purge_plan(plan),
                        },
                        ok_from_precheck=False,
                    )
                    return self._with_plugin_capability(payload, discovered_plugin)

                hook_result = await PluginHookRunner(discovered_plugin).run('on_purge', query_db=session)
                await plugin_service.purge_plugin_services(session, discovered_plugin)
                await session.commit()

            payload = PluginPurgePayloadBuilder.build_success_payload(plugin_id, plan, hook_result)
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件物理清理失败', exc)
