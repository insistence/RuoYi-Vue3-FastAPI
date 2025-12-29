import time

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class RoleManagementTest(BasePageTest):
    """角色管理测试类"""

    def generate_role_data(self) -> dict:
        """生成测试数据"""
        timestamp = int(time.time())
        return {
            'role_name': f'test_role_{timestamp}',
            'role_key': f'test_{timestamp}',
        }

    async def create_role(self, role_name: str, role_key: str, role_sort: int = 3) -> None:
        """创建角色"""
        # 点击新增按钮
        await self.page.get_by_role('button', name='新增').click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写信息
        await dialog.get_by_role('textbox', name='角色名称').fill(role_name)
        await dialog.get_by_role('textbox', name='权限字符').fill(role_key)
        await dialog.get_by_role('spinbutton', name='角色顺序').fill(str(role_sort))

        # 选择菜单权限 (点击第一个复选框)
        await self.page.locator('.el-tree-node__content .el-checkbox').first.click()

        # 确定
        await self.page.get_by_role('button', name='确 定').click()

        # 等待成功提示
        await self.wait_for_selector('div:has-text("新增成功")', timeout=10000)

    async def search_role(self, role_name: str, role_key: str) -> None:
        """搜索角色"""
        search_form = self.page.locator('form').first
        await search_form.get_by_placeholder('请输入角色名称').fill(role_name)
        await search_form.get_by_placeholder('请输入权限字符').fill(role_key)
        await search_form.get_by_role('button', name='搜索').click()

        # 等待加载
        await self.page.wait_for_timeout(1000)

    async def edit_role(self, new_remark: str) -> None:
        """编辑角色"""
        # 点击修改按钮 (第一行)
        # 按钮没有文字，只有图标，所以使用 nth(0)
        row = self.page.locator('tbody tr').first
        await row.get_by_role('button').nth(0).click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 修改备注
        await dialog.get_by_role('textbox', name='备注').fill(new_remark)

        # 确定
        await self.page.get_by_role('button', name='确 定').click()

        # 等待成功提示
        await self.wait_for_selector('div:has-text("修改成功")', timeout=10000)

    async def change_role_status(self) -> None:
        """修改角色状态"""
        # 点击开关 (第一行)
        # 使用 .el-switch__core 或者 role=switch
        # script.py uses .el-switch__action, let's try .el-switch
        switch = self.page.locator('.el-switch').first
        await switch.click()

        # 确认对话框
        await self.page.get_by_role('button', name='确定').click()
        await self.wait_for_selector('div:has-text("成功")', timeout=5000)

        # 再次点击恢复
        await self.page.wait_for_timeout(1000)
        await switch.click()
        await self.page.get_by_role('button', name='确定').click()
        await self.wait_for_selector('div:has-text("成功")', timeout=5000)

    async def delete_role(self) -> None:
        """删除角色"""
        # 点击删除按钮 (第一行第二个按钮)
        row = self.page.locator('tbody tr').first
        await row.get_by_role('button').nth(1).click()

        # 确认删除
        await self.page.get_by_role('button', name='确定').click()

        # 等待成功提示
        await self.wait_for_selector('div:has-text("删除成功")', timeout=10000)

        # 重置搜索
        await self.page.get_by_role('button', name='重置').click()
        await self.page.wait_for_timeout(1000)

    async def test_role_crud_operations(self) -> None:
        """测试角色管理CRUD"""
        # 访问页面
        await self.goto_page(Config.frontend_url + '/system/role')
        await self.wait_for_page_title('角色管理', timeout=10000)

        # 生成测试数据
        data = self.generate_role_data()

        # 1. 新增
        await self.create_role(data['role_name'], data['role_key'])

        # 验证新增结果
        await self.search_role(data['role_name'], data['role_key'])
        rows = await self.get_table_total_rows()
        assert rows >= 1, '新增后搜索应有结果'

        # 2. 修改状态
        await self.change_role_status()

        # 3. 编辑
        await self.edit_role('Updated remark')

        # 4. 删除
        await self.delete_role()

        # 验证删除结果
        await self.search_role(data['role_name'], data['role_key'])
        rows_after = await self.get_table_total_rows()
        assert rows_after == 0, '删除后搜索应无结果'


@pytest.mark.asyncio
async def test_role_management_page() -> None:
    """测试角色管理页面功能"""
    async with async_playwright() as p:
        test_instance = RoleManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_role_crud_operations()
        finally:
            await test_instance.teardown()
