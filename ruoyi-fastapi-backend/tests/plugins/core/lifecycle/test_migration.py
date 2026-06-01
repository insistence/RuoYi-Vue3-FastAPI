import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.discovery.scanner import PluginScanner  # noqa: E402
from plugins.core.lifecycle.migration import PluginMigrationHistoryStore, PluginMigrationRunner  # noqa: E402


class FakeMigrationHistoryStore(PluginMigrationHistoryStore):
    """
    测试用 migration 历史存储。
    """

    def __init__(self, checksums: dict[tuple[str, str], str] | None = None) -> None:
        """
        初始化测试用 migration 历史存储。

        :param checksums: 已执行 migration 校验值映射
        :return: None
        """
        self.checksums = checksums or {}
        self.records = []

    async def get_checksum(self, query_db: object, plugin_id: str, migration_path: str) -> str | None:
        """
        获取已执行 migration 校验值。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 内容校验值
        """
        return self.checksums.get((plugin_id, migration_path))

    async def record_success(
        self,
        query_db: object,
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
        :param version: 插件版本
        :param statement_count: SQL 语句数量
        :return: None
        """
        self.records.append((plugin_id, migration_path, checksum, version, statement_count))


def write_plugin_with_migration(
    plugin_root: Path,
    migration_content: str,
    migration_name: str = '001_demo.py',
) -> None:
    """
    写入带 migration 的测试插件。

    :param plugin_root: 插件根目录
    :param migration_content: migration 文件内容
    :param migration_name: migration 文件名
    :return: None
    """
    (plugin_root / 'migrations').mkdir(parents=True)
    (plugin_root / 'migrations' / migration_name).write_text(migration_content, encoding='utf-8')
    (plugin_root / 'plugin.yaml').write_text(
        f"""
id: demo_migration
name: Demo Migration
version: 1.0.0
backend:
  module: plugins.demo_migration
  migrations:
    - migrations/{migration_name}
""",
        encoding='utf-8',
    )


def write_plugin_with_database_migrations(plugin_root: Path) -> None:
    """
    写入带数据库方言 migration 的测试插件。

    :param plugin_root: 插件根目录
    :return: None
    """
    (plugin_root / 'migrations' / 'mysql').mkdir(parents=True)
    (plugin_root / 'migrations' / 'postgresql').mkdir(parents=True)
    (plugin_root / 'migrations' / 'mysql' / '001_demo.sql').write_text(
        'create table mysql_value (id integer primary key);\n',
        encoding='utf-8',
    )
    (plugin_root / 'migrations' / 'postgresql' / '001_demo.sql').write_text(
        'create table postgresql_value (id integer primary key);\n',
        encoding='utf-8',
    )
    (plugin_root / 'plugin.yaml').write_text(
        """
id: demo_migration
name: Demo Migration
version: 1.0.0
backend:
  module: plugins.demo_migration
  migrations:
    - migrations/mysql/001_demo.sql
    - migrations/postgresql/001_demo.sql
""",
        encoding='utf-8',
    )


@pytest.mark.asyncio
async def test_plugin_migration_runner_executes_async_migration(tmp_path: Path) -> None:
    """
    校验 migration 运行器可以执行异步 Python migration。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("async_migration")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    query_db = []

    results = await PluginMigrationRunner(discovered_plugin).run(query_db)

    assert query_db == ['async_migration']
    assert results[0].migration_path == 'migrations/001_demo.py'
    assert results[0].checksum
    assert results[0].skipped is False


@pytest.mark.asyncio
async def test_plugin_migration_runner_rejects_missing_run_function(tmp_path: Path) -> None:
    """
    校验 migration 缺少 run 函数时会失败。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'VALUE = 1\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    with pytest.raises(RuntimeError, match='run'):
        await PluginMigrationRunner(discovered_plugin).run([])


@pytest.mark.asyncio
async def test_plugin_migration_runner_executes_sql_migration(tmp_path: Path) -> None:
    """
    校验 migration 运行器可以执行 SQL migration。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(
        plugin_root,
        """
-- 初始化演示表
create table demo_migration_value (id integer primary key, name varchar(64));
insert into demo_migration_value (id, name) values (1, 'demo');
""",
        migration_name='001_demo.sql',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with session_maker() as session:
            results = await PluginMigrationRunner(discovered_plugin).run(session)
            rows = (await session.execute(text('select name from demo_migration_value where id = 1'))).all()

        assert results[0].migration_path == 'migrations/001_demo.sql'
        expected_statement_count = 2
        assert results[0].statement_count == expected_statement_count
        assert rows == [('demo',)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_migration_runner_filters_database_dialect_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    校验 migration 运行器只执行当前数据库方言目录下的 migration。

    :param tmp_path: pytest 临时目录
    :param monkeypatch: pytest monkeypatch fixture
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_database_migrations(plugin_root)
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr('plugins.core.lifecycle.migration.DataBaseConfig.db_type', 'mysql')

    try:
        async with session_maker() as session:
            results = await PluginMigrationRunner(discovered_plugin).run(session)
            mysql_rows = (
                await session.execute(text("select name from sqlite_master where name = 'mysql_value'"))
            ).all()
            postgresql_rows = (
                await session.execute(text("select name from sqlite_master where name = 'postgresql_value'"))
            ).all()

        assert [result.migration_path for result in results] == ['migrations/mysql/001_demo.sql']
        assert mysql_rows == [('mysql_value',)]
        assert postgresql_rows == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_migration_runner_records_success_history(tmp_path: Path) -> None:
    """
    校验 migration 执行成功后会记录历史。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("history")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore()
    query_db = []

    results = await PluginMigrationRunner(discovered_plugin, history_store).run(query_db)

    assert query_db == ['history']
    assert len(history_store.records) == 1
    assert history_store.records[0][0] == 'demo_migration'
    assert history_store.records[0][1] == 'migrations/001_demo.py'
    assert history_store.records[0][2] == results[0].checksum
    assert history_store.records[0][3] == '1.0.0'


@pytest.mark.asyncio
async def test_plugin_migration_runner_skips_existing_history(tmp_path: Path) -> None:
    """
    校验已执行且校验值一致的 migration 会跳过。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("should_not_run")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    migration_file = plugin_root / 'migrations' / '001_demo.py'
    checksum = PluginMigrationRunner._calculate_checksum(migration_file)
    history_store = FakeMigrationHistoryStore({('demo_migration', 'migrations/001_demo.py'): checksum})
    query_db = []

    results = await PluginMigrationRunner(discovered_plugin, history_store).run(query_db)

    assert query_db == []
    assert results[0].skipped is True
    assert results[0].checksum == checksum
    assert history_store.records == []


@pytest.mark.asyncio
async def test_plugin_migration_runner_rejects_checksum_drift(tmp_path: Path) -> None:
    """
    校验已执行 migration 内容发生变化时会失败。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("changed")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore({('demo_migration', 'migrations/001_demo.py'): 'old-checksum'})

    with pytest.raises(RuntimeError, match='内容校验值变化'):
        await PluginMigrationRunner(discovered_plugin, history_store).run([])
