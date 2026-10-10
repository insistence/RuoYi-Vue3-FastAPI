import asyncio
import hashlib
import re
from http import HTTPStatus
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.async_api import Locator, expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


async def file_action_row(view: SystemPage, name: str) -> Locator:
    """Element UI 的固定操作列另有一张可见表格。"""
    fixed = view.page.locator('.el-table__fixed-right:visible .el-table__row').filter(
        has=view.page.get_by_text(name, exact=True)
    )
    return fixed if await fixed.count() else view.row(name)


async def select_file(view: SystemPage, name: str) -> None:
    """点击可见复选框外层，核验隐藏原生控件的选择状态。"""
    selection = view.row(name).locator('.el-checkbox')
    await selection.click()
    await expect(selection.locator('input')).to_be_checked()


async def cleanup_file(view: SystemPage, file_id: str, name: str) -> None:
    """只清理本次上传文件，兼容用例已将其永久删除的情况。"""
    response = await view.api.get('/system/file/list', params={'originalName': name, 'pageNum': 1, 'pageSize': 1000})
    assert response.ok
    payload = await response.json()
    assert payload['code'] == HTTPStatus.OK
    records = [record for record in payload['rows'] if record['fileId'] == file_id]
    for record in records:
        if record['status'] == 'active':
            removed = await view.api.delete(f'/system/file/{file_id}')
            assert removed.ok
            assert (await removed.json())['code'] == HTTPStatus.OK
        purged = await view.api.delete(f'/system/file/purge/{file_id}')
        assert purged.ok
        assert (await purged.json())['code'] == HTTPStatus.OK


async def verify_file_details_and_download(view: SystemPage, name: str, file_id: str, contents: bytes) -> None:
    """详情校验持久化摘要，浏览器下载校验原始文件名和真实字节。"""
    action_row = await file_action_row(view, name)
    detail = await view.action(action_row.get_by_role('button').nth(0).click, f'/system/file/{file_id}')
    assert detail['data']['fileHash'] == hashlib.sha256(contents).hexdigest()
    await expect(view.dialog).to_contain_text('文件详细信息')
    await expect(view.dialog).to_contain_text(file_id)
    await expect(view.dialog).to_contain_text(name)
    await expect(view.dialog).to_contain_text(detail['data']['fileHash'])
    await view.dialog.get_by_role('button', name=re.compile(r'^关\s*闭$')).click()
    await expect(view.dialog).to_have_count(0)
    async with view.page.expect_download() as pending:
        await action_row.get_by_role('button').nth(1).click()
    download = await pending.value
    assert await download.failure() is None
    assert download.suggested_filename == name
    download_path = await download.path()
    assert download_path is not None
    assert await asyncio.to_thread(Path(download_path).read_bytes) == contents


async def upload_fixture(view: SystemPage, access_type: str) -> tuple[dict, str, bytes]:
    """文件管理页没有上传控件，使用真实公共上传接口准备唯一文件。"""
    name = f'e2e_{access_type}_{uuid4().hex[:8]}.txt'
    contents = f'{name}\n真实文件下载与恢复校验\n'.encode()
    upload_path = '/common/upload' if access_type == 'public' else '/common/files/upload'
    uploaded = await view.api.post(
        upload_path, multipart={'file': {'name': name, 'mimeType': 'text/plain', 'buffer': contents}}
    )
    assert uploaded.ok
    payload = await uploaded.json()
    assert payload['code'] == HTTPStatus.OK
    assert payload['accessType'] == access_type
    return payload, name, contents


@pytest.mark.parametrize('access_type', ['public', 'private'])
async def test_file_management_lifecycle(browser_harness: BrowserHarness, access_type: str) -> None:
    """真实文件上传夹具→查询/详情/下载→回收站→恢复→永久清理。"""
    view = SystemPage()
    await view.setup(browser_harness)
    payload, name, contents = await upload_fixture(view, access_type)
    file_id = payload['fileId']
    try:
        await view.open('/system/file', '/system/file/list')
        found = await view.search({'文件名称': name})
        assert found['total'] == 1
        record = view.record(found, 'fileId', file_id)
        assert record['originalName'] == name
        assert record['fileSize'] == len(contents)
        await expect(view.row(name)).to_have_count(1)

        await verify_file_details_and_download(view, name, file_id, contents)

        await select_file(view, name)
        await view.button(view.page.locator('.app-main'), '删除').click()
        deleted = await view.confirm_refresh(f'/system/file/{file_id}')
        assert deleted['total'] == 0
        await expect(view.row(name)).to_have_count(0)
        await view.choose(view.form, '文件状态', '已删除')
        deleted = await view.search()
        assert view.record(deleted, 'fileId', file_id)['status'] == 'deleted'
        await expect(view.row(name)).to_contain_text('已删除')

        await select_file(view, name)
        await view.button(view.page.locator('.app-main'), '恢复').click()
        restored = await view.confirm_refresh(f'/system/file/{file_id}/restore', 'PUT')
        assert restored['total'] == 0
        await view.choose(view.form, '文件状态', '正常')
        restored = await view.search()
        assert view.record(restored, 'fileId', file_id)['status'] == 'active'
        await expect(view.row(name)).to_contain_text('正常')

        # 恢复后的文件仍必须能够通过真实下载接口返回完整内容。
        response = await view.api.get(payload['downloadUrl'])
        assert response.ok
        assert await response.body() == contents
        await select_file(view, name)
        await view.button(view.page.locator('.app-main'), '删除').click()
        await view.confirm_refresh(f'/system/file/{file_id}')
        await view.choose(view.form, '文件状态', '已删除')
        await view.search()
        await select_file(view, name)
        await view.button(view.page.locator('.app-main'), '清理').click()
        purged = await view.confirm_refresh(f'/system/file/purge/{file_id}')
        assert purged['total'] == 0
        await expect(view.row(name)).to_have_count(0)
        await view.reset()
        assert (await view.search({'文件名称': name}))['total'] == 0
    finally:
        await cleanup_file(view, file_id, name)
