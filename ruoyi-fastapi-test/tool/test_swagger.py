import pytest
from playwright.async_api import expect

from common.base_page_test import BasePageTest
from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


class SwaggerTest(BasePageTest):
    async def check_swagger_interface(self) -> None:
        """测试系统接口页面 (Swagger UI)"""

        # 1. 直接导航到系统接口页面
        await self.goto_page(Config.frontend_url + '/tool/swagger')

        # 2. 验证页面加载
        # 等待 iframe 出现
        iframe = self.page.locator('iframe')
        await expect(iframe).to_be_visible()

        # 获取 iframe 内容框架
        frame = self.page.frame_locator('iframe')

        # 默认验收容器的禁用状态；本机开发环境可显式验证启用状态。
        h1_locator = frame.locator('h1')
        expected_title = (
            'Swagger UI has been disabled. Please enable it first.' if Config.swagger_disabled else 'RuoYi-FastAPI'
        )
        await expect(h1_locator).to_contain_text(expected_title, timeout=15000)


@pytest.mark.asyncio
async def test_swagger_page(browser_harness: BrowserHarness) -> None:
    """测试系统接口页面功能"""
    test_instance = SwaggerTest()
    await test_instance.setup(browser_harness)
    await test_instance.check_swagger_interface()
