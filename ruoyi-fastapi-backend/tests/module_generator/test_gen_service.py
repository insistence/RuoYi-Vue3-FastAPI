from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text

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
