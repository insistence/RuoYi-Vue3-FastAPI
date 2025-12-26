from datetime import datetime

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class MenuManagementTest(BasePageTest):
    """菜单管理测试"""

    def generate_menu_data(self) -> dict:
        """生成测试数据"""
        timestamp = datetime.now().strftime('%H%M%S')
        return {
            'dir_name': f'测试目录_{timestamp}',
            'menu_name': f'测试菜单_{timestamp}',
            'path_dir': f'test_dir_{timestamp}',
            'path_menu': f'test_menu_{timestamp}',
            'path_menu_new': f'test_menu_new_{timestamp}',
            'order_num': '10',
        }

    async def create_directory(self, menu_name: str, path: str, order_num: str) -> None:
        """创建目录"""
        # 点击顶部新增按钮
        await self.page.get_by_role('button', name='新增').first.click()

        # 等待对话框出现
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写表单
        await dialog.get_by_role('spinbutton', name='显示排序').fill(order_num)
        await dialog.get_by_role('textbox', name='菜单名称').fill(menu_name)
        await dialog.get_by_role('textbox', name='路由地址').fill(path)

        # 提交
        await dialog.get_by_role('button', name='确 定').click()

        # 验证成功提示
        await self.wait_for_selector("div:has-text('新增成功')", timeout=10000)

    async def search_menu(self, menu_name: str) -> None:
        """搜索菜单"""
        # 填写搜索条件
        # 使用 first 匹配搜索表单（通常在顶部），避免匹配到隐藏对话框中的同名字段
        await self.page.locator('form').first.get_by_role('textbox', name='菜单名称').fill(menu_name)
        await self.page.get_by_role('button', name='搜索').click()

        # 等待表格刷新（简单等待）
        await self.page.wait_for_timeout(1000)

    async def create_sub_menu(self, parent_name: str, menu_name: str, path: str, order_num: str) -> None:
        """在指定目录下创建子菜单"""
        # 找到父级菜单行
        row = self.page.locator('tbody tr').filter(has_text=parent_name).first

        # 点击行内新增按钮
        await row.get_by_role('button', name='新增').click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 选择菜单类型为"菜单"
        await dialog.locator('label').filter(has_text='菜单').first.click()

        # 填写表单
        await dialog.get_by_role('spinbutton', name='显示排序').fill(order_num)
        await dialog.get_by_role('textbox', name='菜单名称').fill(menu_name)
        await dialog.get_by_role('textbox', name='路由地址').fill(path)

        # 提交
        await dialog.get_by_role('button', name='确 定').click()

        # 验证成功
        await self.wait_for_selector("div:has-text('新增成功')", timeout=10000)

    async def edit_sub_menu(self, menu_name: str, new_path: str) -> None:
        """修改子菜单"""
        # 搜索子菜单
        await self.search_menu(menu_name)

        row = self.page.locator('tbody tr').filter(has_text=menu_name).first
        await row.get_by_role('button', name='修改').click()

        await self.wait_for_selector('.el-dialog', timeout=5000)
        dialog = self.page.locator('.el-dialog')

        await dialog.get_by_role('textbox', name='路由地址').fill(new_path)
        await self.page.get_by_role('button', name='确 定').click()

        await self.wait_for_selector("div:has-text('修改成功')", timeout=10000)

    async def delete_menus(self, menu_names: list[str]) -> None:
        """删除菜单（列表）"""
        for name in menu_names:
            await self.search_menu(name)
            row = self.page.locator('tbody tr').filter(has_text=name).first

            # 点击删除
            await row.get_by_role('button', name='删除').click()

            # 确认删除
            await self.page.get_by_role('button', name='确定').click()

            await self.wait_for_selector("div:has-text('删除成功')", timeout=10000)

    async def test_menu_crud_operations(self) -> None:
        """测试菜单增删改查流程"""
        data = self.generate_menu_data()

        # 1. 进入菜单管理页面
        await self.goto_page(Config.frontend_url + '/system/menu')
        await self.wait_for_page_title('菜单管理', timeout=10000)

        # 2. 新增目录
        await self.create_directory(data['dir_name'], data['path_dir'], data['order_num'])

        # 3. 搜索目录并新增子菜单
        await self.search_menu(data['dir_name'])
        await self.create_sub_menu(data['dir_name'], data['menu_name'], data['path_menu'], '1')

        # 4. 修改子菜单
        await self.edit_sub_menu(data['menu_name'], data['path_menu_new'])

        # 5. 删除子菜单
        await self.delete_menus([data['menu_name']])

        # 6. 删除目录
        await self.delete_menus([data['dir_name']])


@pytest.mark.asyncio
async def test_menu_management_page() -> None:
    """测试菜单管理页面功能"""
    async with async_playwright() as p:
        test_instance = MenuManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_menu_crud_operations()
        finally:
            await test_instance.teardown()
