from pathlib import Path
from typing import cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.lifecycle.seed import PluginSeedRunner
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginRuntimePayloadBuilder,
)

from ..context import PluginRuntimeContextService
from ..dependency_container import PluginRuntimeDependencies
from ..migration_store import PluginDatabaseMigrationHistoryStore
from ..responses import PluginLifecycleResponse, PluginRuntimeBlockedPayloadDict
from .operations import PluginLifecycleRuntimeOperations


class PluginInstallUseCase:
    """
    插件安装 use case。
    """

    def __init__(
        self,
        dependencies: PluginRuntimeDependencies,
        runtime_operations: PluginLifecycleRuntimeOperations,
        context: PluginRuntimeContextService,
    ) -> None:
        """
        初始化插件安装 use case。

        :param dependencies: 插件运行时依赖容器
        :param runtime_operations: 生命周期工作流所需的运行时协作能力
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.runtime_operations = runtime_operations
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

    async def install_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        安装插件并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件安装结果负载
        """
        payload = await self._install_plugin(plugin_id, dry_run=dry_run)
        payload_view = cast('dict[str, object]', payload)
        payload_view['operation'] = 'install'
        if not dry_run:
            await self.runtime_operations._record_plugin_failure_state(payload_view, '插件安装失败')
        if record_operation_log and not dry_run:
            await self.runtime_operations._record_plugin_operation_log(
                payload_view,
                dry_run=dry_run,
                continue_on_error=False,
            )

        return payload

    async def _install_plugin(self, plugin_id: str, *, dry_run: bool = False) -> PluginLifecycleResponse:
        """
        安装插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件安装结果负载
        """
        try:
            backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
            discovered_plugins = self._discover_plugins(backend_root)
            discovered_plugin = self._get_discovered_plugin_from_list(discovered_plugins, plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)
            blocked_payload = self._build_operation_blocked_payload(discovered_plugin, 'install', dry_run=dry_run)
            if blocked_payload:
                return blocked_payload

            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            actions = PluginPayloadBuilder.build_install_actions(
                discovered_plugin,
                precheck.dependency_result.ok,
                precheck.plugin_dependency_result.ok,
                precheck.structure_result.ok,
                precheck.menu_conflict_result.ok,
            )
            if dry_run:
                payload = PluginLifecyclePayloadBuilder.build_install_dry_run_payload(plugin_id, actions, precheck)
                payload['operation'] = 'install'
                return self._with_plugin_capability(payload, discovered_plugin)
            blocker_payload = PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
                plugin_id,
                operation='install',
                actions=actions,
                precheck=precheck,
            )
            if blocker_payload:
                return blocker_payload
            dependency_install_payload = self.runtime_operations._install_plugin_dependencies_from_result(
                plugin_id,
                precheck.dependency_result,
                dry_run=False,
                discovered_plugin=discovered_plugin,
            )
            dependency_install_view = cast('dict[str, object]', dependency_install_payload)
            if not dependency_install_view.get('ok', False):
                return PluginLifecyclePayloadBuilder.build_precheck_blocker_payload(
                    plugin_id,
                    message='插件依赖安装失败，安装已中止',
                    actions=actions,
                    precheck=precheck,
                    extra_payload={'dependencyInstall': dependency_install_view},
                )
            self.runtime_operations._refresh_dependency_checker()
            self.dependencies = self.runtime_operations.dependencies
            self.context = self.runtime_operations.context
            precheck = await self._build_precheck_context(backend_root, discovered_plugin, discovered_plugins)
            dependency_install_view['postCheck'] = PluginPayloadBuilder.build_dependency_check_payload(
                plugin_id,
                precheck.dependency_result,
            )
            actions = PluginPayloadBuilder.build_install_actions(
                discovered_plugin,
                precheck.dependency_result.ok,
                precheck.plugin_dependency_result.ok,
                precheck.structure_result.ok,
                precheck.menu_conflict_result.ok,
            )
            dependency_blocker_payload = PluginLifecyclePayloadBuilder.build_dependency_blocker_payload(
                plugin_id,
                actions=actions,
                precheck=precheck,
                dependency_install_payload=dependency_install_view,
            )
            if dependency_blocker_payload:
                return dependency_blocker_payload

            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                installed_menu_conflicts = await plugin_service.check_installed_menu_conflict_services(
                    session,
                    discovered_plugin,
                )
                if installed_menu_conflicts:
                    return PluginLifecyclePayloadBuilder.build_installed_menu_conflict_payload(
                        plugin_id,
                        message='插件菜单与已安装菜单存在冲突，安装已中止',
                        actions=actions,
                        precheck=precheck,
                        installed_menu_conflicts=installed_menu_conflicts,
                    )
                plugin = await plugin_service.upsert_discovered_plugin_services(
                    session,
                    discovered_plugin,
                    backend_root / 'plugins',
                    backend_root.parent / 'ruoyi-fastapi-frontend' / 'plugins',
                )
                plugin_enabled = getattr(plugin, 'enabled', '0') == '0'
                await plugin_service.install_plugin_menu_services(session, discovered_plugin, enabled=plugin_enabled)
                installed_configs = await plugin_service.install_plugin_default_config_services(
                    session,
                    discovered_plugin,
                )
                migration_results = await PluginMigrationRunner(
                    discovered_plugin,
                    PluginDatabaseMigrationHistoryStore.with_model_gateway(
                        plugin_service,
                        self.dependencies.model_gateway,
                    ),
                ).run(session)
                seed_results = await PluginSeedRunner(discovered_plugin).run(session)
                hook_result = await PluginHookRunner(discovered_plugin).run('on_install', query_db=session)
                plugin = await plugin_service.mark_plugin_installed_services(session, discovered_plugin)
                await session.commit()

            payload = PluginLifecyclePayloadBuilder.build_success_payload(
                plugin_id,
                message='插件安装完成',
                actions=actions,
                precheck=precheck,
                plugin=plugin,
                installed_configs=installed_configs,
                migration_results=migration_results,
                seed_results=seed_results,
                hook_result=hook_result,
                extra_payload={'dependencyInstall': dependency_install_view},
            )
            payload['operation'] = 'install'
            return self._with_plugin_capability(payload, discovered_plugin)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('插件安装失败', exc)
