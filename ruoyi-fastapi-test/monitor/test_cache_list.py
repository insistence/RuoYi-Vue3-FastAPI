import pytest
from playwright.async_api import async_playwright, expect

from common.base_page_test import BasePageTest
from common.config import Config


class CacheListTest(BasePageTest):
    """缓存列表测试类"""

    async def test_cache_list(self) -> None:
        """测试缓存列表页面"""
        await self.page.goto(Config.frontend_url + '/monitor/cacheList')
        await self.page.wait_for_load_state('networkidle')

        # 1. 缓存列表 - 点击 sys_config
        await self.page.wait_for_selector('text=缓存列表')

        # 等待 sys_config 出现并点击
        sys_config_row = self.page.locator('.el-card', has_text='缓存列表').locator('tr', has_text='sys_config')
        await sys_config_row.wait_for()
        await sys_config_row.click()

        # 2. 键名列表 - 点击 sys.account.captchaEnabled
        await self.page.wait_for_selector('text=键名列表')

        # 等待 sys.account.captchaEnabled 出现并点击
        captcha_row = self.page.locator('.el-card', has_text='键名列表').locator(
            'tr', has_text='sys.account.captchaEnabled'
        )
        await captcha_row.wait_for()
        await captcha_row.click()

        # 3. 验证缓存内容为 false
        await self.page.wait_for_selector('text=缓存内容')

        # 等待数据加载
        await self.page.wait_for_timeout(2000)

        # 获取内容
        # 缓存内容显示在一个 textarea 中
        content_area = self.page.locator('div.el-form-item', has_text='缓存内容:').locator('textarea')

        # 也可以尝试直接获取 .el-form-item__content 的文本，如果 textarea 不可交互
        if await content_area.count() > 0:
            # 尝试等待内容不为空
            try:
                await expect(content_area).not_to_be_empty(timeout=5000)
            except TimeoutError:
                pass

            value = await content_area.input_value()
            print(f'Cache content value: {value}')

            # 如果为空，可能需要重新点击一下
            if not value:
                print('Value is empty, trying to click key again')
                await captcha_row.click()
                await self.page.wait_for_timeout(2000)
                value = await content_area.input_value()
                print(f'Cache content value after retry: {value}')

            assert 'false' in value.lower(), f"Expected 'false' in cache content, got: {value}"
        else:
            # 如果不是 textarea，尝试获取文本
            content_div = self.page.locator('div.el-form-item', has_text='缓存内容:').locator('.el-form-item__content')
            value = await content_div.text_content()
            print(f'Cache content text: {value}')
            assert 'false' in value.lower(), f"Expected 'false' in cache content, got: {value}"


@pytest.mark.asyncio
async def test_cache_list_page() -> None:
    """测试缓存列表页面功能"""
    async with async_playwright() as p:
        test_instance = CacheListTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_cache_list()
        finally:
            await test_instance.teardown()
