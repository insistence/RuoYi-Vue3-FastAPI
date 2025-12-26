import re
import time

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class NoticeManagementTest(BasePageTest):
    """通知公告管理测试类"""

    def generate_notice_data(self) -> dict:
        """生成测试数据"""
        timestamp = int(time.time())
        return {
            'notice_title': f'test_notice_{timestamp}',
            'updated_title': f'updated_notice_{timestamp}',
        }

    async def create_notice(self, notice_title: str, notice_type: int = 1, notice_content: str = '测试内容') -> None:
        """创建通知公告"""
        # 点击新增按钮
        await self.page.get_by_role('button', name='新增').first.click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写公告信息
        await dialog.get_by_role('textbox', name='公告标题').fill(notice_title)

        # 选择公告类型
        # 根据codegen脚本，点击下拉框触发器
        await self.page.locator('div').filter(has_text=re.compile(r'^请选择$')).nth(4).click()
        # 选择对应类型选项，1为通知，2为公告
        if notice_type == 1:
            await self.page.get_by_role('option', name='通知').click()
        else:
            await self.page.get_by_role('option', name='公告').click()

        # 填写公告内容
        await self.page.locator('.ql-container').click()
        await self.page.locator('.ql-editor').fill(notice_content)

        # 等待一段时间确保输入完成
        await self.page.wait_for_timeout(500)

        # 点击确认按钮
        await self.page.get_by_role('button', name='确 定').first.click()

        # 等待一段时间确保请求发送
        await self.page.wait_for_timeout(1000)

        # 等待新增成功提示
        await self.wait_for_selector('div:has-text("新增成功")', timeout=10000)

    async def search_notice(self, notice_title: str) -> None:
        """搜索通知公告"""
        # 在查询表单中输入公告标题进行查询
        await self.page.get_by_role('textbox', name='公告标题').fill(notice_title)

        # 点击搜索按钮
        await self.page.get_by_role('button', name='搜索').first.click()

        # 等待搜索结果加载
        await self.page.wait_for_timeout(1000)

    async def edit_notice(self, updated_title: str, updated_content: str = '更新的测试内容') -> None:
        """编辑通知公告"""
        # 点击编辑按钮
        await self.page.locator('tbody').get_by_role('button', name='修改').nth(0).click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 修改公告标题
        await dialog.get_by_role('textbox', name='公告标题').fill(updated_title)

        # 修改公告内容
        await self.page.locator('.ql-editor').fill(updated_content)

        # 点击确认按钮
        await self.page.get_by_role('button', name='确 定').first.click()

        # 等待编辑成功提示
        await self.wait_for_selector('div:has-text("修改成功")', timeout=10000)

    async def delete_notice(self) -> None:
        """删除通知公告"""
        # 点击删除按钮
        await self.page.locator('tbody').get_by_role('button', name='删除').nth(0).click()

        # 确认删除
        await self.page.get_by_role('button', name='确定').first.click()

        # 等待删除成功提示
        await self.wait_for_selector('div:has-text("删除成功")', timeout=10000)

        # 重置查询表单，确保能看到所有公告
        await self.page.get_by_role('button', name='重置').click()

        # 等待列表刷新
        await self.page.wait_for_timeout(1000)

    async def test_notice_crud_operations(self) -> None:
        """测试通知公告的增删查改功能"""
        # 访问通知公告页面
        await self.goto_page(Config.frontend_url + '/system/notice')

        # 等待页面加载完成
        await self.wait_for_page_title('通知公告', timeout=10000)
        await self.page.wait_for_timeout(1000)  # 等待列表刷新

        # 记录初始公告数量
        initial_notice_count = await self.get_table_total_rows()

        # 生成测试数据
        data = self.generate_notice_data()

        # 创建公告
        await self.create_notice(data['notice_title'])

        # 验证公告已添加到列表中
        await self.page.wait_for_timeout(1000)  # 等待列表刷新
        new_notice_count = await self.get_table_total_rows()
        assert new_notice_count > initial_notice_count, '新增公告后数量应该增加'

        # 搜索公告
        await self.search_notice(data['notice_title'])

        # 验证搜索结果中包含新增的公告
        search_result_count = await self.get_table_total_rows()
        assert search_result_count >= 1, '搜索结果应该至少包含一个公告'

        # 编辑公告
        await self.edit_notice(data['updated_title'])

        # 验证编辑成功
        await self.page.wait_for_timeout(1000)  # 等待列表刷新

        # 重新搜索以验证修改结果
        await self.search_notice(data['updated_title'])

        # 删除公告
        await self.delete_notice()

        # 验证公告已从列表中删除
        await self.page.wait_for_timeout(1000)  # 等待列表刷新
        final_notice_count = await self.get_table_total_rows()
        assert final_notice_count == initial_notice_count, '删除公告后数量应该恢复到初始值'


@pytest.mark.asyncio
async def test_notice_management_page() -> None:
    """测试通知公告页面功能"""
    async with async_playwright() as p:
        test_instance = NoticeManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_notice_crud_operations()
        finally:
            await test_instance.teardown()
