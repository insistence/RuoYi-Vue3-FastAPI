from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plugins.core.management.service.gateway import PluginManagementRuntimeGateway
from plugins.core.management.service.service import PluginService

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from common.vo import CrudResponseModel
    from plugins.core.discovery.registry import PluginRegistry
    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.management.entity.vo.schemas import PluginMigrationModel, PluginModel


class PluginManagementStartupGateway:
    """
    插件启动期管理端口适配器。
    """

    async def list_plugins(self, query_db: AsyncSession) -> list[Any]:
        """
        获取数据库插件状态列表。

        :param query_db: orm对象
        :return: 插件状态列表
        """
        return await PluginService.get_plugin_list_services(query_db)

    async def install_enabled_plugin_menus(
        self,
        query_db: AsyncSession,
        plugin_registry: PluginRegistry,
    ) -> None:
        """
        安装启用插件菜单。

        :param query_db: orm对象
        :param plugin_registry: 插件运行时注册表
        :return: None
        """
        await PluginService.install_enabled_plugin_menu_services(query_db, plugin_registry)

    async def install_enabled_plugin_configs(
        self,
        query_db: AsyncSession,
        plugin_registry: PluginRegistry,
    ) -> None:
        """
        安装启用插件配置。

        :param query_db: orm对象
        :param plugin_registry: 插件运行时注册表
        :return: None
        """
        await PluginService.install_enabled_plugin_config_services(query_db, plugin_registry)

    async def install_enabled_plugin_jobs(
        self,
        query_db: AsyncSession,
        plugin_registry: PluginRegistry,
    ) -> None:
        """
        安装启用插件定时任务。

        :param query_db: orm对象
        :param plugin_registry: 插件运行时注册表
        :return: None
        """
        await PluginService.install_enabled_plugin_job_services(query_db, plugin_registry)

    async def mark_plugin_error(
        self,
        query_db: AsyncSession,
        plugin_id: str,
        error_message: str,
    ) -> CrudResponseModel:
        """
        标记插件运行时异常。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 操作响应
        """
        return await PluginService.mark_plugin_error_services(query_db, plugin_id, error_message)

    async def upsert_discovered_plugin(
        self,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        backend_root: Path,
        frontend_root: Path | None = None,
    ) -> PluginModel:
        """
        写入或更新已发现插件。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件信息
        """
        return await PluginService.upsert_discovered_plugin_services(
            query_db,
            discovered_plugin,
            backend_root,
            frontend_root,
        )

    async def mark_plugin_installed(
        self,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> PluginModel:
        """
        标记插件安装完成。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件信息
        """
        return await PluginService.mark_plugin_installed_services(query_db, discovered_plugin)

    async def get_plugin_migration(
        self,
        query_db: AsyncSession,
        plugin_id: str,
        migration_path: str,
    ) -> PluginMigrationModel | None:
        """
        获取插件 migration 执行历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 插件 migration 执行历史
        """
        return await PluginService.get_plugin_migration_services(query_db, plugin_id, migration_path)

    async def add_plugin_migration(
        self,
        query_db: AsyncSession,
        plugin_migration: PluginMigrationModel,
    ) -> PluginMigrationModel:
        """
        新增插件 migration 执行历史。

        :param query_db: orm对象
        :param plugin_migration: 插件 migration 执行历史
        :return: 插件 migration 执行历史
        """
        return await PluginService.add_plugin_migration_services(query_db, plugin_migration)

    def build_migration_record(
        self,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
    ) -> PluginMigrationModel:
        """
        构建插件 migration 执行历史对象。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param checksum: 内容校验值
        :param version: 执行时插件版本
        :param statement_count: SQL 语句数量
        :return: 插件 migration 执行历史对象
        """
        return PluginManagementRuntimeGateway.build_migration_record(
            plugin_id,
            migration_path,
            checksum,
            version,
            statement_count,
        )
