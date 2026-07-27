from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.core.discovery.scanner import PluginScanner
from plugins.core.lifecycle.seed import PluginSeedRunner


def write_plugin_with_seed(plugin_root: Path, seed_content: str, seed_name: str = 'demo_seed.py') -> None:
    """写入带 seed 的测试插件。"""
    (plugin_root / 'seeds').mkdir(parents=True)
    (plugin_root / 'seeds' / seed_name).write_text(seed_content, encoding='utf-8')
    (plugin_root / 'plugin.yaml').write_text(
        f"""
id: demo_seed
name: Demo Seed
version: 1.0.0
backend:
  module: plugins.demo_seed
  seeds:
    - seeds/{seed_name}
""",
        encoding='utf-8',
    )


@pytest.mark.asyncio
async def test_plugin_seed_runner_executes_async_seed(tmp_path: Path) -> None:
    """校验 seed 运行器可以执行异步 Python seed。"""
    plugin_root = tmp_path / 'plugins' / 'demo_seed'
    write_plugin_with_seed(plugin_root, 'async def run(query_db):\n    query_db.append("async_seed")\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    query_db = []

    results = await PluginSeedRunner(discovered_plugin).run(query_db)

    assert query_db == ['async_seed']
    assert results[0].seed_path == 'seeds/demo_seed.py'


@pytest.mark.asyncio
async def test_plugin_seed_runner_rejects_missing_run_function(tmp_path: Path) -> None:
    """校验 seed 缺少 run 函数时会失败。"""
    plugin_root = tmp_path / 'plugins' / 'demo_seed'
    write_plugin_with_seed(plugin_root, 'VALUE = 1\n')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')

    with pytest.raises(RuntimeError, match='run'):
        await PluginSeedRunner(discovered_plugin).run([])


@pytest.mark.asyncio
async def test_plugin_seed_runner_executes_sql_seed(tmp_path: Path) -> None:
    """校验 seed 运行器可以执行 SQL seed。"""
    plugin_root = tmp_path / 'plugins' / 'demo_seed'
    write_plugin_with_seed(
        plugin_root,
        """
-- 初始化演示数据
create table demo_seed_value (id integer primary key, name varchar(64));
insert into demo_seed_value (id, name) values (1, 'demo');
""",
        seed_name='demo_seed.sql',
    )
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with session_maker() as session:
            results = await PluginSeedRunner(discovered_plugin).run(session)
            rows = (await session.execute(text('select name from demo_seed_value where id = 1'))).all()

        assert results[0].seed_path == 'seeds/demo_seed.sql'
        expected_statement_count = 2
        assert results[0].statement_count == expected_statement_count
        assert rows == [('demo',)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_seed_runner_filters_seed_by_database_dialect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """校验 seed 运行器只执行当前数据库方言目录下的 seed。"""
    plugin_root = tmp_path / 'plugins' / 'demo_seed'
    (plugin_root / 'seeds' / 'mysql').mkdir(parents=True)
    (plugin_root / 'seeds' / 'postgresql').mkdir(parents=True)
    (plugin_root / 'seeds' / 'mysql' / 'demo_seed.sql').write_text(
        'create table demo_seed_value (id integer primary key, name varchar(64));\n'
        "insert into demo_seed_value (id, name) values (1, 'mysql');\n",
        encoding='utf-8',
    )
    (plugin_root / 'seeds' / 'postgresql' / 'demo_seed.sql').write_text(
        'create table demo_seed_value (id integer primary key, name varchar(64));\n'
        "insert into demo_seed_value (id, name) values (1, 'postgresql');\n",
        encoding='utf-8',
    )
    (plugin_root / 'plugin.yaml').write_text(
        """
id: demo_seed
name: Demo Seed
version: 1.0.0
backend:
  module: plugins.demo_seed
  seeds:
    - seeds/mysql/demo_seed.sql
    - seeds/postgresql/demo_seed.sql
""",
        encoding='utf-8',
    )
    monkeypatch.setattr('plugins.core.lifecycle.seed.DataBaseConfig.db_type', 'mysql')
    discovered_plugin = PluginScanner(tmp_path / 'plugins').load_manifest(plugin_root / 'plugin.yaml')
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with session_maker() as session:
            results = await PluginSeedRunner(discovered_plugin).run(session)
            rows = (await session.execute(text('select name from demo_seed_value where id = 1'))).all()

        assert [result.seed_path for result in results] == ['seeds/mysql/demo_seed.sql']
        assert rows == [('mysql',)]
    finally:
        await engine.dispose()
