import json
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from scripts.migrate_job_fields import (
    convert_configuration,
    migrate_store_dictionary,
    parse_legacy_args,
    plan_store_dictionary,
    preflight,
)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (None, []),
        ('', []),
        ('tenant,a', ['tenant', 'a']),
        ('["tenant,a", 2, true]', ['tenant,a', 2, True]),
        ('123', [123]),
        ('null', [None]),
        ('{"a": 1}', [{'a': 1}]),
    ],
)
def test_legacy_args_keep_the_old_execution_meaning(value: str | None, expected: list) -> None:
    assert parse_legacy_args(value) == expected


@pytest.mark.parametrize(('policy', 'grace', 'coalesce'), [('1', None, False), ('2', None, True), ('3', 1, False)])
@pytest.mark.parametrize(('concurrent', 'limit'), [('0', 3), ('1', 1)])
def test_policy_migration_fixes_discard_and_preserves_other_choices(
    policy: str,
    grace: int | None,
    coalesce: bool,
    concurrent: str,
    limit: int,
) -> None:
    values = convert_configuration({'misfire_policy': policy, 'concurrent': concurrent, 'job_group': 'redis'})
    assert values['misfire_grace_time'] == grace
    assert values['coalesce'] is coalesce
    assert values['max_instances'] == limit
    assert values['job_store'] == 'redis'


@pytest.mark.parametrize('kwargs', ['[1]', '{broken', 'null', 'true', '{"value": NaN}'])
def test_invalid_definition_parameters_require_repair_before_migration(kwargs: str) -> None:
    with pytest.raises(ValueError):
        convert_configuration({'job_kwargs': kwargs})


def test_preflight_rejects_duplicate_identity_or_names_without_mutating() -> None:
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql(
            'CREATE TABLE sys_job (job_id bigint, job_name varchar(64), job_group varchar(64), misfire_policy varchar(20), concurrent char(1), job_args varchar(255), job_kwargs varchar(255))'
        )
        connection.exec_driver_sql(
            'CREATE TABLE sys_job_execution (execution_id varchar(32), status varchar(16), job_snapshot json)'
        )
        connection.exec_driver_sql("INSERT INTO sys_job VALUES (1, 'first', 'default', '3', '1', 'hello', '{}')")
        connection.exec_driver_sql("INSERT INTO sys_job VALUES (1, 'second', 'default', '3', '1', '', '{}')")
        with pytest.raises(ValueError, match='任务ID重复'):
            preflight(connection)
        connection.exec_driver_sql("UPDATE sys_job SET job_id=2, job_name='first' WHERE job_name='second'")
        with pytest.raises(ValueError, match='名称重复'):
            preflight(connection)
        connection.exec_driver_sql("UPDATE sys_job SET job_name='second' WHERE job_id=2")
        plan = preflight(connection)
        assert plan['jobs'][0]['job_args'] == ['hello']
        assert connection.execute(text('SELECT job_args FROM sys_job WHERE job_id=1')).scalar_one() == 'hello'
    engine.dispose()


def test_pending_snapshot_is_converted_without_changing_original_data() -> None:
    original = {
        'jobId': 42,
        'jobGroup': 'sqlalchemy',
        'jobArgs': '[1, true]',
        'jobKwargs': '{"limit": 20}',
        'misfirePolicy': '2',
        'concurrent': '0',
    }
    saved = json.dumps(original)
    result = convert_configuration(original, snapshot=True)
    assert result['jobArgs'] == [1, True]
    assert result['jobKwargs'] == {'limit': 20}
    assert result['jobStore'] == 'sqlalchemy'
    assert result['misfireGraceTime'] is None
    assert result['coalesce'] is True
    assert json.dumps(original) == saved


@pytest.fixture
def dictionary_db() -> Generator[Connection, None, None]:
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql(
            'CREATE TABLE sys_dict_type (dict_id integer primary key, dict_name varchar(100), '
            'dict_type varchar(100) unique, status char(1), create_by varchar(64), create_time datetime, '
            'update_by varchar(64), update_time datetime, remark varchar(500))'
        )
        connection.exec_driver_sql(
            'CREATE TABLE sys_dict_data (dict_code integer primary key, dict_sort integer, '
            'dict_label varchar(100), dict_value varchar(100), dict_type varchar(100), css_class varchar(100), '
            'list_class varchar(100), is_default char(1), status char(1), create_by varchar(64), '
            'create_time datetime, remark varchar(500))'
        )
        yield connection
    engine.dispose()


def test_store_dictionary_reuses_ids_and_keeps_custom_labels_and_status(dictionary_db: Connection) -> None:
    dictionary_db.exec_driver_sql(
        "INSERT INTO sys_dict_type (dict_id, dict_name, dict_type) VALUES (5, '任务分组', 'sys_job_group')"
    )
    dictionary_db.exec_driver_sql(
        'INSERT INTO sys_dict_data (dict_code, dict_sort, dict_label, dict_value, dict_type, status) VALUES '
        "(10, 1, '默认', 'default', 'sys_job_group', '0'), "
        "(11, 4, '业务数据库', 'sqlalchemy', 'sys_job_group', '0'), "
        "(12, 2, 'redis', 'redis', 'sys_job_group', '1')"
    )
    plan = plan_store_dictionary(dictionary_db)
    assert plan == {'current': False, 'dict_id': 5, 'missing': []}
    assert dictionary_db.execute(text('SELECT dict_type FROM sys_dict_type')).scalar_one() == 'sys_job_group'
    assert migrate_store_dictionary(dictionary_db, plan) == {'current': False, 'added': 0}
    assert dictionary_db.execute(text('SELECT dict_id, dict_name, dict_type FROM sys_dict_type')).one() == (
        5,
        '调度存储',
        'sys_job_store',
    )
    rows = dictionary_db.execute(
        text(
            'SELECT dict_code, dict_sort, dict_label, dict_value, dict_type, status FROM sys_dict_data ORDER BY dict_code'
        )
    ).all()
    assert rows == [
        (10, 1, '内存', 'default', 'sys_job_store', '0'),
        (11, 4, '业务数据库', 'sqlalchemy', 'sys_job_store', '0'),
        (12, 2, 'Redis', 'redis', 'sys_job_store', '1'),
    ]


def test_store_dictionary_fills_old_missing_options_and_does_not_reset_later_edits(dictionary_db: Connection) -> None:
    dictionary_db.exec_driver_sql(
        "INSERT INTO sys_dict_type (dict_id, dict_name, dict_type) VALUES (5, '任务分组', 'sys_job_group')"
    )
    dictionary_db.exec_driver_sql(
        'INSERT INTO sys_dict_data (dict_code, dict_label, dict_value, dict_type) '
        "VALUES (10, '默认', 'default', 'sys_job_group')"
    )
    assert migrate_store_dictionary(dictionary_db, plan_store_dictionary(dictionary_db)) == {
        'current': False,
        'added': 2,
    }
    assert set(dictionary_db.execute(text('SELECT dict_value FROM sys_dict_data')).scalars()) == {
        'default',
        'sqlalchemy',
        'redis',
    }
    dictionary_db.exec_driver_sql("UPDATE sys_dict_data SET dict_label='自定义内存' WHERE dict_value='default'")
    dictionary_db.exec_driver_sql("DELETE FROM sys_dict_data WHERE dict_value='redis'")
    assert migrate_store_dictionary(dictionary_db, plan_store_dictionary(dictionary_db)) == {
        'current': True,
        'added': 0,
    }
    assert set(dictionary_db.execute(text('SELECT dict_value FROM sys_dict_data')).scalars()) == {
        'default',
        'sqlalchemy',
    }
    assert (
        dictionary_db.execute(text('SELECT dict_label FROM sys_dict_data WHERE dict_code=10')).scalar_one()
        == '自定义内存'
    )


def test_store_dictionary_conflict_stops_before_mutation(dictionary_db: Connection) -> None:
    dictionary_db.exec_driver_sql(
        'INSERT INTO sys_dict_type (dict_id, dict_name, dict_type) VALUES '
        "(5, '任务分组', 'sys_job_group'), (8, '已有字典', 'sys_job_store')"
    )
    with pytest.raises(ValueError, match='同时存在'):
        plan_store_dictionary(dictionary_db)
    assert dictionary_db.execute(text('SELECT dict_name FROM sys_dict_type WHERE dict_id=5')).scalar_one() == '任务分组'


def test_store_dictionary_can_initialize_when_type_is_missing(dictionary_db: Connection) -> None:
    assert migrate_store_dictionary(dictionary_db, plan_store_dictionary(dictionary_db)) == {
        'current': False,
        'added': 3,
    }
    assert dictionary_db.execute(text('SELECT dict_type FROM sys_dict_type')).scalar_one() == 'sys_job_store'
    assert set(dictionary_db.execute(text('SELECT dict_value FROM sys_dict_data')).scalars()) == {
        'default',
        'sqlalchemy',
        'redis',
    }
