import pytest
from playwright.async_api import async_playwright, expect

from common.base_page_test import BasePageTest
from common.config import Config


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

        # 后端未禁用Swagger时，验证 iframe 内部的标题包含 "RuoYi-FastAPI"
        # 当前生产环境已默认禁用Swagger，此处验证标题是否包含默认禁用提示
        h1_locator = frame.locator('h1')
        await expect(h1_locator).to_contain_text('Swagger UI has been disabled. Please enable it first.', timeout=15000)


@pytest.mark.asyncio
async def test_swagger_page() -> None:
    """测试系统接口页面功能"""
    async with async_playwright() as p:
        test_instance = SwaggerTest()
        await test_instance.setup(p)
        try:
            await test_instance.check_swagger_interface()
        finally:
            await test_instance.teardown()
