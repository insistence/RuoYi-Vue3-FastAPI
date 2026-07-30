import json

import pytest

from module_generator.entity.vo.gen_vo import GenTableColumnModel, GenTableModel, GenTableParamsModel
from module_generator.service.gen_service import GenTableService
from utils.template_util import TemplateInitializer, TemplateUtils


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
