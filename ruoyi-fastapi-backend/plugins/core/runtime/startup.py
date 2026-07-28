import asyncio
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from common.router import auto_register_controller_files
from config.database import AsyncSessionLocal
from config.env import AppConfig
from config.get_db import get_db
from plugins.core.discovery.registry import PluginRegistry, RegisteredPlugin
from plugins.core.lifecycle.migration import (
    PluginMigrationHistoryRecord,
    PluginMigrationHistoryStore,
    PluginMigrationRunner,
)
from plugins.core.lifecycle.seed import PluginSeedRunner
from plugins.core.runtime.bootstrap import PluginRuntimeBuilder
from plugins.core.runtime.hooks import PluginHookRunner
from plugins.core.runtime.route_guard import (
    PluginEnabledDependency,
    PluginRouteStateGateway,
    UnavailablePluginRouteStateGateway,
)
from plugins.core.runtime.service.gateway import DefaultPluginCommandRunnerGateway, PluginCommandRunnerGateway
from plugins.core.runtime.startup_gateway import (
    PluginStartupManagementGateway,
    UnavailablePluginStartupManagementGateway,
)
from plugins.core.validation.dependencies import (
    PLUGIN_STARTUP_DEPENDENCY_ERROR_PREFIX,
    DependencyCheckResult,
    PluginDependencyInstallPlanner,
    PythonDependencyInspector,
)
from plugins.core.validation.structure import PluginStructureChecker
from utils.log_util import logger


class PluginStartupMigrationHistoryStore(PluginMigrationHistoryStore):
    """
    启动期插件 migration 历史存储适配器。
    """

    def __init__(self, management_gateway: PluginStartupManagementGateway, async_session_local: Any = None) -> None:
        """
        初始化启动期 migration 历史存储。

        :param management_gateway: 插件启动期管理端口
        :param async_session_local: 独立数据库会话工厂
        :return: None
        """
        self.management_gateway = management_gateway
        self.async_session_local = async_session_local

    async def get_record(
        self,
        query_db: Any,
        plugin_id: str,
        migration_path: str,
    ) -> PluginMigrationHistoryRecord | None:
        """
        获取 migration 执行历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: migration 执行历史
        """
        plugin_migration = await self.management_gateway.get_plugin_migration(query_db, plugin_id, migration_path)
        if not plugin_migration:
            return None
        return PluginMigrationHistoryRecord(
            checksum=plugin_migration.migration_checksum,
            status=getattr(plugin_migration, 'status', 'success'),
            error_message=getattr(plugin_migration, 'error_message', None),
        )

    async def record_running(
        self,
        query_db: Any,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
    ) -> None:
        """
        记录 migration 开始执行。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param checksum: 内容校验值
        :param version: 执行时插件版本
        :param statement_count: SQL 语句数量
        :return: None
        """
        await self._add_plugin_migration(
            query_db,
            self.management_gateway.build_migration_record(
                plugin_id,
                migration_path,
                checksum,
                version,
                statement_count,
                'running',
            ),
        )

    async def record_success(
        self,
        query_db: Any,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
    ) -> None:
        """
        记录 migration 成功执行历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param checksum: 内容校验值
        :param version: 执行时插件版本
        :param statement_count: SQL 语句数量
        :return: None
        """
        await self._add_plugin_migration(
            query_db,
            self.management_gateway.build_migration_record(
                plugin_id,
                migration_path,
                checksum,
                version,
                statement_count,
            ),
        )

    async def record_failure(
        self,
        query_db: Any,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
        error_message: str,
    ) -> None:
        """
        记录 migration 执行失败历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param checksum: 内容校验值
        :param version: 执行时插件版本
        :param statement_count: SQL 语句数量
        :param error_message: 失败错误信息
        :return: None
        """
        await self._add_plugin_migration(
            query_db,
            self.management_gateway.build_migration_record(
                plugin_id,
                migration_path,
                checksum,
                version,
                statement_count,
                'failed',
                error_message,
            ),
        )

    async def _add_plugin_migration(self, query_db: Any, plugin_migration: Any) -> None:
        """
        写入 migration 历史，优先使用独立会话提交。

        :param query_db: 当前启动期 orm对象
        :param plugin_migration: migration 历史模型
        :return: None
        """
        if self.async_session_local is None:
            await self.management_gateway.add_plugin_migration(query_db, plugin_migration)
            return

        async with self.async_session_local() as session:
            await self.management_gateway.add_plugin_migration(session, plugin_migration)
            await session.commit()


class PluginRuntimeStartupManager:
    """
    插件运行时启动协调器。

    将插件发现、实体导入、资源安装、路由注册和生命周期钩子从应用入口中隔离出来，
    让 server.py 只保留高层启动顺序。
    """

    def __init__(
        self,
        builder: PluginRuntimeBuilder | None = None,
        management_gateway: PluginStartupManagementGateway | None = None,
        route_state_gateway: PluginRouteStateGateway | None = None,
        python_dependency_inspector: PythonDependencyInspector | None = None,
        python_dependency_inspector_factory: Callable[[], PythonDependencyInspector] | None = None,
        command_runner_gateway: PluginCommandRunnerGateway | None = None,
        default_enabled_builtin_plugin_ids: set[str] | None = None,
    ) -> None:
        """
        初始化插件运行时启动协调器。

        :param builder: 插件运行时构建器
        :param management_gateway: 插件启动期管理端口
        :param route_state_gateway: 插件路由状态读取端口
        :param python_dependency_inspector: Python 依赖检查器
        :param python_dependency_inspector_factory: Python 依赖检查器工厂
        :param command_runner_gateway: 插件命令执行网关
        :param default_enabled_builtin_plugin_ids: 首次启动默认安装启用的内置插件 ID 集合
        :return: None
        """
        self.builder = builder or PluginRuntimeBuilder()
        self.management_gateway = management_gateway or UnavailablePluginStartupManagementGateway()
        self.route_state_gateway = route_state_gateway or UnavailablePluginRouteStateGateway()
        self.python_dependency_inspector_factory = python_dependency_inspector_factory or PythonDependencyInspector
        self.python_dependency_inspector = python_dependency_inspector or self.python_dependency_inspector_factory()
        self.command_runner_gateway = command_runner_gateway or DefaultPluginCommandRunnerGateway()
        self.default_enabled_builtin_plugin_ids = (
            self.parse_default_enabled_builtin_plugin_ids(AppConfig.app_default_enabled_plugins)
            if default_enabled_builtin_plugin_ids is None
            else set(default_enabled_builtin_plugin_ids)
        )

    def bind_app(self, app: FastAPI) -> None:
        """
        绑定插件运行时对象到 FastAPI state。

        :param app: FastAPI对象
        :return: None
        """
        app.state.plugin_runtime_startup = self
        app.state.plugin_runtime_builder = self.builder
        if not hasattr(app.state, 'plugin_registry'):
            app.state.plugin_registry = self.builder.build_registry()
        if not hasattr(app.state, 'plugin_routes_registered'):
            app.state.plugin_routes_registered = False

    def import_builtin_entities(self) -> None:
        """
        导入内置业务模块实体。

        :return: None
        """
        self.builder.import_builtin_entities()

    @staticmethod
    def parse_default_enabled_builtin_plugin_ids(plugin_ids: str) -> set[str]:
        """
        解析默认启用内置插件配置。

        :param plugin_ids: 逗号分隔的插件 ID 配置
        :return: 插件 ID 集合
        """
        return {plugin_id.strip() for plugin_id in plugin_ids.split(',') if plugin_id.strip()}

    async def prepare_enabled_plugins(self, app: FastAPI, *, startup_write_enabled: bool = True) -> None:
        """
        准备启用插件运行时实体。

        :param app: FastAPI对象
        :param startup_write_enabled: 是否允许执行启动期写库操作
        :return: None
        """
        default_dependency_failed_plugin_ids: set[str] = set()
        if startup_write_enabled:
            default_dependency_failed_plugin_ids = await self.sync_default_enabled_builtin_plugin_install_states()
        await self.load_registry_from_database(app)
        dependency_failed_plugin_ids = await self.check_enabled_plugin_python_dependencies(
            app,
            startup_write_enabled=startup_write_enabled,
        )
        app.state.plugin_dependency_failed_plugin_ids = (
            default_dependency_failed_plugin_ids | dependency_failed_plugin_ids
        )
        self.disable_runtime_plugins(app, dependency_failed_plugin_ids)
        import_failed_plugin_ids = await self.import_enabled_plugin_entities(
            app,
            startup_write_enabled=startup_write_enabled,
        )
        self.disable_runtime_plugins(app, import_failed_plugin_ids)

    async def requires_startup_write(self) -> bool:
        """
        判断当前数据库状态是否要求重新执行启动期全局写入。

        Redis ready 标记用于协调同一代际的并发 worker，但它的生命周期可能长于
        数据库本身。数据库被重建、清空或恢复旧快照后，默认启用插件可能重新缺少
        安装状态，此时不能复用旧 ready 标记。

        :return: 是否需要重新执行启动期写入
        """
        if not self.default_enabled_builtin_plugin_ids:
            return False

        discovered_plugin_ids = {
            plugin.manifest.id
            for plugin in self.builder.discover_plugins()
            if plugin.manifest.id in self.default_enabled_builtin_plugin_ids
        }
        if not discovered_plugin_ids:
            return False

        async for query_db in get_db():
            plugin_list = await self.management_gateway.list_plugins(query_db)
            database_plugin_map = {plugin.plugin_id: plugin for plugin in plugin_list}
            return any(
                self._should_sync_default_enabled_builtin_plugin(database_plugin_map.get(plugin_id))
                for plugin_id in discovered_plugin_ids
            )

        return True

    async def check_enabled_plugin_python_dependencies(
        self,
        app: FastAPI,
        *,
        startup_write_enabled: bool = True,
    ) -> set[str]:
        """
        检查启用插件的 Python 依赖，缺失时标记插件运行时异常。

        :param app: FastAPI对象
        :param startup_write_enabled: 是否允许执行启动期写库操作
        :return: 依赖检查失败的插件 ID 集合
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return set()

        self.python_dependency_inspector.refresh()
        failed_plugin_ids: set[str] = set()
        recovered_plugins: list[RegisteredPlugin] = []
        for plugin in self._list_dependency_check_plugins(plugin_registry):
            python_requirements = plugin.discovered_plugin.manifest.dependencies.python
            failed_messages = []
            if python_requirements:
                dependency_result = self._check_plugin_python_dependencies(plugin.plugin_id, python_requirements)
                failed_messages = self._build_dependency_failed_messages(dependency_result)
            if not failed_messages:
                if startup_write_enabled and self._has_startup_dependency_error(plugin):
                    recovered_plugins.append(plugin)
                continue
            failed_plugin_ids.add(plugin.plugin_id)
            error_message = self._build_dependency_startup_error_message(plugin.plugin_id, failed_messages)
            logger.bind(
                plugin_id=plugin.plugin_id,
                startup_generation=getattr(app.state, 'plugin_startup_generation', None),
                plugin_startup_role_at_creation='writer' if startup_write_enabled else 'reader',
                startup_write_enabled=startup_write_enabled,
            ).error(f'❌ {error_message}')
            if startup_write_enabled:
                await self.mark_plugin_runtime_error(app, plugin.plugin_id, error_message)

        if recovered_plugins:
            await self.recover_plugin_dependency_errors(app, recovered_plugins)
        return failed_plugin_ids

    @classmethod
    def _list_dependency_check_plugins(cls, plugin_registry: PluginRegistry) -> list[RegisteredPlugin]:
        """
        获取本次启动需要检查 Python 依赖的插件。

        除当前启用插件外，还要重新检查上次因启动依赖失败而被隔离的插件，
        避免其进入 error 状态后在后续启动中被启用态过滤器永久跳过。

        :param plugin_registry: 插件运行时注册表
        :return: 需要检查依赖的插件列表
        """
        plugins = list(plugin_registry.list_enabled_plugins())
        checked_plugin_ids = {plugin.plugin_id for plugin in plugins}
        for plugin in plugin_registry.list_plugins():
            if plugin.plugin_id in checked_plugin_ids:
                continue
            if cls._has_startup_dependency_error(plugin):
                plugins.append(plugin)
                checked_plugin_ids.add(plugin.plugin_id)
        return plugins

    @staticmethod
    def _has_startup_dependency_error(plugin: RegisteredPlugin) -> bool:
        """
        判断插件是否仅因启动依赖检查失败而处于异常状态。

        :param plugin: 插件运行时快照
        :return: 是否为启动依赖异常
        """
        database_plugin = plugin.database_plugin
        last_error = getattr(database_plugin, 'last_error', None) if database_plugin else None
        return (
            getattr(database_plugin, 'status', None) == 'error'
            and isinstance(last_error, str)
            and last_error.startswith(PLUGIN_STARTUP_DEPENDENCY_ERROR_PREFIX)
        )

    async def recover_plugin_dependency_errors(
        self,
        app: FastAPI,
        plugins: list[RegisteredPlugin],
    ) -> None:
        """
        恢复启动依赖重新满足的插件状态，并刷新运行时注册表。

        仅处理带启动依赖错误前缀的插件，其他 migration、实体导入或 hook
        异常仍保持 error，避免启动时误清除真实故障。

        :param app: FastAPI对象
        :param plugins: 依赖已恢复的插件列表
        :return: None
        """
        recovered = False
        async for query_db in get_db():
            for plugin in plugins:
                result = await self.management_gateway.recover_plugin_dependency_error(
                    query_db,
                    plugin.discovered_plugin,
                )
                if result.is_success:
                    recovered = True
                    logger.info(f'✅ 插件启动依赖已恢复：{plugin.plugin_id}')
                    continue
                logger.warning(f'⚠️ 插件启动依赖恢复状态写入失败：{plugin.plugin_id}，原因：{result.message}')
            if recovered:
                await query_db.commit()
            else:
                await query_db.rollback()
        if recovered:
            await self.load_registry_from_database(app)

    def _check_plugin_python_dependencies(
        self,
        plugin_id: str,
        python_requirements: list[str],
    ) -> DependencyCheckResult:
        """
        检查单个插件 Python 依赖。

        :param plugin_id: 插件ID
        :param python_requirements: Python 依赖声明列表
        :return: 依赖检查结果
        """
        return DependencyCheckResult(
            plugin_id=plugin_id, items=self.python_dependency_inspector.check(python_requirements)
        )

    @staticmethod
    def _build_dependency_failed_messages(dependency_result: DependencyCheckResult) -> list[str]:
        """
        构建依赖检查失败消息。

        :param dependency_result: 依赖检查结果
        :return: 失败消息列表
        """
        return [item.message for item in dependency_result.items if not item.ok]

    @staticmethod
    def _build_dependency_startup_error_message(plugin_id: str, failed_messages: list[str]) -> str:
        """
        构建包含修复命令的启动依赖检查失败消息。

        :param plugin_id: 插件ID
        :param failed_messages: 依赖检查失败消息
        :return: 启动依赖检查失败消息
        """
        install_command = f'ruoyi plugin install-deps {plugin_id} --env={AppConfig.app_env} --yes'
        return (
            f'{PLUGIN_STARTUP_DEPENDENCY_ERROR_PREFIX}{"；".join(failed_messages)}；安装依赖请执行：{install_command}'
        )

    async def _prompt_and_install_plugin_python_dependencies(
        self,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
    ) -> bool:
        """
        在 TTY 环境中询问是否安装插件 Python 依赖。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :return: 是否已尝试安装依赖
        """
        if not self._can_prompt_dependency_install():
            return False
        failed_messages = self._build_dependency_failed_messages(dependency_result)
        print(f'插件 {plugin_id} 缺少启动所需 Python 依赖：', file=sys.stderr)
        for message in failed_messages:
            print(f'- {message}', file=sys.stderr)
        answer = (await asyncio.to_thread(input, '是否立即安装缺失依赖？[y/N] ')).strip().lower()
        if answer not in {'y', 'yes'}:
            return False
        await self._install_plugin_python_dependencies(dependency_result)
        self.python_dependency_inspector = self.python_dependency_inspector_factory()
        return True

    @staticmethod
    def _can_prompt_dependency_install() -> bool:
        """
        判断当前启动环境是否支持交互确认。

        :return: 是否支持交互确认
        """
        _ = AppConfig.app_workers
        _ = sys.stdin.isatty()
        return False

    async def _install_plugin_python_dependencies(self, dependency_result: DependencyCheckResult) -> None:
        """
        安装插件 Python 依赖。

        :param dependency_result: 依赖检查结果
        :return: None
        """
        install_plan = PluginDependencyInstallPlanner().build_plan(dependency_result)
        for item in install_plan.items:
            if item.kind != 'python':
                continue
            completed = await asyncio.to_thread(
                self.command_runner_gateway.run_command,
                item.command,
                item.workdir,
            )
            if completed.returncode == 0:
                logger.info(f'✅ 插件 {dependency_result.plugin_id} Python 依赖安装完成：{item.requirement}')
                continue
            logger.error(
                f'❌ 插件 {dependency_result.plugin_id} Python 依赖安装失败：{item.requirement}，'
                f'returncode={completed.returncode}，stderr={completed.stderr[-500:]}'
            )

    async def activate_enabled_plugins(self, app: FastAPI, *, startup_write_enabled: bool = True) -> None:
        """
        激活启用插件运行时资源。

        :param app: FastAPI对象
        :param startup_write_enabled: 是否允许执行启动期写库操作
        :return: None
        """
        if startup_write_enabled:
            await self.sync_enabled_plugin_install_states(app)
            await self.install_enabled_plugin_resources(app)
        await self.run_enabled_plugin_hooks(app, 'on_startup', startup_write_enabled=startup_write_enabled)
        self.register_enabled_plugin_routers(app, startup_write_enabled=startup_write_enabled)

    async def shutdown(self, app: FastAPI, *, startup_write_enabled: bool = True) -> None:
        """
        执行插件运行时关闭接入流程。

        :param app: FastAPI对象
        :param startup_write_enabled: 是否允许执行启动期写库操作
        :return: None
        """
        await self.run_enabled_plugin_hooks(app, 'on_shutdown', startup_write_enabled=startup_write_enabled)

    async def load_registry_from_database(self, app: FastAPI) -> None:
        """
        从数据库插件状态构建运行时插件注册表。

        :param app: FastAPI对象
        :return: None
        """
        async for query_db in get_db():
            plugin_list = await self.management_gateway.list_plugins(query_db)
            app.state.plugin_registry = self.builder.build_registry(plugin_list)

    async def import_enabled_plugin_entities(
        self,
        app: FastAPI,
        *,
        startup_write_enabled: bool = True,
    ) -> set[str]:
        """
        导入启用插件实体并标记导入失败插件。

        :param app: FastAPI对象
        :param startup_write_enabled: 是否允许执行启动期写库操作
        :return: 实体导入失败的插件 ID 集合
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return set()

        import_result = self.builder.import_plugin_entities(plugin_registry)
        failed_plugin_ids: set[str] = set()
        for failure in import_result.failures:
            failed_plugin_ids.add(failure.plugin_id)
            logger.bind(
                plugin_id=failure.plugin_id,
                startup_generation=getattr(app.state, 'plugin_startup_generation', None),
                plugin_startup_role_at_creation='writer' if startup_write_enabled else 'reader',
                startup_write_enabled=startup_write_enabled,
            ).error(f'❌ 插件实体导入失败：{failure.error_message}')
            if startup_write_enabled:
                await self.mark_plugin_runtime_error(app, failure.plugin_id, failure.error_message)

        return failed_plugin_ids

    async def install_enabled_plugin_resources(self, app: FastAPI) -> None:
        """
        逐插件同步启用插件的启动期资源。

        每个插件使用独立事务，单个插件资源声明或数据库写入失败时仅隔离该插件，
        不再回滚其他插件或阻断宿主应用启动。

        :param app: FastAPI对象
        :return: None
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return

        plugins = list(plugin_registry.list_enabled_plugins())
        for plugin in plugins:
            await self.install_plugin_resources_with_isolation(app, plugin)

    async def install_plugin_resources_with_isolation(
        self,
        app: FastAPI,
        plugin: RegisteredPlugin,
    ) -> None:
        """
        在独立事务中同步单个插件资源，失败时隔离该插件。

        :param app: FastAPI对象
        :param plugin: 插件运行时快照
        :return: None
        """
        with logger.contextualize(
            plugin_id=plugin.plugin_id,
            plugin_startup_role_at_creation='writer',
            startup_write_enabled=True,
        ):
            logger.info('🔄 开始同步单插件启动资源')
            try:
                async for query_db in get_db():
                    try:
                        await self.management_gateway.install_plugin_resources(
                            query_db,
                            plugin.discovered_plugin,
                            enabled=True,
                        )
                        await query_db.commit()
                    except Exception:
                        await query_db.rollback()
                        raise
            except Exception as exc:
                error_message = f'插件启动资源同步失败：{exc}'
                logger.exception(f'❌ {error_message}')
                await self.mark_plugin_runtime_error(app, plugin.plugin_id, error_message)
                return
            logger.info('✅ 单插件启动资源同步完成')

    async def sync_enabled_plugin_install_states(self, app: FastAPI) -> None:
        """
        将默认启用且尚未持久化安装状态的插件标记为已安装。

        :param app: FastAPI对象
        :return: None
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return

        plugins_to_sync = [
            plugin
            for plugin in plugin_registry.list_enabled_plugins()
            if self._should_sync_plugin_install_state(plugin)
        ]
        if not plugins_to_sync:
            return

        for plugin in plugins_to_sync:
            await self.sync_plugin_install_with_isolation(app, plugin)

        await self.load_registry_from_database(app)

    async def sync_plugin_install_with_isolation(
        self,
        app: FastAPI,
        plugin: RegisteredPlugin,
    ) -> None:
        """
        执行单插件启动安装，失败时记录错误并继续其他插件。

        :param app: FastAPI对象
        :param plugin: 插件运行时快照
        :return: None
        """
        try:
            await self.sync_plugin_install(plugin.discovered_plugin, enabled=True)
        except Exception as exc:
            error_message = f'插件启动安装失败：{exc}'
            logger.exception(f'❌ {plugin.plugin_id} {error_message}')
            await self.mark_plugin_runtime_error(app, plugin.plugin_id, error_message)

    async def sync_plugin_install(self, discovered_plugin: Any, *, enabled: bool) -> None:
        """
        使用独立事务执行单个插件的启动期安装生命周期。

        启动期首次安装与管理端安装保持相同的关键步骤：结构校验、发现状态写入、
        资源同步、migration、seed、on_install 钩子和最终安装状态写入。

        :param discovered_plugin: 已发现插件对象
        :param enabled: 插件资源是否启用
        :return: None
        """
        plugin_id = discovered_plugin.manifest.id
        with logger.contextualize(
            plugin_id=plugin_id,
            plugin_startup_role_at_creation='writer',
            startup_write_enabled=True,
        ):
            logger.info('🔄 开始执行插件启动安装生命周期')
            self.validate_plugin_structure(discovered_plugin)
            async for query_db in get_db():
                try:
                    await self.management_gateway.upsert_discovered_plugin(
                        query_db,
                        discovered_plugin,
                        self.builder.plugins_root,
                        self.builder.frontend_plugins_root,
                    )
                    await self.management_gateway.install_plugin_resources(
                        query_db,
                        discovered_plugin,
                        enabled=enabled,
                    )
                    await self.run_plugin_install_scripts(query_db, discovered_plugin)
                    await self.run_plugin_install_hook(query_db, discovered_plugin)
                    await self.management_gateway.mark_plugin_installed(query_db, discovered_plugin)
                    await query_db.commit()
                except Exception:
                    await query_db.rollback()
                    raise
            logger.info('✅ 插件启动安装生命周期执行完成')

    @staticmethod
    async def run_plugin_install_hook(query_db: Any, discovered_plugin: Any) -> None:
        """
        执行插件首次安装钩子。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: None
        """
        await PluginHookRunner(discovered_plugin).run('on_install', query_db=query_db)

    def validate_plugin_structure(self, discovered_plugin: Any) -> None:
        """
        校验启动期首次安装插件的目录和声明引用。

        :param discovered_plugin: 已发现插件对象
        :return: None
        :raises ValueError: 插件结构校验失败
        """
        result = PluginStructureChecker(
            self.builder.backend_root,
            self.builder.frontend_plugins_root,
        ).check(discovered_plugin)
        if result.ok:
            return
        messages = '；'.join(item.message for item in result.failed_items)
        raise ValueError(f'插件结构校验失败：{messages}')

    @staticmethod
    def _should_sync_plugin_install_state(plugin: RegisteredPlugin) -> bool:
        """
        判断启用插件是否需要在启动期同步安装状态。

        :param plugin: 插件运行时快照
        :return: 是否需要同步
        """
        database_plugin = plugin.database_plugin
        if database_plugin is None:
            return True
        return (
            not getattr(database_plugin, 'installed_version', None)
            and getattr(database_plugin, 'status', None) == 'discovered'
        )

    async def run_plugin_install_scripts(self, query_db: Any, discovered_plugin: Any) -> None:
        """
        执行插件安装期数据库脚本。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: None
        """
        async with AsyncSessionLocal() as migration_session:
            await PluginMigrationRunner(
                discovered_plugin,
                PluginStartupMigrationHistoryStore(self.management_gateway, AsyncSessionLocal),
                manage_execution_transaction=True,
            ).run(migration_session)
        await self.run_plugin_seed_scripts(query_db, discovered_plugin)

    @staticmethod
    async def run_plugin_seed_scripts(query_db: Any, discovered_plugin: Any) -> None:
        """
        执行插件 seed 脚本。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: None
        """
        await PluginSeedRunner(discovered_plugin).run(query_db)

    def register_enabled_plugin_routers(
        self,
        app: FastAPI,
        *,
        startup_write_enabled: bool = True,
    ) -> None:
        """
        注册启用插件 controller 路由。

        :param app: FastAPI对象
        :param startup_write_enabled: 当前worker是否为插件启动writer
        :return: None
        """
        if getattr(app.state, 'plugin_routes_registered', False):
            return
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        plugin_ids = []
        if plugin_registry:
            plugin_ids = [
                plugin.plugin_id
                for plugin in plugin_registry.list_enabled_plugins()
                if plugin.discovered_plugin.manifest.backend.routers.auto_scan
            ]
        for plugin_id in plugin_ids:
            with logger.contextualize(
                plugin_id=plugin_id,
                startup_generation=getattr(app.state, 'plugin_startup_generation', None),
                plugin_startup_role_at_creation='writer' if startup_write_enabled else 'reader',
                startup_write_enabled=startup_write_enabled,
            ):
                controller_files = self._find_plugin_controller_files([plugin_id])
                controller_files = self._filter_plugin_controller_files_by_route_prefix(plugin_id, controller_files)
                if controller_files:
                    auto_register_controller_files(
                        app,
                        controller_files,
                        dependencies=[PluginEnabledDependency(plugin_id, self.route_state_gateway)],
                    )
        app.state.plugin_routes_registered = True

    def _filter_plugin_controller_files_by_route_prefix(self, plugin_id: str, controller_files: list[str]) -> list[str]:
        """
        启动期再次校验插件 controller 路由前缀，避免绕过预检注册宿主命名空间路由。

        :param plugin_id: 插件ID
        :param controller_files: controller 文件路径列表
        :return: 通过命名空间校验的 controller 文件路径列表
        """
        checker = PluginStructureChecker(self.builder.backend_root)
        valid_controller_files = []
        for controller_file in controller_files:
            check_items = checker.check_controller_file_route_prefixes(plugin_id, Path(controller_file))
            if not check_items:
                logger.error(f'❌ 插件 {plugin_id} controller 路由前缀无法静态确认，启动期跳过注册：{controller_file}')
                continue
            failed_items = [item for item in check_items if not item.ok]
            if failed_items:
                logger.error(
                    f'❌ 插件 {plugin_id} controller 路由前缀非法，启动期跳过注册：'
                    f'{"、".join(item.message for item in failed_items)}'
                )
                continue
            valid_controller_files.append(controller_file)

        return valid_controller_files

    def _find_plugin_controller_files(self, plugin_ids: list[str]) -> list[str]:
        """
        查找启用插件 controller 目录下的路由文件。

        :param plugin_ids: 插件ID列表
        :return: 插件controller文件路径列表
        """
        backend_root = self.builder.backend_root
        plugins_root = backend_root / 'plugins'
        controller_files = []
        for plugin_id in plugin_ids:
            controller_dir = plugins_root / plugin_id / 'controller'
            if not controller_dir.is_dir():
                continue
            controller_files.extend(str(path) for path in controller_dir.glob('[!_]*.py'))

        return sorted(controller_files)

    async def run_enabled_plugin_hooks(
        self,
        app: FastAPI,
        hook_name: str,
        *,
        startup_write_enabled: bool = True,
    ) -> None:
        """
        执行启用插件生命周期钩子。

        :param app: FastAPI对象
        :param hook_name: 钩子名称
        :param startup_write_enabled: 是否允许执行启动期写库操作
        :return: None
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return

        for plugin in plugin_registry.list_enabled_plugins():
            await self.run_single_plugin_hook(
                app,
                plugin,
                hook_name,
                startup_write_enabled=startup_write_enabled,
            )

    async def run_single_plugin_hook(
        self,
        app: FastAPI,
        plugin: RegisteredPlugin,
        hook_name: str,
        *,
        startup_write_enabled: bool = True,
    ) -> None:
        """
        执行单个插件生命周期钩子并处理运行时异常。

        :param app: FastAPI对象
        :param plugin: 插件运行时快照
        :param hook_name: 钩子名称
        :param startup_write_enabled: 是否允许执行启动期写库操作
        :return: None
        """
        try:
            await PluginHookRunner(plugin.discovered_plugin).run(
                hook_name,
                app=app,
                startup_write_enabled=startup_write_enabled,
            )
        except Exception as exc:
            logger.bind(
                plugin_id=plugin.plugin_id,
                plugin_hook=hook_name,
                startup_generation=getattr(app.state, 'plugin_startup_generation', None),
                plugin_startup_role_at_creation='writer' if startup_write_enabled else 'reader',
                startup_write_enabled=startup_write_enabled,
                origin_hook=hook_name,
            ).exception(f'❌ 插件生命周期钩子执行失败：{exc}')
            if startup_write_enabled:
                await self.mark_plugin_runtime_error(app, plugin.plugin_id, str(exc))
            elif hook_name == 'on_startup':
                self.disable_runtime_plugins(app, {plugin.plugin_id})

    async def mark_plugin_runtime_error(self, app: FastAPI, plugin_id: str, error_message: str) -> None:
        """
        标记插件运行时异常并刷新运行时注册表。

        :param app: FastAPI对象
        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: None
        """
        async for query_db in get_db():
            result = await self.management_gateway.mark_plugin_error(query_db, plugin_id, error_message)
            if not result.is_success:
                await query_db.rollback()
                registered_plugin = self.get_registered_plugin(app, plugin_id)
                if registered_plugin:
                    await self.management_gateway.upsert_discovered_plugin(
                        query_db,
                        registered_plugin.discovered_plugin,
                        self.builder.plugins_root,
                        self.builder.frontend_plugins_root,
                    )
                    result = await self.management_gateway.mark_plugin_error(query_db, plugin_id, error_message)
            if result.is_success:
                await query_db.commit()
            else:
                await query_db.rollback()
                logger.warning(f'⚠️ 插件运行时异常状态写入失败：{plugin_id}，原因：{result.message}')
        await self.load_registry_from_database(app)

    async def sync_default_enabled_builtin_plugin_install_states(self) -> set[str]:
        """
        首次启动时将内置默认启用插件写入数据库安装状态。

        安装脚本执行前先校验 Python 依赖，避免 migration/seed 导入缺失依赖导致启动
        提前失败。缺失依赖的插件被标记为 error 并隔离，不影响其他插件继续启动。

        :return: 依赖检查失败的默认启用插件 ID 集合
        """
        if not self.default_enabled_builtin_plugin_ids:
            return set()

        discovered_plugins = [
            plugin
            for plugin in self.builder.discover_plugins()
            if plugin.manifest.id in self.default_enabled_builtin_plugin_ids
        ]
        if not discovered_plugins:
            return set()

        failed_plugin_ids: set[str] = set()
        async for query_db in get_db():
            plugin_list = await self.management_gateway.list_plugins(query_db)
        database_plugin_map = {plugin.plugin_id: plugin for plugin in plugin_list}
        plugins_to_sync = [
            plugin
            for plugin in discovered_plugins
            if self._should_sync_default_enabled_builtin_plugin(database_plugin_map.get(plugin.manifest.id))
        ]
        if not plugins_to_sync:
            return failed_plugin_ids

        self.python_dependency_inspector.refresh()
        for plugin in plugins_to_sync:
            plugin_id = plugin.manifest.id
            dependency_failed_messages = self._check_default_plugin_python_dependencies(plugin)
            if dependency_failed_messages:
                failed_plugin_ids.add(plugin_id)
                error_message = self._build_dependency_startup_error_message(
                    plugin_id,
                    dependency_failed_messages,
                )
                logger.error(f'❌ {plugin_id} {error_message}')
                await self.mark_discovered_plugin_startup_error(plugin, error_message)
                continue
            try:
                await self.sync_plugin_install(plugin, enabled=True)
            except Exception as exc:
                failed_plugin_ids.add(plugin_id)
                error_message = f'插件启动安装失败：{exc}'
                logger.exception(f'❌ {plugin_id} {error_message}')
                await self.mark_discovered_plugin_startup_error(plugin, error_message)
        return failed_plugin_ids

    async def mark_discovered_plugin_startup_error(
        self,
        discovered_plugin: Any,
        error_message: str,
    ) -> None:
        """
        以独立事务持久化启动期插件错误，确保安装事务回滚后仍可观测。

        :param discovered_plugin: 已发现插件对象
        :param error_message: 错误信息
        :return: None
        """
        plugin_id = discovered_plugin.manifest.id
        async for query_db in get_db():
            try:
                await self.management_gateway.upsert_discovered_plugin(
                    query_db,
                    discovered_plugin,
                    self.builder.plugins_root,
                    self.builder.frontend_plugins_root,
                )
                result = await self.management_gateway.mark_plugin_error(query_db, plugin_id, error_message)
                if not result.is_success:
                    raise RuntimeError(result.message)
                await query_db.commit()
            except Exception:
                await query_db.rollback()
                logger.exception(f'❌ 插件启动异常状态写入失败：{plugin_id}')

    def _check_default_plugin_python_dependencies(self, discovered_plugin: Any) -> list[str]:
        """
        校验内置默认启用插件的 Python 依赖。

        :param discovered_plugin: 已发现插件
        :return: 依赖检查失败消息列表
        """
        python_requirements = discovered_plugin.manifest.dependencies.python
        if not python_requirements:
            return []
        dependency_result = self._check_plugin_python_dependencies(
            discovered_plugin.manifest.id,
            python_requirements,
        )
        return self._build_dependency_failed_messages(dependency_result)

    @staticmethod
    def _should_sync_default_enabled_builtin_plugin(database_plugin: Any | None) -> bool:
        """
        判断内置默认启用插件是否需要启动期初始化安装状态。

        :param database_plugin: 数据库插件状态
        :return: 是否需要初始化
        """
        if database_plugin is None:
            return True
        return (
            not getattr(database_plugin, 'installed_version', None)
            and getattr(database_plugin, 'status', None) == 'discovered'
            and getattr(database_plugin, 'enabled', None) == '0'
        )

    @staticmethod
    def disable_runtime_plugins(app: FastAPI, plugin_ids: set[str]) -> None:
        """
        在当前 worker 的运行时注册表中停用指定插件，避免非写入 worker 继续导入或注册失败插件。

        :param app: FastAPI对象
        :param plugin_ids: 需要在当前 worker 跳过的插件 ID 集合
        :return: None
        """
        if not plugin_ids:
            return
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return
        app.state.plugin_registry = PluginRegistry(
            [
                replace(plugin, enabled=False, status='error') if plugin.plugin_id in plugin_ids else plugin
                for plugin in plugin_registry.list_plugins()
            ]
        )

    @staticmethod
    def get_registered_plugin(app: FastAPI, plugin_id: str) -> RegisteredPlugin | None:
        """
        从应用运行时注册表获取插件快照。

        :param app: FastAPI对象
        :param plugin_id: 插件ID
        :return: 插件运行时快照
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return None

        return plugin_registry.get_plugin(plugin_id)
