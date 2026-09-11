import argparse
import json
import re
from collections import Counter
from typing import Any

from sqlalchemy import JSON, MetaData, Table, bindparam, func, inspect, select, text, update
from sqlalchemy.engine import Connection

from config.database import create_sync_db_engine
from module_admin.entity.do.job_runtime_do import SysJobExecution, SysJobSync
from scripts.verify_timezone_database import load_source
from utils.time_util import TimezoneUtil


def plan_store_dictionary(connection: Connection) -> dict[str, Any]:
    """
    检查旧任务分组字典，生成复用原记录的调度存储字典迁移计划

    :param connection: 数据库连接
    :return: 字典迁移计划
    """
    metadata = MetaData()
    types = Table('sys_dict_type', metadata, autoload_with=connection)
    data = Table('sys_dict_data', metadata, autoload_with=connection)
    rows = (
        connection.execute(select(types).where(types.c.dict_type.in_(['sys_job_group', 'sys_job_store'])))
        .mappings()
        .all()
    )
    if len(rows) > 1:
        raise ValueError('新旧调度存储字典同时存在，请先处理 sys_job_group 和 sys_job_store 冲突')
    current = bool(rows and rows[0]['dict_type'] == 'sys_job_store')
    if current:
        return {'current': True, 'dict_id': rows[0]['dict_id'], 'missing': []}
    existing = (
        connection.execute(select(data.c.dict_value).where(data.c.dict_type.in_(['sys_job_group', 'sys_job_store'])))
        .scalars()
        .all()
    )
    if len(existing) != len(set(existing)):
        raise ValueError('调度存储字典存在重复键值，请先处理冲突')
    entries = [(1, '内存', 'default'), (2, '数据库', 'sqlalchemy'), (3, 'Redis', 'redis')]
    return {
        'current': False,
        'dict_id': rows[0]['dict_id'] if rows else None,
        'missing': [entry for entry in entries if entry[2] not in existing],
    }


def migrate_store_dictionary(connection: Connection, plan: dict[str, Any]) -> dict[str, Any]:
    """
    将任务分组字典改为调度存储字典，保留已有编号、排序和自定义标签

    :param connection: 数据库连接
    :param plan: 只读检查生成的字典迁移计划
    :return: 字典迁移结果
    """
    if plan['current']:
        return {'current': True, 'added': 0}
    metadata = MetaData()
    types = Table('sys_dict_type', metadata, autoload_with=connection)
    data = Table('sys_dict_data', metadata, autoload_with=connection)
    now = TimezoneUtil.utc_now()
    values = {'dict_name': '调度存储', 'dict_type': 'sys_job_store', 'remark': '调度存储列表'}
    if plan['dict_id'] is None:
        connection.execute(types.insert().values(**values, status='0', create_by='admin', create_time=now))
    else:
        connection.execute(
            update(types).where(types.c.dict_id == plan['dict_id']).values(**values, update_by='admin', update_time=now)
        )
    connection.execute(update(data).where(data.c.dict_type == 'sys_job_group').values(dict_type='sys_job_store'))
    for value, old_label, new_label in [('default', '默认', '内存'), ('redis', 'redis', 'Redis')]:
        connection.execute(
            update(data)
            .where(data.c.dict_type == 'sys_job_store', data.c.dict_value == value, data.c.dict_label == old_label)
            .values(dict_label=new_label)
        )
    for sort, label, value in plan['missing']:
        connection.execute(
            data.insert().values(
                dict_type='sys_job_store',
                dict_sort=sort,
                dict_label=label,
                dict_value=value,
                css_class='',
                list_class='',
                is_default='Y' if value == 'default' else 'N',
                status='0',
                create_by='admin',
                create_time=now,
                remark=f'{label}调度存储',
            )
        )
    return {'current': False, 'added': len(plan['missing'])}


def parse_legacy_args(value: Any) -> list[Any]:
    """
    按旧调度器的规则迁移位置参数，保留原有值类型和逗号分隔语义

    :param value: 旧位置参数
    :return: JSON位置参数数组
    """
    if value is None or value == '':
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value.split(',')
    return parsed if isinstance(parsed, list) else [parsed]


def parse_legacy_kwargs(value: Any) -> dict[str, Any]:
    """
    将旧关键字参数转换为JSON对象

    :param value: 旧关键字参数
    :return: JSON关键字参数对象
    """
    parsed = {} if value is None or value == '' else (json.loads(value) if isinstance(value, str) else value)
    if not isinstance(parsed, dict):
        raise ValueError('关键字参数不是JSON对象')
    return parsed


def convert_configuration(row: dict[str, Any], *, snapshot: bool = False) -> dict[str, Any]:
    """
    转换旧任务字段，修正放弃执行的宽限时间并保留旧并发上限

    :param row: 旧任务记录或执行快照
    :param snapshot: 是否使用接口驼峰字段名
    :return: 新字段和值
    """

    def read(name: str, default: Any = None) -> Any:
        key = (
            ''.join(part.title() if index else part for index, part in enumerate(name.split('_'))) if snapshot else name
        )
        return row.get(f'legacy_{name}', row.get(key, default))

    policy = read('misfire_policy') or '3'
    concurrent = read('concurrent') or '1'
    store = read('job_group') or 'default'
    if policy not in {'1', '2', '3'} or concurrent not in {'0', '1'}:
        raise ValueError('旧执行策略或并发配置无效')
    if store not in {'default', 'sqlalchemy', 'redis'}:
        raise ValueError('旧分组无法对应已注册的调度存储')
    values = {
        'job_store': store,
        'misfire_grace_time': 1 if policy == '3' else None,
        'coalesce': policy == '2',
        'max_instances': 3 if concurrent == '0' else 1,
        'job_args': parse_legacy_args(read('job_args')),
        'job_kwargs': parse_legacy_kwargs(read('job_kwargs')),
        'status': read('status') or '1',
    }
    json.dumps(values, allow_nan=False)
    if snapshot:
        return {
            ''.join(part.title() if index else part for index, part in enumerate(key.split('_'))): value
            for key, value in values.items()
        }
    return values


def table_columns(connection: Connection, name: str) -> dict[str, dict]:
    """
    读取当前表结构，支持DDL部分完成后的再次运行

    :param connection: 数据库连接
    :param name: 表名
    :return: 列名到列定义的映射
    """
    return {column['name']: column for column in inspect(connection).get_columns(name)}


def is_current_schema(connection: Connection) -> bool:
    """
    检查新字段、主键及唯一规则，避免重复转换已升级的数据

    :param connection: 数据库连接
    :return: 是否已完成第二轮字段迁移
    """
    inspector = inspect(connection)
    columns = table_columns(connection, 'sys_job')
    unique = {item['name'] for item in inspector.get_unique_constraints('sys_job')}
    return (
        {'job_store', 'misfire_grace_time', 'coalesce', 'max_instances'} <= columns.keys()
        and isinstance(columns['job_args']['type'], JSON)
        and isinstance(columns['job_kwargs']['type'], JSON)
        and inspector.get_pk_constraint('sys_job')['constrained_columns'] == ['job_id']
        and 'uq_job_group_name' in unique
        and all(not columns[name]['nullable'] for name in ('job_name', 'job_group', 'job_args', 'job_kwargs', 'status'))
        and {'job_id', 'execution_id', 'job_store'} <= table_columns(connection, 'sys_job_log').keys()
        and inspector.has_table('sys_job_sync')
        and {'next_run_time', 'schedule_observed_time'} <= table_columns(connection, 'sys_job_sync').keys()
    )


def preflight(connection: Connection) -> dict[str, Any]:
    """
    只读检查主键、名称冲突及参数，所有定义通过后才允许修改表结构

    :param connection: 数据库连接
    :return: 迁移计划及转换后的任务数据
    """
    if is_current_schema(connection):
        return {'current': True, 'jobs': [], 'requests': [], 'policies': {}}
    metadata = MetaData()
    jobs = Table('sys_job', metadata, autoload_with=connection)
    for names, label in [(['job_id'], '任务ID重复'), (['job_group', 'job_name'], '同一分组内任务名称重复')]:
        columns = [jobs.c[name] for name in names]
        duplicate = connection.execute(select(*columns).group_by(*columns).having(func.count() > 1)).first()
        if duplicate:
            raise ValueError(f'{label}：{tuple(duplicate)}，请先处理冲突')
    converted = []
    policies = Counter()
    for row in connection.execute(select(jobs)).mappings():
        if not row['job_name'] or not row['job_name'].strip() or not row['job_group']:
            raise ValueError(f'任务 {row["job_id"]} 的名称或业务分组为空')
        try:
            values = convert_configuration(dict(row))
        except (TypeError, ValueError) as exc:
            raise ValueError(f'任务 {row["job_id"]} 无法迁移：{type(exc).__name__}，请检查参数和策略') from exc
        converted.append({'job_id': row['job_id'], **values})
        policies[row.get('legacy_misfire_policy', row.get('misfire_policy')) or '3'] += 1
    requests = []
    if not inspect(connection).has_table('sys_job_execution'):
        return {'current': False, 'jobs': converted, 'requests': requests, 'policies': dict(policies)}
    executions = Table('sys_job_execution', metadata, autoload_with=connection)
    active = connection.execute(select(executions.c.execution_id).where(executions.c.status == 'running')).first()
    if active:
        raise ValueError(f'执行 {active[0]} 仍在运行，请等待任务结束后迁移')
    for row in connection.execute(
        select(executions).where(executions.c.status.in_(['pending', 'submitted']))
    ).mappings():
        snapshot = row['job_snapshot']
        if 'maxInstances' in snapshot and 'jobStore' in snapshot and 'misfirePolicy' not in snapshot:
            continue
        try:
            converted_snapshot = {**snapshot, **convert_configuration(snapshot, snapshot=True)}
            converted_snapshot.pop('misfirePolicy', None)
            converted_snapshot.pop('concurrent', None)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'待执行请求 {row["execution_id"]} 的参数或策略无法迁移') from exc
        requests.append({'execution_id': row['execution_id'], 'old_snapshot': snapshot, 'snapshot': converted_snapshot})
    return {'current': False, 'jobs': converted, 'requests': requests, 'policies': dict(policies)}


def add_column(connection: Connection, table: str, name: str, definition: str) -> None:
    """
    仅添加尚不存在的迁移字段

    :param connection: 数据库连接
    :param table: 表名
    :param name: 字段名
    :param definition: 固定的DDL字段定义
    :return: None
    """
    if name not in table_columns(connection, table):
        connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def archive_column(connection: Connection, table: str, name: str) -> None:
    """
    保留旧字段原文，供升级审计和备份恢复时核对

    :param connection: 数据库连接
    :param table: 表名
    :param name: 旧字段名
    :return: None
    """
    columns = table_columns(connection, table)
    if f'legacy_{name}' not in columns and name in columns:
        connection.exec_driver_sql(f'ALTER TABLE {table} RENAME COLUMN {name} TO legacy_{name}')


def migrate_logs(connection: Connection) -> int:
    """
    分批转换日志参数，只从明确的日志编号信息补全关联，不按名称猜测

    :param connection: 数据库连接
    :return: 转换的日志数量
    """
    logs = Table('sys_job_log', MetaData(), autoload_with=connection)
    count = 0
    last_id = -1
    while True:
        rows = (
            connection.execute(select(logs).where(logs.c.job_log_id > last_id).order_by(logs.c.job_log_id).limit(500))
            .mappings()
            .all()
        )
        if not rows:
            return count
        for row in rows:
            values = {'job_store': row['job_group']}
            for name, parser in [('job_args', parse_legacy_args), ('job_kwargs', parse_legacy_kwargs)]:
                try:
                    values[name] = parser(row[f'legacy_{name}'])
                    json.dumps(values[name], allow_nan=False)
                except (TypeError, ValueError):  # noqa: PERF203
                    # 旧字段原文仍保存在legacy列，不为无效历史参数构造可执行值。
                    values[name] = None
            matched = re.search(r'任务ID: (\d+), 执行ID: ([0-9a-f]{32})(?:,|$)', row['job_message'] or '')
            if matched:
                values.update(job_id=int(matched[1]), execution_id=matched[2])
            connection.execute(update(logs).where(logs.c.job_log_id == row['job_log_id']).values(**values))
        count += len(rows)
        last_id = rows[-1]['job_log_id']


def apply_migration(connection: Connection, plan: dict[str, Any]) -> dict[str, Any]:
    """
    应用已通过检查的迁移计划，PostgreSQL使用事务，MySQL可从保留的旧字段重试

    :param connection: 所有应用worker停止后的独占数据库连接
    :param plan: 只读预检产生的迁移计划
    :return: 迁移数量报告
    """
    if plan['current']:
        return {'current': True, 'jobs': 0, 'requests': 0, 'logs': 0}
    mysql = connection.dialect.name == 'mysql'
    if connection.dialect.name not in {'mysql', 'postgresql'}:
        raise ValueError('字段迁移仅支持MySQL和PostgreSQL')
    SysJobSync.__table__.create(connection, checkfirst=True)
    SysJobExecution.__table__.create(connection, checkfirst=True)
    for table in ('sys_job', 'sys_job_log'):
        for name in ('job_args', 'job_kwargs'):
            archive_column(connection, table, name)
            add_column(connection, table, name, 'JSON')
    for name in ('misfire_policy', 'concurrent'):
        archive_column(connection, 'sys_job', name)
    for name, definition in {
        'job_store': "VARCHAR(64) NOT NULL DEFAULT 'default'",
        'misfire_grace_time': 'INTEGER DEFAULT 1',
        'coalesce': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'max_instances': 'INTEGER NOT NULL DEFAULT 1',
    }.items():
        add_column(connection, 'sys_job', name, definition)
    for name, definition in {'job_id': 'BIGINT', 'execution_id': 'VARCHAR(32)', 'job_store': 'VARCHAR(64)'}.items():
        add_column(connection, 'sys_job_log', name, definition)
    for name in ('next_run_time', 'schedule_observed_time'):
        add_column(connection, 'sys_job_sync', name, 'DATETIME(3)' if mysql else 'TIMESTAMP(3) WITH TIME ZONE')
    add_column(connection, 'sys_job_execution', 'legacy_job_snapshot', 'JSON')
    jobs = Table('sys_job', MetaData(), autoload_with=connection)
    for row in plan['jobs']:
        connection.execute(
            update(jobs)
            .where(jobs.c.job_id == row['job_id'])
            .values(**{key: value for key, value in row.items() if key != 'job_id'})
        )
    request_update = text(
        'UPDATE sys_job_execution SET job_snapshot=:snapshot, legacy_job_snapshot=:old_snapshot WHERE execution_id=:execution_id'
    ).bindparams(bindparam('snapshot', type_=JSON), bindparam('old_snapshot', type_=JSON))
    for request in plan['requests']:
        connection.execute(request_update, request)
    log_count = migrate_logs(connection)
    connection.exec_driver_sql(
        "UPDATE sys_job_sync SET sync_status='pending', sync_error=NULL, next_run_time=NULL, schedule_observed_time=NULL"
    )
    finalize_schema(connection)
    return {'current': False, 'jobs': len(plan['jobs']), 'requests': len(plan['requests']), 'logs': log_count}


def finalize_schema(connection: Connection) -> None:
    """
    数据转换完成后建立主键、索引和约束

    :param connection: 数据库连接
    :return: None
    """
    mysql = connection.dialect.name == 'mysql'
    inspector = inspect(connection)
    indexes = {index['name'] for index in inspector.get_indexes('sys_job_log')}
    for name, columns in [('ix_job_log_job_id', 'job_id, create_time'), ('ix_job_log_execution_id', 'execution_id')]:
        if name not in indexes:
            connection.exec_driver_sql(f'CREATE INDEX {name} ON sys_job_log ({columns})')
    primary = inspector.get_pk_constraint('sys_job')
    if primary['constrained_columns'] != ['job_id']:
        if mysql:
            connection.exec_driver_sql('ALTER TABLE sys_job DROP PRIMARY KEY, ADD PRIMARY KEY (job_id)')
        else:
            name = connection.dialect.identifier_preparer.quote(primary['name'])
            connection.exec_driver_sql(f'ALTER TABLE sys_job DROP CONSTRAINT {name}, ADD PRIMARY KEY (job_id)')
    types = {
        'job_name': 'VARCHAR(64)',
        'job_group': 'VARCHAR(64)',
        'job_args': 'JSON',
        'job_kwargs': 'JSON',
        'status': 'CHAR(1)',
    }
    for name, definition in types.items():
        if mysql:
            default = {'job_group': " DEFAULT 'default'", 'status': " DEFAULT '1'"}.get(name, '')
            connection.exec_driver_sql(f'ALTER TABLE sys_job MODIFY COLUMN {name} {definition} NOT NULL{default}')
        else:
            connection.exec_driver_sql(f'ALTER TABLE sys_job ALTER COLUMN {name} SET NOT NULL')
    connection.exec_driver_sql("ALTER TABLE sys_job ALTER COLUMN status SET DEFAULT '1'")
    unique = {constraint['name'] for constraint in inspect(connection).get_unique_constraints('sys_job')}
    if 'uq_job_group_name' not in unique:
        connection.exec_driver_sql('ALTER TABLE sys_job ADD CONSTRAINT uq_job_group_name UNIQUE (job_group, job_name)')
    checks = {constraint['name'] for constraint in inspect(connection).get_check_constraints('sys_job')}
    for name, condition in [
        ('ck_job_max_instances', 'max_instances >= 1'),
        ('ck_job_misfire_grace', 'misfire_grace_time IS NULL OR misfire_grace_time >= 1'),
    ]:
        if name not in checks:
            connection.exec_driver_sql(f'ALTER TABLE sys_job ADD CONSTRAINT {name} CHECK ({condition})')


def main() -> None:
    """
    默认只读预检，显式选择应用迁移时才修改指定数据源

    :return: None
    """
    parser = argparse.ArgumentParser(description='迁移第二轮任务字段，默认只读检查')
    parser.add_argument('--env-file', default='.env.dev', help='数据源配置文件')
    parser.add_argument('--source', help='指定数据源别名')
    parser.add_argument('--config', help='独立DataSourceSettings JSON配置文件')
    parser.add_argument('--apply', action='store_true', help='应用迁移')
    parser.add_argument('--workers-stopped', action='store_true', help='确认所有应用worker及任务执行进程均已停止')
    args = parser.parse_args()
    if args.apply and not args.workers_stopped:
        parser.error('--apply 需要同时指定 --workers-stopped')
    # 复用现有数据库工具的数据源读取方式，不在报告中输出连接口令。
    engine = create_sync_db_engine(config=load_source(args), echo=False)
    try:
        with engine.begin() as connection:
            dictionary_plan = plan_store_dictionary(connection)
            plan = preflight(connection)
            result = (
                apply_migration(connection, plan)
                if args.apply
                else {
                    'current': plan['current'],
                    'jobs': len(plan['jobs']),
                    'requests': len(plan['requests']),
                    'policies': plan['policies'],
                }
            )
            result['dictionary'] = (
                migrate_store_dictionary(connection, dictionary_plan)
                if args.apply
                else {
                    'current': dictionary_plan['current'],
                    'missing': [item[2] for item in dictionary_plan['missing']],
                }
            )
            print(json.dumps({'mode': 'apply' if args.apply else 'check', **result}, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
