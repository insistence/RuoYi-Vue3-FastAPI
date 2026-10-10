from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_dept_management_page(browser_harness: BrowserHarness) -> None:
    """创建真实部门，覆盖两套部门树控件及保存后的负责人字段。"""
    view = SystemPage()
    await view.setup(browser_harness)
    resource = '/system/dept'
    name = f'测试部门_{uuid4().hex[:8]}'
    await view.open('/system/dept', f'{resource}/list')
    try:
        dialog = await view.add()
        await view.choose_department(dialog, '上级部门', '集团总公司')
        await view.fill(dialog, '部门名称', name)
        await view.fill(dialog, '显示排序', '3')
        await view.save(resource, 'POST')
        found = await view.search({'部门名称': name})
        record = view.record(found, 'deptName', name)
        await expect(view.row(name)).to_have_count(1)
        await view.persisted(resource, record['deptId'], {'parentId': 100, 'orderNum': 3})
        dialog = await view.edit(name, resource, record['deptId'])
        await view.fill(dialog, '负责人', '年糕')
        await view.fill(dialog, '联系电话', '13800138000')
        await view.fill(dialog, '邮箱', 'e2e@example.com')
        await view.save(resource, 'PUT')
        await view.persisted(
            resource, record['deptId'], {'leader': '年糕', 'phone': '13800138000', 'email': 'e2e@example.com'}
        )
        await view.reset()
        await expect(view.input(view.form, '部门名称')).to_have_value('')
        await view.search({'部门名称': name})
        deleted = await view.delete(name, resource, record['deptId'])
        assert view.records(deleted) == []
    finally:
        await view.cleanup(resource, 'deptName', [name], 'deptId')
