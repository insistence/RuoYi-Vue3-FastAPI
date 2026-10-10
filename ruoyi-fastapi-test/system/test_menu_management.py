from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_menu_management_page(browser_harness: BrowserHarness) -> None:
    """目录、子菜单、按钮三级菜单的创建、修改、查询和逐级删除。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource = '/system/menu'
    suffix = uuid4().hex[:8]
    directory, menu, button = f'测试目录_{suffix}', f'测试菜单_{suffix}', f'测试按钮_{suffix}'
    await view.open('/system/menu', f'{resource}/list')
    try:
        dialog = await view.add()
        await view.radio(dialog, '菜单类型', '目录')
        await view.fill(dialog, '菜单名称', directory)
        await view.fill(dialog, '显示排序', '10')
        await view.fill(dialog, '路由地址', f'e2e_dir_{suffix}')
        await view.save(resource, 'POST')
        found = await view.search({'菜单名称': directory})
        parent = view.record(found, 'menuName', directory)
        await view.persisted(resource, parent['menuId'], {'menuType': 'M', 'path': f'e2e_dir_{suffix}'})
        await view.button(view.row(directory), '新增').click()
        dialog = view.dialog
        await view.radio(dialog, '菜单类型', '菜单')
        for label, value in {
            '菜单名称': menu,
            '显示排序': '1',
            '路由地址': f'e2e_menu_{suffix}',
            '组件路径': 'system/post/index',
            '权限字符': f'e2e:{suffix}:list',
        }.items():
            await view.fill(dialog, label, value)
        await view.save(resource, 'POST')
        found = await view.search({'菜单名称': menu})
        child = view.record(found, 'menuName', menu)
        await view.persisted(resource, child['menuId'], {'parentId': parent['menuId'], 'menuType': 'C'})
        dialog = await view.edit(menu, resource, child['menuId'])
        await view.fill(dialog, '路由地址', f'e2e_menu_updated_{suffix}')
        await view.save(resource, 'PUT')
        await view.persisted(resource, child['menuId'], {'path': f'e2e_menu_updated_{suffix}'})
        await view.button(view.row(menu), '新增').click()
        dialog = view.dialog
        await view.radio(dialog, '菜单类型', '按钮')
        await view.fill(dialog, '菜单名称', button)
        await view.fill(dialog, '显示排序', '1')
        await view.fill(dialog, '权限字符', f'e2e:{suffix}:add')
        await view.save(resource, 'POST')
        found = await view.search({'菜单名称': button})
        leaf = view.record(found, 'menuName', button)
        await view.persisted(
            resource, leaf['menuId'], {'parentId': child['menuId'], 'menuType': 'F', 'perms': f'e2e:{suffix}:add'}
        )
        for name, item in [(button, leaf), (menu, child), (directory, parent)]:
            await view.search({'菜单名称': name})
            await expect(view.row(name)).to_have_count(1)
            deleted = await view.delete(name, resource, item['menuId'])
            assert view.records(deleted) == []
        await view.reset()
        await expect(view.input(view.form, '菜单名称')).to_have_value('')
    finally:
        await view.cleanup(resource, 'menuName', [button, menu, directory], 'menuId')
