import asyncio
import re
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from zipfile import ZipFile

import pytest
from playwright.async_api import Locator, expect

from common.base_page_test import BasePageTest
from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


class GenTableTest(BasePageTest):
    """只操作本用例导入的生成配置，验证编辑、代码预览及下载。"""

    table_id: int | None = None
    table_name: str = ''
    table_comment: str = ''

    def table_row(self) -> Locator:
        return self.page.locator('.app-container:visible > .el-table .el-table__body-wrapper tbody tr').filter(
            has=self.page.get_by_text(self.table_name, exact=True)
        )

    async def search_table(self) -> dict:
        """等待搜索接口与表格完成，避免初始响应覆盖查询结果。"""
        form = self.page.locator('form').first
        await form.locator('.el-form-item').filter(has_text='表名称').locator('input').fill(self.table_name)
        async with self.page.expect_response(
            lambda response: urlparse(response.url).path.endswith('/tool/gen/list')
        ) as pending:
            await form.get_by_role('button', name=re.compile(r'搜索$')).click()
        payload = await (await pending.value).json()
        assert payload['code'] == HTTPStatus.OK, payload
        await expect(self.page.locator('.el-table .el-loading-mask:visible')).to_have_count(0)
        return payload

    async def import_table(self) -> None:
        """从未导入的真实表中选择一张，不删除任何既有生成配置。"""
        async with self.page.expect_response(
            lambda response: urlparse(response.url).path.endswith('/tool/gen/db/list')
        ) as pending:
            await self.page.get_by_role('button', name=re.compile(r'导入$')).click()
        payload = await (await pending.value).json()
        assert payload['code'] == HTTPStatus.OK and payload['rows'], payload
        self.table_name = payload['rows'][0]['tableName']
        dialog = self.page.get_by_role('dialog', name='导入表', exact=True)
        row = dialog.locator('tbody tr').filter(has=self.page.get_by_text(self.table_name, exact=True))
        await row.locator('.el-checkbox').click()
        await expect(row.locator('.el-checkbox')).to_have_class(re.compile('is-checked'))
        async with self.page.expect_response(
            lambda response: (
                response.request.method == 'POST' and urlparse(response.url).path.endswith('/tool/gen/importTable')
            )
        ) as pending:
            await dialog.get_by_role('button', name=re.compile(r'确\s*定$')).click()
        result = await (await pending.value).json()
        assert result['code'] == HTTPStatus.OK, result
        await expect(dialog).to_be_hidden()
        listed = await self.search_table()
        assert len(listed['rows']) == 1, listed
        self.table_id = listed['rows'][0]['tableId']
        await expect(self.table_row()).to_have_count(1)

    async def edit_table(self) -> None:
        """修改实际生成配置，并重新读取确认服务端持久化结果。"""
        await self.table_row().locator('td').last.get_by_role('button').nth(1).click()
        await self.page.wait_for_url(f'**/tool/gen-edit/index/{self.table_id}**')
        self.table_comment = f'生成验收{uuid4().hex[:8]}'
        await self.page.get_by_role('tab', name='基本信息', exact=True).click()
        await (
            self.page.locator('.el-form-item:visible')
            .filter(has_text='表描述')
            .locator('input')
            .fill(self.table_comment)
        )
        async with self.page.expect_response(
            lambda response: response.request.method == 'PUT' and urlparse(response.url).path.endswith('/tool/gen')
        ) as pending:
            await self.page.get_by_role('button', name=re.compile(r'提交$')).click()
        result = await (await pending.value).json()
        assert result['code'] == HTTPStatus.OK, result
        await self.page.wait_for_url(re.compile(r'/tool/gen(?:\?.*)?$'))
        listed = await self.search_table()
        assert listed['rows'][0]['tableComment'] == self.table_comment
        await expect(self.table_row()).to_contain_text(self.table_comment)

    async def preview_and_download(self) -> None:
        """核对预览接口、可见 Python 代码和实际下载 ZIP 的内容。"""
        async with self.page.expect_response(
            lambda response: urlparse(response.url).path.endswith(f'/tool/gen/preview/{self.table_id}')
        ) as pending:
            await self.table_row().locator('td').last.get_by_role('button').nth(0).click()
        payload = await (await pending.value).json()
        assert payload['code'] == HTTPStatus.OK, payload
        code = payload['data']
        assert any(name.endswith('do.py.jinja2') for name in code), code.keys()
        assert any(self.table_comment in source for source in code.values())
        dialog = self.page.get_by_role('dialog', name='代码预览', exact=True)
        await expect(dialog.locator('pre:visible').first).to_contain_text('class')
        await expect(dialog.locator('pre:visible').first).to_contain_text(self.table_comment)
        await dialog.locator('.el-dialog__headerbtn').click()
        async with self.page.expect_download() as pending:
            await self.table_row().locator('td').last.get_by_role('button').nth(4).click()
        download = await pending.value
        assert download.suggested_filename.endswith('.zip')
        zip_path = Path(await download.path())

        def read_generated_code() -> tuple[list[str], str]:
            with ZipFile(zip_path) as archive:
                names = archive.namelist()
                return names, '\n'.join(archive.read(name).decode('utf-8') for name in names if name.endswith('.py'))

        names, generated = await asyncio.to_thread(read_generated_code)
        assert any(name.endswith('.vue') for name in names), names
        assert any(name.endswith('.py') for name in names), names
        assert self.table_comment in generated and self.table_name in generated

    async def delete_table(self) -> None:
        """通过界面移除刚创建的元数据，并确认实际业务表仍存在。"""
        await self.table_row().locator('td').last.get_by_role('button').nth(2).click()
        async with self.page.expect_response(
            lambda response: (
                response.request.method == 'DELETE'
                and urlparse(response.url).path.endswith(f'/tool/gen/{self.table_id}')
            )
        ) as pending:
            await self.page.get_by_role('button', name=re.compile(r'确定$')).click()
        assert (await (await pending.value).json())['code'] == HTTPStatus.OK
        self.table_id = None
        await self.search_table()
        await expect(self.table_row()).to_have_count(0)
        api = await self.harness.api_context(self.token)
        available = await api.get('/tool/gen/db/list', params={'tableName': self.table_name})
        assert any(row['tableName'] == self.table_name for row in (await available.json())['rows'])

    async def cleanup(self) -> None:
        """失败时仍只清理由本次导入取得 ID 的元数据。"""
        if self.table_id is not None:
            api = await self.harness.api_context(self.token)
            response = await api.delete(f'/tool/gen/{self.table_id}')
            assert (await response.json())['code'] == HTTPStatus.OK


@pytest.mark.asyncio
async def test_gen_table_page(browser_harness: BrowserHarness) -> None:
    """测试真实数据库表的导入、编辑、预览、下载与删除。"""
    test = GenTableTest()
    await test.setup(browser_harness)
    try:
        async with test.page.expect_response(lambda response: urlparse(response.url).path.endswith('/tool/gen/list')):
            await test.page.goto(Config.frontend_url + '/tool/gen')
        await test.import_table()
        await test.edit_table()
        await test.preview_and_download()
        await test.delete_table()
    finally:
        await test.cleanup()
