import pytest

from common.base_page_test import BasePageTest
from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


class CacheMonitorTest(BasePageTest):
    """缓存监控测试类"""

    async def test_cache_monitor(self) -> None:
        """测试缓存监控页面"""
        await self.page.goto(Config.frontend_url + '/monitor/cache')
        await self.page.wait_for_load_state('networkidle')

        # 验证基本信息
        await self.page.wait_for_selector('text=基本信息')
        await self.page.wait_for_selector('text=Redis版本')
        await self.page.wait_for_selector('text=运行模式')

        # 验证命令统计
        await self.page.wait_for_selector('text=命令统计')

        # 验证内存信息
        await self.page.wait_for_selector('text=内存信息')

        # 验证端口为 6379
        port_row = self.page.locator('tr', has_text='端口')
        try:
            await port_row.wait_for(timeout=5000)
            text = await port_row.text_content()
            assert '6379' in text, f"Expected port '6379' in row, but got: {text}"
        except Exception:
            print("Warning: '端口' row not found, checking page content")
            content = await self.page.content()
            assert '6379' in content, "Port '6379' not found in page content"


@pytest.mark.asyncio
async def test_cache_monitor_page(browser_harness: BrowserHarness) -> None:
    """测试缓存监控页面功能"""
    test_instance = CacheMonitorTest()
    await test_instance.setup(browser_harness)
    await test_instance.test_cache_monitor()
