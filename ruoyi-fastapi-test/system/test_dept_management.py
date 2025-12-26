import time

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class DeptManagementTest(BasePageTest):
    """部门管理页面测试类"""

    def generate_dept_data(self) -> dict:
        """生成测试数据"""
        timestamp = int(time.time())
        return {
            'dept_name': f'测试部门_{timestamp}',
            'order_num': '3',
            'leader_name': '年糕',
        }

    async def create_dept(self, dept_name: str, order_num: str) -> None:
        """创建部门"""
        # 点击新增按钮
        await self.page.get_by_role('button', name='新增').first.click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 上级部门
        # 使用 label 定位父级 form-item，再点击内部的 wrapper
        await dialog.locator('div.el-form-item').filter(has_text='上级部门').locator('.el-select__wrapper').click()
        # 选择 "集团总公司" (根节点)
        # 使用 .el-popper 定位下拉框中的内容
        await self.page.locator('.el-popper:visible').get_by_text('集团总公司').click()

        # 填写部门名称
        await dialog.get_by_role('textbox', name='部门名称').fill(dept_name)

        # 填写显示排序
        # el-input-number 通常是一个 spinbutton 或者 input
        await dialog.get_by_role('spinbutton', name='显示排序').fill(order_num)

        # 点击确定
        await self.page.get_by_role('button', name='确 定').click()
        # 等待成功消息
        await self.wait_for_selector("div:has-text('成功')", timeout=10000)

    async def search_dept(self, dept_name: str) -> None:
        """搜索部门"""
        search_form = self.page.locator('form').first
        await search_form.get_by_role('textbox', name='部门名称').fill(dept_name)
        # 点击搜索按钮
        await self.page.get_by_role('button', name='搜索').first.click()

        # 等待加载
        await self.page.wait_for_timeout(1000)

    async def edit_dept(self, leader_name: str) -> None:
        """编辑部门"""
        # 点击修改按钮 (第一行)
        # 树形表格结构可能不同，但通常也是在 tbody 的 row 中
        await self.page.locator('tbody').get_by_role('button', name='修改').nth(0).click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 修改负责人
        await dialog.get_by_role('textbox', name='负责人').fill(leader_name)

        # 确定
        await self.page.get_by_role('button', name='确 定').click()

        # 等待成功提示
        await self.wait_for_selector('div:has-text("修改成功")', timeout=10000)

    async def delete_dept(self) -> None:
        """删除部门"""
        # 点击删除按钮
        await self.page.locator('tbody').get_by_role('button', name='删除').nth(0).click()

        # 确认删除
        await self.page.get_by_role('button', name='确定').click()

        # 等待成功提示
        await self.wait_for_selector('div:has-text("删除成功")', timeout=10000)

        # 重置搜索
        await self.page.get_by_role('button', name='重置').click()
        await self.page.wait_for_timeout(1000)

    async def test_dept_crud_operations(self) -> None:
        """测试部门管理增删查改"""
        # 访问页面
        await self.goto_page(Config.frontend_url + '/system/dept')
        await self.wait_for_page_title('部门管理', timeout=10000)

        # 生成测试数据
        data = self.generate_dept_data()

        # 1. 新增
        await self.create_dept(data['dept_name'], data['order_num'])

        # 验证新增
        await self.search_dept(data['dept_name'])
        # 树形表格，只要有行显示即可
        rows = await self.page.query_selector_all('.el-table__row')
        assert len(rows) >= 1, '新增后搜索应有结果'

        # 2. 编辑
        await self.edit_dept(data['leader_name'])

        # 重新搜索以验证修改结果
        await self.search_dept(data['dept_name'])

        # 3. 删除
        await self.delete_dept()

        # 验证删除
        await self.search_dept(data['dept_name'])
        rows_after = await self.page.query_selector_all('.el-table__row')
        assert len(rows_after) == 0, '删除后搜索应无结果'


@pytest.mark.asyncio
async def test_dept_management_page() -> None:
    """测试部门管理页面功能"""
    async with async_playwright() as p:
        test_instance = DeptManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_dept_crud_operations()
        finally:
            await test_instance.teardown()
