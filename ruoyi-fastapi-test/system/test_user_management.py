import time

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class UserManagementTest(BasePageTest):
    """用户管理测试类"""

    def generate_user_data(self) -> dict:
        """生成测试数据"""
        timestamp = int(time.time())
        return {
            'user_name': f'test_{timestamp}',
            'nick_name': f'测试用户_{timestamp}',
            'phone': '13888888888',
        }

    async def create_user(self, user_name: str, nick_name: str, phone: str) -> None:
        """创建用户"""
        # 点击新增按钮
        await self.page.get_by_role('button', name='新增').click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写基本信息
        await dialog.get_by_role('textbox', name='用户昵称').fill(nick_name)

        # 归属部门
        # 使用 label 定位父级 form-item，再点击内部的 wrapper
        await dialog.locator('div.el-form-item').filter(has_text='归属部门').locator('.el-select__wrapper').click()
        # 选择 "集团总公司" (根节点)
        # 使用 .el-popper 定位下拉框中的内容
        await self.page.locator('.el-popper:visible').get_by_text('集团总公司').click()

        await dialog.get_by_role('textbox', name='用户名称').fill(user_name)
        # 手机号码在搜索框也有，所以必须限定在 dialog 内
        # 注意：有些 label 可能不带 *，或者带 * 但 get_by_role 需要准确匹配
        # 这里使用 get_by_placeholder 或者 filter 来定位更稳妥，或者直接 scope 到 dialog
        await dialog.locator('div.el-form-item').filter(has_text='手机号码').get_by_role('textbox').fill(phone)
        await dialog.locator('div.el-form-item').filter(has_text='邮箱').get_by_role('textbox').fill('test@example.com')
        await dialog.locator('div.el-form-item').filter(has_text='用户密码').get_by_role('textbox').fill('123456')

        # 用户性别
        # 定位 label 为 "用户性别" 的父级 form-item，然后找里面的 "请选择" 文本
        await dialog.locator('div.el-form-item').filter(has_text='用户性别').get_by_text('请选择').click()
        await self.page.get_by_role('option', name='男').click()

        # 岗位
        await dialog.locator('div.el-form-item').filter(has_text='岗位').get_by_text('请选择').click()
        await self.page.get_by_role('option', name='董事长').click()

        # 角色
        await dialog.locator('div.el-form-item').filter(has_text='角色').get_by_text('请选择').click()
        await self.page.get_by_role('option', name='普通角色').click()

        await dialog.locator('div.el-form-item').filter(has_text='备注').get_by_role('textbox').fill('测试用户')

        # 点击确定
        await self.page.get_by_role('button', name='确 定').click()
        # 等待成功消息
        await self.wait_for_selector("div:has-text('成功')", timeout=10000)

    async def search_user(self, user_name: str) -> None:
        """搜索用户"""
        search_form = self.page.locator('form').first
        await search_form.get_by_role('textbox', name='用户名称').fill(user_name)
        await search_form.get_by_role('button', name='搜索').click()

        # 等待加载
        await self.page.wait_for_timeout(1000)

    async def edit_user(self) -> None:
        """编辑用户"""
        # 点击修改按钮 (第一行)
        row = self.page.locator('tbody tr').first
        await row.get_by_role('button').nth(0).click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 修改性别为女
        await dialog.locator('div.el-form-item').filter(has_text='用户性别').locator('.el-select').click()
        await self.page.get_by_role('option', name='女').click()

        # 确定
        await self.page.get_by_role('button', name='确 定').click()

        # 等待成功提示
        await self.wait_for_selector('div:has-text("修改成功")', timeout=10000)

    async def change_user_status(self) -> None:
        """修改用户状态"""
        # 点击开关 (第一行)
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

    async def delete_user(self) -> None:
        """删除用户"""
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

    async def test_user_crud_operations(self) -> None:
        """测试用户管理增删查改"""
        # 访问页面
        await self.goto_page(Config.frontend_url + '/system/user')
        await self.wait_for_page_title('用户管理', timeout=10000)

        # 生成测试数据
        data = self.generate_user_data()

        # 1. 新增
        await self.create_user(data['user_name'], data['nick_name'], data['phone'])

        # 验证新增结果
        await self.search_user(data['user_name'])
        rows = await self.get_table_total_rows()
        assert rows >= 1, '新增后搜索应有结果'

        # 2. 修改状态
        await self.change_user_status()

        # 3. 编辑
        await self.edit_user()

        # 4. 删除
        await self.delete_user()

        # 验证删除结果
        await self.search_user(data['user_name'])
        rows_after = await self.get_table_total_rows()
        assert rows_after == 0, '删除后搜索应无结果'


@pytest.mark.asyncio
async def test_user_management_page() -> None:
    """测试用户管理页面功能"""
    async with async_playwright() as p:
        test_instance = UserManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_user_crud_operations()
        finally:
            await test_instance.teardown()
