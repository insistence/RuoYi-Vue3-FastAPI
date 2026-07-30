from unittest.mock import AsyncMock, patch

import pytest

from module_generator.dao.gen_dao import GenTableDao
from module_generator.entity.vo.gen_vo import GenTablePageQueryModel
from utils.page_util import PageUtil


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
