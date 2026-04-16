from datetime import datetime

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class DictManagementTest(BasePageTest):
    """字典管理测试类"""

    def generate_dict_data(self) -> dict:
        """生成测试数据"""
        timestamp = datetime.now().strftime('%H%M%S')
        return {
            'dict_name': f'测试字典_{timestamp}',
            'dict_type': f'test_dict_{timestamp}',
            'dict_data_label_1': '正常',
            'dict_data_value_1': '1',
            'dict_data_label_2': '异常',
            'dict_data_value_2': '2',
            'remark': f'备注_{timestamp}',
        }

    async def create_dict_type(self, dict_name: str, dict_type: str) -> None:
        """创建字典类型"""
        # 点击新增按钮
        await self.page.get_by_role('button', name='新增').first.click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写表单
        await dialog.get_by_role('textbox', name='字典名称').fill(dict_name)
        await dialog.get_by_role('textbox', name='字典类型').fill(dict_type)

        # 提交
        await dialog.get_by_role('button', name='确 定').click()

        # 验证成功
        await self.wait_for_selector("div:has-text('新增成功')", timeout=10000)

    async def search_dict_type(self, dict_name: str, dict_type: str) -> None:
        """搜索字典类型"""
        form = self.page.locator('form').first
        await form.get_by_role('textbox', name='字典名称').fill(dict_name)
        await form.get_by_role('textbox', name='字典类型').fill(dict_type)
        # 点击搜索按钮
        await self.page.get_by_role('button', name='搜索').click()
        await self.page.wait_for_timeout(1000)

    async def edit_dict_type(self, dict_name: str, remark: str) -> None:
        """修改字典类型"""
        await self.search_dict_type(dict_name, '')

        # 点击修改按钮
        row = self.page.locator('tbody tr').first
        await row.get_by_role('button', name='修改').click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        await dialog.get_by_role('textbox', name='备注').fill(remark)
        await dialog.get_by_role('button', name='确 定').click()

        await self.wait_for_selector("div:has-text('修改成功')", timeout=10000)

    async def manage_dict_data(self, dict_type: str, data: dict) -> None:
        """管理字典数据"""
        # 1. 进入字典数据页面
        # 点击字典类型链接
        row = self.page.locator('tbody tr').first
        await row.get_by_role('link', name=dict_type).click()

        # 等待页面切换（Playwright在SPA中通常不需要处理多标签页，除非新开tab）
        # 这里是 router-link，应该是页内跳转
        # 检查是否到了字典数据页面
        # 或者等待URL变化，或者等待特定元素
        # data.vue 有 "关闭" 按钮
        await self.wait_for_selector("button:has-text('关闭')", timeout=5000)

        # 2. 新增数据1 (正常)
        await self.create_dict_data(data['dict_data_label_1'], data['dict_data_value_1'], '1', '主要(primary)')

        # 3. 新增数据2 (异常)
        await self.create_dict_data(data['dict_data_label_2'], data['dict_data_value_2'], '2', '危险(danger)')

        # 4. 修改数据
        await self.edit_dict_data(data['dict_data_label_2'], '测试备注')

        # 5. 删除数据
        await self.delete_dict_data(data['dict_data_label_2'])
        await self.delete_dict_data(data['dict_data_label_1'])

        # 6. 关闭页面 (返回字典类型)
        await self.page.get_by_role('button', name='关闭', exact=True).click()
        # 等待返回
        await self.wait_for_selector('text=字典名称')  # 假设返回后能看到原来的页面元素

    async def create_dict_data(self, label: str, value: str, sort: str, list_class: str) -> None:
        """创建字典数据"""
        # 点击新增按钮
        await self.page.get_by_role('button', name='新增').first.click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        await dialog.get_by_role('textbox', name='数据标签').fill(label)
        await dialog.get_by_role('textbox', name='数据键值').fill(value)
        await dialog.get_by_role('spinbutton', name='显示排序').fill(sort)

        # 选择回显样式
        # 点击下拉框触发器
        # el-select 的结构通常是 wrapper -> input (readonly)
        # 我们可以点击 label 为 "回显样式" 的 form-item 下的 select
        select_trigger = dialog.locator("label:has-text('回显样式') + div .el-select")
        if await select_trigger.count() == 0:
            # 尝试直接找 .el-select，可能布局不同
            select_trigger = dialog.locator('.el-select').filter(has_text='默认(default)').first

        # 如果还是找不到，尝试点击那个默认值文本
        if await select_trigger.count() == 0:
            await dialog.get_by_text('默认(default)').click()
        else:
            await select_trigger.click()

        # 选择选项 (选项在 body 的 el-popper 中)
        # 等待选项出现
        await self.page.get_by_role('option', name=list_class).click()

        await dialog.get_by_role('button', name='确 定').click()
        await self.wait_for_selector("div:has-text('新增成功')", timeout=10000)

    async def edit_dict_data(self, label: str, remark: str) -> None:
        """修改字典数据"""
        # 点击修改按钮
        row = self.page.locator('tbody tr').filter(has_text=label).first
        await row.get_by_role('button', name='修改').click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        await dialog.get_by_role('textbox', name='备注').fill(remark)
        await dialog.get_by_role('button', name='确 定').click()

        await self.wait_for_selector("div:has-text('修改成功')", timeout=10000)

    async def delete_dict_data(self, label: str) -> None:
        """删除字典数据"""
        # 点击删除按钮
        row = self.page.locator('tbody tr').filter(has_text=label).first
        await row.get_by_role('button', name='删除').click()

        await self.page.get_by_role('button', name='确定').click()
        await self.wait_for_selector("div:has-text('删除成功')", timeout=10000)

    async def delete_dict_type(self, dict_name: str) -> None:
        """删除字典类型"""
        await self.search_dict_type(dict_name, '')

        # 点击删除按钮
        row = self.page.locator('tbody tr').filter(has_text=dict_name).first
        await row.get_by_role('button', name='删除').click()

        await self.page.get_by_role('button', name='确定').click()
        await self.wait_for_selector("div:has-text('删除成功')", timeout=10000)

    async def test_dict_crud_operations(self) -> None:
        """测试字典管理全流程"""
        data = self.generate_dict_data()

        # 1. 进入字典管理
        await self.goto_page(Config.frontend_url + '/system/dict')
        # 等待页面加载
        await self.wait_for_selector('text=字典名称')  # 页面标题或其他标识

        # 2. 创建字典类型
        await self.create_dict_type(data['dict_name'], data['dict_type'])

        # 3. 搜索并修改
        await self.edit_dict_type(data['dict_name'], data['remark'])

        # 4. 管理字典数据
        await self.manage_dict_data(data['dict_type'], data)

        # 5. 删除字典类型
        await self.delete_dict_type(data['dict_name'])


@pytest.mark.asyncio
async def test_dict_management_page() -> None:
    """测试字典管理页面功能"""
    async with async_playwright() as p:
        test_instance = DictManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_dict_crud_operations()
        finally:
            await test_instance.teardown()
