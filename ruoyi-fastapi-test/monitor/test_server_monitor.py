import pytest
from playwright.async_api import async_playwright, expect

from common.base_page_test import BasePageTest
from common.config import Config


class ServerMonitorTest(BasePageTest):
    """服务监控测试类"""

    async def test_server_monitor(self) -> None:
        """测试服务监控页面"""
        async with self.page.expect_response(
            lambda response: (
                response.url.endswith('/monitor/server') and response.request.resource_type in {'xhr', 'fetch'}
            )
        ) as server_response:
            await self.page.goto(Config.frontend_url + '/monitor/server')
        payload = await (await server_response.value).json()
        await self.page.wait_for_load_state('networkidle')

        # 验证主要板块存在
        await self.page.wait_for_selector('text=CPU')
        await self.page.wait_for_selector('text=内存')
        await self.page.wait_for_selector('text=服务器信息')
        await self.page.wait_for_selector('text=Python解释器信息')
        await self.page.wait_for_selector('text=磁盘状态')

        # 容器和本机部署的路径不同，页面应展示 API 返回的实际路径。
        project_path = payload['data']['sys']['userDir']
        assert project_path, '服务器应返回非空项目路径'
        project_path_row = self.page.locator('tr', has_text='项目路径')
        await expect(project_path_row).to_contain_text(project_path)


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
