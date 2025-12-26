import time

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class ConfigManagementTest(BasePageTest):
    """参数设置测试类"""

    def generate_config_data(self) -> dict:
        """生成测试数据"""
        timestamp = int(time.time())
        return {
            'config_name': f'test_config_{timestamp}',
            'config_key': f'test_config_key_{timestamp}',
            'config_value': f'test_config_value_{timestamp}',
        }

    async def create_config(self, config_name: str, config_key: str, config_value: str) -> None:
        """创建参数配置"""
        # 点击新增按钮
        await self.page.get_by_role('button', name='新增').first.click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写参数信息
        await dialog.get_by_role('textbox', name='参数名称').fill(config_name)
        await dialog.get_by_role('textbox', name='参数键名').fill(config_key)
        await dialog.get_by_role('textbox', name='参数键值').fill(config_value)

        # 等待一段时间确保输入完成
        await self.page.wait_for_timeout(500)

        # 选择参数状态 - 选择系统内置选项为N（否），避免后端限制删除
        # 在对话框中找到系统内置的单选按钮并选择
        await self.wait_for_selector('input[type="radio"]', timeout=5000)
        # 点击系统内置'否'选项
        # 根据codegen脚本，使用更精确的定位器
        await self.page.locator('label:nth-child(2) > .el-radio__input > .el-radio__inner').click()

        # 等待一段时间确保选择完成
        await self.page.wait_for_timeout(500)

        # 点击确认按钮
        confirm_button = self.page.get_by_role('button', name='确 定').first
        await confirm_button.click()

        # 等待一段时间确保请求发送
        await self.page.wait_for_timeout(1000)

        # 等待新增成功提示
        await self.wait_for_selector('div:has-text("新增成功")', timeout=10000)

    async def search_config(self, config_name: str, config_key: str = '') -> None:
        """搜索参数配置"""
        # 在查询表单中输入参数信息进行查询
        await self.page.get_by_role('textbox', name='参数名称').fill(config_name)
        if config_key:
            await self.page.get_by_role('textbox', name='参数键名').fill(config_key)

        # 点击搜索按钮
        await self.page.get_by_role('button', name='搜索').first.click()

        # 等待搜索结果加载
        await self.page.wait_for_timeout(1000)

    async def edit_config(self, updated_value: str) -> None:
        """编辑参数配置"""
        # 点击编辑按钮
        await self.page.locator('tbody').get_by_role('button', name='修改').nth(0).click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 修改参数键值
        await dialog.get_by_role('textbox', name='参数键值').fill(updated_value)

        # 确认
        await self.page.get_by_role('button', name='确 定').first.click()

        # 等待编辑成功提示
        await self.wait_for_selector('div:has-text("修改成功")', timeout=10000)

    async def delete_config(self) -> None:
        """删除参数配置"""
        # 点击删除按钮
        await self.page.locator('tbody').get_by_role('button', name='删除').nth(0).click()

        # 确认删除
        await self.page.get_by_role('button', name='确定').first.click()

        # 等待删除成功提示
        await self.wait_for_selector('div:has-text("删除成功")', timeout=10000)

        # 重置查询表单，确保能看到所有参数
        reset_button = self.page.get_by_role('button', name='重置')
        await reset_button.click()

        # 等待列表刷新
        await self.page.wait_for_timeout(1000)

    async def test_config_crud_operations(self) -> None:
        """测试参数设置的增删查改功能"""
        # 访问参数设置页面
        await self.goto_page(Config.frontend_url + '/system/config')

        # 等待页面加载完成
        await self.wait_for_page_title('参数设置', timeout=10000)
        await self.page.wait_for_timeout(1000)  # 等待列表刷新

        # 记录初始参数数量
        initial_config_count = await self.get_table_total_rows()

        # 生成测试数据
        data = self.generate_config_data()

        # 1.新增
        await self.create_config(data['config_name'], data['config_key'], data['config_value'])

        # 验证新增
        await self.page.wait_for_timeout(1000)  # 等待列表刷新
        new_config_count = await self.get_table_total_rows()
        assert new_config_count > initial_config_count, '新增参数后数量应该增加'

        # 2.搜索
        await self.search_config(data['config_name'], data['config_key'])

        # 验证搜索
        search_result_count = await self.get_table_total_rows()
        assert search_result_count >= 1, '搜索结果应该至少包含一个参数'

        # 3.编辑
        await self.edit_config(f'updated_config_value_{time.time()}')

        # 验证编辑
        await self.page.wait_for_timeout(1000)  # 等待列表刷新

        # 重新搜索以验证修改结果
        await self.search_config(data['config_name'])

        # 4.删除
        await self.delete_config()

        # 验证删除
        await self.page.wait_for_timeout(1000)  # 等待列表刷新
        final_config_count = await self.get_table_total_rows()
        assert final_config_count == initial_config_count, '删除参数后数量应该恢复到初始值'


@pytest.mark.asyncio
async def test_config_management_page() -> None:
    """测试参数设置页面功能"""
    async with async_playwright() as p:
        test_instance = ConfigManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_config_crud_operations()
        finally:
            await test_instance.teardown()
