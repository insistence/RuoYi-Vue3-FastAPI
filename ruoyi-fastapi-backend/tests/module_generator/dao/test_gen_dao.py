from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from module_generator.dao.gen_dao import GenTableColumnDao, GenTableDao
from module_generator.entity.vo.gen_vo import GenTablePageQueryModel
from utils.page_util import PageUtil

TABLE_ID = 7
COLUMN_ID = 9
CLIENT_AUDIT_TIME = datetime(2000, 1, 1)


@pytest.mark.asyncio
async def test_get_gen_table_by_name_is_scoped_to_data_source() -> None:
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    await GenTableDao.get_gen_table_by_name(db, 'orders', 'reporting')

    statement = db.execute.await_args.args[0]
    params = statement.compile().params
    assert 'orders' in params.values()
    assert 'reporting' in params.values()


@pytest.mark.asyncio
async def test_get_gen_table_list_filters_source_when_requested() -> None:
    query_object = GenTablePageQueryModel(dataSourceName='reporting')

    with patch.object(PageUtil, 'paginate', new=AsyncMock(return_value=[])) as paginate:
        await GenTableDao.get_gen_table_list(object(), query_object, is_page=True)

    query = paginate.await_args.args[1]
    assert 'reporting' in query.compile().params.values()


@pytest.mark.asyncio
async def test_get_gen_db_table_list_does_not_bind_unreferenced_model_defaults() -> None:
    query_object = GenTablePageQueryModel(formColNum=3)

    with patch.object(PageUtil, 'paginate', new=AsyncMock(return_value=[])) as paginate:
        result = await GenTableDao.get_gen_db_table_list(object(), query_object, is_page=True)

    query = paginate.await_args.args[1]
    assert query.compile().params == {}
    assert result == []


@pytest.mark.asyncio
async def test_get_gen_db_table_list_only_binds_active_sql_filters() -> None:
    query_object = GenTablePageQueryModel(
        tableName='sys_user',
        tableComment='用户',
        beginTime='2026-07-01',
        endTime='2026-07-30',
        formColNum=2,
    )

    with patch.object(PageUtil, 'paginate', new=AsyncMock(return_value=[])) as paginate:
        await GenTableDao.get_gen_db_table_list(object(), query_object)

    query = paginate.await_args.args[1]
    compiled_sql = str(query.compile())
    assert query.compile().params == {
        'table_name': 'sys_user',
        'table_comment': '用户',
        'begin_time': '2026-07-01',
        'end_time': '2026-07-30',
    }
    assert ')and ' not in compiled_sql


@pytest.mark.asyncio
async def test_get_gen_db_table_list_uses_target_source_config() -> None:
    query_object = GenTablePageQueryModel()

    with patch.object(PageUtil, 'paginate', new=AsyncMock(return_value=[])) as paginate:
        await GenTableDao.get_gen_db_table_list(
            object(),
            query_object,
            excluded_table_names={'sys_user'},
            source_config=SimpleNamespace(db_type='postgresql'),
        )

    query = paginate.await_args.args[1]
    assert 'list_table' in str(query.compile())
    assert query.compile().params['excluded_table_names'] == ('sys_user',)


@pytest.mark.asyncio
async def test_edit_gen_table_keeps_alias_fields_while_excluding_audit_times() -> None:
    db = MagicMock()
    db.execute = AsyncMock()

    await GenTableDao.edit_gen_table_dao(
        db,
        {'tableId': TABLE_ID, 'tableName': 'orders', 'updateTime': CLIENT_AUDIT_TIME},
    )

    params = db.execute.await_args.args[1][0]
    assert params['table_id'] == TABLE_ID
    assert params['table_name'] == 'orders'
    assert 'create_time' not in params
    assert 'update_time' not in params


@pytest.mark.asyncio
async def test_edit_gen_table_column_keeps_alias_fields_while_excluding_audit_times() -> None:
    db = MagicMock()
    db.execute = AsyncMock()

    await GenTableColumnDao.edit_gen_table_column_dao(
        db,
        {'columnId': COLUMN_ID, 'columnName': 'order_id', 'updateTime': CLIENT_AUDIT_TIME},
    )

    params = db.execute.await_args.args[1][0]
    assert params['column_id'] == COLUMN_ID
    assert params['column_name'] == 'order_id'
    assert 'create_time' not in params
    assert 'update_time' not in params
