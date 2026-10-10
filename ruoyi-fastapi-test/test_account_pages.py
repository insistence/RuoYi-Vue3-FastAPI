from __future__ import annotations

import re
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from playwright.async_api import expect

if TYPE_CHECKING:
    from playwright.async_api import APIResponse, Locator, Response

    from common.browser_harness import BrowserHarness

pytestmark = pytest.mark.e2e


async def successful_payload(response: APIResponse | Response) -> dict[str, Any]:
    """验证真实接口的 HTTP 与业务状态，避免仅凭成功提示判断保存结果。"""
    assert response.ok, f'账户 API HTTP 状态异常：{response.status}'
    payload = await response.json()
    assert payload['code'] == HTTPStatus.OK, payload.get('msg')
    return payload


def profile_input(form: Locator, label: str) -> Locator:
    """用用户看到的表单标签兼容 Element UI 和 Element Plus。"""
    return form.locator('.el-form-item').filter(has_text=label).locator('input')


async def test_profile_edit_persists_and_reload_shows_saved_values(browser_harness: BrowserHarness) -> None:
    """编辑个人资料，重读 API 和重新打开页面，最后恢复修改前的资料。"""
    api = await browser_harness.api_context(await browser_harness.login())
    payload = await successful_payload(await api.get('/system/user/profile'))
    original = {key: payload['data'].get(key) for key in ('nickName', 'phonenumber', 'email', 'sex')}
    identity = uuid4().hex[:12]
    updated = {
        'nickName': f'E2E account {identity}',
        'phonenumber': f'139{int(identity, 16) % 100000000:08d}',
        'email': f'e2e-{identity}@example.com',
    }
    labels = {'nickName': '用户昵称', 'phonenumber': '手机号码', 'email': '邮箱'}
    page = await browser_harness.new_page(authenticated=True)
    try:
        await page.goto('/user/profile')
        await page.get_by_role('tab', name='基本资料', exact=True).click()
        form = page.locator('.el-tab-pane:visible .el-form')
        await expect(profile_input(form, '用户昵称')).to_have_value(original['nickName'])
        for key, value in updated.items():
            await profile_input(form, labels[key]).fill(value)
        async with page.expect_response(
            lambda response: (
                urlsplit(response.url).path.endswith('/system/user/profile') and response.request.method == 'PUT'
            )
        ) as pending:
            await form.get_by_role('button', name=re.compile(r'保存\s*$')).click()
        await successful_payload(await pending.value)
        saved = await successful_payload(await api.get('/system/user/profile'))
        assert {key: saved['data'][key] for key in updated} == updated
        assert saved['data']['sex'] == original['sex']
        await page.reload()
        for key, value in updated.items():
            await expect(profile_input(form, labels[key])).to_have_value(value)
        await expect(page.locator('.list-group-item').filter(has_text='用户邮箱')).to_contain_text(updated['email'])
    finally:
        await successful_payload(await api.put('/system/user/profile', data=original))
        restored = await successful_payload(await api.get('/system/user/profile'))
        assert {key: restored['data'].get(key) for key in original} == original


async def test_screen_lock_rejects_wrong_password_and_restores_previous_page(browser_harness: BrowserHarness) -> None:
    """从个人中心锁屏，错误密码和路由跳转不能解锁，正确密码返回锁前页面。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/user/profile')
    await expect(page.get_by_role('tab', name='基本资料', exact=True)).to_be_visible()
    await page.locator('.navbar .avatar-wrapper').hover()
    await page.locator('.el-dropdown-menu:visible').get_by_text('锁定屏幕', exact=True).click()
    await page.wait_for_url('**/lock')
    password = page.get_by_placeholder('请输入登录密码', exact=True)
    await password.press('Enter')
    await expect(page.locator('.error-msg')).to_have_text('请输入密码')
    await password.fill('E2E-incorrect-password')
    async with page.expect_response(
        lambda response: urlsplit(response.url).path.endswith('/unlockscreen') and response.request.method == 'POST'
    ) as pending:
        await password.press('Enter')
    response = await pending.value
    assert response.ok
    rejected = await response.json()
    assert rejected['code'] != HTTPStatus.OK
    assert rejected['msg'] == '密码错误，请重新输入'
    await expect(page.locator('.error-msg')).to_have_text('密码错误，请重新输入')
    await expect(password).to_have_value('')
    await expect(page).to_have_url(re.compile(r'/lock$'))
    await page.goto('/system/user')
    await page.wait_for_url('**/lock')
    await expect(password).to_be_visible()
    await password.fill('admin123')
    async with page.expect_response(
        lambda response: urlsplit(response.url).path.endswith('/unlockscreen') and response.request.method == 'POST'
    ) as pending:
        await password.press('Enter')
    await successful_payload(await pending.value)
    await page.wait_for_url('**/user/profile')
    await expect(page.get_by_role('tab', name='基本资料', exact=True)).to_be_visible()
    await expect(page.locator('.lock-container')).to_have_count(0)


@pytest.mark.parametrize(
    ('route', 'message', 'home_link'),
    [
        ('/401', '您没有访问权限！', '回首页'),
        ('/e2e-page-does-not-exist', '找不到网页！', '返回首页'),
    ],
    ids=['401', '404'],
)
async def test_error_pages_return_to_working_dashboard(
    browser_harness: BrowserHarness, route: str, message: str, home_link: str
) -> None:
    """错误页面的返回入口必须恢复真实首页和已登录的导航功能。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto(route)
    await expect(page.get_by_text(message, exact=True)).to_be_visible()
    await page.get_by_role('link', name=home_link, exact=True).click()
    await page.wait_for_url('**/index')
    await expect(page.locator('.app-main')).to_be_visible()
    await expect(page.locator('.tags-view-item.active')).to_contain_text('首页')
    await page.locator('.navbar .avatar-wrapper').hover()
    await page.locator('.el-dropdown-menu:visible').get_by_text('个人中心', exact=True).click()
    await page.wait_for_url('**/user/profile')
    await expect(page.get_by_role('tab', name='基本资料', exact=True)).to_be_visible()


@pytest.mark.parametrize('route', ['/auth-center/login', '/auth-center/consent', '/auth-center/change-password'])
async def test_auth_center_without_interaction_returns_to_login(browser_harness: BrowserHarness, route: str) -> None:
    """真实开关或缺失交互都会拒绝进入认证表单，错误页可返回原登录页。"""
    page = await browser_harness.new_page()
    await page.goto('/login')
    await expect(page.get_by_placeholder('账号', exact=True)).to_be_visible()
    async with page.expect_response(
        lambda response: urlsplit(response.url).path.endswith('/auth/status') and response.request.method == 'GET'
    ) as pending:
        await page.goto(route)
    payload = await successful_payload(await pending.value)
    await page.wait_for_url('**/auth-center/error?**')
    query = parse_qs(urlsplit(page.url).query)
    if payload['data']['enabled']:
        assert query['message'] == ['认证请求不完整，请返回应用重新登录']
        await expect(page.get_by_role('alert')).to_contain_text('认证请求不完整')
    else:
        assert query['reason'] == ['disabled']
        await expect(page.get_by_role('alert')).to_contain_text('当前未开放统一认证服务')
    await expect(page.get_by_role('textbox')).to_have_count(0)
    await page.get_by_role('button', name=re.compile(r'返回上一页\s*$')).click()
    await page.wait_for_url('**/login')
    await expect(page.get_by_placeholder('账号', exact=True)).to_be_visible()
    await expect(page.get_by_placeholder('密码', exact=True)).to_be_visible()
