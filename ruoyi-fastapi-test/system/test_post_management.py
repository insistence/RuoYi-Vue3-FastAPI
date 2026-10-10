from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_post_management_page(browser_harness: BrowserHarness) -> None:
    """岗位增删改查同时验证界面结果和后端保存值。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource = '/system/post'
    suffix = uuid4().hex[:8]
    name, code = f'测试岗位_{suffix}', f'e2e_{suffix}'
    await view.open('/system/post', f'{resource}/list')
    try:
        dialog = await view.add()
        for label, value in {'岗位名称': name, '岗位编码': code, '岗位顺序': '10'}.items():
            await view.fill(dialog, label, value)
        await view.save(resource, 'POST')
        found = await view.search({'岗位名称': name, '岗位编码': code})
        assert found['total'] == 1
        record = view.record(found, 'postCode', code)
        await expect(view.row(name)).to_have_count(1)
        await view.persisted(resource, record['postId'], {'postName': name, 'postSort': 10})
        dialog = await view.edit(name, resource, record['postId'])
        await view.fill(dialog, '备注', f'更新备注_{suffix}')
        await view.save(resource, 'PUT')
        await view.persisted(resource, record['postId'], {'remark': f'更新备注_{suffix}'})
        await view.reset()
        await expect(view.input(view.form, '岗位编码')).to_have_value('')
        await view.search({'岗位名称': name})
        deleted = await view.delete(name, resource, record['postId'])
        assert deleted['total'] == 0
    finally:
        await view.cleanup(resource, 'postCode', [code], 'postId')
