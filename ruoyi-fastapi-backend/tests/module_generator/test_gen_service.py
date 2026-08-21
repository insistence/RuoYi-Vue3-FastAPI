from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text

from exceptions.exception import ServiceException
from module_generator.entity.vo.gen_vo import EditGenTableModel, GenTableColumnModel
from module_generator.service.gen_service import GenTableService


def test_get_data_source_list_services_returns_camel_case_response(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        db_default_source='primary',
        db_sources={
            'primary': SimpleNamespace(db_type='mysql'),
            'reporting': SimpleNamespace(db_type='postgresql'),
        },
    )
    monkeypatch.setattr('module_generator.service.gen_service.DataBaseConfig', settings)

    result = GenTableService.get_data_source_list_services()

    assert [item.model_dump(by_alias=True) for item in result] == [
        {'name': 'primary', 'dbType': 'mysql', 'isDefault': True},
        {'name': 'reporting', 'dbType': 'postgresql', 'isDefault': False},
    ]


@pytest.mark.asyncio
async def test_get_gen_db_table_list_by_name_services_transforms_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine('sqlite:///:memory:')
    with engine.connect() as connection:
        rows = connection.execute(
            text("select 'sys_user' as table_name, '用户表' as table_comment, null as create_time, null as update_time")
        ).fetchall()

    @asynccontextmanager
    async def session(_source_name: str) -> AsyncGenerator[object, None]:
        yield SimpleNamespace()

    settings = SimpleNamespace(
        db_default_source='primary',
        get_source=lambda _source_name: SimpleNamespace(db_type='mysql'),
    )
    registry = SimpleNamespace(session=session)
    monkeypatch.setattr('module_generator.service.gen_service.DataBaseConfig', settings)
    monkeypatch.setattr('module_generator.service.gen_service.DataSourceRegistry', registry)

    with patch(
        'module_generator.service.gen_service.GenTableDao.get_gen_db_table_list_by_names',
        new=AsyncMock(return_value=rows),
    ):
        result = await GenTableService.get_gen_db_table_list_by_name_services(object(), ['sys_user'], 'reporting')

    assert result[0].table_name == 'sys_user'
    assert result[0].data_source_name == 'reporting'


@pytest.mark.asyncio
async def test_batch_gen_code_services_rejects_tables_from_other_sources() -> None:
    with (
        patch(
            'module_generator.service.gen_service.GenTableDao.get_gen_table_names',
            new=AsyncMock(return_value={'sys_user'}),
        ),
        patch('module_generator.service.gen_service.TemplateInitializer.init_jinja2') as init_jinja2,
        pytest.raises(ServiceException) as exc_info,
    ):
        await GenTableService.batch_gen_code_services(
            object(),
            ['sys_user', 'report_order'],
            'reporting',
        )

    assert exc_info.value.message == '业务表不存在或不属于数据源 reporting：report_order'
    init_jinja2.assert_not_called()


@pytest.mark.asyncio
async def test_edit_gen_table_services_preserves_alias_fields_for_both_daos() -> None:
    table_id = 7
    column_id = 9
    page_object = EditGenTableModel(
        tableId=table_id,
        tableName='orders',
        updateBy='admin',
        columns=[GenTableColumnModel(columnId=column_id, columnName='order_id')],
    )
    query_db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    table_info = SimpleNamespace(table_id=table_id, data_source_name='primary')

    with (
        patch.object(
            GenTableService,
            'get_gen_table_by_id_services',
            new=AsyncMock(return_value=table_info),
        ),
        patch(
            'module_generator.service.gen_service.GenTableDao.edit_gen_table_dao',
            new=AsyncMock(),
        ) as edit_table,
        patch(
            'module_generator.service.gen_service.GenTableColumnDao.edit_gen_table_column_dao',
            new=AsyncMock(),
        ) as edit_column,
    ):
        await GenTableService.edit_gen_table_services(query_db, page_object)

    table_payload = edit_table.await_args.args[1]
    column_payload = edit_column.await_args.args[1]
    assert table_payload['tableId'] == table_id
    assert table_payload['tableName'] == 'orders'
    assert column_payload['columnId'] == column_id
    assert column_payload['columnName'] == 'order_id'
    assert 'createTime' not in table_payload
    assert 'updateTime' not in table_payload
    assert 'createTime' not in column_payload
    assert 'updateTime' not in column_payload
