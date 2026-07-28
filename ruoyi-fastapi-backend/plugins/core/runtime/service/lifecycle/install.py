from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from plugins.core.lifecycle.migration import PluginMigrationError
from plugins.core.lifecycle.seed import PluginSeedRunner
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.support import (
    PluginLifecyclePayloadBuilder,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginRuntimePayloadBuilder,
)

from .common import PluginLifecycleUseCaseSupport
from .runner import PluginLifecycleStep, PluginLifecycleStepFailed, PluginLifecycleStepRunner

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.lifecycle.migration import PluginMigrationResult
    from plugins.core.lifecycle.seed import PluginSeedResult
    from plugins.core.runtime.hooks import PluginHookResult

    from ..context import PluginRuntimeContextService
    from ..dependency_container import PluginRuntimeDependencies
    from ..responses import PluginLifecycleResponse
    from .operations import PluginLifecycleRuntimeOperations


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
    plugin: object | None = None
    installed_configs: list[object] | None = None
    migration_results: list[PluginMigrationResult] | None = None
    seed_results: list[PluginSeedResult] | None = None
    hook_result: PluginHookResult | None = None
    session: AsyncSession | None = None
    lifecycle_uow: object | None = None
    session_context: object | None = None


class PluginInstallUseCase(PluginLifecycleUseCaseSupport):
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

    async def install_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
        operated_by: str | None = None,
    ) -> PluginLifecycleResponse:
        """
        安装插件并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :param operated_by: 操作者用户名，非预演时写入审计日志
        :return: 插件安装结果负载
        """
        payload = await self._install_plugin(plugin_id, dry_run=dry_run)
        payload_view = cast('dict[str, object]', payload)
        payload_view['operation'] = 'install'
        if not dry_run:
            await self.runtime_operations.record_plugin_failure_state(payload_view, '插件安装失败')
        if record_operation_log and not dry_run:
            if operated_by is not None:
                payload_view['operatedBy'] = operated_by
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
                extra_payload=self._build_migration_failure_extra(exc.original_error),
            )
        except Exception as exc:
            await self._close_install_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件安装失败',
                exc,
                plugin_id=plugin_id,
                failed_step='prepare_install',
                extra_payload=self._build_migration_failure_extra(exc),
            )

    @staticmethod
    def _build_migration_failure_extra(error: Exception) -> dict[str, object] | None:
        """
        构建 migration 失败恢复建议负载。

        :param error: 原始异常
        :return: 额外异常负载
        """
        if not isinstance(error, PluginMigrationError):
            return None

        return {'migrationRecovery': error.to_recovery_payload()}

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
            PluginLifecycleStep('install_jobs', self._install_step_install_jobs),
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
        生成缺失依赖安装计划。

        :param context: 插件安装上下文
        :return: 依赖缺失阻断 payload 或 None
        """
        dependency_install_payload = await self.runtime_operations.install_plugin_dependencies_from_result_async(
            context.plugin_id,
            cast('PluginPrecheckContext', context.precheck).dependency_result,
            dry_run=True,
            discovered_plugin=context.discovered_plugin,
        )
        context.dependency_install_view = cast('dict[str, object]', dependency_install_payload)
        if context.dependency_install_view.get('dependencyOk', False):
            return None

        return PluginLifecyclePayloadBuilder.build_precheck_blocker_payload(
            context.plugin_id,
            message='插件依赖缺失，安装已中止，请先显式安装依赖',
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
        context.session_context = self.dependencies.lifecycle_uow_gateway.open_lifecycle_unit_of_work()
        context.lifecycle_uow = await context.session_context.__aenter__()
        context.session = context.lifecycle_uow.session

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
        installed_menu_conflicts = await context.lifecycle_uow.check_installed_menu_conflicts(
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
        context.plugin = await context.lifecycle_uow.upsert_discovered_plugin(
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
        await context.lifecycle_uow.install_plugin_menu(
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
        context.installed_configs = await context.lifecycle_uow.install_plugin_default_config(
            context.discovered_plugin,
        )

        return None

    async def _install_step_install_jobs(
        self,
        context: PluginInstallLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        同步插件定时任务。

        :param context: 插件安装上下文
        :return: None
        """
        plugin_enabled = getattr(context.plugin, 'enabled', '0') == '0'
        await context.lifecycle_uow.install_plugin_jobs(
            context.discovered_plugin,
            enabled=plugin_enabled,
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
        context.migration_results = await self.dependencies.migration_execution_gateway.run_plugin_migrations(
            context.discovered_plugin,
        )

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
        context.plugin = await context.lifecycle_uow.mark_plugin_installed(
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
        await context.lifecycle_uow.commit()

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
        await self._close_lifecycle_session(context)

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
