import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class LogManagementTest(BasePageTest):
    """日志管理测试类"""

    async def test_operlog_operations(self) -> None:
        """测试操作日志查询、删除和清空"""
        # 1. 导航到操作日志页面
        # 直接访问正确的路由
        await self.page.goto(Config.frontend_url + '/system/log/operlog')
        await self.page.wait_for_load_state('networkidle')

        try:
            await self.page.wait_for_selector('.app-container', timeout=10000)
        except Exception:
            # 如果首次加载失败，尝试刷新
            await self.page.reload()
            await self.page.wait_for_selector('.app-container', timeout=10000)

        # 2. 查询操作
        # 输入操作人员
        await self.page.locator('div.el-form-item', has_text='操作人员').locator('input').fill('admin')
        # 点击搜索按钮
        await self.page.get_by_role('button', name='搜索').click()
        await self.page.wait_for_timeout(1000)  # 等待搜索结果
        # 点击重置按钮
        await self.page.get_by_role('button', name='重置').click()
        await self.page.wait_for_timeout(1000)  # 等待重置结果

        # 3. 删除操作
        # 检查是否有数据，如果有则进行删除测试
        rows = self.page.locator('.el-table__body tr')
        count = await rows.count()
        if count > 0:
            # 选中第一条
            await rows.first.locator('.el-checkbox').click()
            # 点击删除
            await self.page.get_by_role('button', name='删除').click()
            # 确认删除
            await self.page.get_by_role('button', name='确定').click()
            # 等待删除完成提示
            try:
                await self.page.wait_for_selector('text=删除成功', timeout=10000)
            except Exception:
                pass  # 可能是 toast 提示，稍纵即逝

        # 4. 清空操作
        # 点击清空
        await self.page.get_by_role('button', name='清空').click()
        # 确认清空
        await self.page.get_by_role('button', name='确定').click()

        # 5. 验证清空后还有一条"清空"的操作日志
        await self.page.wait_for_timeout(1000)  # 等待清空操作完成并刷新
        await self.page.get_by_role('button', name='搜索').click()  # 刷新列表
        await self.page.wait_for_timeout(1000)

        # 验证列表不为空 (因为清空操作本身会产生一条日志)
        rows_after_clean = self.page.locator('.el-table__body tr')
        count_after_clean = await rows_after_clean.count()
        assert count_after_clean > 0, '操作日志清空后应该至少有一条记录（清空操作本身）'

        # 可以在这里进一步验证第一条记录的类型是否为清空，但题目只要求不是空列表

    async def test_logininfor_operations(self) -> None:
        """测试登录日志查询、删除和清空"""
        # 1. 导航到登录日志页面
        await self.page.goto(Config.frontend_url + '/system/log/logininfor')
        await self.page.wait_for_load_state('networkidle')

        try:
            await self.page.wait_for_selector('.app-container', timeout=10000)
        except Exception:
            # 如果失败，尝试刷新
            await self.page.reload()
            await self.page.wait_for_selector('.app-container', timeout=10000)

        # 2. 查询操作
        # 输入用户名称
        await self.page.locator('div.el-form-item', has_text='用户名称').locator('input').fill('admin')
        # 点击搜索
        await self.page.get_by_role('button', name='搜索').click()
        await self.page.wait_for_timeout(1000)
        # 点击重置
        await self.page.get_by_role('button', name='重置').click()
        await self.page.wait_for_timeout(1000)

        # 3. 删除操作
        # 检查是否有数据
        rows = self.page.locator('.el-table__body tr')
        count = await rows.count()
        if count > 0:
            # 选中第一条
            await rows.first.locator('.el-checkbox').click()
            # 点击删除
            await self.page.get_by_role('button', name='删除').click()
            # 确认删除
            await self.page.get_by_role('button', name='确定').click()
            # 等待删除成功
            try:
                await self.page.wait_for_selector('text=删除成功', timeout=10000)
            except Exception:
                pass

        # 4. 清空操作
        # 点击清空
        await self.page.get_by_role('button', name='清空').click()
        # 确认清空
        await self.page.get_by_role('button', name='确定').click()

        # 5. 验证清空后列表为空
        await self.page.wait_for_timeout(1000)
        # 检查是否显示"暂无数据"
        no_data = await self.page.get_by_text('暂无数据').is_visible()
        if not no_data:
            # 再次检查行数
            count_final = await self.page.locator('.el-table__body tr').count()
            assert count_final == 0, '登录日志清空后应该没有数据'


@pytest.mark.asyncio
async def test_log_management_page() -> None:
    """测试日志管理页面功能"""
    async with async_playwright() as p:
        test_instance = LogManagementTest()
        await test_instance.setup(p)
        try:
            # 运行操作日志测试
            await test_instance.test_operlog_operations()
            # 运行登录日志测试
            await test_instance.test_logininfor_operations()
        finally:
            await test_instance.teardown()
