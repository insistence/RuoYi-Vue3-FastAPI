import importlib.util
import re
from pathlib import Path
from types import ModuleType

SQL_LINE_COMMENT_PATTERN = re.compile(r'^\s*--')
DATABASE_DIALECT_DIRS = {'mysql', 'postgresql'}


class PluginLifecycleScriptHelper:
    """
    插件生命周期脚本通用工具。

    migration 和 seed 都支持 Python/SQL 文件、数据库方言目录和插件根目录约束，
    这里集中这些纯辅助逻辑，避免两个 runner 各自维护一套实现。
    """

    @staticmethod
    def split_sql_statements(sql_content: str) -> list[str]:
        """
        将 SQL 文件内容拆分为语句列表。

        :param sql_content: SQL 文件内容
        :return: SQL 语句列表
        """
        statement_chunks = []
        current_lines = []
        for line in sql_content.splitlines():
            if not line.strip() or SQL_LINE_COMMENT_PATTERN.match(line):
                continue
            current_lines.append(line)
            if line.rstrip().endswith(';'):
                statement_chunks.append('\n'.join(current_lines))
                current_lines = []
        if current_lines:
            statement_chunks.append('\n'.join(current_lines))

        return [statement.strip().removesuffix(';').strip() for statement in statement_chunks if statement.strip()]

    @staticmethod
    def filter_current_database_paths(
        script_paths: list[str],
        *,
        root_dir: str,
        database_type: str,
    ) -> list[str]:
        """
        过滤当前数据库方言不匹配的脚本。

        :param script_paths: 脚本相对路径列表
        :param root_dir: 方言目录父级，例如 migrations 或 seeds
        :param database_type: 当前数据库类型
        :return: 当前数据库需要执行的脚本列表
        """
        filtered_paths = []
        for script_path in script_paths:
            path_parts = Path(script_path).parts
            dialect_dir = path_parts[1] if len(path_parts) > 1 and path_parts[0] == root_dir else None
            if dialect_dir in DATABASE_DIALECT_DIRS and dialect_dir != database_type:
                continue
            filtered_paths.append(script_path)

        return filtered_paths

    @staticmethod
    def resolve_file(
        plugin_root: Path,
        script_path: str,
        *,
        supported_suffixes: set[str],
        label: str,
    ) -> Path:
        """
        解析生命周期脚本文件绝对路径。

        :param plugin_root: 插件后端根目录
        :param script_path: 脚本相对插件根目录路径
        :param supported_suffixes: 支持的文件后缀
        :param label: 脚本类型展示名
        :return: 脚本文件绝对路径
        """
        script_file = (plugin_root / script_path).resolve()
        resolved_plugin_root = plugin_root.resolve()
        if resolved_plugin_root not in script_file.parents:
            raise RuntimeError(f'插件 {label} 路径不能越过插件根目录：{script_path}')
        if script_file.suffix not in supported_suffixes:
            raise RuntimeError(f'插件 {label} 仅支持 Python 或 SQL 文件：{script_path}')
        if not script_file.is_file():
            raise RuntimeError(f'插件 {label} 文件不存在：{script_path}')

        return script_file

    @staticmethod
    def load_module(module_name: str, script_file: Path, *, label: str) -> ModuleType:
        """
        加载生命周期 Python 脚本模块。

        :param module_name: 模块名
        :param script_file: 脚本文件绝对路径
        :param label: 脚本类型展示名
        :return: Python 模块
        """
        module_spec = importlib.util.spec_from_file_location(module_name, script_file)
        if module_spec is None or module_spec.loader is None:
            raise RuntimeError(f'插件 {label} 模块加载失败：{script_file}')
        script_module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(script_module)

        return script_module

    @staticmethod
    def build_module_name(plugin_id: str, plugin_root: Path, script_file: Path) -> str:
        """
        构建生命周期脚本模块名。

        :param plugin_id: 插件ID
        :param plugin_root: 插件后端根目录
        :param script_file: 脚本文件绝对路径
        :return: 模块名
        """
        relative_path = script_file.relative_to(plugin_root).with_suffix('')
        module_suffix = '.'.join(relative_path.parts)

        return f'plugins.{plugin_id}.{module_suffix}'
