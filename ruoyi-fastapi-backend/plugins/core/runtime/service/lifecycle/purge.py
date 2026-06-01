from typing import Any

from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPurgePayloadBuilder,
    PluginRuntimePayloadBuilder,
)


class PluginPurgeOperationMixin:
    """
    插件物理清理操作。
    """

    async def purge_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> dict[str, Any]:
        """
        物理清理插件平台元数据并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件物理清理结果负载
        """
        payload = await self._purge_plugin(plugin_id, dry_run=dry_run)
        if record_operation_log and not dry_run:
            await self._record_plugin_operation_log(payload, dry_run=dry_run, continue_on_error=False)

        return payload

    async def _purge_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
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

            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
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
