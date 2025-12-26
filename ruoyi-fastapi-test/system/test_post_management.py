from datetime import datetime

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class PostManagementTest(BasePageTest):
    """岗位管理测试类"""

    def generate_post_data(self) -> dict:
        """生成测试数据"""
        timestamp = datetime.now().strftime('%H%M%S')
        return {
            'post_name': f'测试岗位_{timestamp}',
            'post_code': f'test_{timestamp}',
            'post_sort': '10',
            'remark': f'测试备注_{timestamp}',
        }

    async def test_post_crud_operations(self) -> None:
        """测试岗位增删改查流程"""
        # 1. 导航到岗位管理页面
        await self.navigate_to_post_management()

        # 生成测试数据
        data = self.generate_post_data()

        # 2. 新增岗位
        await self.create_post(data['post_name'], data['post_code'], data['post_sort'])

        # 3. 搜索岗位
        await self.search_post(data['post_name'], data['post_code'])

        # 4. 修改岗位
        await self.edit_post(data['post_name'], data['remark'])

        # 5. 删除岗位
        await self.delete_post(data['post_name'])

    async def navigate_to_post_management(self) -> None:
        """导航到岗位管理"""
        # 直接导航到岗位管理页面
        await self.goto_page(Config.frontend_url + '/system/post')
        # 等待页面加载
        await self.wait_for_selector('.app-container')

    async def create_post(self, post_name: str, post_code: str, post_sort: str) -> None:
        """新增岗位"""
        await self.page.get_by_role('button', name='新增').click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写表单
        # 注意：Element Plus 表单必填项可能有 * 号，Label 匹配可能需要注意
        await dialog.get_by_role('textbox', name='岗位名称').fill(post_name)
        await dialog.get_by_role('textbox', name='岗位编码').fill(post_code)

        # 岗位顺序是 input-number
        # script.py 使用 spinbutton
        await dialog.get_by_role('spinbutton', name='岗位顺序').fill(post_sort)

        await dialog.get_by_role('button', name='确 定').click()

        # 等待成功提示
        await self.wait_for_selector("div:has-text('新增成功')", timeout=10000)

    async def search_post(self, post_name: str, post_code: str) -> None:
        """搜索岗位"""
        # 填写搜索表单
        # 限定在搜索区域，防止定位到弹窗或其他地方（虽然此时没有弹窗）
        search_form = self.page.locator('.el-form').first

        await search_form.get_by_role('textbox', name='岗位编码').fill(post_code)
        await search_form.get_by_role('textbox', name='岗位名称').fill(post_name)

        await self.page.get_by_role('button', name='搜索').click()

        # 等待表格加载结果
        # 验证表格中包含刚创建的岗位
        await self.wait_for_selector(f"tbody tr:has-text('{post_name}')", timeout=10000)

    async def edit_post(self, post_name: str, remark: str) -> None:
        """修改岗位"""
        # 确保当前显示的是我们要修改的岗位
        await self.search_post(post_name, '')

        row = self.page.locator('tbody tr').first
        # 点击修改按钮
        await row.get_by_role('button', name='修改').click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 修改备注
        await dialog.get_by_role('textbox', name='备注').fill(remark)

        await dialog.get_by_role('button', name='确 定').click()

        # 等待成功提示
        await self.wait_for_selector("div:has-text('修改成功')", timeout=10000)

    async def delete_post(self, post_name: str) -> None:
        """删除岗位"""
        # 确保当前显示的是我们要删除的岗位
        search_form = self.page.locator('.el-form').first
        await search_form.get_by_role('textbox', name='岗位编码').clear()
        await search_form.get_by_role('textbox', name='岗位名称').fill(post_name)
        await self.page.get_by_role('button', name='搜索').click()

        await self.wait_for_selector(f"tbody tr:has-text('{post_name}')", timeout=10000)

        row = self.page.locator('tbody tr').first
        # 点击删除按钮
        await row.get_by_role('button', name='删除').click()

        # 确认删除
        await self.page.get_by_role('button', name='确定').click()

        # 等待成功提示
        await self.wait_for_selector("div:has-text('删除成功')", timeout=10000)


@pytest.mark.asyncio
async def test_post_management_page() -> None:
    """测试岗位管理页面功能"""
    async with async_playwright() as p:
        test_instance = PostManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_post_crud_operations()
        finally:
            await test_instance.teardown()
