import subprocess
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PluginStateGateway(Protocol):
    """
    插件管理状态网关协议。
    """

    def get_async_session_local(self) -> Any:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        """

    def get_plugin_service(self) -> Any:
        """
        获取插件管理服务类。

        :return: 插件管理服务类
        """


@runtime_checkable
class PluginManagementModelGateway(Protocol):
    """
    插件管理模型工厂网关协议。
    """

    def build_operation_log_export_query(self, export_limit: int) -> Any:
        """
        构建插件操作日志导出查询对象。

        :param export_limit: 导出数量上限
        :return: 插件操作日志导出查询对象
        """

    def build_config_update(self, values: dict[str, Any]) -> Any:
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
    ) -> Any:
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
    def get_async_session_local() -> Any:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        :raises RuntimeError: 默认网关不提供数据库访问能力
        """
        raise RuntimeError('插件运行时缺少数据库会话适配器')

    @staticmethod
    def get_plugin_service() -> Any:
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
    def build_operation_log_export_query(export_limit: int) -> Any:
        """
        构建插件操作日志导出查询对象。

        :param export_limit: 导出数量上限
        :return: 插件操作日志导出查询对象
        :raises RuntimeError: 默认网关不提供管理状态 VO 适配器
        """
        raise RuntimeError('插件运行时缺少操作日志查询适配器')

    @staticmethod
    def build_config_update(values: dict[str, Any]) -> Any:
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
    ) -> Any:
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
