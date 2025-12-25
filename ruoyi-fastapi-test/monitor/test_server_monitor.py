import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class ServerMonitorTest(BasePageTest):
    """服务监控测试类"""

    async def test_server_monitor(self) -> None:
        """测试服务监控页面"""
        await self.page.goto(Config.frontend_url + '/monitor/server')
        await self.page.wait_for_load_state('networkidle')

        # 验证主要板块存在
        await self.page.wait_for_selector('text=CPU')
        await self.page.wait_for_selector('text=内存')
        await self.page.wait_for_selector('text=服务器信息')
        await self.page.wait_for_selector('text=Python解释器信息')
        await self.page.wait_for_selector('text=磁盘状态')

        # 验证项目路径为 /app
        # 尝试在表格行中查找
        project_path_row = self.page.locator('tr', has_text='项目路径')
        try:
            await project_path_row.wait_for(timeout=5000)
            text = await project_path_row.text_content()
            assert '/app' in text, f"Expected project path '/app' in row, but got: {text}"
        except Exception:
            # 如果没找到行，尝试全局搜索
            print("Warning: '项目路径' row not found, checking page content")
            content = await self.page.content()
            assert '/app' in content, "Project path '/app' not found in page content"


@pytest.mark.asyncio
async def test_server_monitor_page() -> None:
    """测试服务监控页面功能"""
    async with async_playwright() as p:
        test_instance = ServerMonitorTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_server_monitor()
        finally:
            await test_instance.teardown()
