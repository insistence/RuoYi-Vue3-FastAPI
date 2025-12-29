import pytest
from playwright.async_api import async_playwright

from common.config import Config
from common.login_helper import LoginHelper


@pytest.mark.asyncio
async def test_dashboard_page() -> None:
    """测试仪表盘页面"""
    # 首先登录获取token
    helper = LoginHelper()
    token = helper.login(username='admin', password='admin123')
    assert token is not None, '登录应该成功'

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        # 设置认证token
        await context.add_cookies(
            [
                {
                    'name': 'Admin-Token',
                    'value': token,
                    'domain': 'localhost',
                    'path': '/',
                    'httpOnly': False,
                    'secure': False,
                }
            ]
        )
        page = await context.new_page()

        # 访问仪表盘页面
        await page.goto(Config.frontend_url + '/index')

        # 检查页面是否包含仪表盘相关元素
        await page.wait_for_selector('div:has-text("首页")', timeout=10000)
        title = await page.inner_text('div:has-text("首页")')
        assert '首页' in title

        await context.close()
        await browser.close()


@pytest.mark.asyncio
async def test_druid_page() -> None:
    """测试数据监控页面"""
    # 首先登录获取token
    helper = LoginHelper()
    token = helper.login(username='admin', password='admin123')
    assert token is not None, '登录应该成功'

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        # 设置认证token
        await context.add_cookies(
            [
                {
                    'name': 'Admin-Token',
                    'value': token,
                    'domain': 'localhost',
                    'path': '/',
                    'httpOnly': False,
                    'secure': False,
                }
            ]
        )
        page = await context.new_page()

        # 访问数据库监控页面
        await page.goto(Config.frontend_url + '/monitor/druid')

        # 检查页面是否包含缓存监控相关元素
        await page.wait_for_selector('div:has-text("数据监控")', timeout=10000)
        title = await page.inner_text('div:has-text("数据监控")')
        assert '数据监控' in title

        await context.close()
        await browser.close()


@pytest.mark.asyncio
async def test_build_page() -> None:
    """测试表单构建页面"""
    # 首先登录获取token
    helper = LoginHelper()
    token = helper.login(username='admin', password='admin123')
    assert token is not None, '登录应该成功'

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        # 设置认证token
        await context.add_cookies(
            [
                {
                    'name': 'Admin-Token',
                    'value': token,
                    'domain': 'localhost',
                    'path': '/',
                    'httpOnly': False,
                    'secure': False,
                }
            ]
        )
        page = await context.new_page()

        # 访问数据库监控页面
        await page.goto(Config.frontend_url + '/tool/build')

        # 检查页面是否包含缓存监控相关元素
        await page.wait_for_selector('div:has-text("Form Generator")', timeout=10000)
        title = await page.inner_text('div:has-text("Form Generator")')
        assert '表单构建' in title

        await context.close()
        await browser.close()
