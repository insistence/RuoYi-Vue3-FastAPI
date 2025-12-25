import pytest
from playwright.async_api import async_playwright

from common.config import Config
from common.login_helper import LoginHelper


@pytest.mark.asyncio
async def test_login_page_loads() -> None:
    """测试登录页面是否能正常加载"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 访问登录页面
        await page.goto(Config.frontend_url + '/login')

        # 检查页面标题或特定元素是否存在
        title = await page.title()
        assert 'vfadmin' in title

        # 检查登录表单元素是否存在
        username_input = await page.query_selector('input[placeholder="账号"]')
        password_input = await page.query_selector('input[placeholder="密码"]')

        assert username_input is not None
        assert password_input is not None

        await browser.close()


@pytest.mark.asyncio
async def test_captcha_generation() -> None:
    """测试验证码是否正常生成（在测试环境中，验证码已禁用，但仍应能访问登录页面）"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 访问登录页面
        await page.goto(Config.frontend_url + '/login')

        # 在测试环境中验证码已禁用，但仍应能访问登录页面
        title = await page.title()
        assert 'vfadmin' in title

        await browser.close()


def test_login_without_captcha() -> None:
    """测试在禁用验证码的情况下登录流程"""
    helper = LoginHelper()

    # 尝试登录（测试环境中验证码已禁用）
    token = helper.login(username='admin', password='admin123')

    # 验证登录结果
    assert token is not None, '登录应该成功'
    assert len(token) > 0, '应该返回有效的token'


@pytest.mark.asyncio
async def test_login_flow_with_playwright() -> None:
    """使用Playwright测试完整的登录流程（测试环境中验证码已禁用）"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 访问登录页面
        await page.goto(Config.frontend_url + '/login')

        # 等待页面加载
        await page.wait_for_selector('input[placeholder="账号"]')

        # 输入用户名和密码
        await page.fill('input[placeholder="账号"]', 'admin')
        await page.fill('input[placeholder="密码"]', 'admin123')

        # 在测试环境中验证码已禁用，所以不需要处理验证码
        # 直接点击登录按钮
        # 尝试多种可能的选择器
        try:
            await page.click('button:has-text("登录")')
        except Exception:
            try:
                await page.click('button[type="submit"]')
            except Exception:
                await page.click('button.el-button')

        # 等待页面跳转或检查登录结果
        try:
            # 等待跳转到主页或检查登录成功消息
            await page.wait_for_url('**/index**', timeout=10000)
            success = True
        except Exception:
            # 检查是否有错误消息
            error_message = await page.query_selector('.el-message')
            if error_message:
                error_text = await error_message.text_content()
                print(f'登录失败: {error_text}')
                success = False
            else:
                success = False

        assert success, '登录应该成功'

        await browser.close()


@pytest.mark.asyncio
async def test_protected_routes_require_auth() -> None:
    """测试受保护的路由需要认证"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 直接访问受保护的页面（如用户管理）
        await page.goto(Config.frontend_url + '/system/user')

        # 检查是否被重定向到登录页面
        current_url = page.url

        # 检查页面是否包含登录相关的元素（如账号密码输入框）
        try:
            has_username_input = await page.is_visible('input[placeholder*="账号" i], input[placeholder*="username" i]')
        except Exception:
            has_username_input = False

        try:
            has_password_input = await page.is_visible('input[placeholder*="密码" i], input[placeholder*="password" i]')
        except Exception:
            has_password_input = False

        try:
            has_login_button = await page.is_visible('button:has-text("登录"), button:has-text("Login"), .login-btn')
        except Exception:
            has_login_button = False

        # 检查URL是否包含login路径
        is_redirected_to_login = '/login' in current_url.lower() or '/#/login' in current_url

        # 断言：应该重定向到登录页面或页面包含登录相关元素
        assert is_redirected_to_login or has_username_input or has_password_input or has_login_button, (
            f'未登录用户访问受保护页面时，没有重定向到登录页。当前URL: {current_url}, 页面内容: {await page.content()}'
        )

        await browser.close()


@pytest.mark.asyncio
async def test_authenticated_access() -> None:
    """测试认证后的访问"""
    # 首先通过API登录获取token
    helper = LoginHelper()
    token = helper.login(username='admin', password='admin123')

    assert token is not None, '登录应该成功'

    # 使用Playwright测试带认证的访问
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state={  # 使用storage state来保持登录状态
                'cookies': [
                    {
                        'name': 'Admin-Token',
                        'value': token,
                        'domain': 'localhost',
                        'path': '/',
                        'httpOnly': False,
                        'secure': False,
                        'sameSite': 'Lax',
                    }
                ],
                'origins': [],
            }
        )
        page = await context.new_page()

        # 访问受保护的页面
        await page.goto(Config.frontend_url + '/system/user')

        # 检查是否能够访问受保护的页面（而不是被重定向到登录页）
        current_url = page.url
        assert '/login' not in current_url, '已登录用户应该能够访问受保护页面'

        # 检查页面是否包含用户管理相关的元素
        try:
            # 等待页面加载
            await page.wait_for_selector('div:has-text("用户管理")', timeout=10000)
            has_user_management = True
        except Exception:
            has_user_management = False

        # 或者检查是否有表格或其他用户管理组件
        table_element = await page.query_selector('el-table')
        if not has_user_management and table_element:
            has_user_management = True

        assert has_user_management, '应该能够访问用户管理页面'

        await context.close()
        await browser.close()
