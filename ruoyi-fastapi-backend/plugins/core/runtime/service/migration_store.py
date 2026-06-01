from typing import Any

from plugins.core.lifecycle.migration import PluginMigrationHistoryStore


class PluginDatabaseMigrationHistoryStore(PluginMigrationHistoryStore):
    """
    插件数据库 migration 历史存储。

    使用 Adapter 模式将插件 core runner 需要的历史接口适配到外部 migration 历史服务。
    """

    def __init__(self, plugin_service: Any) -> None:
        """
        初始化插件数据库 migration 历史存储。

        :param plugin_service: 插件服务类
        :return: None
        """
        self.plugin_service = plugin_service
        self.infrastructure_gateway: Any | None = None

    @classmethod
    def with_gateway(cls, plugin_service: Any, infrastructure_gateway: Any) -> 'PluginDatabaseMigrationHistoryStore':
        """
        使用基础设施网关构建 migration 历史存储。

        :param plugin_service: 插件服务类
        :param infrastructure_gateway: 插件基础设施网关
        :return: migration 历史存储
        """
        store = cls(plugin_service)
        store.infrastructure_gateway = infrastructure_gateway
        return store

    async def get_checksum(self, query_db: Any, plugin_id: str, migration_path: str) -> str | None:
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
        return plugin_migration.migration_checksum if plugin_migration else None

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
        await self.plugin_service.add_plugin_migration_services(
            query_db,
            self.infrastructure_gateway.build_migration_record(
                plugin_id,
                migration_path,
                checksum,
                version,
                statement_count,
            ),
        )
