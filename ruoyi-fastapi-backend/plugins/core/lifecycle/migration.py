import hashlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

from config.env import DataBaseConfig
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.script import PluginLifecycleScriptHelper

SUPPORTED_MIGRATION_SUFFIXES = {'.py', '.sql'}


@dataclass(frozen=True)
class PluginMigrationResult:
    """
    插件 migration 执行结果。

    :param migration_path: migration 相对插件根目录路径
    :param module_name: migration 模块名
    :param statement_count: SQL 语句数量
    :param checksum: migration 内容校验值
    :param skipped: 是否跳过执行
    """

    migration_path: str
    module_name: str
    statement_count: int = 0
    checksum: str | None = None
    skipped: bool = False


class PluginMigrationHistoryStore:
    """
    插件 migration 历史存储接口。
    """

    async def get_checksum(self, query_db: Any, plugin_id: str, migration_path: str) -> str | None:
        """
        获取已执行 migration 的内容校验值。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 内容校验值，不存在时返回 None
        """
        raise NotImplementedError

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
        raise NotImplementedError


class PluginMigrationRunner:
    """
    插件 migration 运行器。

    使用 Command Runner 模式按 manifest 声明顺序执行插件结构迁移脚本。
    Python migration 模块需要暴露 `run(query_db)` 函数，SQL migration 会按分号拆分并逐条执行。
    """

    def __init__(
        self,
        discovered_plugin: DiscoveredPlugin,
        history_store: PluginMigrationHistoryStore | None = None,
    ) -> None:
        """
        初始化插件 migration 运行器。

        :param discovered_plugin: 已发现插件对象
        :param history_store: migration 执行历史存储
        :return: None
        """
        self.discovered_plugin = discovered_plugin
        self.history_store = history_store

    async def run(self, query_db: Any) -> list[PluginMigrationResult]:
        """
        执行插件清单声明的 migration。

        :param query_db: orm对象
        :return: migration 执行结果列表
        """
        return [
            await self._run_migration(migration_path, query_db)
            for migration_path in self._filter_current_database_migrations(
                self.discovered_plugin.manifest.backend.migrations
            )
        ]

    async def _run_migration(self, migration_path: str, query_db: Any) -> PluginMigrationResult:
        """
        执行单个 migration。

        :param migration_path: migration 相对插件根目录路径
        :param query_db: orm对象
        :return: migration 执行结果
        """
        migration_file = self._resolve_migration_file(migration_path)
        checksum = self._calculate_checksum(migration_file)
        existing_checksum = await self._get_existing_checksum(query_db, migration_path)
        if existing_checksum:
            if existing_checksum != checksum:
                raise RuntimeError(
                    f'插件 migration 已执行但内容校验值变化：{migration_path}，请新增 migration 文件而不是修改历史文件'
                )
            return PluginMigrationResult(
                migration_path=migration_path,
                module_name=self._build_migration_module_name(migration_file),
                checksum=checksum,
                skipped=True,
            )

        if migration_file.suffix == '.sql':
            result = await self._run_sql_migration(migration_path, migration_file, query_db, checksum)
        else:
            result = await self._run_python_migration(migration_path, migration_file, query_db, checksum)

        await self._record_success(query_db, result)

        return result

    async def _run_python_migration(
        self,
        migration_path: str,
        migration_file: Path,
        query_db: Any,
        checksum: str,
    ) -> PluginMigrationResult:
        """
        执行 Python migration。

        :param migration_path: migration 相对插件根目录路径
        :param migration_file: migration 文件绝对路径
        :param query_db: orm对象
        :param checksum: migration 内容校验值
        :return: migration 执行结果
        """
        migration_module = self._load_migration_module(migration_file)
        migration_runner = getattr(migration_module, 'run', None)
        if not callable(migration_runner):
            raise RuntimeError(f'插件 migration 必须暴露 run(query_db) 函数：{migration_path}')

        result = migration_runner(query_db)
        if inspect.isawaitable(result):
            await result

        return PluginMigrationResult(
            migration_path=migration_path,
            module_name=migration_module.__name__,
            checksum=checksum,
        )

    async def _run_sql_migration(
        self,
        migration_path: str,
        migration_file: Path,
        query_db: Any,
        checksum: str,
    ) -> PluginMigrationResult:
        """
        执行 SQL migration。

        :param migration_path: migration 相对插件根目录路径
        :param migration_file: migration 文件绝对路径
        :param query_db: orm对象
        :param checksum: migration 内容校验值
        :return: migration 执行结果
        """
        statements = self._load_sql_statements(migration_file)
        for statement in statements:
            await query_db.execute(text(statement))

        return PluginMigrationResult(
            migration_path=migration_path,
            module_name=self._build_migration_module_name(migration_file),
            statement_count=len(statements),
            checksum=checksum,
        )

    async def _get_existing_checksum(self, query_db: Any, migration_path: str) -> str | None:
        """
        获取已执行 migration 的内容校验值。

        :param query_db: orm对象
        :param migration_path: migration 相对路径
        :return: 内容校验值，不存在时返回 None
        """
        if not self.history_store:
            return None

        return await self.history_store.get_checksum(query_db, self.discovered_plugin.manifest.id, migration_path)

    async def _record_success(self, query_db: Any, result: PluginMigrationResult) -> None:
        """
        记录 migration 成功执行历史。

        :param query_db: orm对象
        :param result: migration 执行结果
        :return: None
        """
        if not self.history_store or not result.checksum:
            return

        await self.history_store.record_success(
            query_db,
            self.discovered_plugin.manifest.id,
            result.migration_path,
            result.checksum,
            self.discovered_plugin.manifest.version,
            result.statement_count,
        )

    def _load_sql_statements(self, migration_file: Path) -> list[str]:
        """
        加载 SQL migration 语句列表。

        :param migration_file: migration 文件绝对路径
        :return: SQL 语句列表
        """
        return PluginLifecycleScriptHelper.split_sql_statements(migration_file.read_text(encoding='utf-8'))

    def _resolve_migration_file(self, migration_path: str) -> Path:
        """
        解析 migration 文件绝对路径。

        :param migration_path: migration 相对插件根目录路径
        :return: migration 文件绝对路径
        """
        return PluginLifecycleScriptHelper.resolve_file(
            self.discovered_plugin.backend_path,
            migration_path,
            supported_suffixes=SUPPORTED_MIGRATION_SUFFIXES,
            label='migration',
        )

    @staticmethod
    def _split_sql_statements(sql_content: str) -> list[str]:
        """
        将 SQL migration 内容拆分为语句列表。

        :param sql_content: SQL 文件内容
        :return: SQL 语句列表
        """
        return PluginLifecycleScriptHelper.split_sql_statements(sql_content)

    @classmethod
    def _filter_current_database_migrations(cls, migration_paths: list[str]) -> list[str]:
        """
        过滤当前数据库方言不匹配的 migration。

        :param migration_paths: migration 相对路径列表
        :return: 当前数据库需要执行的 migration 列表
        """
        return PluginLifecycleScriptHelper.filter_current_database_paths(
            migration_paths,
            root_dir='migrations',
            database_type=DataBaseConfig.db_type,
        )

    def _load_migration_module(self, migration_file: Path) -> Any:
        """
        加载 migration Python 模块。

        :param migration_file: migration 文件绝对路径
        :return: migration 模块
        """
        module_name = self._build_migration_module_name(migration_file)
        return PluginLifecycleScriptHelper.load_module(module_name, migration_file, label='migration')

    @staticmethod
    def _calculate_checksum(migration_file: Path) -> str:
        """
        计算 migration 文件内容校验值。

        :param migration_file: migration 文件绝对路径
        :return: SHA256 内容校验值
        """
        return hashlib.sha256(migration_file.read_bytes()).hexdigest()

    def _build_migration_module_name(self, migration_file: Path) -> str:
        """
        构建 migration 模块名。

        :param migration_file: migration 文件绝对路径
        :return: migration 模块名
        """
        return PluginLifecycleScriptHelper.build_module_name(
            self.discovered_plugin.manifest.id,
            self.discovered_plugin.backend_path,
            migration_file,
        )
