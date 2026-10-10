import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness

pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


async def test_dashboard_page(browser_harness: BrowserHarness) -> None:
    """验证首页组件渲染完成。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/index')
    await expect(page.locator('.app-main')).to_be_visible()
    await expect(page.locator('.tags-view-item.active')).to_contain_text('首页')


async def test_druid_page(browser_harness: BrowserHarness) -> None:
    """验证数据监控页面主体。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/monitor/druid')
    await expect(page.locator('.app-main')).to_contain_text('我是数据监控')


async def test_build_page(browser_harness: BrowserHarness) -> None:
    """验证表单构建器主体，而非仅匹配菜单标题。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/tool/build')
    await expect(page.locator('.app-main')).to_contain_text('Form Generator')
