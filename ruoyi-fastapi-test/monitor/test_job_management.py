import asyncio
import re
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from time import monotonic
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from playwright.async_api import Locator, expect

from common.base_page_test import BasePageTest
from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


class JobManagementTest(BasePageTest):
    """通过真实界面验证任务配置、异步同步和手动执行。"""

    job_id: int | None = None

    def job_row(self, job_name: str) -> Locator:
        return self.page.locator('.app-container:visible > .el-table .el-table__body-wrapper tbody tr').filter(
            has=self.page.get_by_text(job_name, exact=True)
        )

    def job_actions(self, job_name: str) -> Locator:
        """Element UI 固定列有隐藏副本，仅返回操作列中实际可见的按钮。"""
        rows = self.page.locator('.app-container:visible > .el-table tbody tr').filter(
            has=self.page.get_by_text(job_name, exact=True)
        )
        return rows.locator('td:last-child').get_by_role('button')

    async def submit(self, action: Callable[[], Awaitable], method: str, path: str) -> dict:
        """等待本次操作的响应，不依赖短暂提示或固定延时。"""
        async with self.page.expect_response(
            lambda response: response.request.method == method and urlparse(response.url).path.endswith(path)
        ) as response_info:
            await action()
        response = await response_info.value
        assert response.status == HTTPStatus.OK, await response.text()
        payload = await response.json()
        assert payload['code'] == HTTPStatus.OK, payload
        return payload['data']

    async def poll_api(self, path: str, ready: Callable[[dict], bool], **params) -> dict:
        """轮询异步结果，超时时保留最后一次响应以便诊断。"""
        deadline = monotonic() + 30
        while True:
            response = await self.context.request.get(
                Config.backend_url + path,
                params=params,
                headers={'Authorization': f'Bearer {self.token}'},
            )
            assert response.status == HTTPStatus.OK, await response.text()
            payload = await response.json()
            assert payload['code'] == HTTPStatus.OK, payload
            if ready(payload):
                return payload
            assert monotonic() < deadline, f'{path} 未达到预期状态: {payload}'
            await asyncio.sleep(0.25)

    async def wait_for_sync(self, mutation: dict) -> None:
        """已保存后，还要确认本次配置版本已由调度器应用。"""
        assert mutation['saved'] is True, mutation
        assert len(mutation['jobs']) == 1, mutation
        changed = mutation['jobs'][0]
        await self.poll_api(
            '/monitor/job/sync/list',
            lambda payload: any(
                row['jobId'] == changed['jobId']
                and row['syncStatus'] == 'applied'
                and row['appliedVersion'] == changed['configVersion']
                and row['deleted'] == changed['deleted']
                for row in payload['rows']
            ),
            jobId=changed['jobId'],
        )

    async def search_job(self, job_name: str) -> None:
        form = self.page.locator('form').first
        await form.get_by_placeholder('请输入任务名称', exact=True).fill(job_name)
        async with self.page.expect_response(
            lambda response: (
                urlparse(response.url).path.endswith('/monitor/job/list')
                and parse_qs(urlparse(response.url).query).get('jobName') == [job_name]
            )
        ) as response_info:
            await form.get_by_role('button', name=re.compile(r'搜索$')).click()
        response = await response_info.value
        assert response.status == HTTPStatus.OK
        assert (await response.json())['code'] == HTTPStatus.OK
        await expect(self.page.locator('.el-table .el-loading-mask:visible')).to_have_count(0)

    async def create_job(self, job_name: str) -> None:
        await self.page.get_by_role('button', name=re.compile(r'新增$')).click()
        dialog = self.page.get_by_role('dialog', name='添加任务', exact=True)
        await dialog.locator('.el-form-item').filter(has_text='任务名称').locator('input').fill(job_name)
        await (
            dialog.locator('.el-form-item')
            .filter(has_text=re.compile(r'(业务|任务)分组'))
            .locator('input')
            .fill('playwright')
        )
        executor = dialog.locator('.el-form-item').filter(has_text='任务执行器').locator('.el-select')
        await executor.click()
        await self.page.locator('.el-select-dropdown:visible').get_by_text('进程池', exact=True).click()
        await dialog.get_by_placeholder('请输入调用目标字符串').fill('module_task.scheduler_test.job')
        # 手动执行验证运行结果；年度计划避免启停断言与高频定时执行相互干扰。
        await dialog.get_by_placeholder('请输入cron执行表达式').fill('0 0 0 1 1 ?')
        mutation = await self.submit(
            dialog.get_by_role('button', name=re.compile(r'确\s*定$')).click, 'POST', '/monitor/job'
        )
        self.job_id = mutation['jobs'][0]['jobId']
        await self.wait_for_sync(mutation)
        await expect(dialog).to_be_hidden()
        await self.search_job(job_name)
        await expect(self.job_row(job_name)).to_have_count(1)

    async def edit_job(self, job_name: str, new_job_name: str) -> None:
        # 同步状态列也包含按钮，操作按钮仅在最后一列定位。
        await self.job_actions(job_name).nth(0).click()
        dialog = self.page.get_by_role('dialog', name='修改任务', exact=True)
        await dialog.locator('.el-form-item').filter(has_text='任务名称').locator('input').fill(new_job_name)
        mutation = await self.submit(
            dialog.get_by_role('button', name=re.compile(r'确\s*定$')).click, 'PUT', '/monitor/job'
        )
        await self.wait_for_sync(mutation)
        await expect(dialog).to_be_hidden()
        await self.search_job(new_job_name)
        await expect(self.job_row(new_job_name)).to_have_count(1)

    async def toggle_job_status(self, job_name: str, enabled: bool) -> None:
        switch = self.job_row(job_name).locator('.el-switch')
        await self.job_row(job_name).locator('.el-switch').click()
        confirm = self.page.get_by_role('dialog').get_by_role('button', name=re.compile(r'确定$'))
        mutation = await self.submit(confirm.click, 'PUT', '/monitor/job/changeStatus')
        await self.wait_for_sync(mutation)
        await self.search_job(job_name)
        if enabled:
            await expect(switch).to_have_class(re.compile(r'is-checked'))
        else:
            await expect(switch).not_to_have_class(re.compile(r'is-checked'))

    async def run_job_once(self, job_name: str) -> str:
        direct_run = self.page.get_by_role('button', name=f'立即执行 {job_name}', exact=True)
        if await direct_run.count():
            await direct_run.click()
        else:
            await self.job_actions(job_name).filter(has_text='更多').hover()
            await self.page.locator('.el-dropdown-menu:visible').get_by_text('执行一次', exact=True).click()
        confirm = self.page.get_by_role('dialog').get_by_role('button', name=re.compile(r'确定$'))
        execution = await self.submit(confirm.click, 'PUT', '/monitor/job/run')
        execution_id = execution['executionId']
        result = await self.poll_api(
            f'/monitor/job/execution/{execution_id}',
            lambda payload: payload['data']['status'] not in ('pending', 'submitted', 'running'),
        )
        assert result['data']['status'] == 'success', result
        assert result['data']['jobId'] == self.job_id
        assert result['data']['source'] == 'manual'
        dialog = self.page.get_by_role('dialog', name='任务运行记录', exact=True)
        await expect(dialog.locator('.execution-focus code')).to_have_text(execution_id)
        row = dialog.locator('tbody tr').filter(has_text=job_name)
        await expect(row.locator('.el-tag')).to_have_text('执行成功', timeout=10000)
        await dialog.get_by_role('button', name=re.compile(r'关\s*闭$')).click()
        await expect(dialog).to_be_hidden()
        return execution_id

    async def view_job_log(self, job_name: str, execution_id: str) -> None:
        # 执行状态和日志分别落库，先等待本次执行的日志出现。
        await self.poll_api('/monitor/jobLog/list', lambda payload: len(payload['rows']) == 1, executionId=execution_id)
        direct_log = self.job_actions(job_name).nth(3)
        if await direct_log.count():
            await direct_log.click()
        else:
            await self.job_actions(job_name).filter(has_text='更多').hover()
            await self.page.locator('.el-dropdown-menu:visible').get_by_text('调度日志', exact=True).click()
        await self.page.wait_for_url(f'**/monitor/job-log/index/{self.job_id}')
        job_id_input = (
            self.page.locator('.app-container:visible .el-form-item').filter(has_text='任务编号').locator('input')
        )
        await expect(job_id_input).to_have_value(str(self.job_id))
        row = self.page.locator('.app-container:visible > .el-table .el-table__body-wrapper tbody tr').filter(
            has_text=job_name
        )
        await expect(row.get_by_text('成功', exact=True)).to_be_visible()
        await self.page.get_by_role('button', name=re.compile(r'关闭$')).click()
        await self.page.wait_for_url('**/monitor/job')

    async def delete_job(self, job_name: str) -> None:
        await self.search_job(job_name)
        await self.job_actions(job_name).nth(1).click()
        confirm = self.page.get_by_role('dialog').get_by_role('button', name=re.compile(r'确定$'))
        mutation = await self.submit(confirm.click, 'DELETE', f'/monitor/job/{self.job_id}')
        await self.wait_for_sync(mutation)
        self.job_id = None
        await self.search_job(job_name)
        await expect(self.job_row(job_name)).to_have_count(0)

    async def cleanup_job(self) -> None:
        """失败时也只清理本用例创建的任务。"""
        if self.job_id is not None:
            response = await self.context.request.delete(
                f'{Config.backend_url}/monitor/job/{self.job_id}',
                headers={'Authorization': f'Bearer {self.token}'},
            )
            assert response.status == HTTPStatus.OK, await response.text()
            assert (await response.json())['code'] == HTTPStatus.OK

    async def test_job_crud_operations(self) -> None:
        job_name = f'测试任务_{uuid4().hex[:12]}'
        edited_name = job_name + '_edit'
        await self.goto_page(Config.frontend_url + '/monitor/job')
        await self.create_job(job_name)
        await self.edit_job(job_name, edited_name)
        await self.toggle_job_status(edited_name, enabled=True)
        await self.toggle_job_status(edited_name, enabled=False)
        execution_id = await self.run_job_once(edited_name)
        await self.view_job_log(edited_name, execution_id)
        await self.delete_job(edited_name)


@pytest.mark.asyncio
async def test_job_management_page(browser_harness: BrowserHarness) -> None:
    """测试定时任务管理页面功能。"""
    test_instance = JobManagementTest()
    await test_instance.setup(browser_harness)
    try:
        await test_instance.test_job_crud_operations()
    finally:
        await test_instance.cleanup_job()
