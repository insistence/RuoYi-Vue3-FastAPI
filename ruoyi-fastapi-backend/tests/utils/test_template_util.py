import json
from types import SimpleNamespace

import pytest

from config import database
from module_generator.entity.vo.gen_vo import GenTableColumnModel, GenTableModel, GenTableParamsModel
from module_generator.service.gen_service import GenTableService
from utils.template_util import TemplateInitializer, TemplateUtils

MAX_GENERATED_LINE_LENGTH = 120


def _gen_table(
    *,
    gen_view: bool,
    tpl_web_type: str = 'element-ui',
    tpl_category: str = 'crud',
) -> GenTableModel:
    columns = [
        GenTableColumnModel(
            columnName='item_id',
            columnComment='编号',
            columnType='bigint',
            pythonType='int',
            pythonField='itemId',
            isPk='1',
            isList='1',
            htmlType='input',
        ),
        GenTableColumnModel(
            columnName='item_name',
            columnComment='名称（展示名称）',
            columnType='varchar(100)',
            pythonType='str',
            pythonField='itemName',
            isList='1',
            htmlType='input',
        ),
        GenTableColumnModel(
            columnName='status',
            columnComment='状态',
            columnType='char(1)',
            pythonType='str',
            pythonField='status',
            isList='1',
            htmlType='select',
            dictType='sys_normal_disable',
        ),
    ]
    return GenTableModel(
        tableName='gen_item',
        tableComment='生成测试',
        className='GenItem',
        tplCategory=tpl_category,
        tplWebType=tpl_web_type,
        packageName='module_test',
        moduleName='test',
        businessName='item',
        functionName='测试项',
        functionAuthor='RuoYi',
        formColNum=2,
        options=json.dumps(
            {
                'genView': gen_view,
                'parentMenuId': 3,
                'treeCode': 'item_id',
                'treeParentCode': 'parent_id',
                'treeName': 'item_name',
            }
        ),
        columns=columns,
        pkColumn=columns[0],
    )


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ('1', True),
        ('0', False),
        ('true', True),
        ('false', False),
        (None, False),
    ],
)
def test_get_gen_view_supports_stored_option_formats(value: object, expected: bool) -> None:
    params = {'genView': value} if value is not None else None

    assert TemplateUtils.get_gen_view(params) is expected


@pytest.mark.parametrize(('value', 'expected'), [('1', True), ('0', False)])
def test_gen_table_params_accepts_frontend_string_switch(value: str, expected: bool) -> None:
    assert GenTableParamsModel(genView=value).gen_view is expected


@pytest.mark.parametrize(
    ('tpl_web_type', 'view_template'),
    [
        ('element-ui', 'vue/view.vue.jinja2'),
        ('element-plus', 'vue/v3/view.vue.jinja2'),
    ],
)
def test_template_list_and_context_include_optional_view(tpl_web_type: str, view_template: str) -> None:
    gen_table = _gen_table(gen_view=True, tpl_web_type=tpl_web_type)

    templates = TemplateUtils.get_template_list(gen_table)
    context = TemplateUtils.prepare_context(gen_table)

    assert view_template in templates
    assert context['genView'] is True
    assert TemplateUtils.get_file_name(view_template, gen_table) == 'frontend/views/test/item/view.vue'


def test_template_list_omits_view_when_disabled() -> None:
    gen_table = _gen_table(gen_view=False)

    templates = TemplateUtils.get_template_list(gen_table)
    context = TemplateUtils.prepare_context(gen_table)

    assert 'vue/view.vue.jinja2' not in templates
    assert context['genView'] is False


@pytest.mark.parametrize('tpl_web_type', ['element-ui', 'element-plus'])
@pytest.mark.parametrize('tpl_category', ['crud', 'tree'])
def test_detail_templates_render_with_list_integration(tpl_web_type: str, tpl_category: str) -> None:
    gen_table = _gen_table(gen_view=True, tpl_web_type=tpl_web_type, tpl_category=tpl_category)
    context = TemplateUtils.prepare_context(gen_table)
    env = TemplateInitializer.init_jinja2()
    templates = TemplateUtils.get_template_list(gen_table)

    rendered = {template: env.get_template(template).render(**context) for template in templates}
    index_name = 'index-tree.vue.jinja2' if tpl_category == 'tree' else 'index.vue.jinja2'
    index_template = f'vue{"/v3" if tpl_web_type == "element-plus" else ""}/{index_name}'
    view_template = f'vue{"/v3" if tpl_web_type == "element-plus" else ""}/view.vue.jinja2'

    assert 'handleViewData' in rendered[index_template]
    assert '<item-view-drawer ref="itemViewRef" />' in rendered[index_template]
    assert '测试项详情' in rendered[view_template]
    assert 'getItem(itemId)' in rendered[view_template]
    assert 'sys_normal_disable' in rendered[view_template]


@pytest.mark.asyncio
async def test_set_table_from_options_restores_view_flag() -> None:
    gen_table = _gen_table(gen_view=True)
    gen_table.view = False

    result = await GenTableService.set_table_from_options(gen_table)

    assert result.view is True


def test_secondary_source_templates_use_named_dependency_and_isolated_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gen_table = _gen_table(gen_view=False)
    gen_table.data_source_name = 'reporting'
    monkeypatch.setattr(
        type(database.DataBaseConfig),
        'get_source',
        lambda _self, _name=None: SimpleNamespace(db_type='postgresql'),
    )

    context = TemplateUtils.prepare_context(gen_table)
    env = TemplateInitializer.init_jinja2()
    controller = env.get_template('python/controller.py.jinja2').render(**context)
    entity = env.get_template('python/do.py.jinja2').render(**context)

    assert "DBSessionDependency('reporting')" in controller
    assert 'from common.aspect.db_session import DBSessionDependency' in controller
    assert "DataSourceBase = get_data_source_base('reporting')" in entity
    assert 'class GenItem(DataSourceBase):' in entity
    assert 'from config.database import Base' not in entity
    assert 'from datetime import datetime' not in entity
    compile(entity, '<generated-entity>', 'exec')
    dao = env.get_template('python/dao.py.jinja2').render(**context)
    assert 'if key not in set()' in dao
    compile(dao, '<generated-dao>', 'exec')
    compile(controller, '<generated-controller>', 'exec')


def test_python_templates_handle_audit_timestamps_by_exact_column_name() -> None:
    columns = [
        GenTableColumnModel(
            columnName='item_id',
            columnComment='编号',
            columnType='bigint',
            pythonType='int',
            pythonField='itemId',
            isPk='1',
            isInsert='1',
        ),
        GenTableColumnModel(
            columnName='create_by',
            columnComment='创建者',
            columnType='varchar(64)',
            pythonType='str',
            pythonField='createBy',
            isInsert='1',
            isEdit='0',
        ),
        GenTableColumnModel(
            columnName='update_by',
            columnComment='更新者',
            columnType='varchar(64)',
            pythonType='str',
            pythonField='updateBy',
            isInsert='1',
            isEdit='1',
        ),
        GenTableColumnModel(
            columnName='create_time',
            columnComment='创建时间',
            columnType='datetime',
            pythonType='datetime',
            pythonField='createTime',
            isInsert='1',
            isEdit='0',
        ),
        GenTableColumnModel(
            columnName='update_time',
            columnComment='更新时间',
            columnType='datetime',
            pythonType='datetime',
            pythonField='updateTime',
            isInsert='1',
            isEdit='1',
        ),
        GenTableColumnModel(
            columnName='created_time',
            columnComment='其他时间',
            columnType='datetime',
            pythonType='datetime',
            pythonField='createdTime',
            isInsert='1',
            isEdit='1',
        ),
    ]
    gen_table = _gen_table(gen_view=False)
    gen_table.columns = columns
    gen_table.pk_column = columns[0]

    context = TemplateUtils.prepare_context(gen_table)
    env = TemplateInitializer.init_jinja2()
    entity = env.get_template('python/do.py.jinja2').render(**context)
    dao = env.get_template('python/dao.py.jinja2').render(**context)
    controller = env.get_template('python/controller.py.jinja2').render(**context)

    assert 'from datetime import datetime' in entity
    assert 'create_time = Column(DateTime, nullable=True, default=datetime.now,' in entity
    assert 'update_time = Column(DateTime, nullable=True, default=datetime.now, onupdate=datetime.now,' in entity
    assert 'created_time = Column(DateTime, nullable=True, comment=' in entity
    assert "model_dump(exclude={'create_time', 'update_time'})" in dao
    assert "if key not in {'create_time', 'update_time'}" in dao
    assert 'create_time = datetime.now()' not in controller
    assert 'update_time = datetime.now()' not in controller
    assert 'create_by = current_user.user.user_name' in controller
    assert 'update_by = current_user.user.user_name' in controller
    compile(entity, '<generated-audit-entity>', 'exec')
    compile(dao, '<generated-audit-dao>', 'exec')
    compile(controller, '<generated-audit-controller>', 'exec')
    assert entity.index('from datetime import datetime') < entity.index('from sqlalchemy import')
    assert all(len(line) <= MAX_GENERATED_LINE_LENGTH for line in entity.splitlines())
    assert all(len(line) <= MAX_GENERATED_LINE_LENGTH for line in dao.splitlines())
    assert all(len(line) <= MAX_GENERATED_LINE_LENGTH for line in controller.splitlines())


def test_dao_audit_filter_uses_a_set_for_a_single_timestamp() -> None:
    columns = [
        GenTableColumnModel(
            columnName='item_id',
            columnComment='编号',
            columnType='bigint',
            pythonType='int',
            pythonField='itemId',
            isPk='1',
            isInsert='1',
        ),
        GenTableColumnModel(
            columnName='create_time',
            columnComment='创建时间',
            columnType='datetime',
            pythonType='datetime',
            pythonField='createTime',
            isInsert='1',
        ),
    ]
    gen_table = _gen_table(gen_view=False)
    gen_table.columns = columns
    gen_table.pk_column = columns[0]

    context = TemplateUtils.prepare_context(gen_table)
    dao = TemplateInitializer.init_jinja2().get_template('python/dao.py.jinja2').render(**context)

    assert "if key not in {'create_time'}" in dao
    compile(dao, '<generated-single-audit-dao>', 'exec')


def test_sub_table_entity_template_uses_required_nullable_semantics() -> None:
    gen_table = _gen_table(gen_view=False, tpl_category='sub')
    gen_table.sub_table_name = 'gen_item_detail'
    gen_table.sub_table_fk_name = 'item_id'
    gen_table.sub_table = GenTableModel(
        tableName='gen_item_detail',
        tableComment='生成测试明细',
        className='GenItemDetail',
        columns=[
            GenTableColumnModel(
                columnName='required_value',
                columnComment='必填值',
                columnType='varchar(100)',
                pythonType='str',
                pythonField='requiredValue',
                isRequired='1',
            ),
            GenTableColumnModel(
                columnName='optional_value',
                columnComment='可选值',
                columnType='varchar(100)',
                pythonType='str',
                pythonField='optionalValue',
                isRequired='0',
            ),
            GenTableColumnModel(
                columnName='create_time',
                columnComment='创建时间',
                columnType='datetime',
                pythonType='datetime',
                pythonField='createTime',
            ),
            GenTableColumnModel(
                columnName='update_time',
                columnComment='更新时间',
                columnType='datetime',
                pythonType='datetime',
                pythonField='updateTime',
            ),
        ],
        businessName='itemDetail',
        functionName='生成测试明细',
    )
    gen_table.sub_table.pk_column = gen_table.sub_table.columns[0]

    context = TemplateUtils.prepare_context(gen_table)
    env = TemplateInitializer.init_jinja2()
    entity = env.get_template('python/do.py.jinja2').render(**context)
    dao = env.get_template('python/dao.py.jinja2').render(**context)

    assert "required_value = Column(String(100), nullable=False, comment='必填值')" in entity
    assert "optional_value = Column(String(100), nullable=True, comment='可选值')" in entity
    assert 'create_time = Column(DateTime, nullable=True, default=datetime.now,' in entity
    assert 'update_time = Column(DateTime, nullable=True, default=datetime.now, onupdate=datetime.now,' in entity
    assert "model_dump(exclude={'create_time', 'update_time'})" in dao
    assert "if key not in {'create_time', 'update_time'}" in dao
    compile(entity, '<generated-sub-entity>', 'exec')
    compile(dao, '<generated-sub-dao>', 'exec')


def test_named_data_source_bases_are_cached_and_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    database.get_data_source_base.cache_clear()
    monkeypatch.setattr(type(database.DataBaseConfig), 'get_source', lambda _self, _name: object())

    reporting_base = database.get_data_source_base('reporting')
    archive_base = database.get_data_source_base('archive')

    assert reporting_base is database.get_data_source_base('reporting')
    assert reporting_base is not archive_base
    assert reporting_base.metadata is not archive_base.metadata


@pytest.mark.parametrize(
    ('db_type', 'column_type', 'expected'),
    [
        ('postgresql', 'JSONB', 'JSONB'),
        ('postgresql', 'INET', 'INET'),
        ('postgresql', 'ARRAY', 'ARRAY'),
        ('postgresql', 'VARCHAR(64)', 'String(64)'),
        ('mysql', 'DECIMAL(10, 2)', 'DECIMAL(10, 2)'),
        ('mysql', 'LONGBLOB', 'LargeBinary'),
    ],
)
def test_sqlalchemy_type_mapping_uses_target_source(
    monkeypatch: pytest.MonkeyPatch, db_type: str, column_type: str, expected: str
) -> None:
    monkeypatch.setattr(
        type(database.DataBaseConfig),
        'get_source',
        lambda _self, _name=None: SimpleNamespace(db_type=db_type),
    )

    assert TemplateUtils.get_sqlalchemy_type(column_type) == expected
