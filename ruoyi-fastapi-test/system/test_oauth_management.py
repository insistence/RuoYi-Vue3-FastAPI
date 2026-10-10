from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from playwright.async_api import expect

if TYPE_CHECKING:
    from playwright.async_api import APIRequestContext, APIResponse, Locator, Page, Response

    from common.browser_harness import BrowserHarness

pytestmark = pytest.mark.e2e
SUCCESS_CODE = 200


def button_name(label: str) -> re.Pattern[str]:
    """允许 Vue2 Element UI 按钮名称前存在字体图标，仍精确匹配文字结尾。"""
    return re.compile(rf'{re.escape(label)}$')


async def successful_json(response: APIResponse | Response) -> dict[str, Any]:
    """同时验证 HTTP 与真实业务响应，不将错误页当成空列表。"""
    assert response.ok, f'OAuth API HTTP 状态异常：{response.status}'
    payload = await response.json()
    assert payload['code'] == SUCCESS_CODE, payload.get('msg')
    return payload


async def click_response(page: Page, button: Locator, path: str, method: str) -> dict[str, Any]:
    """点击操作后等待对应业务请求完成，兼容两个框架的 API 前缀。"""
    async with page.expect_response(
        lambda response: urlparse(response.url).path.endswith(path) and response.request.method == method
    ) as pending:
        await button.click()
    return await successful_json(await pending.value)


async def find_record(page: Page, kind: str, placeholder: str, name: str) -> Locator:
    """按唯一名称查询当前用例的记录，避开分页和其他测试的数据。"""
    await page.get_by_placeholder(placeholder, exact=True).fill(name)
    await click_response(
        page, page.get_by_role('button', name=button_name('查找')), f'/system/oauth/{kind}/list', 'GET'
    )
    rows = page.locator('.el-table__body tr').filter(has_text=name)
    await expect(rows.first).to_be_visible()
    return rows


async def change_record_status(page: Page, rows: Locator, kind: str, identifier: str, *, enable: bool) -> None:
    """从实际行菜单停用或启用，再确认弹窗提交的接口成功。"""
    await rows.get_by_role('button', name=button_name('更多')).click()
    label = '重新启用' if enable else {'client': '停用应用', 'resource': '停用服务', 'scope': '停用权限'}[kind]
    await page.locator('.el-dropdown-menu:visible').get_by_text(label, exact=True).click()
    endpoint = f'/system/oauth/{kind}/changeStatus' if enable else f'/system/oauth/{kind}/{identifier}'
    await click_response(
        page,
        page.locator('.el-message-box').get_by_role('button', name=button_name('确定')),
        endpoint,
        'PUT' if enable else 'DELETE',
    )


async def assert_record_status(api: APIRequestContext, kind: str, identifier: str, status: str) -> None:
    """直接读取持久化记录，验证 UI 操作确实改变后端状态。"""
    payload = await successful_json(await api.get(f'/system/oauth/{kind}/{identifier}'))
    assert payload['data']['status'] == status


@pytest.mark.parametrize(
    ('kind', 'label', 'name_placeholder', 'id_placeholder'),
    [
        ('resource', '服务', '例如：订单服务', '例如：orders-api'),
        ('scope', '权限', '例如：查看订单', '例如：orders.read'),
    ],
    ids=['resource', 'scope'],
)
async def test_oauth_resource_and_scope_lifecycle(
    browser_harness: BrowserHarness, kind: str, label: str, name_placeholder: str, id_placeholder: str
) -> None:
    """资源与权限分别验证新增、筛选、编辑、软停用和重新启用。"""
    identifier = f'e2e-{kind}-{uuid4().hex[:12]}'
    name = f'E2E {label} {identifier}'
    page = await browser_harness.new_page(authenticated=True)
    api = await browser_harness.api_context(await browser_harness.login())
    created = False
    try:
        await page.goto(f'/system/oauth/{kind}')
        await page.get_by_role('button', name=button_name(f'新增{label}')).click()
        dialog = page.get_by_role('dialog', name=f'新增{label}', exact=True)
        await dialog.get_by_placeholder(name_placeholder, exact=True).fill(name)
        await dialog.get_by_placeholder(id_placeholder, exact=True).fill(identifier)
        if kind == 'resource':
            await dialog.get_by_placeholder('例如：https://api.example.com', exact=True).fill(
                f'https://example.com/{identifier}'
            )
        await click_response(
            page, dialog.get_by_role('button', name=button_name(f'保存{label}')), f'/system/oauth/{kind}', 'POST'
        )
        created = True
        await expect(dialog).to_be_hidden()
        rows = await find_record(page, kind, f'输入{label}名称', name)
        await rows.get_by_role('button', name=button_name('编辑')).click()
        dialog = page.get_by_role('dialog', name=f'编辑{label}', exact=True)
        await expect(dialog.get_by_placeholder(id_placeholder, exact=True)).to_be_disabled()
        changed_name = f'{name} edited'
        await dialog.get_by_placeholder(name_placeholder, exact=True).fill(changed_name)
        await click_response(
            page, dialog.get_by_role('button', name=button_name(f'保存{label}')), f'/system/oauth/{kind}', 'PUT'
        )
        await expect(dialog).to_be_hidden()
        rows = await find_record(page, kind, f'输入{label}名称', changed_name)
        detail = await successful_json(await api.get(f'/system/oauth/{kind}/{identifier}'))
        assert detail['data'][f'{kind}Name'] == changed_name
        await change_record_status(page, rows, kind, identifier, enable=False)
        await assert_record_status(api, kind, identifier, '1')
        rows = await find_record(page, kind, f'输入{label}名称', changed_name)
        await change_record_status(page, rows, kind, identifier, enable=True)
        await assert_record_status(api, kind, identifier, '0')
    finally:
        if created:
            await successful_json(await api.delete(f'/system/oauth/{kind}/{identifier}'))
            await assert_record_status(api, kind, identifier, '1')


async def test_oauth_client_registration_edit_secret_and_status(browser_harness: BrowserHarness) -> None:
    """应用注册、编辑、密钥一次性展示及停用恢复都经过真实后端。"""
    name = f'E2E application {uuid4().hex[:12]}'
    page = await browser_harness.new_page(authenticated=True)
    api = await browser_harness.api_context(await browser_harness.login())
    client_id = None
    try:
        await page.goto('/system/oauth/client')
        await page.get_by_role('button', name=button_name('注册应用')).click()
        dialog = page.get_by_role('dialog', name='注册应用', exact=True)
        await dialog.locator('.el-form-item').filter(has_text='应用名称').locator('input').fill(name)
        await dialog.get_by_role('tab', name='回调地址', exact=True).click()
        await dialog.get_by_placeholder('https://portal.example.com/callback', exact=True).fill(
            'https://example.com/e2e/callback'
        )
        await dialog.get_by_placeholder('https://portal.example.com/callback', exact=True).blur()
        result = await click_response(
            page, dialog.get_by_role('button', name=button_name('保存应用')), '/system/oauth/client', 'POST'
        )
        client_id = result['data']['clientId']
        await expect(dialog).to_be_hidden()
        rows = await find_record(page, 'client', '输入应用名称', name)
        await rows.get_by_role('button', name=button_name('编辑')).click()
        dialog = page.get_by_role('dialog', name='编辑应用', exact=True)
        name = f'{name} edited'
        await dialog.locator('.el-form-item').filter(has_text='应用名称').locator('input').fill(name)
        await click_response(
            page, dialog.get_by_role('button', name=button_name('保存应用')), '/system/oauth/client', 'PUT'
        )
        await expect(dialog).to_be_hidden()
        rows = await find_record(page, 'client', '输入应用名称', name)
        detail = await successful_json(await api.get(f'/system/oauth/client/{client_id}'))
        assert detail['data']['clientName'] == name
        await rows.get_by_role('button', name=button_name('更多')).click()
        await page.locator('.el-dropdown-menu:visible').get_by_text('轮换应用密钥', exact=True).click()
        await click_response(
            page,
            page.locator('.el-message-box').get_by_role('button', name=button_name('确定')),
            f'/system/oauth/client/{client_id}/secret',
            'POST',
        )
        secret_dialog = page.get_by_role('dialog', name='保存应用密钥', exact=True)
        await expect(secret_dialog.get_by_role('button', name=button_name('完成'))).to_be_disabled()
        secret_input = secret_dialog.locator('.el-form-item').filter(has_text='应用密钥').locator('input')
        assert await secret_input.input_value(), '轮换后应显示一次性应用密钥'
        await secret_dialog.get_by_text('我已将密钥保存到安全位置', exact=True).click()
        await expect(secret_dialog.get_by_role('checkbox', name='我已将密钥保存到安全位置')).to_be_checked()
        await secret_dialog.get_by_role('button', name=button_name('完成')).click()
        await expect(secret_dialog).to_be_hidden()
        rows = await find_record(page, 'client', '输入应用名称', name)
        await change_record_status(page, rows, 'client', client_id, enable=False)
        await assert_record_status(api, 'client', client_id, '1')
        rows = await find_record(page, 'client', '输入应用名称', name)
        await change_record_status(page, rows, 'client', client_id, enable=True)
        await assert_record_status(api, 'client', client_id, '0')
    finally:
        if client_id:
            await successful_json(await api.delete(f'/system/oauth/client/{client_id}'))
            await assert_record_status(api, 'client', client_id, '1')


async def test_oauth_grant_access_policy_create_and_release(browser_harness: BrowserHarness) -> None:
    """在用户首次授权前新增禁止策略，并验证解除后的真实策略状态。"""
    api = await browser_harness.api_context(await browser_harness.login())
    profile = await successful_json(await api.get('/system/user/profile'))
    user_id = profile['data']['userId']
    name = f'E2E access policy {uuid4().hex[:12]}'
    result = await successful_json(
        await api.post(
            '/system/oauth/client',
            data={
                'clientName': name,
                'clientType': 'public',
                'tokenEndpointAuthMethod': 'none',
                'scopeCodes': ['openid'],
                'redirectUris': ['https://example.com/e2e/callback'],
            },
        )
    )
    client_id = result['data']['clientId']
    path = f'/system/oauth/grant/user/{user_id}/client/{client_id}/access'
    try:
        page = await browser_harness.new_page(authenticated=True)
        await page.goto('/system/oauth/grant')
        await page.get_by_role('button', name=button_name('访问策略')).click()
        drawer = page.locator('.el-drawer:visible')
        await drawer.get_by_role('button', name=button_name('新增禁止策略')).click()
        dialog = page.get_by_role('dialog', name='禁止用户访问应用', exact=True)
        await dialog.get_by_placeholder('输入用户管理中的用户编号', exact=True).fill(str(user_id))
        await dialog.get_by_placeholder('输入客户端管理中的 Client ID', exact=True).fill(client_id)
        await dialog.get_by_placeholder('填写原因，便于后续审计', exact=True).fill('E2E access policy test')
        await click_response(page, dialog.get_by_role('button', name=button_name('确认禁止')), path, 'PUT')
        await expect(dialog).to_be_hidden()
        await drawer.get_by_placeholder('Client ID', exact=True).fill(client_id)
        await click_response(
            page, drawer.get_by_role('button', name=button_name('查找')), '/system/oauth/grant/access/list', 'GET'
        )
        rows = drawer.locator('.el-table__body tr').filter(has_text=client_id)
        await expect(rows.first).to_contain_text('禁止访问')
        await rows.get_by_role('button', name=button_name('解除禁止')).click()
        dialog = page.get_by_role('dialog', name='解除应用访问禁止', exact=True)
        await dialog.get_by_placeholder('填写原因，便于后续审计', exact=True).fill('E2E release access policy')
        await click_response(page, dialog.get_by_role('button', name=button_name('确认解除')), path, 'PUT')
        await expect(dialog).to_be_hidden()
        await expect(rows.first).to_contain_text('允许访问')
        policies = await successful_json(
            await api.get('/system/oauth/grant/access/list', params={'userId': user_id, 'clientId': client_id})
        )
        assert len(policies['rows']) == 1
        assert policies['rows'][0]['accessStatus'] == 'allowed'
    finally:
        await successful_json(await api.put(path, data={'blocked': False, 'reason': 'E2E cleanup'}))
        await successful_json(await api.delete(f'/system/oauth/client/{client_id}'))


async def test_oauth_session_search_and_reset(browser_harness: BrowserHarness) -> None:
    """没有协议会话时仍验证真实查询参数、空态及禁止批量强退。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/system/oauth/session')
    await page.get_by_placeholder('用户编号', exact=True).fill('987654321')
    await page.get_by_placeholder('IP 地址', exact=True).fill('192.0.2.240')
    async with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith('/system/oauth/session/list')
            and parse_qs(urlparse(response.url).query).get('userId') == ['987654321']
        )
    ) as pending:
        await page.get_by_role('button', name=button_name('查找')).click()
    response = await pending.value
    payload = await successful_json(response)
    assert parse_qs(urlparse(response.url).query)['userId'] == ['987654321']
    assert parse_qs(urlparse(response.url).query)['ipAddress'] == ['192.0.2.240']
    assert payload['rows'] == []
    await expect(page.get_by_role('button', name=button_name('强制下线'))).to_be_disabled()
    await expect(page.locator('.app-main .el-empty')).to_be_visible()
    await click_response(
        page, page.get_by_role('button', name=button_name('清空')), '/system/oauth/session/list', 'GET'
    )
    await expect(page.get_by_placeholder('用户编号', exact=True)).to_have_value('')
    await expect(page.get_by_placeholder('IP 地址', exact=True)).to_have_value('')


async def test_oidc_key_status_and_rotation_form_validation(browser_harness: BrowserHarness) -> None:
    """核对真实认证状态并验证必填校验，不更改实例的签名密钥。"""
    page = await browser_harness.new_page(authenticated=True)
    async with page.expect_response(
        lambda response: urlparse(response.url).path.endswith('/system/oauth/key/list')
    ) as pending:
        await page.goto('/system/oauth/key')
    payload = await successful_json(await pending.value)
    expected_status = (
        '尚未启用'
        if payload['enabled'] is False
        else '已启用并可以提供认证'
        if payload['ready']
        else '等待初始化签名密钥'
    )
    await expect(page.locator('.overview-state').first).to_contain_text(expected_status)
    await page.get_by_role('button', name=button_name('安排密钥轮换')).click()
    dialog = page.get_by_role('dialog', name='安排签名密钥轮换', exact=True)
    await dialog.get_by_role('button', name=button_name('创建轮换计划')).click()
    await expect(dialog.get_by_text('请输入便于识别的密钥编号', exact=True)).to_be_visible()
    await expect(dialog.get_by_text('请选择公开公钥时间', exact=True)).to_be_visible()
    await expect(dialog.get_by_text('请选择开始签名时间', exact=True)).to_be_visible()
    await dialog.get_by_placeholder('例如：2026-09-primary', exact=True).fill('invalid key with spaces')
    await dialog.get_by_role('button', name=button_name('创建轮换计划')).click()
    await expect(dialog.get_by_text('只能使用字母、数字、点、横线和下划线', exact=True)).to_be_visible()
    await dialog.get_by_role('button', name=button_name('取消')).click()
    await expect(dialog).to_be_hidden()
