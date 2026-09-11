import importlib.util
import json
import sys
from datetime import date, time, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import database
from config.env import AppConfig
from exceptions.exception import ServiceWarning
from module_generator.entity.vo.gen_vo import GenTableColumnModel, GenTableModel
from utils import common_util
from utils.template_util import TemplateInitializer, TemplateUtils


def column(
    name: str, sql_type: str, python_type: str, *, pk: bool = False, query_type: str = 'EQ'
) -> GenTableColumnModel:
    return GenTableColumnModel(
        columnName=name,
        columnComment=name,
        columnType=sql_type,
        pythonType=python_type,
        pythonField=TemplateUtils.to_camel_case(name),
        isPk='1' if pk else '0',
        isInsert='1',
        isEdit='0' if pk else '1',
        isList='1',
        isQuery='0' if pk else '1',
        queryType=query_type,
        htmlType='time' if python_type == 'time' else 'datetime' if python_type in {'date', 'datetime'} else 'input',
    )


def make_table(db_type: str, category: str, web_type: str) -> GenTableModel:
    instant = 'timestamp(3)' if db_type == 'mysql' else 'timestamp(3) with time zone'
    columns = [
        column('item_id', 'bigint', 'int', pk=True),
        column('item_name', 'varchar(64)', 'str'),
        column('birthday', 'date', 'date', query_type='BETWEEN'),
        column('opening_time', 'time(3)', 'time', query_type='BETWEEN'),
    ]
    if category != 'sub':
        columns.extend(
            [
                column('occurred_at', instant, 'datetime', query_type='BETWEEN'),
                column('alarm_at', instant, 'datetime'),
                column('create_time', instant, 'datetime'),
                column('update_time', instant, 'datetime'),
            ]
        )
    if category == 'tree':
        columns.append(column('parent_id', 'bigint', 'int'))
    table = GenTableModel(
        tableName='generated_time_item',
        tableComment='时间样例',
        className='TimeItem',
        tplCategory=category,
        tplWebType=web_type,
        packageName='module_generated_time',
        moduleName='test',
        businessName='item',
        functionName='时间样例',
        functionAuthor='test',
        formColNum=2,
        options=json.dumps(
            {'genView': True, 'treeCode': 'item_id', 'treeParentCode': 'parent_id', 'treeName': 'item_name'}
        ),
        columns=columns,
        pkColumn=columns[0],
    )
    if category == 'sub':
        children = [
            column('detail_id', 'bigint', 'int', pk=True),
            column('parent_item_id', 'bigint', 'int'),
            column('birthday', 'date', 'date'),
            column('occurred_at', instant, 'datetime'),
        ]
        table.sub_table_name = 'generated_time_detail'
        # 子表外键刻意使用不同于主表主键的名称，验证生成关联字段的映射。
        table.sub_table_fk_name = 'parent_item_id'
        table.sub_table = GenTableModel(
            tableName=table.sub_table_name,
            tableComment='子表',
            className='TimeDetail',
            businessName='detail',
            functionName='子表',
            columns=children,
            pkColumn=children[0],
        )
    return table


def render_case(db_type: str, category: str, web_type: str) -> dict[str, str]:
    with patch.object(type(database.DataBaseConfig), 'get_source', return_value=SimpleNamespace(db_type=db_type)):
        table = make_table(db_type, category, web_type)
        context = TemplateUtils.prepare_context(table)
        environment = TemplateInitializer.init_jinja2()
        return {
            name: environment.get_template(name).render(**context) for name in TemplateUtils.get_template_list(table)
        }


@pytest.mark.parametrize('category', ['crud', 'tree', 'sub'])
@pytest.mark.parametrize('web_type', ['element-ui', 'element-plus'])
def test_generated_frontend_contains_business_files_and_reuses_project_time_modules(
    category: str, web_type: str
) -> None:
    table = make_table('mysql', category, web_type)
    rendered = render_case('mysql', category, web_type)
    files = {TemplateUtils.get_file_name(name, table): content for name, content in rendered.items()}

    assert '' not in files
    assert len(files) == len(rendered)
    assert {path for path in files if path.startswith('frontend/')} == {
        'frontend/api/test/item.js',
        'frontend/views/test/item/index.vue',
        'frontend/views/test/item/view.vue',
    }
    page = files['frontend/views/test/item/index.vue']
    assert 'from "@/components/BusinessDateTimePicker"' in page
    assert 'serializeTimeFieldsForSubmit } from "@/utils/time"' in page
    assert 'initializeBusinessTimezone' not in page
    assert '@/api/login' not in page


def import_generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rendered: dict[str, str]) -> tuple:
    class TestBase(DeclarativeBase):
        pass

    monkeypatch.setattr(database, 'Base', TestBase)
    monkeypatch.setattr(common_util, 'Base', TestBase)
    for name in [
        'module_generated_time',
        'module_generated_time.entity',
        'module_generated_time.entity.do',
        'module_generated_time.entity.vo',
        'module_generated_time.dao',
    ]:
        package = ModuleType(name)
        package.__path__ = [str(tmp_path)]
        monkeypatch.setitem(sys.modules, name, package)
    modules = []
    for kind, folder in [('do', 'entity.do'), ('vo', 'entity.vo'), ('dao', 'dao')]:
        name = f'module_generated_time.{folder}.item_{kind}'
        path = tmp_path / f'item_{kind}.py'
        path.write_text(rendered[f'python/{kind}.py.jinja2'], encoding='utf-8')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        modules.append(module)
    return TestBase, *modules


@pytest.mark.parametrize('db_type', ['mysql', 'postgresql'])
@pytest.mark.parametrize('category', ['crud', 'tree', 'sub'])
@pytest.mark.asyncio
async def test_generated_import_crud_and_query(
    db_type: str, category: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, _do, vo, dao = import_generated(tmp_path, monkeypatch, render_case(db_type, category, 'element-plus'))
    monkeypatch.setattr(AppConfig, 'app_timezone', 'America/New_York')
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            payload = {'itemId': 1, 'itemName': 'first', 'birthday': '2000-02-29', 'openingTime': '09:15:00.123'}
            if category != 'sub':
                payload.update(occurredAt='2026-03-08T03:30:00.123-04:00', alarmAt='2026-11-01T01:30:00.456-05:00')
            await dao.ItemDao.add_item_dao(session, vo.ItemModel(**payload))
            if category == 'sub':
                await dao.ItemDao.add_detail_dao(
                    session,
                    vo.DetailModel(
                        detailId=10,
                        parentItemId=1,
                        birthday='2000-02-29',
                        occurredAt='2026-11-01T01:30:00.456-05:00',
                    ),
                )
            await session.commit()
            result = await dao.ItemDao.get_item_detail_by_id(session, 1)
            assert result.birthday == date(2000, 2, 29)
            assert result.opening_time == time(9, 15, 0, 123000)
            instant = result.timedetail_list[0].occurred_at if category == 'sub' else result.occurred_at
            assert instant.tzinfo == timezone.utc
            assert instant.microsecond == (456000 if category == 'sub' else 123000)
            serialized = vo.ItemModel.model_validate(result).model_dump(mode='json', by_alias=True)
            assert serialized['birthday'] == '2000-02-29'
            await dao.ItemDao.edit_item_dao(session, {'item_id': 1, 'item_name': 'changed'})
            await session.commit()
            filters = {'beginBirthday': '2000-02-29', 'endBirthday': '2000-02-29', 'beginOpeningTime': '09:00:00'}
            if category != 'sub':
                filters.update(beginOccurredAt='2026-03-08', endOccurredAt='2026-03-08')
            rows = await dao.ItemDao.get_item_list(session, vo.ItemPageQueryModel(**filters), is_page=False)
            assert len(rows) == 1
            assert rows[0]['itemName'] == 'changed'
            empty = await dao.ItemDao.get_item_list(
                session, vo.ItemPageQueryModel(endBirthday='2000-02-28'), is_page=False
            )
            assert empty == []
            if category == 'sub':
                await dao.ItemDao.edit_detail_dao(session, {'detail_id': 10, 'occurred_at': None})
                await dao.ItemDao.delete_detail_dao(session, vo.DetailModel(detailId=10))
            await dao.ItemDao.delete_item_dao(session, vo.ItemModel(itemId=1))
            await session.commit()
            assert await dao.ItemDao.get_item_detail_by_id(session, 1) is None
        with pytest.raises(ValidationError):
            vo.ItemModel(birthday='2000-02-30')
        with pytest.raises(ValidationError):
            vo.ItemModel(openingTime='25:00:00')
        with pytest.raises(ValidationError):
            vo.ItemPageQueryModel(beginBirthday='2000-03-01', endBirthday='2000-02-29')
        with pytest.raises(ValidationError):
            (vo.DetailModel if category == 'sub' else vo.ItemModel)(occurredAt='2026-03-08 02:30:00')
    finally:
        await engine.dispose()


@pytest.mark.parametrize('column_type', ['timestamp(3) without time zone', 'timestamp', 'TIMESTAMP(6)'])
def test_rejects_postgres_ambiguous_timestamp(column_type: str) -> None:
    table = make_table('postgresql', 'crud', 'element-plus')
    table.columns[4].column_type = column_type
    with patch.object(type(database.DataBaseConfig), 'get_source', return_value=SimpleNamespace(db_type='postgresql')):
        with pytest.raises(ServiceWarning) as error:
            TemplateUtils.prepare_context(table)
        assert 'TIMESTAMP(3) WITH TIME ZONE' in error.value.message


def test_mysql_time_requires_explicit_time_of_day_control() -> None:
    table = make_table('mysql', 'crud', 'element-plus')
    table.columns[3].html_type = 'datetime'
    with patch.object(type(database.DataBaseConfig), 'get_source', return_value=SimpleNamespace(db_type='mysql')):
        with pytest.raises(ServiceWarning) as error:
            TemplateUtils.prepare_context(table)
        assert 'MySQL TIME' in error.value.message
