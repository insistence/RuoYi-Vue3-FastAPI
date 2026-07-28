from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.core.discovery.scanner import PluginScanner
from plugins.core.lifecycle.migration import (
    PluginMigrationError,
    PluginMigrationHistoryRecord,
    PluginMigrationHistoryStore,
    PluginMigrationRunner,
)


class FakeManagedMigrationSession(list):
    """
    测试用托管 migration 执行 session。
    """

    def __init__(self) -> None:
        """初始化测试用托管 migration 执行 session。"""
        super().__init__()
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        """记录提交动作。"""
        self.committed = True

    async def rollback(self) -> None:
        """记录回滚动作。"""
        self.rolled_back = True


class FakeMigrationHistoryStore(PluginMigrationHistoryStore):
    """
    测试用 migration 历史存储。
    """

    def __init__(
        self,
        checksums: dict[tuple[str, str], str] | None = None,
        records: dict[tuple[str, str], PluginMigrationHistoryRecord] | None = None,
    ) -> None:
        """初始化测试用 migration 历史存储。"""
        self.history_records = records or {
            key: PluginMigrationHistoryRecord(checksum=value) for key, value in (checksums or {}).items()
        }
        self.records = []
        self.running_records = []
        self.failure_records = []

    async def get_record(
        self,
        query_db: object,
        plugin_id: str,
        migration_path: str,
    ) -> PluginMigrationHistoryRecord | None:
        """获取已执行 migration 记录。"""
        return self.history_records.get((plugin_id, migration_path))

    async def record_running(
        self,
        query_db: object,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
    ) -> None:
        """记录 migration 开始执行。"""
        self.running_records.append((plugin_id, migration_path, checksum, version, statement_count))

    async def record_success(
        self,
        query_db: object,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
    ) -> None:
        """记录 migration 成功执行历史。"""
        self.records.append((plugin_id, migration_path, checksum, version, statement_count))

    async def record_failure(
        self,
        query_db: object,
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
        error_message: str,
    ) -> None:
        """记录 migration 失败历史。"""
        self.failure_records.append((plugin_id, migration_path, checksum, version, statement_count, error_message))


def write_plugin_with_migration(
    plugin_root: Path,
    migration_content: str,
    migration_name: str = '001_demo.py',
) -> None:
    """写入带 migration 的测试插件。"""
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
    """写入带数据库方言 migration 的测试插件。"""
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
    """校验 migration 运行器可以执行异步 Python migration。"""
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
    """校验 migration 缺少 run 函数时会失败。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'VALUE = 1\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    with pytest.raises(RuntimeError, match='run'):
        await PluginMigrationRunner(discovered_plugin).run([])


@pytest.mark.asyncio
async def test_plugin_migration_runner_executes_sql_migration(tmp_path: Path) -> None:
    """校验 migration 运行器可以执行 SQL migration。"""
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
    """校验 migration 运行器只执行当前数据库方言目录下的 migration。"""
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
    """校验 migration 执行成功后会记录历史。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("history")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore()
    query_db = []

    results = await PluginMigrationRunner(discovered_plugin, history_store).run(query_db)

    assert query_db == ['history']
    assert len(history_store.running_records) == 1
    assert history_store.running_records[0][0] == 'demo_migration'
    assert history_store.running_records[0][1] == 'migrations/001_demo.py'
    assert history_store.running_records[0][2] == results[0].checksum
    assert history_store.running_records[0][3] == '1.0.0'
    assert len(history_store.records) == 1
    assert history_store.records[0][0] == 'demo_migration'
    assert history_store.records[0][1] == 'migrations/001_demo.py'
    assert history_store.records[0][2] == results[0].checksum
    assert history_store.records[0][3] == '1.0.0'
    assert results[0].status == 'success'
    assert isinstance(results[0].duration_ms, int)


@pytest.mark.asyncio
async def test_plugin_migration_runner_commits_managed_execution_transaction(tmp_path: Path) -> None:
    """校验托管执行事务模式会在记录 success 前提交 migration 执行 session。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("managed")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore()
    query_db = FakeManagedMigrationSession()

    results = await PluginMigrationRunner(
        discovered_plugin,
        history_store,
        manage_execution_transaction=True,
    ).run(query_db)

    assert query_db == ['managed']
    assert query_db.committed is True
    assert query_db.rolled_back is False
    assert len(history_store.records) == 1
    assert history_store.records[0][2] == results[0].checksum


@pytest.mark.asyncio
async def test_plugin_migration_runner_reports_recovery_when_success_history_write_fails(tmp_path: Path) -> None:
    """校验 migration 执行事务已提交但 success 历史写入失败时返回 running 恢复建议。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("managed")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore()
    query_db = FakeManagedMigrationSession()

    async def fail_record_success(*_args: object, **_kwargs: object) -> None:
        """模拟 success 历史写入失败。"""
        raise RuntimeError('history down')

    history_store.record_success = fail_record_success  # type: ignore[method-assign]

    with pytest.raises(PluginMigrationError, match='成功历史记录失败') as exc_info:
        await PluginMigrationRunner(
            discovered_plugin,
            history_store,
            manage_execution_transaction=True,
        ).run(query_db)

    assert query_db == ['managed']
    assert query_db.committed is True
    assert query_db.rolled_back is False
    assert exc_info.value.status == 'running'
    assert 'mark-success' in exc_info.value.recovery_suggestion
    assert len(history_store.running_records) == 1
    assert history_store.failure_records == []
    assert history_store.records == []


@pytest.mark.asyncio
async def test_plugin_migration_runner_skips_existing_history(tmp_path: Path) -> None:
    """校验已执行且校验值一致的 migration 会跳过。"""
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
    assert results[0].status == 'success'
    assert results[0].duration_ms == 0
    assert results[0].checksum == checksum
    assert history_store.running_records == []
    assert history_store.records == []


@pytest.mark.asyncio
async def test_plugin_migration_runner_records_failure_history(tmp_path: Path) -> None:
    """校验 migration 执行失败后会记录失败历史并继续抛出原错误。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'def run(query_db):\n    raise RuntimeError("boom")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore()

    with pytest.raises(PluginMigrationError, match='boom') as exc_info:
        await PluginMigrationRunner(discovered_plugin, history_store).run([])

    assert exc_info.value.status == 'failed'
    assert exc_info.value.to_recovery_payload()['migrationPath'] == 'migrations/001_demo.py'
    assert len(history_store.running_records) == 1
    assert len(history_store.failure_records) == 1
    failure_record = history_store.failure_records[0]
    assert failure_record[0] == 'demo_migration'
    assert failure_record[1] == 'migrations/001_demo.py'
    assert failure_record[3] == '1.0.0'
    assert failure_record[4] == 0
    assert failure_record[5] == 'boom'
    assert history_store.records == []


@pytest.mark.asyncio
async def test_plugin_migration_runner_rolls_back_managed_execution_transaction(tmp_path: Path) -> None:
    """校验托管执行事务模式会在 migration 失败时回滚执行 session。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'def run(query_db):\n    raise RuntimeError("boom")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore()
    query_db = FakeManagedMigrationSession()

    with pytest.raises(PluginMigrationError, match='boom'):
        await PluginMigrationRunner(
            discovered_plugin,
            history_store,
            manage_execution_transaction=True,
        ).run(query_db)

    assert query_db.committed is True
    assert query_db.rolled_back is True
    assert len(history_store.failure_records) == 1


@pytest.mark.asyncio
async def test_plugin_migration_runner_rejects_checksum_drift(tmp_path: Path) -> None:
    """校验已执行 migration 内容发生变化时会失败。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("changed")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    history_store = FakeMigrationHistoryStore({('demo_migration', 'migrations/001_demo.py'): 'old-checksum'})

    with pytest.raises(PluginMigrationError, match='内容校验值变化') as exc_info:
        await PluginMigrationRunner(discovered_plugin, history_store).run([])

    assert exc_info.value.status == 'success'
    assert '新增一个后续 migration' in exc_info.value.recovery_suggestion


@pytest.mark.asyncio
async def test_plugin_migration_runner_rejects_running_history(tmp_path: Path) -> None:
    """校验 running 状态的 migration 不会被自动重跑。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("should_not_run")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    migration_file = plugin_root / 'migrations' / '001_demo.py'
    checksum = PluginMigrationRunner._calculate_checksum(migration_file)
    history_store = FakeMigrationHistoryStore(
        records={
            ('demo_migration', 'migrations/001_demo.py'): PluginMigrationHistoryRecord(
                checksum=checksum,
                status='running',
            )
        }
    )
    query_db = []

    with pytest.raises(PluginMigrationError, match='running') as exc_info:
        await PluginMigrationRunner(discovered_plugin, history_store).run(query_db)

    assert exc_info.value.status == 'running'
    assert 'mark-success' in exc_info.value.recovery_suggestion
    assert query_db == []
    assert history_store.running_records == []
    assert history_store.records == []


@pytest.mark.asyncio
async def test_plugin_migration_runner_retries_failed_history(tmp_path: Path) -> None:
    """校验 failed 状态的 migration 允许修复后重试。"""
    plugin_root = tmp_path / 'plugins' / 'demo_migration'
    write_plugin_with_migration(plugin_root, 'async def run(query_db):\n    query_db.append("retry")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    migration_file = plugin_root / 'migrations' / '001_demo.py'
    checksum = PluginMigrationRunner._calculate_checksum(migration_file)
    history_store = FakeMigrationHistoryStore(
        records={
            ('demo_migration', 'migrations/001_demo.py'): PluginMigrationHistoryRecord(
                checksum='old-failed-checksum',
                status='failed',
                error_message='boom',
            )
        }
    )
    query_db = []

    results = await PluginMigrationRunner(discovered_plugin, history_store).run(query_db)

    assert query_db == ['retry']
    assert len(history_store.running_records) == 1
    assert history_store.running_records[0][2] == checksum
    assert len(history_store.records) == 1
    assert history_store.records[0][2] == results[0].checksum
    assert results[0].status == 'success'
