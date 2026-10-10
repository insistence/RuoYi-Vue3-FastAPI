import re
from http import HTTPStatus
from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


async def check_assigned_user(view: SystemPage, role_id: int, name: str, *, assigned: bool) -> None:
    """重新读取已授权用户，验证新增和取消授权确实保存。"""
    response = await view.api.get('/system/role/authUser/allocatedList', params={'roleId': role_id, 'userName': name})
    payload = await response.json()
    assert response.ok and payload['code'] == HTTPStatus.OK, payload
    assert payload['total'] == int(assigned)
    assert [record['userName'] for record in payload['rows']] == ([name] if assigned else [])


async def assign_and_cancel(view: SystemPage, role_id: int, user_name: str) -> None:
    """先后验证单条取消和批量取消授权。"""
    resource = '/system/role'
    for bulk in (False, True):
        await view.action(view.button(view.page, '添加用户').click, f'{resource}/authUser/unallocatedList')
        dialog = view.dialog
        await view.fill(dialog, '用户名称', user_name)
        available = await view.action(view.button(dialog, '搜索').click, f'{resource}/authUser/unallocatedList')
        assert available['total'] == 1
        target = dialog.locator('.el-table__row').filter(has=view.page.get_by_text(user_name, exact=True))
        await target.locator('.el-checkbox').click()
        await view.save(f'{resource}/authUser/selectAll', 'PUT')
        await view.search({'用户名称': user_name})
        await expect(view.row(user_name)).to_have_count(1)
        await check_assigned_user(view, role_id, user_name, assigned=True)
        # 旧角色页的操作提示必须随页面停用关闭，不能遮挡当前授权操作。
        await expect(view.page.locator('.el-popper.el-tooltip:visible')).to_have_count(0)
        if bulk:
            await view.row(user_name).locator('.el-checkbox').click()
            await view.button(view.page, '批量取消授权').click()
            await view.confirm_refresh(f'{resource}/authUser/cancelAll', 'PUT')
        else:
            await view.button(view.row(user_name), '取消授权').click()
            await view.confirm_refresh(f'{resource}/authUser/cancel', 'PUT')
        await expect(view.row(user_name)).to_have_count(0)
        await check_assigned_user(view, role_id, user_name, assigned=False)
        await view.reset()


@pytest.mark.asyncio
async def test_role_management_page(browser_harness: BrowserHarness) -> None:
    """角色 CRUD、菜单/数据权限、状态及分配用户页面的授权与撤销。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource = '/system/role'
    suffix = uuid4().hex[:8]
    name, key, user_name = f'测试角色_{suffix}', f'e2e_role_{suffix}', f'e2e_auth_{suffix}'
    await view.open('/system/role', f'{resource}/list')
    try:
        # 独立的真实用户作为授权目标，避免修改已有业务用户的权限。
        response = await view.api.post(
            '/system/user',
            data={
                'userName': user_name,
                'nickName': '授权测试用户',
                'password': 'Test123456!',
                'deptId': 100,
                'status': '0',
                'roleIds': [],
                'postIds': [],
            },
        )
        payload = await response.json()
        assert response.ok and payload['code'] == HTTPStatus.OK, payload
        dialog = await view.add()
        for label, value in {'角色名称': name, '权限字符': key, '角色顺序': '3'}.items():
            await view.fill(dialog, label, value)
        menu_node = (
            dialog.locator('.el-tree-node__content')
            .filter(has=view.page.locator('.el-tree-node__label').filter(has_text=re.compile(r'^系统管理$')))
            .first
        )
        await menu_node.locator('.el-checkbox').click()
        await expect(menu_node.locator('input[type=checkbox]')).to_be_checked()
        await view.save(resource, 'POST')
        found = await view.search({'角色名称': name, '权限字符': key})
        assert found['total'] == 1
        record = view.record(found, 'roleKey', key)
        role_id = record['roleId']
        await view.persisted(resource, role_id, {'roleName': name, 'roleSort': 3})
        response = await view.api.get(f'/system/menu/roleMenuTreeselect/{role_id}')
        permissions = await response.json()
        assert response.ok and permissions['code'] == HTTPStatus.OK and permissions['checkedKeys'], permissions
        await view.toggle_status(name, resource, role_id)
        dialog = await view.edit(name, resource, role_id)
        await view.fill(dialog, '备注', 'Updated remark')
        await view.save(resource, 'PUT')
        await view.persisted(resource, role_id, {'remark': 'Updated remark'})
        await view.action(lambda: view.row_action(name, '数据权限'), f'{resource}/{role_id}')
        await view.choose(view.dialog, '权限范围', '仅本人数据权限')
        await view.save(f'{resource}/dataScope', 'PUT')
        await view.persisted(resource, role_id, {'dataScope': '5'})
        await view.action(lambda: view.row_action(name, '分配用户'), f'{resource}/authUser/allocatedList')
        await expect(view.page).to_have_url(re.compile(rf'/system/role-auth/user/{role_id}$'))
        view.list_path = f'{resource}/authUser/allocatedList'
        await view.rendered()
        await assign_and_cancel(view, role_id, user_name)
        await view.button(view.page, '关闭').click()
        view.list_path = f'{resource}/list'
        await expect(view.page).to_have_url(re.compile(r'/system/role$'))
        await view.search({'角色名称': name, '权限字符': key})
        assert (await view.delete(name, resource, role_id))['total'] == 0
        await view.reset()
        assert (await view.search({'角色名称': name}))['total'] == 0
    finally:
        await view.cleanup('/system/user', 'userName', [user_name], 'userId')
        await view.cleanup(resource, 'roleKey', [key], 'roleId')
