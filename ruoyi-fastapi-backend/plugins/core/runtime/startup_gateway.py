from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from common.vo import CrudResponseModel
    from plugins.core.discovery.registry import PluginRegistry
    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.management.entity.vo.schemas import PluginMigrationModel, PluginModel


@runtime_checkable
class PluginStartupManagementGateway(Protocol):
    """
    插件启动期依赖的管理端口。
    """

    async def list_plugins(self, query_db: AsyncSession) -> list[Any]:
        """
        获取数据库插件状态列表。

        :param query_db: orm对象
        :return: 插件状态列表
        """

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

    def build_migration_record(
        self,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
        status: str = 'success',
        error_message: str | None = None,
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


class UnavailablePluginStartupManagementGateway:
    """
    不可用的插件启动期管理端口。
    """

    @staticmethod
    def _raise_unavailable() -> NoReturn:
        """
        抛出启动期管理端口不可用异常。

        :return: NoReturn
        :raises RuntimeError: 默认端口不提供管理服务能力
        """
        raise RuntimeError('插件启动期缺少管理服务适配器')

    async def list_plugins(self, query_db: AsyncSession) -> list[Any]:
        """
        获取数据库插件状态列表。

        :param query_db: orm对象
        :return: 插件状态列表
        """
        self._raise_unavailable()

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
        self._raise_unavailable()

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
        self._raise_unavailable()

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
        self._raise_unavailable()

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
        self._raise_unavailable()

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
        self._raise_unavailable()

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
        self._raise_unavailable()

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
        self._raise_unavailable()

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
        self._raise_unavailable()

    def build_migration_record(
        self,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
        status: str = 'success',
        error_message: str | None = None,
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
        self._raise_unavailable()
