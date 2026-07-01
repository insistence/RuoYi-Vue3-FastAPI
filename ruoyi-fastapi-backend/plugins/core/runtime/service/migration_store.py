from typing import TYPE_CHECKING

from plugins.core.lifecycle.migration import PluginMigrationHistoryStore

from .gateway import PluginManagementModelGateway, PluginManagementServiceProtocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PluginDatabaseMigrationHistoryStore(PluginMigrationHistoryStore):
    """
    插件数据库 migration 历史存储。

    使用 Adapter 模式将插件 core runner 需要的历史接口适配到外部 migration 历史服务。
    """

    def __init__(self, plugin_service: type[PluginManagementServiceProtocol]) -> None:
        """
        初始化插件数据库 migration 历史存储。

        :param plugin_service: 插件服务类
        :return: None
        """
        self.plugin_service = plugin_service
        self.model_gateway: PluginManagementModelGateway | None = None

    @classmethod
    def with_model_gateway(
        cls,
        plugin_service: type[PluginManagementServiceProtocol],
        model_gateway: PluginManagementModelGateway,
    ) -> 'PluginDatabaseMigrationHistoryStore':
        """
        使用模型工厂网关构建 migration 历史存储。

        :param plugin_service: 插件服务类
        :param model_gateway: 插件管理模型工厂网关
        :return: migration 历史存储
        """
        store = cls(plugin_service)
        store.model_gateway = model_gateway
        return store

    async def get_checksum(self, query_db: 'AsyncSession', plugin_id: str, migration_path: str) -> str | None:
        """
        获取已执行 migration 的内容校验值。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 内容校验值，不存在时返回 None
        """
        plugin_migration = await self.plugin_service.get_plugin_migration_services(
            query_db,
            plugin_id,
            migration_path,
        )
        if plugin_migration and getattr(plugin_migration, 'status', 'success') != 'success':
            return None
        return plugin_migration.migration_checksum if plugin_migration else None

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
        await self.plugin_service.add_plugin_migration_services(
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
        await self.plugin_service.add_plugin_migration_services(
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
