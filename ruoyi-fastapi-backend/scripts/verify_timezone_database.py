import argparse
import asyncio
import importlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import Column, Integer, MetaData, Table, inspect, select, text

from common.types import DbUtcDateTime
from config.database import Base, create_async_db_engine, create_sync_db_engine
from config.env import DataSourceSettings
from utils.time_util import TimezoneUtil

BACKEND = Path(__file__).resolve().parents[1]
MILLISECOND_PRECISION = 3
MAIN_INSTANT_COLUMNS = 73
PLUGIN_INSTANT_COLUMNS = 4
TIMEZONE_LENGTH = 64
ASYNC_PROBE_ID = 99


def load_source(args: argparse.Namespace) -> DataSourceSettings:
    """
    从本地配置读取待验证数据源

    :param args: 命令行参数
    :return: 数据源连接配置
    """
    if args.config:
        return DataSourceSettings.model_validate_json(Path(args.config).read_text(encoding='utf-8'))
    values = dotenv_values(args.env_file)
    sources = json.loads(values['DB_SOURCES'])
    return DataSourceSettings.model_validate(sources[args.source or values['DB_DEFAULT_SOURCE']])


def initialize(source: DataSourceSettings, report: dict) -> DataSourceSettings:  # noqa: PLR0915
    """
    创建隔离测试库并验证UTC种子数据

    :param source: 具备建库权限的源连接配置
    :param report: 原地补充数据库版本和初始化结果的报告字典
    :return: 新建隔离测试库的连接配置
    """
    name = f'ruoyi_timezone_verify_{uuid4().hex[:12]}'
    admin = create_sync_db_engine(config=source, echo=False)
    try:
        with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            report['version'] = connection.execute(text('SELECT version()')).scalar_one()
            connection.exec_driver_sql(f'CREATE DATABASE {name}')
    finally:
        admin.dispose()
    target = source.model_copy(update={'db_database': name, 'db_echo': False})
    report['database'] = name
    sql_name = 'ruoyi-fastapi.sql' if target.db_type == 'mysql' else 'ruoyi-fastapi-pg.sql'
    scripts = [BACKEND / 'sql' / sql_name, BACKEND / 'plugins/ai/migrations' / target.db_type / '001_init.sql']
    contents = [path.read_text(encoding='utf-8') for path in scripts]
    assert all(not re.search(r'(?im)^\s*(USE\s|(?:DROP|CREATE)\s+DATABASE\b)', content) for content in contents)
    connection_args = {
        'host': target.db_host,
        'port': target.db_port,
        'user': target.db_username,
        'password': target.db_password.get_secret_value(),
        'database': name,
    }
    before = TimezoneUtil.utc_now() - timedelta(seconds=1)
    if target.db_type == 'mysql':
        import pymysql  # noqa: PLC0415 - load only the selected driver
        from pymysql.constants import CLIENT  # noqa: PLC0415

        connection = pymysql.connect(
            **connection_args, charset='utf8mb4', autocommit=True, client_flag=CLIENT.MULTI_STATEMENTS
        )
    else:
        import psycopg2  # noqa: PLC0415 - load only the selected driver

        connection = psycopg2.connect(**connection_args)
        connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            if target.db_type == 'mysql':
                cursor.execute('SELECT @@global.time_zone, @@system_time_zone')
                report['server_default_timezone'] = cursor.fetchone()
                cursor.execute("SET time_zone = '+08:00'")
                cursor.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema=DATABASE()')
            else:
                cursor.execute('SHOW timezone')
                report['server_default_timezone'] = cursor.fetchone()[0]
                cursor.execute("SET TIME ZONE 'America/New_York'")
                cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
            assert cursor.fetchone()[0] == 0, 'Refusing to initialize a nonempty database'
            for content in contents:
                cursor.execute(content)
                if target.db_type == 'mysql':
                    while cursor.nextset():
                        pass
    finally:
        connection.close()
    engine = create_sync_db_engine(config=target, echo=False)
    try:
        with engine.connect() as connection:
            value = connection.execute(text('SELECT create_time FROM sys_dept WHERE dept_id=100')).scalar_one()
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            assert before <= value <= TimezoneUtil.utc_now() + timedelta(seconds=1), 'Seed time is not UTC'
            report['seed_time_utc'] = value.isoformat()
            preferences = connection.execute(text('SELECT time_zone FROM sys_user')).scalars().all()
            assert preferences and all(preference == 'auto' for preference in preferences)
            report['user_timezone_default'] = 'auto'
    finally:
        engine.dispose()
    return target


def inspect_schema(source: DataSourceSettings, report: dict) -> None:
    """
    逐列核对实际数据库和ORM的时间类型约定

    :param source: 隔离测试库的数据源配置
    :param report: 原地补充验证结果的报告字典
    """
    for folder in [
        'module_admin/entity/do',
        'module_generator/entity/do',
        'plugins/core/management/entity/do',
        'plugins/ai/entity/do',
    ]:
        for path in (BACKEND / folder).glob('*.py'):
            importlib.import_module(path.relative_to(BACKEND).with_suffix('').as_posix().replace('/', '.'))
    engine = create_sync_db_engine(config=source, echo=False)
    try:
        catalog = inspect(engine)
        columns = []
        for table in Base.metadata.tables.values():
            instants = [column for column in table.columns if isinstance(column.type, DbUtcDateTime)]
            if not instants:
                continue
            actual = {column['name']: column for column in catalog.get_columns(table.name)}
            for column in instants:
                found = actual[column.name]
                assert found['nullable'] == column.nullable, f'{table.name}.{column.name}: nullable mismatch'
                if source.db_type == 'mysql':
                    assert type(found['type']).__name__ == 'DATETIME' and found['type'].fsp == MILLISECOND_PRECISION
                else:
                    assert found['type'].timezone is True and found['type'].precision == MILLISECOND_PRECISION
                default = found['default']
                assert default is None or re.fullmatch(r'NULL(?:::[\w ()]+)?', default), (
                    f'{table.name}.{column.name}: unexpected server default'
                )
                columns.append(
                    {
                        'table': table.name,
                        'column': column.name,
                        'type': str(found['type']),
                        'precision': 3,
                        'nullable': column.nullable,
                        'orm_default': 'callable' if column.default and column.default.is_callable else None,
                        'server_default': found['default'],
                    }
                )
        main = [column for column in columns if not column['table'].startswith('ai_')]
        plugin = [column for column in columns if column['table'].startswith('ai_')]
        assert len(main) == MAIN_INSTANT_COLUMNS and len(plugin) == PLUGIN_INSTANT_COLUMNS, (len(main), len(plugin))
        logs = {column['name']: column for column in catalog.get_columns('sys_job_log')}
        assert type(logs['run_duration_ms']['type']).__name__ == 'BIGINT'
        assert logs['run_duration_ms']['nullable'] and logs['time_zone']['nullable']
        assert logs['time_zone']['type'].length == TIMEZONE_LENGTH
        report['schema_columns'] = columns
        report['main_instant_columns'], report['plugin_instant_columns'] = len(main), len(plugin)
    finally:
        engine.dispose()


async def verify_drivers(source: DataSourceSettings, report: dict) -> None:
    """
    验证同步和异步驱动的UTC会话、精度及重连行为

    :param source: 隔离测试库的数据源配置
    :param report: 原地补充验证结果的报告字典
    """
    engine = create_sync_db_engine(config=source, echo=False)
    async_engine = create_async_db_engine(config=source, echo=False)
    metadata = MetaData()
    probe = Table(
        'timezone_verify_probe', metadata, Column('id', Integer, primary_key=True), Column('instant', DbUtcDateTime())
    )
    metadata.create_all(engine)
    values = [
        datetime(2026, 1, 1, 0, 0, 0, micros, tzinfo=timezone(timedelta(minutes=offset)))
        for offset in [0, 480, -300, 345]
        for micros in [1, 123456, 999999]
    ]
    timezone_query = 'SELECT @@session.time_zone' if source.db_type == 'mysql' else 'SHOW TIME ZONE'
    try:
        with engine.begin() as connection:
            assert connection.execute(text(timezone_query)).scalar_one() in {'UTC', '+00:00'}
            connection.execute(probe.insert(), [{'id': i + 1, 'instant': value} for i, value in enumerate(values)])
        async with async_engine.begin() as connection:
            assert (await connection.execute(text(timezone_query))).scalar_one() in {'UTC', '+00:00'}
            actual = (await connection.execute(select(probe.c.instant).order_by(probe.c.id))).scalars().all()
            assert actual == [TimezoneUtil.to_utc_milliseconds(value) for value in values]
            assert all(value.tzinfo == timezone.utc for value in actual)
            await connection.execute(probe.insert().values(id=ASYNC_PROBE_ID, instant=values[-1]))
        await async_engine.dispose()
        async with async_engine.connect() as connection:
            assert (await connection.execute(text(timezone_query))).scalar_one() in {'UTC', '+00:00'}
        with engine.connect() as connection:
            value = connection.execute(select(probe.c.instant).where(probe.c.id == ASYNC_PROBE_ID)).scalar_one()
            assert value == TimezoneUtil.to_utc_milliseconds(values[-1])
            connection.commit()
            connection.invalidate()
        with engine.connect() as connection:
            assert connection.execute(text(timezone_query)).scalar_one() in {'UTC', '+00:00'}
        report['driver_roundtrips'] = len(values) + 1
        report['sync_async_pool_reconnect'] = 'passed'
    finally:
        engine.dispose()
        await async_engine.dispose()


async def verify_generator(source: DataSourceSettings, report: dict) -> None:
    """
    使用真实数据库验证普通表、树表和主子表生成代码

    :param source: 隔离测试库的数据源配置
    :param report: 原地补充验证结果的报告字典
    """
    from pytest import MonkeyPatch  # noqa: PLC0415

    from tests.module_generator import test_generated_time_contract as generated  # noqa: PLC0415

    output = BACKEND / '.cache/timezone-database' / source.db_database
    output.mkdir(parents=True, exist_ok=True)
    engine = create_sync_db_engine(config=source, echo=False)
    try:
        for category in ['crud', 'tree', 'sub']:
            assert source.db_database.startswith('ruoyi_timezone_verify_')
            with engine.begin() as connection:
                connection.exec_driver_sql('DROP TABLE IF EXISTS generated_time_detail')
                connection.exec_driver_sql('DROP TABLE IF EXISTS generated_time_item')
            with MonkeyPatch.context() as monkeypatch:
                monkeypatch.setattr(
                    generated, 'create_async_engine', lambda _url: create_async_db_engine(config=source, echo=False)
                )
                await generated.test_generated_import_crud_and_query(source.db_type, category, output, monkeypatch)
        report['generated_import_crud_query'] = ['crud', 'tree', 'sub']
    finally:
        engine.dispose()


async def verify_metadata_and_scheduler(source: DataSourceSettings, report: dict) -> None:
    """
    验证数据库元数据时间及持久化调度行为

    :param source: 隔离测试库的数据源配置
    :param report: 原地补充验证结果的报告字典
    """
    from pytest import MonkeyPatch  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: PLC0415

    from module_generator.dao.gen_dao import GenTableDao  # noqa: PLC0415
    from module_generator.entity.vo.gen_vo import GenTablePageQueryModel  # noqa: PLC0415
    from tests.config.test_scheduler_job_persistence import verify_persistent_scheduler  # noqa: PLC0415

    async_engine = create_async_db_engine(config=source, echo=False)
    engine = create_sync_db_engine(config=source, echo=False)
    try:
        async with async_sessionmaker(async_engine)() as session:
            rows = await GenTableDao.get_gen_db_table_list(session, GenTablePageQueryModel(), source_config=source)
            assert rows
            for row in rows:
                for key in ['createTime', 'updateTime']:
                    value = row.get(key)
                    if source.db_type == 'postgresql':
                        assert value is None
                    elif value:
                        assert TimezoneUtil.parse_rfc3339(value) <= TimezoneUtil.utc_now() + timedelta(seconds=1)
            if source.db_type == 'mysql':
                filtered = await GenTableDao.get_gen_db_table_list(
                    session, GenTablePageQueryModel(beginTime='2000-01-01'), source_config=source
                )
                assert filtered
        report['metadata_time_contract'] = 'passed'
        with MonkeyPatch.context() as monkeypatch:
            await verify_persistent_scheduler(
                engine, monkeypatch, async_sessionmaker(async_engine, expire_on_commit=False)
            )
        report['persistent_restart_manual_cron'] = 'passed'
    finally:
        await async_engine.dispose()
        engine.dispose()


def main() -> None:
    """
    运行真实数据库的时区契约验收并输出报告
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', default='.env.dev')
    parser.add_argument('--source')
    parser.add_argument('--config', help='Standalone DataSourceSettings JSON file (local/ignored)')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    report = {'python': sys.version, 'started_at': TimezoneUtil.utc_now().isoformat()}
    source = load_source(args)
    report['dialect'] = source.db_type
    target = initialize(source, report)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    inspect_schema(target, report)
    asyncio.run(verify_drivers(target, report))
    asyncio.run(verify_generator(target, report))
    asyncio.run(verify_metadata_and_scheduler(target, report))
    report['status'] = 'passed'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        f'{source.db_type} {report["version"]}: passed; database={target.db_database}; '
        f'{MAIN_INSTANT_COLUMNS}+4 time columns, 13 roundtrips, 3 generated CRUD cases'
    )


if __name__ == '__main__':
    main()
