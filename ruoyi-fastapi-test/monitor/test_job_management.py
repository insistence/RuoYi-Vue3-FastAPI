from datetime import datetime

import pytest
from playwright.async_api import async_playwright

from common.base_page_test import BasePageTest
from common.config import Config


class JobManagementTest(BasePageTest):
    """定时任务管理测试"""

    def generate_job_data(self) -> dict:
        """生成测试数据"""
        timestamp = datetime.now().strftime('%H%M%S')
        return {
            'job_name': f'测试任务_{timestamp}',
            'job_group': '默认',
            'job_executor': '进程池',
            'invoke_target': 'module_task.scheduler_test.job',  # 必须为这个值
            'cron_expression': '0/2 * * * * ?',  # 每2秒执行一次
            'new_invoke_target': 'module_task.scheduler_test.job',  # 修改时也用这个
            'job_name_edit': f'测试任务_{timestamp}_edit',
        }

    async def create_job(
        self, job_name: str, job_group: str, job_executor: str, invoke_target: str, cron_expression: str
    ) -> None:
        """创建定时任务"""
        await self.page.get_by_role('button', name='新增').click()

        # 等待对话框
        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 填写表单
        await dialog.get_by_role('textbox', name='任务名称').fill(job_name)

        # 选择任务分组
        await dialog.locator("label:has-text('任务分组') + div .el-select").click()
        await self.page.get_by_role('option', name=job_group).click()

        # 选择任务执行器
        await dialog.locator("label:has-text('任务执行器') + div .el-select").click()
        await self.page.get_by_role('option', name=job_executor).click()

        # 填写调用方法
        await dialog.get_by_role('textbox', name='调用方法').fill(invoke_target)

        # 填写cron表达式
        await dialog.get_by_role('textbox', name='cron表达式').fill(cron_expression)

        # 策略：如果"失败"策略等有默认值，就不管了

        await dialog.get_by_role('button', name='确 定').click()
        await self.wait_for_selector("div:has-text('新增成功')", timeout=10000)

    async def search_job(self, job_name: str) -> None:
        """搜索任务"""
        # 我们可以限制在 form 里搜索
        form = self.page.locator('form').first
        await form.get_by_role('textbox', name='任务名称').fill(job_name)
        await self.page.get_by_role('button', name='搜索').click()
        await self.page.wait_for_timeout(1000)  # 等待搜索结果

    async def edit_job(self, job_name: str, new_invoke_target: str) -> None:
        """修改任务"""
        await self.search_job(job_name)

        # 点击修改 (在操作列)
        row = self.page.locator('tbody tr').first
        # 操作列按钮顺序: 修改, 删除, 执行一次, 详细, 日志
        await row.locator('button').nth(0).click()

        dialog = self.page.get_by_role('dialog')
        await dialog.wait_for()

        # 修改调用方法
        await dialog.get_by_role('textbox', name='调用方法').fill(new_invoke_target)

        await dialog.get_by_role('button', name='确 定').click()
        await self.wait_for_selector("div:has-text('修改成功')", timeout=10000)

    async def toggle_job_status(self, job_name: str) -> None:
        """切换任务状态"""
        await self.search_job(job_name)

        row = self.page.locator('tbody tr').first
        # 切换开关
        # 需要点击可见的 .el-switch 或 .el-switch__core
        await row.locator('.el-switch').click()

        # 确认切换
        await self.page.get_by_role('button', name='确定').click()
        await self.page.wait_for_timeout(1000)
        await self.wait_for_selector("div:has-text('成功')", timeout=10000)

    async def run_job_once(self, job_name: str) -> None:
        """执行一次任务"""
        await self.search_job(job_name)

        row = self.page.locator('tbody tr').first
        # 点击执行一次 (第3个按钮)
        await row.locator('button').nth(2).click()

        # 确认执行
        await self.page.get_by_role('button', name='确定').click()
        await self.wait_for_selector("div:has-text('执行成功')", timeout=10000)

    async def view_job_log(self, job_name: str) -> None:
        """查看调度日志"""
        # 可以点击顶部的 "日志" 按钮，也可以点击行的 "调度日志"
        # 我们点击行的 "调度日志" (icon="Operation")
        await self.search_job(job_name)
        row = self.page.locator('tbody tr').first

        log_btn = row.locator('button').nth(4)
        await log_btn.click()

        # 等待跳转到日志页面 (实际上是 router push 到 /monitor/job-log)
        # 检查 URL
        await self.page.wait_for_url('**/monitor/job-log**')

        # 验证在日志页面
        await self.wait_for_selector('text=调度日志')

        # 关闭返回 (点击 "关闭" 按钮)
        await self.page.get_by_role('button', name='关闭').click()

        # 等待返回任务列表
        await self.page.wait_for_url('**/monitor/job')

    async def delete_job(self, job_name: str) -> None:
        """删除任务"""
        await self.search_job(job_name)

        row = self.page.locator('tbody tr').first
        # 点击删除 (第2个按钮)
        await row.locator('button').nth(1).click()

        # 确认删除
        await self.page.get_by_role('button', name='确定').click()
        await self.wait_for_selector("div:has-text('删除成功')", timeout=10000)

    async def test_job_crud_operations(self) -> None:
        """测试定时任务管理全流程"""
        data = self.generate_job_data()

        # 1. 进入定时任务页面
        await self.goto_page(Config.frontend_url + '/monitor/job')
        await self.wait_for_selector('text=任务名称')

        # 2. 创建任务
        await self.create_job(
            data['job_name'], data['job_group'], data['job_executor'], data['invoke_target'], data['cron_expression']
        )

        # 3. 修改任务 (修改调用方法)
        await self.edit_job(data['job_name'], data['new_invoke_target'])

        # 4. 切换状态 (开启/关闭)
        await self.toggle_job_status(data['job_name'])  # 开启
        await self.page.wait_for_timeout(1000)
        await self.toggle_job_status(data['job_name'])  # 关闭

        # 5. 执行一次
        await self.run_job_once(data['job_name'])

        # 6. 查看日志
        await self.view_job_log(data['job_name'])

        # 7. 删除任务
        await self.delete_job(data['job_name'])


@pytest.mark.asyncio
async def test_job_management_page() -> None:
    """测试定时任务管理页面功能"""
    async with async_playwright() as p:
        test_instance = JobManagementTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_job_crud_operations()
        finally:
            await test_instance.teardown()
