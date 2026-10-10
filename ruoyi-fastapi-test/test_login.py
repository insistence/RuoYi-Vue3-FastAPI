import re

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness

pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


async def test_login_page_loads(browser_harness: BrowserHarness) -> None:
    """登录表单完成渲染后才验收。"""
    page = await browser_harness.new_page()
    await page.goto('/login')
    await expect(page.get_by_placeholder('账号')).to_be_visible()
    await expect(page.get_by_placeholder('密码')).to_be_visible()
    await expect(page.get_by_role('button', name=re.compile(r'登\s*录'))).to_be_enabled()


async def test_captcha_generation(browser_harness: BrowserHarness) -> None:
    """验证隔离测试环境确实关闭验证码。"""
    api = await browser_harness.api_context()
    response = await api.get('/captchaImage')
    assert response.ok
    assert (await response.json())['captchaEnabled'] is False
    page = await browser_harness.new_page()
    await page.goto('/login')
    await expect(page.get_by_placeholder('账号')).to_be_visible()
    await expect(page.get_by_placeholder('验证码')).to_have_count(0)


async def test_login_without_captcha(browser_harness: BrowserHarness) -> None:
    """真实登录 API 必须返回有效令牌。"""
    assert await browser_harness.login()


async def test_login_flow_with_playwright(browser_harness: BrowserHarness) -> None:
    """通过表单登录，验证登录成功后的首页。"""
    page = await browser_harness.new_page()
    await page.goto('/login')
    await browser_harness.login_through_page(page)
    await expect(page.locator('.app-main')).to_be_visible()


async def test_protected_routes_require_auth(browser_harness: BrowserHarness) -> None:
    """独立无 Cookie 上下文必须被路由守卫送回登录页。"""
    page = await browser_harness.new_page()
    await page.goto('/system/user')
    await page.wait_for_url('**/login**')
    await expect(page.get_by_placeholder('账号')).to_be_visible()
    await expect(page.get_by_placeholder('密码')).to_be_visible()


async def test_authenticated_access(browser_harness: BrowserHarness) -> None:
    """已登录用户必须加载用户管理数据表。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/system/user')
    await expect(page.locator('.app-main .el-table')).to_be_visible()
    assert '/login' not in page.url
