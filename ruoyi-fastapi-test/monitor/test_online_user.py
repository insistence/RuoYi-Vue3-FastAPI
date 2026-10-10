import re
from urllib.parse import urlparse

import pytest
from playwright.async_api import expect

from common.base_page_test import BasePageTest
from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


class OnlineUserTest(BasePageTest):
    """在线用户测试类。"""

    async def search_secondary_user(self) -> None:
        await self.page.locator('.el-form-item', has_text='用户名称').locator('input').fill('niangao')
        async with self.page.expect_response(
            lambda response: urlparse(response.url).path.endswith('/monitor/online/list')
        ) as response_info:
            await self.page.get_by_role('button', name='搜索').click()
        assert (await response_info.value).ok

    async def test_online_user_operations(self) -> None:
        """真实登录第二账号，强退后必须从结果中消失。"""
        context = await self.harness.new_context()
        page = await context.new_page()
        await page.goto(Config.frontend_url + '/login')
        await page.get_by_placeholder('账号').fill('niangao')
        await page.get_by_placeholder('密码').fill('admin123')
        await page.get_by_role('button', name=re.compile(r'登\s*录')).click()
        await page.wait_for_url('**/index')

        await self.page.goto(Config.frontend_url + '/monitor/online')
        await self.search_secondary_user()
        rows = self.page.locator('.el-table__body tr').filter(has_text='niangao')
        await expect(rows).to_have_count(1)
        await rows.first.get_by_role('button', name='强退').click()
        await self.page.get_by_role('button', name='确定', exact=True).click()
        await expect(self.page.get_by_text('删除成功', exact=True)).to_be_visible()
        await self.search_secondary_user()
        await expect(rows).to_have_count(0)


@pytest.mark.asyncio
async def test_online_user_page(browser_harness: BrowserHarness) -> None:
    """测试在线用户页面功能。"""
    test_instance = OnlineUserTest()
    await test_instance.setup(browser_harness)
    await test_instance.test_online_user_operations()
