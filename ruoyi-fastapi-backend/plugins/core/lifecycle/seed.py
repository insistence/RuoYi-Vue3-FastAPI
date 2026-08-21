import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

from config.env import DataBaseConfig
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.script import PluginLifecycleScriptHelper

SUPPORTED_SEED_SUFFIXES = {'.py', '.sql'}


@dataclass(frozen=True)
class PluginSeedResult:
    """
    插件 seed 执行结果。
    """

    seed_path: str
    module_name: str
    statement_count: int = 0


class PluginSeedRunner:
    """
    插件 seed 运行器。

    使用 Command Runner 模式按 manifest 声明顺序执行插件初始化脚本。
    Python seed 模块需要暴露 `run(query_db)` 函数，SQL seed 会按分号拆分并逐条执行。
    """

    def __init__(self, discovered_plugin: DiscoveredPlugin) -> None:
        """
        初始化插件 seed 运行器。

        :param discovered_plugin: 已发现插件对象
        """
        self.discovered_plugin = discovered_plugin

    async def run(self, query_db: Any) -> list[PluginSeedResult]:
        """
        执行插件清单声明的 seed。

        :param query_db: orm对象
        :return: seed 执行结果列表
        """
        return [
            await self._run_seed(seed_path, query_db)
            for seed_path in self._filter_current_database_seeds(self.discovered_plugin.manifest.backend.seeds)
        ]

    async def _run_seed(self, seed_path: str, query_db: Any) -> PluginSeedResult:
        """
        执行单个 seed。

        :param seed_path: seed 相对插件根目录路径
        :param query_db: orm对象
        :return: seed 执行结果
        """
        seed_file = self._resolve_seed_file(seed_path)
        if seed_file.suffix == '.sql':
            return await self._run_sql_seed(seed_path, seed_file, query_db)

        return await self._run_python_seed(seed_path, seed_file, query_db)

    async def _run_python_seed(self, seed_path: str, seed_file: Path, query_db: Any) -> PluginSeedResult:
        """
        执行 Python seed。

        :param seed_path: seed 相对插件根目录路径
        :param seed_file: seed 文件绝对路径
        :param query_db: orm对象
        :return: seed 执行结果
        """
        seed_module = self._load_seed_module(seed_file)
        seed_runner = getattr(seed_module, 'run', None)
        if not callable(seed_runner):
            raise RuntimeError(f'插件 seed 必须暴露 run(query_db) 函数：{seed_path}')

        result = seed_runner(query_db)
        if inspect.isawaitable(result):
            await result

        return PluginSeedResult(seed_path=seed_path, module_name=seed_module.__name__)

    async def _run_sql_seed(self, seed_path: str, seed_file: Path, query_db: Any) -> PluginSeedResult:
        """
        执行 SQL seed。

        :param seed_path: seed 相对插件根目录路径
        :param seed_file: seed 文件绝对路径
        :param query_db: orm对象
        :return: seed 执行结果
        """
        statements = self._load_sql_statements(seed_file)
        for statement in statements:
            await query_db.execute(text(statement))

        return PluginSeedResult(
            seed_path=seed_path,
            module_name=self._build_seed_module_name(seed_file),
            statement_count=len(statements),
        )

    def _load_sql_statements(self, seed_file: Path) -> list[str]:
        """
        加载 SQL seed 语句列表。

        :param seed_file: seed 文件绝对路径
        :return: SQL 语句列表
        """
        return PluginLifecycleScriptHelper.split_sql_statements(seed_file.read_text(encoding='utf-8'))

    def _resolve_seed_file(self, seed_path: str) -> Path:
        """
        解析 seed 文件绝对路径。

        :param seed_path: seed 相对插件根目录路径
        :return: seed 文件绝对路径
        """
        return PluginLifecycleScriptHelper.resolve_file(
            self.discovered_plugin.backend_path,
            seed_path,
            supported_suffixes=SUPPORTED_SEED_SUFFIXES,
            label='seed',
        )

    @classmethod
    def _filter_current_database_seeds(cls, seed_paths: list[str]) -> list[str]:
        """
        过滤当前数据库方言不匹配的 seed。

        :param seed_paths: seed 相对路径列表
        :return: 当前数据库需要执行的 seed 列表
        """
        return PluginLifecycleScriptHelper.filter_current_database_paths(
            seed_paths,
            root_dir='seeds',
            database_type=DataBaseConfig.default_source.db_type,
        )

    def _load_seed_module(self, seed_file: Path) -> Any:
        """
        加载 seed Python 模块。

        :param seed_file: seed 文件绝对路径
        :return: seed 模块
        """
        module_name = self._build_seed_module_name(seed_file)
        return PluginLifecycleScriptHelper.load_module(module_name, seed_file, label='seed')

    def _build_seed_module_name(self, seed_file: Path) -> str:
        """
        构建 seed 模块名。

        :param seed_file: seed 文件绝对路径
        :return: seed 模块名
        """
        return PluginLifecycleScriptHelper.build_module_name(
            self.discovered_plugin.manifest.id,
            self.discovered_plugin.backend_path,
            seed_file,
        )
