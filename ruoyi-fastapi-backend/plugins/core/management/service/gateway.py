import subprocess
from importlib import import_module
from typing import TYPE_CHECKING

from plugins.core.runtime.service.gateway import (
    AsyncSessionFactoryProtocol,
    PluginManagementServiceProtocol,
)
from plugins.core.types import PluginConfigValue

if TYPE_CHECKING:
    from plugins.core.management.entity.vo.schemas import (
        PluginConfigUpdateModel,
        PluginMigrationModel,
        PluginOperationLogExportQueryModel,
    )


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
        return import_module('config.database').AsyncSessionLocal

    @staticmethod
    def get_plugin_service() -> type[PluginManagementServiceProtocol]:
        """
        获取插件服务类。

        :return: 插件服务类
        """
        return import_module('plugins.core.management.service.service').PluginService

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

    @staticmethod
    def build_migration_record(
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
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
        )

    @staticmethod
    def run_command(
        command: list[str],
        workdir: str,
        *,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """
        执行系统命令。

        :param command: 命令参数列表
        :param workdir: 命令工作目录
        :param timeout: 命令超时时间
        :return: 命令执行结果
        """
        return subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
