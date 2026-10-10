from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_dict_management_page(browser_harness: BrowserHarness) -> None:
    """字典类型和两条字典数据的完整真实 CRUD，包括回显样式。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource, data_resource = '/system/dict/type', '/system/dict/data'
    suffix = uuid4().hex[:8]
    name, kind = f'测试字典_{suffix}', f'e2e_dict_{suffix}'
    await view.open('/system/dict', f'{resource}/list')
    try:
        dialog = await view.add()
        await view.fill(dialog, '字典名称', name)
        await view.fill(dialog, '字典类型', kind)
        await view.save(resource, 'POST')
        found = await view.search({'字典名称': name, '字典类型': kind})
        assert found['total'] == 1
        record = view.record(found, 'dictType', kind)
        dialog = await view.edit(name, resource, record['dictId'])
        await view.fill(dialog, '备注', '字典类型修改备注')
        await view.save(resource, 'PUT')
        await view.persisted(resource, record['dictId'], {'remark': '字典类型修改备注'})
        await view.action(view.button(view.row(name), '列表').click, f'{data_resource}/list')
        view.list_path = f'{data_resource}/list'
        await view.rendered()
        entries = []
        for label, value, style, style_value in [
            ('正常', '1', '主要(primary)', 'primary'),
            ('异常', '2', '危险(danger)', 'danger'),
        ]:
            dialog = await view.add()
            for field, content in {'数据标签': label, '数据键值': value, '显示排序': value}.items():
                await view.fill(dialog, field, content)
            await view.choose(dialog, '回显样式', style)
            saved = await view.save(data_resource, 'POST')
            entry = view.record(saved, 'dictLabel', label)
            entries.append(entry)
            await expect(view.row(label)).to_have_count(1)
            await view.persisted(
                data_resource,
                entry['dictCode'],
                {'dictValue': value, 'dictSort': int(value), 'listClass': style_value, 'dictType': kind},
            )
        dialog = await view.edit('异常', data_resource, entries[1]['dictCode'])
        await view.fill(dialog, '备注', '字典数据修改备注')
        await view.save(data_resource, 'PUT')
        await view.persisted(data_resource, entries[1]['dictCode'], {'remark': '字典数据修改备注'})
        for entry in reversed(entries):
            await view.delete(entry['dictLabel'], data_resource, entry['dictCode'])
        await view.button(view.page, '关闭').click()
        view.list_path = f'{resource}/list'
        await view.rendered()
        await view.search({'字典名称': name})
        deleted = await view.delete(name, resource, record['dictId'])
        assert deleted['total'] == 0
        await view.reset()
        await view.action(view.button(view.page, '刷新缓存').click, f'{resource}/refreshCache', 'DELETE')
    finally:
        await view.cleanup(data_resource, 'dictType', [kind], 'dictCode')
        await view.cleanup(resource, 'dictType', [kind], 'dictId')
