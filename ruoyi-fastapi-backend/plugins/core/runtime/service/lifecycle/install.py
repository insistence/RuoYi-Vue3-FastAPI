from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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
from .runner import PluginLifecycleStep, PluginLifecycleStepFailed, PluginLifecycleStepRunner


@dataclass(slots=True)
class PluginInstallLifecycleContext:
    """
    插件安装声明式生命周期上下文。
    """

    plugin_id: str
    dry_run: bool
    backend_root: Path | None = None
    discovered_plugins: list[DiscoveredPlugin] | None = None
    discovered_plugin: DiscoveredPlugin | None = None
    precheck: PluginPrecheckContext | None = None
    actions: list[dict[str, object]] | None = None
    dependency_install_view: dict[str, object] | None = None
    plugin: Any | None = None
    installed_configs: Any | None = None
    migration_results: Any | None = None
    seed_results: Any | None = None
    hook_result: Any | None = None
    session: Any | None = None
    plugin_service: Any | None = None
    session_context: Any | None = None


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
            await self.runtime_operations.record_plugin_failure_state(payload_view, '插件安装失败')
        if record_operation_log and not dry_run:
            await self.runtime_operations.record_plugin_operation_log(
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
        context = PluginInstallLifecycleContext(plugin_id=plugin_id, dry_run=dry_run)
        try:
            result = await PluginLifecycleStepRunner(self._build_install_steps()).run(context)
            if result.stop:
                await self._close_install_session(result.context)
                return result.stop.payload
            payload = self._build_install_success_payload(result.context)
            payload['operation'] = 'install'
            return self._with_plugin_capability(payload, result.context.discovered_plugin)
        except PluginLifecycleStepFailed as exc:
            await self._close_install_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件安装失败',
                exc.original_error,
                plugin_id=plugin_id,
                failed_step=exc.step_name,
            )
        except Exception as exc:
            await self._close_install_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件安装失败',
                exc,
                plugin_id=plugin_id,
                failed_step='prepare_install',
            )

    def _build_install_steps(self) -> list[PluginLifecycleStep[PluginInstallLifecycleContext]]:
        """
        构建插件安装声明式生命周期步骤。

        :return: 插件安装步骤列表
        """
        return [
            PluginLifecycleStep('discover_plugin', self._install_step_discover_plugin),
            PluginLifecycleStep('build_precheck', self._install_step_build_precheck),
            PluginLifecycleStep('install_dependencies', self._install_step_install_dependencies),
            PluginLifecycleStep('build_post_dependency_precheck', self._install_step_build_post_dependency_precheck),
            PluginLifecycleStep('open_session', self._install_step_open_session),
            PluginLifecycleStep('check_installed_menu_conflicts', self._install_step_check_installed_menu_conflicts),
            PluginLifecycleStep('upsert_plugin', self._install_step_upsert_plugin),
            PluginLifecycleStep('install_menus', self._install_step_install_menus),
            PluginLifecycleStep('install_configs', self._install_step_install_configs),
            PluginLifecycleStep('run_migrations', self._install_step_run_migrations),
            PluginLifecycleStep('run_seeds', self._install_step_run_seeds),
            PluginLifecycleStep('run_install_hook', self._install_step_run_install_hook),
            PluginLifecycleStep('mark_installed', self._install_step_mark_installed),
            PluginLifecycleStep('commit', self._install_step_commit),
            PluginLifecycleStep('close_session', self._install_step_close_session),
        ]

    async def _install_step_discover_plugin(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        发现插件并检查运行模式阻断。

        :param context: 插件安装上下文
        :return: 阻断 payload 或 None
        """
        context.backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        context.discovered_plugins = self._discover_plugins(context.backend_root)
        context.discovered_plugin = self._get_discovered_plugin_from_list(context.discovered_plugins, context.plugin_id)
        if not context.discovered_plugin:
            return PluginPayloadBuilder.build_plugin_not_found_payload(context.plugin_id)

        return self._build_operation_blocked_payload(
            context.discovered_plugin,
            'install',
            dry_run=context.dry_run,
        )

    async def _install_step_build_precheck(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        构建安装预检和动作计划。

        :param context: 插件安装上下文
        :return: dry-run 或阻断 payload
        """
        self._refresh_install_actions(await self._build_install_precheck(context), context)
        if context.dry_run:
            payload = PluginLifecyclePayloadBuilder.build_install_dry_run_payload(
                context.plugin_id,
                context.actions or [],
                cast('PluginPrecheckContext', context.precheck),
            )
            payload['operation'] = 'install'
            return self._with_plugin_capability(payload, context.discovered_plugin)

        return PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
            context.plugin_id,
            operation='install',
            actions=context.actions or [],
            precheck=cast('PluginPrecheckContext', context.precheck),
        )

    async def _install_step_install_dependencies(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        安装缺失依赖。

        :param context: 插件安装上下文
        :return: 依赖安装失败 payload 或 None
        """
        dependency_install_payload = await self.runtime_operations.install_plugin_dependencies_from_result_async(
            context.plugin_id,
            cast('PluginPrecheckContext', context.precheck).dependency_result,
            dry_run=False,
            discovered_plugin=context.discovered_plugin,
        )
        context.dependency_install_view = cast('dict[str, object]', dependency_install_payload)
        if context.dependency_install_view.get('ok', False):
            self.runtime_operations.refresh_dependency_checker()
            return None

        return PluginLifecyclePayloadBuilder.build_precheck_blocker_payload(
            context.plugin_id,
            message='插件依赖安装失败，安装已中止',
            actions=context.actions or [],
            precheck=cast('PluginPrecheckContext', context.precheck),
            extra_payload={'dependencyInstall': context.dependency_install_view},
        )

    async def _install_step_build_post_dependency_precheck(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        依赖安装后重新预检。

        :param context: 插件安装上下文
        :return: 依赖阻断 payload 或 None
        """
        precheck = await self._build_install_precheck(context)
        if context.dependency_install_view is not None:
            context.dependency_install_view['postCheck'] = PluginPayloadBuilder.build_dependency_check_payload(
                context.plugin_id,
                precheck.dependency_result,
            )
        self._refresh_install_actions(precheck, context)

        return PluginLifecyclePayloadBuilder.build_dependency_blocker_payload(
            context.plugin_id,
            actions=context.actions or [],
            precheck=precheck,
            dependency_install_payload=context.dependency_install_view or {},
        )

    async def _install_step_open_session(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        打开安装数据库会话。

        :param context: 插件安装上下文
        :return: None
        """
        gateway = self.dependencies.state_gateway
        async_session_local = gateway.get_async_session_local()
        context.session_context = async_session_local()
        context.session = await context.session_context.__aenter__()
        context.plugin_service = gateway.get_plugin_service()

        return None

    async def _install_step_check_installed_menu_conflicts(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        检查已安装菜单冲突。

        :param context: 插件安装上下文
        :return: 菜单冲突 payload 或 None
        """
        installed_menu_conflicts = await context.plugin_service.check_installed_menu_conflict_services(
            context.session,
            context.discovered_plugin,
        )
        if not installed_menu_conflicts:
            return None

        return PluginLifecyclePayloadBuilder.build_installed_menu_conflict_payload(
            context.plugin_id,
            message='插件菜单与已安装菜单存在冲突，安装已中止',
            actions=context.actions or [],
            precheck=cast('PluginPrecheckContext', context.precheck),
            installed_menu_conflicts=installed_menu_conflicts,
        )

    async def _install_step_upsert_plugin(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        写入插件基础状态。

        :param context: 插件安装上下文
        :return: None
        """
        context.plugin = await context.plugin_service.upsert_discovered_plugin_services(
            context.session,
            context.discovered_plugin,
            Path(self.dependencies.runtime_environment.get_backend_plugins_dir()),
            Path(self.dependencies.runtime_environment.get_frontend_plugins_dir()),
        )

        return None

    async def _install_step_install_menus(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        安装插件菜单。

        :param context: 插件安装上下文
        :return: None
        """
        plugin_enabled = getattr(context.plugin, 'enabled', '0') == '0'
        await context.plugin_service.install_plugin_menu_services(
            context.session,
            context.discovered_plugin,
            enabled=plugin_enabled,
        )

        return None

    async def _install_step_install_configs(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        安装插件默认配置。

        :param context: 插件安装上下文
        :return: None
        """
        context.installed_configs = await context.plugin_service.install_plugin_default_config_services(
            context.session,
            context.discovered_plugin,
        )

        return None

    async def _install_step_run_migrations(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        执行插件 migration。

        :param context: 插件安装上下文
        :return: None
        """
        context.migration_results = await PluginMigrationRunner(
            context.discovered_plugin,
            PluginDatabaseMigrationHistoryStore.with_model_gateway(
                context.plugin_service,
                self.dependencies.model_gateway,
            ),
        ).run(context.session)

        return None

    async def _install_step_run_seeds(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        执行插件 seed。

        :param context: 插件安装上下文
        :return: None
        """
        context.seed_results = await PluginSeedRunner(context.discovered_plugin).run(context.session)

        return None

    async def _install_step_run_install_hook(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        执行插件安装钩子。

        :param context: 插件安装上下文
        :return: None
        """
        context.hook_result = await PluginHookRunner(context.discovered_plugin).run(
            'on_install',
            query_db=context.session,
        )

        return None

    async def _install_step_mark_installed(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        标记插件已安装。

        :param context: 插件安装上下文
        :return: None
        """
        context.plugin = await context.plugin_service.mark_plugin_installed_services(
            context.session,
            context.discovered_plugin,
        )

        return None

    async def _install_step_commit(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        提交安装事务。

        :param context: 插件安装上下文
        :return: None
        """
        await context.session.commit()

        return None

    async def _install_step_close_session(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        关闭安装数据库会话。

        :param context: 插件安装上下文
        :return: None
        """
        if context.session_context is not None:
            await self._close_install_session(context)

        return None

    async def _close_install_session(self, context: PluginInstallLifecycleContext) -> None:
        """
        关闭安装数据库会话。

        :param context: 插件安装上下文
        :return: None
        """
        if context.session_context is None:
            return
        await context.session_context.__aexit__(None, None, None)
        context.session_context = None
        context.session = None

    async def _build_install_precheck(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginPrecheckContext:
        """
        构建安装预检上下文。

        :param context: 插件安装上下文
        :return: 插件预检上下文
        """
        return await self._build_precheck_context(
            cast('Path', context.backend_root),
            cast('DiscoveredPlugin', context.discovered_plugin),
            context.discovered_plugins or [],
        )

    def _refresh_install_actions(
        self,
        precheck: PluginPrecheckContext,
        context: PluginInstallLifecycleContext,
    ) -> None:
        """
        刷新安装预检和动作计划。

        :param precheck: 插件预检上下文
        :param context: 插件安装上下文
        :return: None
        """
        context.precheck = precheck
        context.actions = PluginPayloadBuilder.build_install_actions(
            cast('DiscoveredPlugin', context.discovered_plugin),
            precheck.dependency_result.ok,
            precheck.plugin_dependency_result.ok,
            precheck.structure_result.ok,
            precheck.menu_conflict_result.ok,
        )

    def _build_install_success_payload(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse:
        """
        构建安装成功负载。

        :param context: 插件安装上下文
        :return: 安装成功负载
        """
        return PluginLifecyclePayloadBuilder.build_success_payload(
            context.plugin_id,
            message='插件安装完成',
            actions=context.actions or [],
            precheck=cast('PluginPrecheckContext', context.precheck),
            plugin=context.plugin,
            installed_configs=context.installed_configs,
            migration_results=context.migration_results,
            seed_results=context.seed_results,
            hook_result=context.hook_result,
            extra_payload={'dependencyInstall': context.dependency_install_view or {}},
        )
