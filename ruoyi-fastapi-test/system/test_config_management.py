from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_config_management_page(browser_harness: BrowserHarness) -> None:
    """从两套真实界面完成参数新增、查询、修改、重置和删除。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource = '/system/config'
    suffix = uuid4().hex[:8]
    name, key = f'测试参数_{suffix}', f'e2e.config.{suffix}'
    initial = await view.open('/system/config', f'{resource}/list')
    try:
        dialog = await view.add()
        for label, value in {'参数名称': name, '参数键名': key, '参数键值': '原始值'}.items():
            await view.fill(dialog, label, value)
        await view.radio(dialog, '系统内置', '否')
        created = await view.save(resource, 'POST')
        assert created['total'] == initial['total'] + 1
        found = await view.search({'参数名称': name, '参数键名': key})
        assert found['total'] == 1
        record = view.record(found, 'configKey', key)
        await expect(view.row(name)).to_have_count(1)
        await view.persisted(
            resource, record['configId'], {'configName': name, 'configValue': '原始值', 'configType': 'N'}
        )
        dialog = await view.edit(name, resource, record['configId'])
        await view.fill(dialog, '参数键值', '修改后的值')
        await view.save(resource, 'PUT')
        await view.persisted(resource, record['configId'], {'configValue': '修改后的值'})
        await expect(view.row(name)).to_contain_text('修改后的值')
        deleted = await view.delete(name, resource, record['configId'])
        assert deleted['total'] == 0
        reset = await view.reset()
        assert reset['total'] == initial['total']
        await expect(view.input(view.form, '参数名称')).to_have_value('')
        await view.action(view.button(view.page, '刷新缓存').click, f'{resource}/refreshCache', 'DELETE')
    finally:
        await view.cleanup(resource, 'configKey', [key], 'configId')
