import subprocess
from collections.abc import Mapping
from importlib import import_module
from typing import TYPE_CHECKING

from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.runtime.service.gateway import (
    AsyncSessionFactoryProtocol,
    PluginCommandOutputCallback,
    PluginManagementServiceProtocol,
    run_plugin_command,
)
from plugins.core.runtime.service.migration_store import PluginDatabaseMigrationHistoryStore
from plugins.core.types import PluginConfigValue, PluginStateRecord

if TYPE_CHECKING:
    from plugins.core.management.entity.vo.schemas import (
        PluginConfigUpdateModel,
        PluginConfigValueModel,
        PluginMigrationModel,
        PluginOperationLogDetailModel,
        PluginOperationLogExportQueryModel,
    )


class PluginManagementLifecycleUnitOfWork:
    """
    插件管理生命周期主事务工作单元。
    """

    def __init__(
        self,
        async_session_local: AsyncSessionFactoryProtocol,
        plugin_service: type[PluginManagementServiceProtocol],
    ) -> None:
        """
        初始化生命周期主事务工作单元。

        :param async_session_local: 异步数据库会话工厂
        :param plugin_service: 插件管理服务类
        :return: None
        """
        self.async_session_local = async_session_local
        self.plugin_service = plugin_service
        self.session_context: object | None = None
        self.session: object | None = None

    async def __aenter__(self) -> 'PluginManagementLifecycleUnitOfWork':
        """
        打开生命周期主事务会话。

        :return: 生命周期主事务工作单元
        """
        self.session_context = self.async_session_local()
        self.session = await self.session_context.__aenter__()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """
        关闭生命周期主事务会话。

        :param exc_type: 异常类型
        :param exc: 异常对象
        :param traceback: 异常堆栈
        :return: None
        """
        if self.session_context is None:
            return
        await self.session_context.__aexit__(exc_type, exc, traceback)
        self.session_context = None
        self.session = None

    async def check_installed_menu_conflicts(self, discovered_plugin: object) -> list[object]:
        """
        检查已安装菜单冲突。

        :param discovered_plugin: 已发现插件
        :return: 菜单冲突列表
        """
        return await self.plugin_service.check_installed_menu_conflict_services(self.session, discovered_plugin)

    async def upsert_discovered_plugin(
        self,
        discovered_plugin: object,
        backend_root: object,
        frontend_root: object | None = None,
    ) -> object:
        """
        写入或更新已发现插件。

        :param discovered_plugin: 已发现插件
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件模型
        """
        return await self.plugin_service.upsert_discovered_plugin_services(
            self.session,
            discovered_plugin,
            backend_root,
            frontend_root,
        )

    async def install_plugin_menu(self, discovered_plugin: object, *, enabled: bool) -> None:
        """
        安装插件菜单。

        :param discovered_plugin: 已发现插件
        :param enabled: 是否启用菜单
        :return: None
        """
        await self.plugin_service.install_plugin_menu_services(self.session, discovered_plugin, enabled=enabled)

    async def install_plugin_default_config(self, discovered_plugin: object) -> list[object]:
        """
        安装插件默认配置。

        :param discovered_plugin: 已发现插件
        :return: 插件配置列表
        """
        return await self.plugin_service.install_plugin_default_config_services(self.session, discovered_plugin)

    async def install_plugin_jobs(self, discovered_plugin: object, *, enabled: bool) -> None:
        """
        同步单个插件任务。

        :param discovered_plugin: 已发现插件
        :param enabled: 插件任务是否启用
        :return: None
        """
        await self.plugin_service.install_plugin_job_services(
            self.session,
            discovered_plugin,
            enabled=enabled,
        )

    async def mark_plugin_installed(self, discovered_plugin: object) -> object:
        """
        标记插件已安装。

        :param discovered_plugin: 已发现插件
        :return: 插件模型
        """
        return await self.plugin_service.mark_plugin_installed_services(self.session, discovered_plugin)

    async def build_plugin_purge_plan(self, discovered_plugin: object) -> object:
        """
        构建插件物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        return await self.plugin_service.build_plugin_purge_plan_services(self.session, discovered_plugin)

    async def purge_plugin_metadata(self, discovered_plugin: object) -> object:
        """
        清理插件平台元数据。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        return await self.plugin_service.purge_plugin_services(self.session, discovered_plugin)

    async def build_plugin_purge_plan_by_id(self, plugin_id: str) -> object:
        """
        按插件 ID 构建孤儿元数据清理计划。

        :param plugin_id: 插件ID
        :return: 插件物理清理计划
        """
        return await self.plugin_service.build_plugin_purge_plan_by_id_services(self.session, plugin_id)

    async def purge_plugin_metadata_by_id(self, plugin_id: str) -> object:
        """
        按插件 ID 清理孤儿元数据。

        :param plugin_id: 插件ID
        :return: 插件物理清理计划
        """
        return await self.plugin_service.purge_plugin_metadata_by_id_services(self.session, plugin_id)

    async def commit(self) -> None:
        """
        提交生命周期主事务。

        :return: None
        """
        await self.session.commit()


class PluginManagementRuntimeGateway:
    """
    插件管理状态运行时基础设施适配器。

    该对象负责将插件运行时端口适配到平台管理状态能力，包括数据库会话、
    插件管理服务、VO 构造和系统命令执行；可被 Web 管理入口和 CLI 共同复用。
    """

    @staticmethod
    def get_async_session_local() -> AsyncSessionFactoryProtocol:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        """
        return import_module('config.database').DataSourceRegistry.session

    @staticmethod
    def get_plugin_service() -> type[PluginManagementServiceProtocol]:
        """
        获取插件服务类。

        :return: 插件服务类
        """
        return import_module('plugins.core.management.service.service').PluginService

    def open_lifecycle_unit_of_work(self) -> PluginManagementLifecycleUnitOfWork:
        """
        打开插件生命周期主事务工作单元。

        :return: 插件生命周期主事务工作单元
        """
        return PluginManagementLifecycleUnitOfWork(self.get_async_session_local(), self.get_plugin_service())

    async def list_plugin_states(self) -> list[PluginStateRecord]:
        """
        获取插件状态列表。

        :return: 插件状态列表
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            return await plugin_service.get_plugin_list_services(session)

    async def get_plugin_state(self, plugin_id: str) -> PluginStateRecord | None:
        """
        获取插件状态。

        :param plugin_id: 插件ID
        :return: 插件状态
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            return await plugin_service.plugin_detail_services(session, plugin_id)

    @staticmethod
    def build_operation_log_export_query(export_limit: int) -> 'PluginOperationLogExportQueryModel':
        """
        构建插件操作日志导出查询对象。

        :param export_limit: 导出数量上限
        :return: 插件操作日志导出查询对象
        """
        plugin_vo = import_module('plugins.core.management.entity.vo.schemas')
        return plugin_vo.PluginOperationLogExportQueryModel(exportLimit=export_limit)

    @staticmethod
    def build_config_update(values: dict[str, PluginConfigValue]) -> 'PluginConfigUpdateModel':
        """
        构建插件配置更新对象。

        :param values: 配置键值
        :return: 插件配置更新对象
        """
        plugin_vo = import_module('plugins.core.management.entity.vo.schemas')
        return plugin_vo.PluginConfigUpdateModel(values=values)

    async def get_plugin_config(
        self,
        discovered_plugin: object,
        *,
        reveal_secret: bool = False,
    ) -> list['PluginConfigValueModel']:
        """
        获取插件配置。

        :param discovered_plugin: 已发现插件
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置列表
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            configs = await plugin_service.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=reveal_secret,
            )
            return configs

    async def update_plugin_config(
        self,
        discovered_plugin: object,
        values: dict[str, PluginConfigValue],
    ) -> list['PluginConfigValueModel']:
        """
        更新插件配置。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :return: 插件配置列表
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            await self._ensure_plugin_installed(session, plugin_service, discovered_plugin.manifest.id)
            configs = await plugin_service.update_plugin_config_services(
                session,
                discovered_plugin,
                self.build_config_update(values),
            )
            await session.commit()
            return configs

    async def set_plugin_config(
        self,
        discovered_plugin: object,
        values: dict[str, PluginConfigValue],
        *,
        audit_operation: str,
        success_message: str,
    ) -> list['PluginConfigValueModel']:
        """
        在同一事务中更新插件配置并记录审计日志。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :param audit_operation: 审计操作类型
        :param success_message: 操作成功提示
        :return: 插件配置列表
        """
        from plugins.core.runtime.support import PluginConfigPayloadBuilder  # noqa: PLC0415

        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            await self._ensure_plugin_installed(session, plugin_service, discovered_plugin.manifest.id)
            before_configs = await plugin_service.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=True,
            )
            configs = await plugin_service.update_plugin_config_services(
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
            await plugin_service.add_plugin_operation_log_services(
                session,
                audit_payload,
                dry_run=False,
                continue_on_error=False,
            )
            await session.commit()
            return configs

    @staticmethod
    async def _ensure_plugin_installed(
        session: object,
        plugin_service: type[PluginManagementServiceProtocol],
        plugin_id: str,
    ) -> None:
        """
        拒绝为尚未安装的插件创建或更新持久化配置。

        :param session: 数据库会话
        :param plugin_service: 插件管理服务类
        :param plugin_id: 插件ID
        :return: None
        :raises ValueError: 插件尚未安装
        """
        if not await plugin_service.is_plugin_installed_services(session, plugin_id):
            raise ValueError(f'插件尚未安装，不能修改配置：{plugin_id}')

    async def add_plugin_operation_log(
        self,
        payload: Mapping[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """
        记录插件操作审计日志。

        :param payload: 操作日志负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续
        :return: None
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            await plugin_service.add_plugin_operation_log_services(
                session,
                dict(payload),
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
            await session.commit()

    async def list_plugin_operation_logs(self, *, export_limit: int) -> list['PluginOperationLogDetailModel']:
        """
        获取插件操作审计日志列表。

        :param export_limit: 导出数量上限
        :return: 插件操作日志详情列表
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            return await plugin_service.get_plugin_operation_log_export_list_services(
                session,
                self.build_operation_log_export_query(export_limit),
            )

    async def mark_plugin_error(self, plugin_id: str, error_message: str) -> bool:
        """
        标记插件错误状态。

        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 是否标记成功
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            result = await plugin_service.mark_plugin_error_services(session, plugin_id, error_message)
            if getattr(result, 'is_success', False):
                await session.commit()
                return True
            return False

    async def list_plugin_migrations(
        self,
        plugin_id: str,
        status: str | None = None,
    ) -> list['PluginMigrationModel']:
        """
        查询插件 migration 历史。

        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: 插件 migration 历史列表
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            return await plugin_service.get_plugin_migration_list_services(session, plugin_id, status)

    async def get_plugin_migration(self, plugin_id: str, migration_path: str) -> 'PluginMigrationModel | None':
        """
        获取插件 migration 历史。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 插件 migration 历史
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            return await plugin_service.get_plugin_migration_services(session, plugin_id, migration_path)

    async def mark_plugin_migration_status(
        self,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> 'PluginMigrationModel | None':
        """
        人工标记插件 migration 历史状态。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 插件 migration 历史
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            migration = await plugin_service.mark_plugin_migration_status_services(
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
        """
        构建插件物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            return await plugin_service.build_plugin_purge_plan_services(session, discovered_plugin)

    async def set_plugin_enabled_state(
        self,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: object | None = None,
    ) -> object:
        """
        更新插件启停状态，并在启用时同步插件菜单。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param discovered_plugin: 已发现插件
        :return: 操作响应
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            response = await plugin_service.update_plugin_enabled_services(
                session,
                plugin_id,
                enabled,
                discovered_plugin,
            )
            if getattr(response, 'is_success', False):
                if enabled and discovered_plugin is not None:
                    await plugin_service.install_plugin_menu_services(session, discovered_plugin, enabled=True)
                await session.commit()
            return response

    async def mark_plugin_uninstalled_state(self, plugin_id: str) -> object:
        """
        标记插件安全卸载。

        :param plugin_id: 插件ID
        :return: 操作响应
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as session:
            response = await plugin_service.mark_plugin_uninstalled_services(session, plugin_id)
            if getattr(response, 'is_success', False):
                await session.commit()
            return response

    async def run_plugin_migrations(self, discovered_plugin: object) -> object:
        """
        使用独立执行事务运行插件 migration。

        :param discovered_plugin: 已发现插件
        :return: migration 执行结果列表
        """
        async_session_local = self.get_async_session_local()
        plugin_service = self.get_plugin_service()
        async with async_session_local() as migration_session:
            return await PluginMigrationRunner(
                discovered_plugin,
                PluginDatabaseMigrationHistoryStore.with_model_gateway(
                    plugin_service,
                    self,
                    async_session_local,
                ),
                manage_execution_transaction=True,
            ).run(migration_session)

    @staticmethod
    def build_migration_record(
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
        status: str = 'success',
        error_message: str | None = None,
    ) -> 'PluginMigrationModel':
        """
        构建插件 migration 执行历史对象。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param checksum: 内容校验值
        :param version: 执行时插件版本
        :param statement_count: SQL 语句数量
        :return: 插件 migration 执行历史对象
        """
        plugin_vo = import_module('plugins.core.management.entity.vo.schemas')
        return plugin_vo.PluginMigrationModel(
            pluginId=plugin_id,
            migrationPath=migration_path,
            migrationChecksum=checksum,
            version=version,
            statementCount=statement_count,
            status=status,
            errorMessage=error_message,
        )

    @staticmethod
    def run_command(
        command: list[str],
        workdir: str,
        *,
        timeout: int | None = None,
        output_callback: PluginCommandOutputCallback | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """
        执行系统命令。

        :param command: 命令参数列表
        :param workdir: 命令工作目录
        :param timeout: 命令超时时间
        :param output_callback: 实时输出回调
        :return: 命令执行结果
        """
        return run_plugin_command(
            command,
            workdir,
            timeout=timeout,
            output_callback=output_callback,
        )
