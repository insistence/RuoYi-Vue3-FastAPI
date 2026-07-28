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
    from plugins.core.types import PluginStateRecord

    from ..context import PluginRuntimeContextService
    from ..dependency_container import PluginRuntimeDependencies
    from ..responses import PluginLifecycleResponse
    from .operations import PluginLifecycleRuntimeOperations


@dataclass(slots=True)
class PluginUpgradeLifecycleContext:
    """
    插件升级声明式生命周期上下文。
    """

    plugin_id: str
    dry_run: bool
    backend_root: Path | None = None
    discovered_plugins: list[DiscoveredPlugin] | None = None
    discovered_plugin: DiscoveredPlugin | None = None
    precheck: PluginPrecheckContext | None = None
    actions: list[dict[str, object]] | None = None
    database_plugin: PluginStateRecord | None = None
    database_error: str | None = None
    version_state: dict[str, object] | None = None
    plugin: object | None = None
    installed_configs: list[object] | None = None
    migration_results: list[PluginMigrationResult] | None = None
    seed_results: list[PluginSeedResult] | None = None
    hook_result: PluginHookResult | None = None
    session: AsyncSession | None = None
    lifecycle_uow: object | None = None
    session_context: object | None = None


class PluginUpgradeUseCase(PluginLifecycleUseCaseSupport):
    """
    插件升级 use case。
    """

    def __init__(
        self,
        dependencies: PluginRuntimeDependencies,
        runtime_operations: PluginLifecycleRuntimeOperations,
        context: PluginRuntimeContextService,
    ) -> None:
        """
        初始化插件升级 use case。

        :param dependencies: 插件运行时依赖容器
        :param runtime_operations: 生命周期工作流所需的运行时协作能力
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.runtime_operations = runtime_operations
        self.context = context

    async def _load_database_plugin_state(self, plugin_id: str) -> tuple[PluginStateRecord | None, str | None]:
        """
        读取数据库插件状态。

        :param plugin_id: 插件ID
        :return: 数据库插件状态和错误信息
        """
        return await self.context.load_database_plugin_state(plugin_id)

    async def upgrade_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
        operated_by: str | None = None,
    ) -> PluginLifecycleResponse:
        """
        升级插件并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :param operated_by: 操作者用户名，非预演时写入审计日志
        :return: 插件升级结果负载
        """
        payload = await self._upgrade_plugin(plugin_id, dry_run=dry_run)
        payload_view = cast('dict[str, object]', payload)
        payload_view['operation'] = 'upgrade'
        if not dry_run:
            await self.runtime_operations.record_plugin_failure_state(payload_view, '插件升级失败')
        if record_operation_log and not dry_run:
            if operated_by is not None:
                payload_view['operatedBy'] = operated_by
            await self.runtime_operations.record_plugin_operation_log(
                payload_view,
                dry_run=dry_run,
                continue_on_error=False,
            )

        return payload

    async def _upgrade_plugin(self, plugin_id: str, *, dry_run: bool = False) -> PluginLifecycleResponse:
        """
        升级插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件升级结果负载
        """
        context = PluginUpgradeLifecycleContext(plugin_id=plugin_id, dry_run=dry_run)
        try:
            result = await PluginLifecycleStepRunner(self._build_upgrade_steps()).run(context)
            if result.stop:
                await self._close_upgrade_session(result.context)
                return result.stop.payload
            payload = self._build_upgrade_success_payload(result.context)
            payload['operation'] = 'upgrade'
            return self._with_plugin_capability(payload, result.context.discovered_plugin)
        except PluginLifecycleStepFailed as exc:
            await self._close_upgrade_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件升级失败',
                exc.original_error,
                plugin_id=plugin_id,
                failed_step=exc.step_name,
                extra_payload=self._build_migration_failure_extra(exc.original_error),
            )
        except Exception as exc:
            await self._close_upgrade_session(context)
            return PluginRuntimePayloadBuilder.build_exception_payload(
                '插件升级失败',
                exc,
                plugin_id=plugin_id,
                failed_step='prepare_upgrade',
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

    def _build_upgrade_steps(self) -> list[PluginLifecycleStep[PluginUpgradeLifecycleContext]]:
        """
        构建插件升级声明式生命周期步骤。

        :return: 插件升级步骤列表
        """
        return [
            PluginLifecycleStep('discover_plugin', self._upgrade_step_discover_plugin),
            PluginLifecycleStep('build_precheck', self._upgrade_step_build_precheck),
            PluginLifecycleStep('load_installed_plugin', self._upgrade_step_load_installed_plugin),
            PluginLifecycleStep('check_upgrade_blockers', self._upgrade_step_check_upgrade_blockers),
            PluginLifecycleStep('open_session', self._upgrade_step_open_session),
            PluginLifecycleStep('check_installed_menu_conflicts', self._upgrade_step_check_installed_menu_conflicts),
            PluginLifecycleStep('upsert_plugin', self._upgrade_step_upsert_plugin),
            PluginLifecycleStep('install_menus', self._upgrade_step_install_menus),
            PluginLifecycleStep('install_configs', self._upgrade_step_install_configs),
            PluginLifecycleStep('install_jobs', self._upgrade_step_install_jobs),
            PluginLifecycleStep('run_migrations', self._upgrade_step_run_migrations),
            PluginLifecycleStep('run_seeds', self._upgrade_step_run_seeds),
            PluginLifecycleStep('run_upgrade_hook', self._upgrade_step_run_upgrade_hook),
            PluginLifecycleStep('mark_installed', self._upgrade_step_mark_installed),
            PluginLifecycleStep('commit', self._upgrade_step_commit),
            PluginLifecycleStep('close_session', self._upgrade_step_close_session),
        ]

    async def _upgrade_step_discover_plugin(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        发现插件并检查运行模式阻断。

        :param context: 插件升级上下文
        :return: 阻断 payload 或 None
        """
        context.backend_root = Path(self.dependencies.runtime_environment.get_backend_dir())
        context.discovered_plugins = self._discover_plugins(context.backend_root)
        context.discovered_plugin = self._get_discovered_plugin_from_list(context.discovered_plugins, context.plugin_id)
        if not context.discovered_plugin:
            return PluginPayloadBuilder.build_plugin_not_found_payload(context.plugin_id)

        return self._build_operation_blocked_payload(
            context.discovered_plugin,
            'upgrade',
            dry_run=context.dry_run,
        )

    async def _upgrade_step_build_precheck(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        构建升级预检和动作计划。

        :param context: 插件升级上下文
        :return: dry-run payload 或 None
        """
        precheck = await self._build_upgrade_precheck(context)
        self._refresh_upgrade_actions(precheck, context)
        if not context.dry_run:
            return None

        context.database_plugin, context.database_error = await self._load_database_plugin_state(context.plugin_id)
        context.version_state = PluginPayloadBuilder.build_upgrade_version_state(
            context.discovered_plugin,
            context.database_plugin,
        )
        payload = PluginPayloadBuilder.build_upgrade_dry_run_payload(
            context.plugin_id,
            self._build_upgrade_operation_payload(context),
            database_error=context.database_error,
        )
        payload['operation'] = 'upgrade'
        return self._with_plugin_capability(payload, context.discovered_plugin)

    async def _upgrade_step_load_installed_plugin(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        读取已安装插件状态。

        :param context: 插件升级上下文
        :return: None
        """
        context.database_plugin = await self.dependencies.state_query_gateway.get_plugin_state(context.plugin_id)
        context.version_state = PluginPayloadBuilder.build_upgrade_version_state(
            context.discovered_plugin,
            context.database_plugin,
        )

        return None

    async def _upgrade_step_open_session(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        打开升级生命周期主事务工作单元。

        :param context: 插件升级上下文
        :return: None
        """
        context.session_context = self.dependencies.lifecycle_uow_gateway.open_lifecycle_unit_of_work()
        context.lifecycle_uow = await context.session_context.__aenter__()
        context.session = context.lifecycle_uow.session

        return None

    async def _upgrade_step_check_upgrade_blockers(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        检查升级执行前阻断。

        :param context: 插件升级上下文
        :return: 阻断 payload 或 None
        """
        blocker_payload = PluginRuntimePayloadBuilder.build_upgrade_pre_execution_blocker(
            context.plugin_id,
            context.version_state or {},
            context.actions or [],
            cast('PluginPrecheckContext', context.precheck),
        )
        if blocker_payload:
            return blocker_payload
        if not (context.version_state or {}).get('needsUpgrade'):
            payload = PluginLifecyclePayloadBuilder.build_upgrade_latest_payload(
                context.plugin_id,
                context.version_state or {},
                cast('PluginPrecheckContext', context.precheck),
            )
            payload['operation'] = 'upgrade'
            return self._with_plugin_capability(payload, context.discovered_plugin)

        return PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
            context.plugin_id,
            operation='upgrade',
            actions=context.actions or [],
            precheck=cast('PluginPrecheckContext', context.precheck),
            extra_payload=context.version_state or {},
        )

    async def _upgrade_step_check_installed_menu_conflicts(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        检查已安装菜单冲突。

        :param context: 插件升级上下文
        :return: 菜单冲突 payload 或 None
        """
        installed_menu_conflicts = await context.lifecycle_uow.check_installed_menu_conflicts(
            context.discovered_plugin,
        )
        if not installed_menu_conflicts:
            return None

        return PluginLifecyclePayloadBuilder.build_installed_menu_conflict_payload(
            context.plugin_id,
            message='插件菜单与已安装菜单存在冲突，升级已中止',
            actions=context.actions or [],
            precheck=cast('PluginPrecheckContext', context.precheck),
            installed_menu_conflicts=installed_menu_conflicts,
            extra_payload=context.version_state or {},
        )

    async def _upgrade_step_upsert_plugin(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        更新插件基础状态。

        :param context: 插件升级上下文
        :return: None
        """
        await context.lifecycle_uow.upsert_discovered_plugin(
            context.discovered_plugin,
            Path(self.dependencies.runtime_environment.get_backend_plugins_dir()),
            Path(self.dependencies.runtime_environment.get_frontend_plugins_dir()),
        )

        return None

    async def _upgrade_step_install_menus(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        安装已启用插件菜单。

        :param context: 插件升级上下文
        :return: None
        """
        plugin_enabled = getattr(context.database_plugin, 'enabled', '1') == '0'
        await context.lifecycle_uow.install_plugin_menu(
            context.discovered_plugin,
            enabled=plugin_enabled,
        )

        return None

    async def _upgrade_step_install_configs(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        安装新增默认配置。

        :param context: 插件升级上下文
        :return: None
        """
        context.installed_configs = await context.lifecycle_uow.install_plugin_default_config(
            context.discovered_plugin,
        )

        return None

    async def _upgrade_step_install_jobs(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        同步升级后插件定时任务。

        :param context: 插件升级上下文
        :return: None
        """
        plugin_enabled = getattr(context.database_plugin, 'enabled', '1') == '0'
        await context.lifecycle_uow.install_plugin_jobs(
            context.discovered_plugin,
            enabled=plugin_enabled,
        )

        return None

    async def _upgrade_step_run_migrations(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        执行升级 migration。

        :param context: 插件升级上下文
        :return: None
        """
        context.migration_results = await self.dependencies.migration_execution_gateway.run_plugin_migrations(
            context.discovered_plugin,
        )

        return None

    async def _upgrade_step_run_seeds(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        执行升级 seed。

        :param context: 插件升级上下文
        :return: None
        """
        context.seed_results = await PluginSeedRunner(context.discovered_plugin).run(context.session)

        return None

    async def _upgrade_step_run_upgrade_hook(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        执行升级钩子。

        :param context: 插件升级上下文
        :return: None
        """
        context.hook_result = await PluginHookRunner(context.discovered_plugin).run(
            'on_upgrade',
            query_db=context.session,
        )

        return None

    async def _upgrade_step_mark_installed(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        标记插件已安装。

        :param context: 插件升级上下文
        :return: None
        """
        context.plugin = await context.lifecycle_uow.mark_plugin_installed(
            context.discovered_plugin,
        )

        return None

    async def _upgrade_step_commit(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        提交升级事务。

        :param context: 插件升级上下文
        :return: None
        """
        await context.lifecycle_uow.commit()

        return None

    async def _upgrade_step_close_session(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse | None:
        """
        关闭升级数据库会话。

        :param context: 插件升级上下文
        :return: None
        """
        await self._close_upgrade_session(context)

        return None

    async def _build_upgrade_precheck(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginPrecheckContext:
        """
        构建升级预检上下文。

        :param context: 插件升级上下文
        :return: 插件预检上下文
        """
        return await self._build_precheck_context(
            cast('Path', context.backend_root),
            cast('DiscoveredPlugin', context.discovered_plugin),
            context.discovered_plugins or [],
        )

    def _refresh_upgrade_actions(
        self,
        precheck: PluginPrecheckContext,
        context: PluginUpgradeLifecycleContext,
    ) -> None:
        """
        刷新升级预检和动作计划。

        :param precheck: 插件预检上下文
        :param context: 插件升级上下文
        :return: None
        """
        context.precheck = precheck
        context.actions = PluginPayloadBuilder.build_upgrade_actions(
            cast('DiscoveredPlugin', context.discovered_plugin),
            precheck.dependency_result.ok,
            precheck.plugin_dependency_result.ok,
            precheck.structure_result.ok,
            precheck.menu_conflict_result.ok,
        )

    def _build_upgrade_operation_payload(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> dict[str, object]:
        """
        构建升级预检操作 payload。

        :param context: 插件升级上下文
        :return: 升级操作 payload
        """
        precheck = cast('PluginPrecheckContext', context.precheck)
        return {
            'versionState': context.version_state or {},
            'dependencyResult': precheck.dependency_result,
            'pluginDependencyResult': precheck.plugin_dependency_result,
            'structureResult': precheck.structure_result,
            'menuConflictResult': precheck.menu_conflict_result,
            'actions': context.actions or [],
            'manifestOk': precheck.manifest_result.ok,
            'manifestIssues': precheck.manifest_issues,
            'manifestWarnings': precheck.manifest_warnings,
            'pluginDependencyErrors': precheck.plugin_dependency_errors,
            'structureErrors': precheck.structure_errors,
            'menuConflicts': precheck.menu_conflicts,
        }

    def _build_upgrade_success_payload(
        self,
        context: PluginUpgradeLifecycleContext,
    ) -> PluginLifecycleResponse:
        """
        构建升级成功负载。

        :param context: 插件升级上下文
        :return: 升级成功负载
        """
        return PluginLifecyclePayloadBuilder.build_success_payload(
            context.plugin_id,
            message='插件升级完成',
            actions=context.actions or [],
            precheck=cast('PluginPrecheckContext', context.precheck),
            plugin=context.plugin,
            installed_configs=context.installed_configs,
            migration_results=context.migration_results,
            seed_results=context.seed_results,
            hook_result=context.hook_result,
            extra_payload=context.version_state or {},
        )

    async def _close_upgrade_session(self, context: PluginUpgradeLifecycleContext) -> None:
        """
        关闭升级数据库会话。

        :param context: 插件升级上下文
        :return: None
        """
        await self._close_lifecycle_session(context)
