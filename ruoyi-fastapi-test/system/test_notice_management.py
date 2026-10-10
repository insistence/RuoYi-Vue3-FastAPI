from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_notice_management_page(browser_harness: BrowserHarness) -> None:
    """公告富文本新增、查询、编辑和删除均走真实后端。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource = '/system/notice'
    title = f'测试公告_{uuid4().hex[:8]}'
    updated_title = f'{title}_更新'
    initial = await view.open('/system/notice', f'{resource}/list')
    try:
        dialog = await view.add()
        await view.fill(dialog, '公告标题', title)
        await view.choose(dialog, '公告类型', '通知')
        await dialog.locator('.ql-editor').fill('首次公告内容')
        created = await view.save(resource, 'POST')
        assert created['total'] == initial['total'] + 1
        found = await view.search({'公告标题': title})
        assert found['total'] == 1
        record = view.record(found, 'noticeTitle', title)
        saved = await view.persisted(resource, record['noticeId'], {'noticeTitle': title, 'noticeType': '1'})
        assert '首次公告内容' in saved['noticeContent']
        dialog = await view.edit(title, resource, record['noticeId'])
        await view.fill(dialog, '公告标题', updated_title)
        await dialog.locator('.ql-editor').fill('修改后的公告内容')
        await view.save(resource, 'PUT')
        await view.search({'公告标题': updated_title})
        await expect(view.row(updated_title)).to_have_count(1)
        saved = await view.persisted(resource, record['noticeId'], {'noticeTitle': updated_title})
        assert '修改后的公告内容' in saved['noticeContent']
        deleted = await view.delete(updated_title, resource, record['noticeId'])
        assert deleted['total'] == 0
        reset = await view.reset()
        assert reset['total'] == initial['total']
    finally:
        await view.cleanup(resource, 'noticeTitle', [title, updated_title], 'noticeId')
