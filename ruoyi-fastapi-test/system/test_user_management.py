import re
from http import HTTPStatus
from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


async def verify_auth_role(view: SystemPage, user_id: int, *, assigned: bool) -> None:
    """每次授权变更后重读真实后端，普通角色选中状态必须一致。"""
    response = await view.api.get(f'/system/user/authRole/{user_id}')
    payload = await response.json()
    assert response.ok and payload['code'] == HTTPStatus.OK, payload
    roles = [role for role in payload['roles'] if role['roleKey'] == 'common']
    assert len(roles) == 1
    assert bool(roles[0]['flag']) is assigned


async def reset_password(view: SystemPage, name: str, browser_harness: BrowserHarness) -> None:
    """通过界面重置密码，并使用新密码实际登录验证。"""
    await view.row_action(name, '重置密码')
    prompt = view.page.locator('.el-message-box:visible')
    await prompt.locator('input').fill('Updated123456!')
    await view.action(view.button(prompt, '确定').click, '/system/user/resetPwd', 'PUT')
    await expect(prompt).to_have_count(0)
    anonymous = await browser_harness.api_context()
    logged_in = await anonymous.post('/login', form={'username': name, 'password': 'Updated123456!'})
    login_result = await logged_in.json()
    assert logged_in.ok and login_result['code'] == HTTPStatus.OK, login_result
    token = login_result.get('token') or login_result.get('data', {}).get('token')
    assert token
    user_api = await browser_harness.api_context(token)
    logout = await user_api.post('/logout')
    assert logout.ok and (await logout.json())['code'] == HTTPStatus.OK


@pytest.mark.asyncio
async def test_user_management_page(browser_harness: BrowserHarness) -> None:
    """用户完整 CRUD、状态、密码及独立分配角色页面。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource = '/system/user'
    suffix = uuid4().hex[:8]
    name, nick = f'e2e_{suffix}', f'测试用户_{suffix}'
    phone = f'138{int(suffix, 16) % 100000000:08d}'
    await view.open('/system/user', f'{resource}/list')
    try:
        dialog = await view.add()
        for label, value in {
            '用户名称': name,
            '用户昵称': nick,
            '手机号码': phone,
            '邮箱': f'{name}@example.com',
            '用户密码': 'Test123456!',
            '备注': '测试用户',
        }.items():
            await view.fill(dialog, label, value)
        await view.choose_department(dialog, '归属部门', '集团总公司')
        await view.choose(dialog, '用户性别', '男')
        await view.choose(dialog, '岗位', '董事长')
        await dialog.locator('.el-dialog__header').click()
        await view.choose(dialog, '角色', '普通角色')
        await dialog.locator('.el-dialog__header').click()
        await view.save(resource, 'POST')
        found = await view.search({'用户名称': name})
        assert found['total'] == 1
        record = view.record(found, 'userName', name)
        user_id = record['userId']
        await view.persisted(resource, user_id, {'nickName': nick, 'sex': '0', 'deptId': 100, 'phonenumber': phone})
        await verify_auth_role(view, user_id, assigned=True)
        await view.toggle_status(name, resource, user_id)
        dialog = await view.edit(name, resource, user_id)
        await view.choose(dialog, '用户性别', '女')
        await view.save(resource, 'PUT')
        await view.persisted(resource, user_id, {'sex': '1'})
        await reset_password(view, name, browser_harness)
        for assigned in (False, True):
            await view.action(lambda: view.row_action(name, '分配角色'), f'{resource}/authRole/{user_id}')
            await expect(view.page).to_have_url(re.compile(rf'/system/user-auth/role/{user_id}$'))
            await view.rendered()
            role = view.row('普通角色')
            await expect(role.locator('input[type=checkbox]')).to_be_checked(checked=not assigned)
            await role.locator('.el-checkbox').click()
            await expect(role.locator('input[type=checkbox]')).to_be_checked(checked=assigned)
            await view.action(view.button(view.page, '提交').click, f'{resource}/authRole', 'PUT')
            await expect(view.page).to_have_url(re.compile(r'/system/user$'))
            await verify_auth_role(view, user_id, assigned=assigned)
            await view.search({'用户名称': name})
        deleted = await view.delete(name, resource, user_id)
        assert deleted['total'] == 0
        await view.reset()
        assert (await view.search({'用户名称': name}))['total'] == 0
    finally:
        await view.cleanup(resource, 'userName', [name], 'userId')
