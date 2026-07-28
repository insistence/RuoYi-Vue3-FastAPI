import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.runtime.service.gateway import PluginCommandOutputCallback
from plugins.core.runtime.service.migration_store import PluginDatabaseMigrationHistoryStore
from plugins.core.runtime.support import PluginConfigPayloadBuilder

from .management import FakePluginService
from .session import FakeSession, FakeSessionLocal

MIN_NPM_INSTALL_COMMAND_LENGTH = 3


class FakePluginLifecycleUnitOfWork:
    """
    测试用插件生命周期主事务工作单元。
    """

    def __init__(self, gateway: 'FakePluginRuntimeGateway') -> None:
        """初始化测试生命周期 UoW。"""
        self.gateway = gateway
        self.session_context: FakeSession | None = None
        self.session: FakeSession | None = None

    async def __aenter__(self) -> 'FakePluginLifecycleUnitOfWork':
        """打开测试生命周期主事务会话。"""
        self.session_context = self.gateway.session_local()
        self.session = await self.session_context.__aenter__()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """关闭测试生命周期主事务会话。"""
        if self.session_context is None:
            return
        await self.session_context.__aexit__(exc_type, exc, traceback)
        self.session_context = None
        self.session = None

    async def check_installed_menu_conflicts(self, discovered_plugin: object) -> list[SimpleNamespace]:
        """检查已安装菜单冲突。"""
        return await FakePluginService.check_installed_menu_conflict_services(self.session, discovered_plugin)

    async def upsert_discovered_plugin(
        self,
        discovered_plugin: object,
        backend_root: Path,
        frontend_root: Path | None = None,
    ) -> SimpleNamespace:
        """写入或更新已发现插件。"""
        return await FakePluginService.upsert_discovered_plugin_services(
            self.session,
            discovered_plugin,
            backend_root,
            frontend_root,
        )

    async def install_plugin_menu(self, discovered_plugin: object, *, enabled: bool) -> None:
        """安装插件菜单。"""
        await FakePluginService.install_plugin_menu_services(self.session, discovered_plugin, enabled=enabled)

    async def install_plugin_default_config(self, discovered_plugin: object) -> list[SimpleNamespace]:
        """安装插件默认配置。"""
        return await FakePluginService.install_plugin_default_config_services(self.session, discovered_plugin)

    async def install_plugin_jobs(self, discovered_plugin: object, *, enabled: bool) -> None:
        """同步插件任务。"""
        await FakePluginService.install_plugin_job_services(self.session, discovered_plugin, enabled=enabled)

    async def mark_plugin_installed(self, discovered_plugin: object) -> SimpleNamespace:
        """标记插件已安装。"""
        return await FakePluginService.mark_plugin_installed_services(self.session, discovered_plugin)

    async def build_plugin_purge_plan(self, discovered_plugin: object) -> object:
        """构建插件物理清理计划。"""
        return await FakePluginService.build_plugin_purge_plan_services(self.session, discovered_plugin)

    async def purge_plugin_metadata(self, discovered_plugin: object) -> object:
        """清理插件平台元数据。"""
        return await FakePluginService.purge_plugin_services(self.session, discovered_plugin)

    async def build_plugin_purge_plan_by_id(self, plugin_id: str) -> object:
        """按插件 ID 构建孤儿元数据清理计划。"""
        return await FakePluginService.build_plugin_purge_plan_by_id_services(self.session, plugin_id)

    async def purge_plugin_metadata_by_id(self, plugin_id: str) -> object:
        """按插件 ID 清理孤儿元数据。"""
        return await FakePluginService.purge_plugin_metadata_by_id_services(self.session, plugin_id)

    async def commit(self) -> None:
        """提交测试生命周期主事务。"""
        await self.session.commit()


class FakePluginRuntimeGateway:
    """
    测试用插件运行时适配器。
    """

    def __init__(self) -> None:
        """初始化测试用插件运行时适配器。"""
        self.session_local = FakeSessionLocal()
        self.completed_process = CompletedProcess(args=[], returncode=0, stdout='1 passed\n', stderr='')
        self.commands: list[tuple[list[str], str, int | None]] = []

    def open_lifecycle_unit_of_work(self) -> FakePluginLifecycleUnitOfWork:
        """打开测试生命周期主事务工作单元。"""
        return FakePluginLifecycleUnitOfWork(self)

    def get_async_session_local(self) -> FakeSessionLocal:
        """获取测试会话工厂。"""
        return self.session_local

    def get_plugin_service(self) -> type[FakePluginService]:
        """获取测试插件服务。"""
        return FakePluginService

    async def list_plugin_states(self) -> list[SimpleNamespace]:
        """获取测试插件状态列表。"""
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_list_services(session)

    async def get_plugin_state(self, plugin_id: str) -> SimpleNamespace | None:
        """获取测试插件状态。"""
        async with self.session_local() as session:
            return await FakePluginService.plugin_detail_services(session, plugin_id)

    @staticmethod
    def build_operation_log_export_query(export_limit: int) -> SimpleNamespace:
        """构建测试用插件操作日志导出查询对象。"""
        return SimpleNamespace(export_limit=export_limit, exportLimit=export_limit)

    @staticmethod
    def build_config_update(values: dict[str, object]) -> SimpleNamespace:
        """构建测试用插件配置更新对象。"""
        return SimpleNamespace(values=values)

    async def get_plugin_config(
        self,
        discovered_plugin: object,
        *,
        reveal_secret: bool = False,
    ) -> list[SimpleNamespace]:
        """获取测试插件配置。"""
        async with self.session_local() as session:
            configs = await FakePluginService.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=reveal_secret,
            )
            return configs

    async def update_plugin_config(
        self,
        discovered_plugin: object,
        values: dict[str, object],
    ) -> list[SimpleNamespace]:
        """更新测试插件配置。"""
        async with self.session_local() as session:
            configs = await FakePluginService.update_plugin_config_services(
                session,
                discovered_plugin,
                self.build_config_update(values),
            )
            await session.commit()
            return configs

    async def set_plugin_config(
        self,
        discovered_plugin: object,
        values: dict[str, object],
        *,
        audit_operation: str,
        success_message: str,
    ) -> list[SimpleNamespace]:
        """在同一事务中更新测试插件配置并记录审计日志。"""
        async with self.session_local() as session:
            before_configs = await FakePluginService.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=True,
            )
            configs = await FakePluginService.update_plugin_config_services(
                session,
                discovered_plugin,
                self.build_config_update(values),
            )
            audit_payload = PluginConfigPayloadBuilder.build_audit_payload(
                discovered_plugin.manifest.id,
                operation=audit_operation,
                values=values,
                before_configs=before_configs,
                after_configs=configs,
                message=success_message,
            )
            await FakePluginService.add_plugin_operation_log_services(
                session,
                audit_payload,
                dry_run=False,
                continue_on_error=False,
            )
            await session.commit()
            return configs

    async def add_plugin_operation_log(
        self,
        payload: dict[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """记录测试插件操作日志。"""
        async with self.session_local() as session:
            await FakePluginService.add_plugin_operation_log_services(
                session,
                payload,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
            await session.commit()

    async def list_plugin_operation_logs(self, *, export_limit: int) -> list[SimpleNamespace]:
        """获取测试插件操作审计日志列表。"""
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_operation_log_export_list_services(
                session,
                self.build_operation_log_export_query(export_limit),
            )

    async def mark_plugin_error(self, plugin_id: str, error_message: str) -> bool:
        """标记测试插件错误状态。"""
        async with self.session_local() as session:
            result = await FakePluginService.mark_plugin_error_services(session, plugin_id, error_message)
            if getattr(result, 'is_success', False):
                await session.commit()
                return True
            return False

    async def list_plugin_migrations(
        self,
        plugin_id: str,
        status: str | None = None,
    ) -> list[SimpleNamespace]:
        """查询测试插件 migration 历史。"""
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_migration_list_services(session, plugin_id, status)

    async def get_plugin_migration(self, plugin_id: str, migration_path: str) -> SimpleNamespace | None:
        """获取测试插件 migration 历史。"""
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_migration_services(session, plugin_id, migration_path)

    async def mark_plugin_migration_status(
        self,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> SimpleNamespace | None:
        """人工标记测试插件 migration 历史状态。"""
        async with self.session_local() as session:
            migration = await FakePluginService.mark_plugin_migration_status_services(
                session,
                plugin_id,
                migration_path,
                status,
                error_message,
            )
            if migration:
                await session.commit()
            return migration

    async def build_plugin_purge_plan(self, discovered_plugin: object) -> object:
        """构建测试插件物理清理计划。"""
        async with self.session_local() as session:
            return await FakePluginService.build_plugin_purge_plan_services(session, discovered_plugin)

    async def run_plugin_migrations(self, discovered_plugin: object) -> list[object]:
        """使用独立测试 session 执行插件 migration。"""
        async with self.session_local() as migration_session:
            return await PluginMigrationRunner(
                discovered_plugin,
                PluginDatabaseMigrationHistoryStore.with_model_gateway(
                    FakePluginService,
                    self,
                    self.session_local,
                ),
                manage_execution_transaction=True,
            ).run(migration_session)

    async def set_plugin_enabled_state(
        self,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: object | None = None,
    ) -> SimpleNamespace:
        """更新测试插件启停状态，并在启用时同步菜单。"""
        async with self.session_local() as session:
            response = await FakePluginService.update_plugin_enabled_services(
                session,
                plugin_id,
                enabled,
                discovered_plugin,
            )
            if getattr(response, 'is_success', False):
                if enabled and discovered_plugin is not None:
                    await FakePluginService.install_plugin_menu_services(session, discovered_plugin, enabled=True)
                await session.commit()
            return response

    async def mark_plugin_uninstalled_state(self, plugin_id: str) -> SimpleNamespace:
        """标记测试插件安全卸载。"""
        async with self.session_local() as session:
            response = await FakePluginService.mark_plugin_uninstalled_services(session, plugin_id)
            if getattr(response, 'is_success', False):
                await session.commit()
            return response

    @staticmethod
    def build_migration_record(
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
        status: str = 'success',
        error_message: str | None = None,
    ) -> SimpleNamespace:
        """构建测试用插件 migration 执行历史对象。"""
        return SimpleNamespace(
            plugin_id=plugin_id,
            migration_path=migration_path,
            migration_checksum=checksum,
            version=version,
            statement_count=statement_count,
            status=status,
            error_message=error_message,
            attempt_count=0,
            started_time=None,
            finished_time=None,
            create_time=None,
            update_time=None,
        )

    def run_command(
        self,
        command: list[str],
        workdir: str,
        *,
        timeout: int | None = None,
        output_callback: PluginCommandOutputCallback | None = None,
    ) -> CompletedProcess[str]:
        """记录测试用系统命令。"""
        self.commands.append((command, workdir, timeout))
        self._simulate_npm_package_json_update(command, workdir)
        if output_callback is not None:
            if self.completed_process.stdout:
                output_callback('stdout', self.completed_process.stdout)
            if self.completed_process.stderr:
                output_callback('stderr', self.completed_process.stderr)
        return self.completed_process

    def _simulate_npm_package_json_update(self, command: list[str], workdir: str) -> None:
        """模拟 npm install 对 package.json 根依赖声明的改写。"""
        if (
            self.completed_process.returncode != 0
            or len(command) < MIN_NPM_INSTALL_COMMAND_LENGTH
            or command[:2] != ['npm', 'install']
        ):
            return
        target = command[-1]
        package_json_path = Path(workdir) / 'package.json'
        if not package_json_path.is_file():
            return
        package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
        dependency_field = 'devDependencies' if '--save-dev' in command else 'dependencies'
        dependency_name = target.rsplit('@', maxsplit=1)[0] if '@' in target.lstrip('@') else target
        package_json.setdefault(dependency_field, {})[dependency_name] = '^npm-written'
        package_json_path.write_text(json.dumps(package_json, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
