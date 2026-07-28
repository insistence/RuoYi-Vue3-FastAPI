from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeAlias, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextlib import AbstractAsyncContextManager
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from common.vo import CrudResponseModel
    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.lifecycle.migration import PluginMigrationResult
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

PluginCommandOutputKind = Literal['status', 'stdout', 'stderr']
PluginCommandOutputCallback: TypeAlias = Callable[[PluginCommandOutputKind, str], None]


def run_plugin_command(
    command: list[str],
    workdir: str,
    *,
    timeout: int | None = None,
    output_callback: PluginCommandOutputCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    执行插件系统命令，并可选实时转发标准输出和错误输出。

    :param command: 命令参数列表
    :param workdir: 命令工作目录
    :param timeout: 命令超时时间
    :param output_callback: 实时输出回调
    :return: 命令执行结果
    """
    if output_callback is None:
        return subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    callback_lock = threading.Lock()

    def consume_stream(
        stream: Any,
        kind: Literal['stdout', 'stderr'],
        output_parts: list[str],
    ) -> None:
        """持续读取并转发单个子进程输出流。"""
        try:
            for text in iter(stream.readline, ''):
                output_parts.append(text)
                with callback_lock:
                    output_callback(kind, text)
        finally:
            stream.close()

    stdout_thread = threading.Thread(
        target=consume_stream,
        args=(process.stdout, 'stdout', stdout_parts),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=consume_stream,
        args=(process.stderr, 'stderr', stderr_parts),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        stdout_thread.join()
        stderr_thread.join()
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output=''.join(stdout_parts),
            stderr=''.join(stderr_parts),
        ) from exc

    stdout_thread.join()
    stderr_thread.join()
    return subprocess.CompletedProcess(
        args=command,
        returncode=return_code,
        stdout=''.join(stdout_parts),
        stderr=''.join(stderr_parts),
    )


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
    async def install_plugin_job_services(
        cls,
        query_db: AsyncSession,
        discovered_plugin: DiscoveredPlugin,
        *,
        enabled: bool,
    ) -> None:
        """
        同步单个插件任务。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :param enabled: 插件任务是否启用
        :return: None
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
    async def is_plugin_installed_services(cls, query_db: AsyncSession, plugin_id: str) -> bool:
        """
        判断插件是否已经完成安装。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 是否已安装
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
    async def build_plugin_purge_plan_by_id_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
    ) -> PluginPurgePlan:
        """
        按插件 ID 构建孤儿元数据清理计划。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 插件清理计划
        """

    @classmethod
    async def purge_plugin_metadata_by_id_services(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
    ) -> PluginPurgePlan:
        """
        按插件 ID 清理孤儿元数据。

        :param query_db: orm对象
        :param plugin_id: 插件ID
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
class PluginConfigGateway(Protocol):
    """
    插件配置网关协议。
    """

    async def get_plugin_config(
        self,
        discovered_plugin: DiscoveredPlugin,
        *,
        reveal_secret: bool = False,
    ) -> list[PluginConfigValueModel]:
        """
        获取插件配置。

        :param discovered_plugin: 已发现插件
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置列表
        """

    async def update_plugin_config(
        self,
        discovered_plugin: DiscoveredPlugin,
        values: dict[str, PluginConfigValue],
    ) -> list[PluginConfigValueModel]:
        """
        更新插件配置。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :return: 插件配置列表
        """

    async def set_plugin_config(
        self,
        discovered_plugin: DiscoveredPlugin,
        values: dict[str, PluginConfigValue],
        *,
        audit_operation: str,
        success_message: str,
    ) -> list[PluginConfigValueModel]:
        """
        在同一事务中更新插件配置并记录审计日志。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :param audit_operation: 审计操作类型
        :param success_message: 操作成功提示
        :return: 插件配置列表
        """


@runtime_checkable
class PluginAuditGateway(Protocol):
    """
    插件审计网关协议。
    """

    async def list_plugin_operation_logs(self, *, export_limit: int) -> list[PluginOperationLogDetailModel]:
        """
        获取插件操作审计日志列表。

        :param export_limit: 导出数量上限
        :return: 插件操作日志详情列表
        """

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

    async def mark_plugin_error(self, plugin_id: str, error_message: str) -> bool:
        """
        标记插件错误状态。

        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 是否标记成功
        """


@runtime_checkable
class PluginStateQueryGateway(Protocol):
    """
    插件状态查询网关协议。
    """

    async def list_plugin_states(self) -> list[PluginStateRecord]:
        """
        获取插件状态列表。

        :return: 插件状态列表
        """

    async def get_plugin_state(self, plugin_id: str) -> PluginStateRecord | None:
        """
        获取插件状态。

        :param plugin_id: 插件ID
        :return: 插件状态
        """


@runtime_checkable
class PluginMigrationHistoryGateway(Protocol):
    """
    插件 migration 历史网关协议。
    """

    async def list_plugin_migrations(
        self,
        plugin_id: str,
        status: str | None = None,
    ) -> list[PluginMigrationModel]:
        """
        查询插件 migration 历史。

        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: 插件 migration 历史列表
        """

    async def get_plugin_migration(self, plugin_id: str, migration_path: str) -> PluginMigrationModel | None:
        """
        获取插件 migration 历史。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 插件 migration 历史
        """

    async def mark_plugin_migration_status(
        self,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> PluginMigrationModel | None:
        """
        人工标记插件 migration 历史状态。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 插件 migration 历史
        """


@runtime_checkable
class PluginPurgePlanGateway(Protocol):
    """
    插件清理计划网关协议。
    """

    async def build_plugin_purge_plan(self, discovered_plugin: DiscoveredPlugin) -> PluginPurgePlan:
        """
        构建插件物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """


@runtime_checkable
class PluginLifecycleStateGateway(Protocol):
    """
    插件生命周期状态写入网关协议。
    """

    async def set_plugin_enabled_state(
        self,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: DiscoveredPlugin | None = None,
    ) -> CrudResponseModel:
        """
        更新插件启停状态，并在启用时同步插件菜单。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param discovered_plugin: 已发现插件
        :return: 操作响应
        """

    async def mark_plugin_uninstalled_state(self, plugin_id: str) -> CrudResponseModel:
        """
        标记插件安全卸载。

        :param plugin_id: 插件ID
        :return: 操作响应
        """


@runtime_checkable
class PluginLifecycleUnitOfWork(Protocol):
    """
    插件生命周期主事务工作单元协议。
    """

    session: AsyncSession

    async def check_installed_menu_conflicts(self, discovered_plugin: DiscoveredPlugin) -> list[PluginMenuConflictItem]:
        """
        检查已安装菜单冲突。

        :param discovered_plugin: 已发现插件
        :return: 菜单冲突列表
        """

    async def upsert_discovered_plugin(
        self,
        discovered_plugin: DiscoveredPlugin,
        backend_root: Path,
        frontend_root: Path | None = None,
    ) -> PluginModel:
        """
        写入或更新已发现插件。

        :param discovered_plugin: 已发现插件
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件模型
        """

    async def install_plugin_menu(self, discovered_plugin: DiscoveredPlugin, *, enabled: bool) -> None:
        """
        安装插件菜单。

        :param discovered_plugin: 已发现插件
        :param enabled: 是否启用菜单
        :return: None
        """

    async def install_plugin_default_config(self, discovered_plugin: DiscoveredPlugin) -> list[PluginConfigModel]:
        """
        安装插件默认配置。

        :param discovered_plugin: 已发现插件
        :return: 插件配置列表
        """

    async def install_plugin_jobs(self, discovered_plugin: DiscoveredPlugin, *, enabled: bool) -> None:
        """
        同步单个插件任务。

        :param discovered_plugin: 已发现插件
        :param enabled: 插件任务是否启用
        :return: None
        """

    async def mark_plugin_installed(self, discovered_plugin: DiscoveredPlugin) -> PluginModel:
        """
        标记插件已安装。

        :param discovered_plugin: 已发现插件
        :return: 插件模型
        """

    async def build_plugin_purge_plan(self, discovered_plugin: DiscoveredPlugin) -> PluginPurgePlan:
        """
        构建插件物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """

    async def purge_plugin_metadata(self, discovered_plugin: DiscoveredPlugin) -> PluginPurgePlan:
        """
        清理插件平台元数据。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """

    async def build_plugin_purge_plan_by_id(self, plugin_id: str) -> PluginPurgePlan:
        """
        按插件 ID 构建孤儿元数据清理计划。

        :param plugin_id: 插件ID
        :return: 插件物理清理计划
        """

    async def purge_plugin_metadata_by_id(self, plugin_id: str) -> PluginPurgePlan:
        """
        按插件 ID 清理孤儿元数据。

        :param plugin_id: 插件ID
        :return: 插件物理清理计划
        """

    async def commit(self) -> None:
        """
        提交生命周期主事务。

        :return: None
        """


@runtime_checkable
class PluginLifecycleUnitOfWorkGateway(Protocol):
    """
    插件生命周期主事务工作单元网关协议。
    """

    def open_lifecycle_unit_of_work(self) -> AbstractAsyncContextManager[PluginLifecycleUnitOfWork]:
        """
        打开生命周期主事务工作单元。

        :return: 生命周期主事务工作单元上下文
        """


@runtime_checkable
class PluginMigrationExecutionGateway(Protocol):
    """
    插件 migration 独立执行网关协议。
    """

    async def run_plugin_migrations(self, discovered_plugin: DiscoveredPlugin) -> list[PluginMigrationResult]:
        """
        使用独立执行事务运行插件 migration。

        :param discovered_plugin: 已发现插件
        :return: migration 执行结果列表
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


class UnavailablePluginStateQueryGateway:
    """
    不可用的插件状态查询网关。
    """

    @staticmethod
    async def list_plugin_states() -> list[PluginStateRecord]:
        """
        获取插件状态列表。

        :return: 插件状态列表
        :raises RuntimeError: 默认网关不提供插件状态查询能力
        """
        raise RuntimeError('插件运行时缺少插件状态查询适配器')

    @staticmethod
    async def get_plugin_state(plugin_id: str) -> PluginStateRecord | None:
        """
        获取插件状态。

        :param plugin_id: 插件ID
        :return: 插件状态
        :raises RuntimeError: 默认网关不提供插件状态查询能力
        """
        raise RuntimeError('插件运行时缺少插件状态查询适配器')


class UnavailablePluginMigrationHistoryGateway:
    """
    不可用的插件 migration 历史网关。
    """

    @staticmethod
    async def list_plugin_migrations(
        plugin_id: str,
        status: str | None = None,
    ) -> list[PluginMigrationModel]:
        """
        查询插件 migration 历史。

        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: 插件 migration 历史列表
        :raises RuntimeError: 默认网关不提供插件 migration 历史能力
        """
        raise RuntimeError('插件运行时缺少 migration 历史适配器')

    @staticmethod
    async def get_plugin_migration(plugin_id: str, migration_path: str) -> PluginMigrationModel | None:
        """
        获取插件 migration 历史。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 插件 migration 历史
        :raises RuntimeError: 默认网关不提供插件 migration 历史能力
        """
        raise RuntimeError('插件运行时缺少 migration 历史适配器')

    @staticmethod
    async def mark_plugin_migration_status(
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> PluginMigrationModel | None:
        """
        人工标记插件 migration 历史状态。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 插件 migration 历史
        :raises RuntimeError: 默认网关不提供插件 migration 历史能力
        """
        raise RuntimeError('插件运行时缺少 migration 历史适配器')


class UnavailablePluginPurgePlanGateway:
    """
    不可用的插件清理计划网关。
    """

    @staticmethod
    async def build_plugin_purge_plan(discovered_plugin: DiscoveredPlugin) -> PluginPurgePlan:
        """
        构建插件物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        :raises RuntimeError: 默认网关不提供插件清理计划能力
        """
        raise RuntimeError('插件运行时缺少清理计划适配器')


class UnavailablePluginLifecycleStateGateway:
    """
    不可用的插件生命周期状态写入网关。
    """

    @staticmethod
    async def set_plugin_enabled_state(
        plugin_id: str,
        enabled: bool,
        discovered_plugin: DiscoveredPlugin | None = None,
    ) -> CrudResponseModel:
        """
        更新插件启停状态。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param discovered_plugin: 已发现插件
        :return: 操作响应
        :raises RuntimeError: 默认网关不提供生命周期状态写入能力
        """
        raise RuntimeError('插件运行时缺少生命周期状态适配器')

    @staticmethod
    async def mark_plugin_uninstalled_state(plugin_id: str) -> CrudResponseModel:
        """
        标记插件安全卸载。

        :param plugin_id: 插件ID
        :return: 操作响应
        :raises RuntimeError: 默认网关不提供生命周期状态写入能力
        """
        raise RuntimeError('插件运行时缺少生命周期状态适配器')


class UnavailablePluginLifecycleUnitOfWorkGateway:
    """
    不可用的插件生命周期主事务工作单元网关。
    """

    @staticmethod
    def open_lifecycle_unit_of_work() -> AbstractAsyncContextManager[PluginLifecycleUnitOfWork]:
        """
        打开生命周期主事务工作单元。

        :return: 生命周期主事务工作单元上下文
        :raises RuntimeError: 默认网关不提供生命周期主事务能力
        """
        raise RuntimeError('插件运行时缺少生命周期主事务适配器')


class UnavailablePluginMigrationExecutionGateway:
    """
    不可用的插件 migration 独立执行网关。
    """

    @staticmethod
    async def run_plugin_migrations(discovered_plugin: DiscoveredPlugin) -> list[PluginMigrationResult]:
        """
        使用独立执行事务运行插件 migration。

        :param discovered_plugin: 已发现插件
        :return: migration 执行结果列表
        :raises RuntimeError: 默认网关不提供 migration 执行能力
        """
        raise RuntimeError('插件运行时缺少 migration 执行适配器')


class UnavailablePluginConfigGateway:
    """
    不可用的插件配置网关。
    """

    @staticmethod
    async def get_plugin_config(
        discovered_plugin: DiscoveredPlugin,
        *,
        reveal_secret: bool = False,
    ) -> list[PluginConfigValueModel]:
        """
        获取插件配置。

        :param discovered_plugin: 已发现插件
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置列表
        :raises RuntimeError: 默认网关不提供插件配置能力
        """
        raise RuntimeError('插件运行时缺少插件配置适配器')

    @staticmethod
    async def update_plugin_config(
        discovered_plugin: DiscoveredPlugin,
        values: dict[str, PluginConfigValue],
    ) -> list[PluginConfigValueModel]:
        """
        更新插件配置。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :return: 插件配置列表
        :raises RuntimeError: 默认网关不提供插件配置能力
        """
        raise RuntimeError('插件运行时缺少插件配置适配器')

    @staticmethod
    async def set_plugin_config(
        discovered_plugin: DiscoveredPlugin,
        values: dict[str, PluginConfigValue],
        *,
        audit_operation: str,
        success_message: str,
    ) -> list[PluginConfigValueModel]:
        """
        在同一事务中更新插件配置并记录审计日志。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :param audit_operation: 审计操作类型
        :param success_message: 操作成功提示
        :return: 插件配置列表
        :raises RuntimeError: 默认网关不提供插件配置能力
        """
        raise RuntimeError('插件运行时缺少插件配置适配器')


class UnavailablePluginAuditGateway:
    """
    不可用的插件审计网关。
    """

    @staticmethod
    async def list_plugin_operation_logs(*, export_limit: int) -> list[PluginOperationLogDetailModel]:
        """
        获取插件操作审计日志列表。

        :param export_limit: 导出数量上限
        :return: 插件操作日志详情列表
        :raises RuntimeError: 默认网关不提供插件审计能力
        """
        raise RuntimeError('插件运行时缺少插件审计适配器')

    @staticmethod
    async def add_plugin_operation_log(
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
        :raises RuntimeError: 默认网关不提供插件审计能力
        """
        raise RuntimeError('插件运行时缺少插件审计适配器')

    @staticmethod
    async def mark_plugin_error(plugin_id: str, error_message: str) -> bool:
        """
        标记插件错误状态。

        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 是否标记成功
        :raises RuntimeError: 默认网关不提供插件审计能力
        """
        raise RuntimeError('插件运行时缺少插件审计适配器')


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
