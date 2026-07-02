from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from common.vo import CrudResponseModel
    from plugins.core.discovery.registry import PluginRegistry
    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.lifecycle.purge import PluginPurgePlan
    from plugins.core.management.entity.vo.schemas import (
        PluginConfigModel,
        PluginConfigUpdateModel,
        PluginConfigValueModel,
        PluginMigrationModel,
        PluginModel,
        PluginOperationLogDetailModel,
        PluginOperationLogExportQueryModel,
    )
    from plugins.core.types import PluginConfigValue, PluginStateRecord
    from plugins.core.validation.menus import PluginMenuConflictItem


@runtime_checkable
class AsyncSessionFactoryProtocol(Protocol):
    """
    异步数据库会话工厂协议。
    """

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        """
        创建异步数据库会话上下文。

        :return: 异步数据库会话上下文
        """


@runtime_checkable
class PluginManagementServiceProtocol(Protocol):
    """
    插件运行时依赖的管理服务协议。
    """

    @classmethod
    async def get_plugin_list_services(cls, query_db: AsyncSession) -> list[PluginStateRecord]:
        """
        获取插件状态列表。

        :param query_db: orm对象
        :return: 插件状态列表
        """

    @classmethod
    async def plugin_detail_services(cls, query_db: AsyncSession, plugin_id: str) -> PluginStateRecord | None:
        """
        获取插件详情。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 插件状态
        """

    @classmethod
    async def upsert_discovered_plugin_services(
        cls,
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

    @classmethod
    async def update_plugin_enabled_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: DiscoveredPlugin | None = None,
    ) -> CrudResponseModel:
        """
        更新插件启停状态。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param discovered_plugin: 已发现插件对象
        :return: 操作响应
        """

    @classmethod
    async def mark_plugin_installed_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> PluginModel:
        """
        标记插件安装完成。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件信息
        """

    @classmethod
    async def mark_plugin_uninstalled_services(cls, query_db: AsyncSession, plugin_id: str) -> CrudResponseModel:
        """
        标记插件卸载完成。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 操作响应
        """

    @classmethod
    async def install_enabled_plugin_menu_services(
        cls,
        query_db: AsyncSession,
        plugin_registry: PluginRegistry,
    ) -> None:
        """
        安装启用插件菜单。

        :param query_db: orm对象
        :param plugin_registry: 插件注册表
        :return: None
        """

    @classmethod
    async def install_plugin_menu_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        *,
        enabled: bool,
    ) -> None:
        """
        安装插件菜单。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param enabled: 是否启用
        :return: None
        """

    @classmethod
    async def install_plugin_default_config_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> list[PluginConfigModel]:
        """
        安装插件默认配置。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件配置列表
        """

    @classmethod
    async def get_plugin_config_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        *,
        reveal_secret: bool = False,
    ) -> list[PluginConfigValueModel]:
        """
        获取插件配置。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置值列表
        """

    @classmethod
    async def update_plugin_config_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        update_model: PluginConfigUpdateModel,
    ) -> list[PluginConfigValueModel]:
        """
        更新插件配置。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :param update_model: 配置更新对象
        :return: 插件配置值列表
        """

    @classmethod
    async def add_plugin_operation_log_services(
        cls,
        query_db: AsyncSession,
        payload: dict[str, Any],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> object:
        """
        记录插件操作审计日志。

        :param query_db: orm对象
        :param payload: 操作结果负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续
        :return: 操作日志模型
        """

    @classmethod
    async def get_plugin_operation_log_export_list_services(
        cls,
        query_db: AsyncSession,
        query_object: PluginOperationLogExportQueryModel,
    ) -> list[PluginOperationLogDetailModel]:
        """
        获取插件操作日志导出列表。

        :param query_db: orm对象
        :param query_object: 操作日志导出查询对象
        :return: 操作日志详情列表
        """

    @classmethod
    async def check_installed_menu_conflict_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> list[PluginMenuConflictItem]:
        """
        检查已安装菜单冲突。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 菜单冲突列表
        """

    @classmethod
    async def mark_plugin_error_services(
        cls, query_db: AsyncSession, plugin_id: str, error_message: str
    ) -> CrudResponseModel:
        """
        标记插件错误。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 操作响应
        """

    @classmethod
    async def build_plugin_purge_plan_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> PluginPurgePlan:
        """
        构建插件清理计划。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件清理计划
        """

    @classmethod
    async def purge_plugin_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
    ) -> PluginPurgePlan:
        """
        清理插件平台元数据。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件对象
        :return: 插件清理计划
        """

    @classmethod
    async def get_plugin_migration_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        migration_path: str,
    ) -> PluginMigrationModel | None:
        """
        获取插件 migration 历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 插件 migration 历史
        """

    @classmethod
    async def get_plugin_migration_list_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        status: str | None = None,
    ) -> list[PluginMigrationModel]:
        """
        获取插件 migration 历史列表。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: 插件 migration 历史列表
        """

    @classmethod
    async def add_plugin_migration_services(
        cls,
        query_db: AsyncSession,
        plugin_migration: PluginMigrationModel,
    ) -> PluginMigrationModel:
        """
        新增插件 migration 历史。

        :param query_db: orm对象
        :param plugin_migration: 插件 migration 历史
        :return: 插件 migration 历史
        """

    @classmethod
    async def mark_plugin_migration_status_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> PluginMigrationModel | None:
        """
        人工标记插件 migration 历史状态。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 插件 migration 历史
        """


@runtime_checkable
class PluginStateGateway(Protocol):
    """
    插件管理状态网关协议。
    """

    def get_async_session_local(self) -> AsyncSessionFactoryProtocol:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        """

    def get_plugin_service(self) -> type[PluginManagementServiceProtocol]:
        """
        获取插件管理服务类。

        :return: 插件管理服务类
        """


@runtime_checkable
class PluginManagementModelGateway(Protocol):
    """
    插件管理模型工厂网关协议。
    """

    def build_operation_log_export_query(self, export_limit: int) -> PluginOperationLogExportQueryModel:
        """
        构建插件操作日志导出查询对象。

        :param export_limit: 导出数量上限
        :return: 插件操作日志导出查询对象
        """

    def build_config_update(self, values: dict[str, PluginConfigValue]) -> PluginConfigUpdateModel:
        """
        构建插件配置更新对象。

        :param values: 配置键值
        :return: 插件配置更新对象
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


@runtime_checkable
class PluginCommandRunnerGateway(Protocol):
    """
    插件命令执行网关协议。
    """

    def run_command(
        self,
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


class UnavailablePluginStateGateway:
    """
    不可用的插件管理状态网关。
    """

    @staticmethod
    def get_async_session_local() -> AsyncSessionFactoryProtocol:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        :raises RuntimeError: 默认网关不提供数据库访问能力
        """
        raise RuntimeError('插件运行时缺少数据库会话适配器')

    @staticmethod
    def get_plugin_service() -> type[PluginManagementServiceProtocol]:
        """
        获取插件管理服务类。

        :return: 插件管理服务类
        :raises RuntimeError: 默认网关不提供插件管理服务适配器
        """
        raise RuntimeError('插件运行时缺少插件管理服务适配器')


class UnavailablePluginManagementModelGateway:
    """
    不可用的插件管理模型工厂网关。
    """

    @staticmethod
    def build_operation_log_export_query(export_limit: int) -> PluginOperationLogExportQueryModel:
        """
        构建插件操作日志导出查询对象。

        :param export_limit: 导出数量上限
        :return: 插件操作日志导出查询对象
        :raises RuntimeError: 默认网关不提供管理状态 VO 适配器
        """
        raise RuntimeError('插件运行时缺少操作日志查询适配器')

    @staticmethod
    def build_config_update(values: dict[str, PluginConfigValue]) -> PluginConfigUpdateModel:
        """
        构建插件配置更新对象。

        :param values: 配置键值
        :return: 插件配置更新对象
        :raises RuntimeError: 默认网关不提供管理状态 VO 适配器
        """
        raise RuntimeError('插件运行时缺少配置更新适配器')

    @staticmethod
    def build_migration_record(
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
        :raises RuntimeError: 默认网关不提供管理状态 VO 适配器
        """
        raise RuntimeError('插件运行时缺少 migration 历史记录适配器')


class DefaultPluginCommandRunnerGateway:
    """
    默认插件命令执行网关。
    """

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
