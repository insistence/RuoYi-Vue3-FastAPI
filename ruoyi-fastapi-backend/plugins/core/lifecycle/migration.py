import asyncio
import hashlib
import inspect
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

from config.env import DataBaseConfig
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.script import PluginLifecycleScriptHelper

SUPPORTED_MIGRATION_SUFFIXES = {'.py', '.sql'}
MIGRATION_ERROR_MESSAGE_MAX_LENGTH = 1000


class PluginMigrationError(RuntimeError):
    """
    插件 migration 可恢复错误。
    """

    def __init__(
        self,
        message: str,
        *,
        migration_path: str,
        status: str,
        recovery_suggestion: str,
    ) -> None:
        """
        初始化插件 migration 错误。

        :param message: 错误消息
        :param migration_path: migration 相对插件根目录路径
        :param status: 当前 migration 状态
        :param recovery_suggestion: 恢复建议
        """
        super().__init__(message)
        self.migration_path = migration_path
        self.status = status
        self.recovery_suggestion = recovery_suggestion

    def to_recovery_payload(self) -> dict[str, object]:
        """
        转换为恢复建议负载。

        :return: migration 恢复建议负载
        """
        return {
            'migrationPath': self.migration_path,
            'status': self.status,
            'suggestion': self.recovery_suggestion,
        }


@dataclass(frozen=True)
class PluginMigrationHistoryRecord:
    """
    插件 migration 历史记录。

    :param checksum: migration 内容校验值
    :param status: 执行状态
    :param error_message: 失败错误信息
    """

    checksum: str
    status: str = 'success'
    error_message: str | None = None


@dataclass(frozen=True)
class PluginMigrationResult:
    """
    插件 migration 执行结果。

    :param migration_path: migration 相对插件根目录路径
    :param module_name: migration 模块名
    :param statement_count: SQL 语句数量
    :param checksum: migration 内容校验值
    :param skipped: 是否跳过执行
    :param status: 执行状态
    :param duration_ms: 执行耗时，单位毫秒
    :param recovery_suggestion: 恢复建议
    """

    migration_path: str
    module_name: str
    statement_count: int = 0
    checksum: str | None = None
    skipped: bool = False
    status: str = 'success'
    duration_ms: int = 0
    recovery_suggestion: str | None = None


class PluginMigrationHistoryStore:
    """
    插件 migration 历史存储接口。
    """

    async def get_record(
        self,
        query_db: Any,
        plugin_id: str,
        migration_path: str,
    ) -> PluginMigrationHistoryRecord | None:
        """
        获取 migration 执行历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: migration 执行历史，不存在时返回 None
        """
        raise NotImplementedError

    async def get_checksum(self, query_db: Any, plugin_id: str, migration_path: str) -> str | None:
        """
        获取已执行 migration 的内容校验值。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 内容校验值，不存在时返回 None
        """
        record = await self.get_record(query_db, plugin_id, migration_path)
        if not record or record.status != 'success':
            return None
        return record.checksum

    async def record_running(
        self,
        query_db: Any,
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

    async def record_failure(
        self,
        query_db: Any,
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
        :param statement_count: 已解析 SQL 语句数量
        :param error_message: 失败错误信息
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
        *,
        manage_execution_transaction: bool = False,
    ) -> None:
        """
        初始化插件 migration 运行器。

        :param discovered_plugin: 已发现插件对象
        :param history_store: migration 执行历史存储
        :param manage_execution_transaction: 是否由 runner 提交或回滚执行 session
        :return: None
        """
        self.discovered_plugin = discovered_plugin
        self.history_store = history_store
        self.manage_execution_transaction = manage_execution_transaction

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
        checksum = await asyncio.to_thread(self._calculate_checksum, migration_file)
        existing_record = await self._get_existing_record(query_db, migration_path)
        if existing_record:
            if existing_record.status == 'success':
                if existing_record.checksum != checksum:
                    raise PluginMigrationError(
                        f'插件 migration 已执行但内容校验值变化：{migration_path}，请新增 migration 文件而不是修改历史文件',
                        migration_path=migration_path,
                        status='success',
                        recovery_suggestion='请恢复原 migration 文件内容，或新增一个后续 migration 文件承载变更。',
                    )
                return PluginMigrationResult(
                    migration_path=migration_path,
                    module_name=self._build_migration_module_name(migration_file),
                    checksum=checksum,
                    skipped=True,
                    status='success',
                )
            if existing_record.status == 'running':
                raise PluginMigrationError(
                    f'插件 migration 上次执行仍处于 running 状态：{migration_path}，'
                    '请确认数据库结构状态后手动处理迁移历史',
                    migration_path=migration_path,
                    status='running',
                    recovery_suggestion=(
                        '请检查数据库结构是否已应用；若已成功应用，执行 mark-success；'
                        '若未完成，执行 mark-failed 后修复并重试。'
                    ),
                )
            if existing_record.status != 'failed':
                raise PluginMigrationError(
                    f'插件 migration 历史状态不支持自动执行：{migration_path}，状态：{existing_record.status}',
                    migration_path=migration_path,
                    status=existing_record.status,
                    recovery_suggestion='请人工确认 migration 历史状态，并通过恢复命令标记为 success 或 failed。',
                )

        started_at = time.perf_counter()
        await self._record_running(query_db, migration_path, checksum)
        try:
            if migration_file.suffix == '.sql':
                result = await self._run_sql_migration(migration_path, migration_file, query_db, checksum)
            else:
                result = await self._run_python_migration(migration_path, migration_file, query_db, checksum)
            await self._commit_execution_transaction(query_db)
        except Exception as exc:
            with suppress(Exception):
                await self._rollback_execution_transaction(query_db)
            await self._record_failure(query_db, migration_path, checksum, str(exc))
            await self._commit_execution_transaction(query_db)
            raise PluginMigrationError(
                f'插件 migration 执行失败：{migration_path}，{exc}',
                migration_path=migration_path,
                status='failed',
                recovery_suggestion='请修复 migration 幂等性或数据库结构问题后重试；必要时人工确认后标记成功。',
            ) from exc

        duration_ms = max(int((time.perf_counter() - started_at) * 1000), 0)
        result = PluginMigrationResult(
            migration_path=result.migration_path,
            module_name=result.module_name,
            statement_count=result.statement_count,
            checksum=result.checksum,
            skipped=result.skipped,
            status='success',
            duration_ms=duration_ms,
        )

        try:
            await self._record_success(query_db, result)
        except Exception as exc:
            raise PluginMigrationError(
                f'插件 migration 已执行，但成功历史记录失败：{migration_path}，{exc}',
                migration_path=migration_path,
                status='running',
                recovery_suggestion=(
                    '请检查数据库结构是否已应用；若已成功应用，执行 mark-success；'
                    '若未完成，执行 mark-failed 后修复并重试。'
                ),
            ) from exc

        return result

    async def _commit_execution_transaction(self, query_db: Any) -> None:
        """
        提交 migration 执行事务。

        :param query_db: migration 执行 session
        :return: None
        """
        if not self.manage_execution_transaction:
            return

        await self._call_execution_transaction_method(query_db, 'commit')

    async def _rollback_execution_transaction(self, query_db: Any) -> None:
        """
        回滚 migration 执行事务。

        :param query_db: migration 执行 session
        :return: None
        """
        if not self.manage_execution_transaction:
            return

        await self._call_execution_transaction_method(query_db, 'rollback')

    async def _call_execution_transaction_method(self, query_db: Any, method_name: str) -> None:
        """
        调用 migration 执行 session 的事务方法。

        :param query_db: migration 执行 session
        :param method_name: 事务方法名
        :return: None
        """
        method = getattr(query_db, method_name, None)
        if not callable(method):
            raise RuntimeError(f'migration 执行 session 缺少 {method_name} 方法')

        result = method()
        if inspect.isawaitable(result):
            await result

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
        statements = await asyncio.to_thread(self._load_sql_statements, migration_file)
        for statement in statements:
            await query_db.execute(text(statement))

        return PluginMigrationResult(
            migration_path=migration_path,
            module_name=self._build_migration_module_name(migration_file),
            statement_count=len(statements),
            checksum=checksum,
        )

    async def _get_existing_record(self, query_db: Any, migration_path: str) -> PluginMigrationHistoryRecord | None:
        """
        获取 migration 已有执行历史。

        :param query_db: orm对象
        :param migration_path: migration 相对路径
        :return: migration 执行历史
        """
        if not self.history_store:
            return None

        return await self.history_store.get_record(query_db, self.discovered_plugin.manifest.id, migration_path)

    async def _record_running(self, query_db: Any, migration_path: str, checksum: str) -> None:
        """
        记录 migration 开始执行。

        :param query_db: orm对象
        :param migration_path: migration 相对路径
        :param checksum: migration 内容校验值
        :return: None
        """
        if not self.history_store:
            return

        await self.history_store.record_running(
            query_db,
            self.discovered_plugin.manifest.id,
            migration_path,
            checksum,
            self.discovered_plugin.manifest.version,
            self._get_statement_count(migration_path),
        )

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

    async def _record_failure(
        self,
        query_db: Any,
        migration_path: str,
        checksum: str,
        error_message: str,
    ) -> None:
        """
        记录 migration 失败历史。

        :param query_db: orm对象
        :param migration_path: migration 相对路径
        :param checksum: migration 内容校验值
        :param error_message: 失败错误信息
        :return: None
        """
        if not self.history_store:
            return

        try:
            statement_count = self._get_statement_count(migration_path)
        except Exception:
            statement_count = 0
        await self.history_store.record_failure(
            query_db,
            self.discovered_plugin.manifest.id,
            migration_path,
            checksum,
            self.discovered_plugin.manifest.version,
            statement_count,
            error_message[:MIGRATION_ERROR_MESSAGE_MAX_LENGTH],
        )

    def _get_statement_count(self, migration_path: str) -> int:
        """
        获取 SQL migration 语句数量。

        :param migration_path: migration 相对路径
        :return: SQL 语句数量
        """
        migration_file = self._resolve_migration_file(migration_path)
        if migration_file.suffix != '.sql':
            return 0
        return len(self._load_sql_statements(migration_file))

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
