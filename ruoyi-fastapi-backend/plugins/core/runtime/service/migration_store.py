from typing import TYPE_CHECKING

from plugins.core.lifecycle.migration import PluginMigrationHistoryRecord, PluginMigrationHistoryStore

from .gateway import AsyncSessionFactoryProtocol, PluginManagementModelGateway, PluginManagementServiceProtocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PluginDatabaseMigrationHistoryStore(PluginMigrationHistoryStore):
    """
    插件数据库 migration 历史存储。

    使用 Adapter 模式将插件 core runner 需要的历史接口适配到外部 migration 历史服务。
    """

    def __init__(
        self,
        plugin_service: type[PluginManagementServiceProtocol],
        async_session_local: AsyncSessionFactoryProtocol | None = None,
    ) -> None:
        """
        初始化插件数据库 migration 历史存储。

        :param plugin_service: 插件服务类
        :param async_session_local: 独立数据库会话工厂
        :return: None
        """
        self.plugin_service = plugin_service
        self.model_gateway: PluginManagementModelGateway | None = None
        self.async_session_local = async_session_local

    @classmethod
    def with_model_gateway(
        cls,
        plugin_service: type[PluginManagementServiceProtocol],
        model_gateway: PluginManagementModelGateway,
        async_session_local: AsyncSessionFactoryProtocol | None = None,
    ) -> 'PluginDatabaseMigrationHistoryStore':
        """
        使用模型工厂网关构建 migration 历史存储。

        :param plugin_service: 插件服务类
        :param model_gateway: 插件管理模型工厂网关
        :param async_session_local: 独立数据库会话工厂
        :return: migration 历史存储
        """
        store = cls(plugin_service, async_session_local)
        store.model_gateway = model_gateway
        return store

    async def get_record(
        self,
        query_db: 'AsyncSession',
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
        plugin_migration = await self.plugin_service.get_plugin_migration_services(
            query_db,
            plugin_id,
            migration_path,
        )
        if not plugin_migration:
            return None
        return PluginMigrationHistoryRecord(
            checksum=plugin_migration.migration_checksum,
            status=getattr(plugin_migration, 'status', 'success'),
            error_message=getattr(plugin_migration, 'error_message', None),
        )

    async def record_running(
        self,
        query_db: 'AsyncSession',
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
        if self.model_gateway is None:
            raise RuntimeError('插件运行时缺少 migration 历史记录模型网关')
        await self._add_plugin_migration(
            query_db,
            self.model_gateway.build_migration_record(
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
        query_db: 'AsyncSession',
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
        if self.model_gateway is None:
            raise RuntimeError('插件运行时缺少 migration 历史记录模型网关')
        await self._add_plugin_migration(
            query_db,
            self.model_gateway.build_migration_record(
                plugin_id,
                migration_path,
                checksum,
                version,
                statement_count,
            ),
        )

    async def record_failure(
        self,
        query_db: 'AsyncSession',
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
        if self.model_gateway is None:
            raise RuntimeError('插件运行时缺少 migration 历史记录模型网关')
        await self._add_plugin_migration(
            query_db,
            self.model_gateway.build_migration_record(
                plugin_id,
                migration_path,
                checksum,
                version,
                statement_count,
                'failed',
                error_message,
            ),
        )

    async def _add_plugin_migration(self, query_db: 'AsyncSession', plugin_migration: object) -> None:
        """
        写入 migration 历史，优先使用独立会话提交。

        :param query_db: 当前生命周期 orm对象
        :param plugin_migration: migration 历史模型
        :return: None
        """
        if self.async_session_local is None:
            await self.plugin_service.add_plugin_migration_services(query_db, plugin_migration)
            return

        async with self.async_session_local() as session:
            await self.plugin_service.add_plugin_migration_services(session, plugin_migration)
            await session.commit()
