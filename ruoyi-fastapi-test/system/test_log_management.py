import asyncio
import re
from http import HTTPStatus

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from system.page import SystemPage

pytestmark = pytest.mark.e2e


async def wait_for_audit(view: SystemPage, path: str) -> dict:
    """日志经 Redis Stream 异步入库，轮询真实查询直到目标事件可见。"""
    for _ in range(30):
        payload = await view.search()
        if any(record['operUrl'].endswith(path) for record in payload['rows']):
            return payload
        await asyncio.sleep(0.2)
    raise AssertionError(f'目标操作日志未在限定时间内写入：{path}')


@pytest.mark.asyncio
async def test_log_management_page(browser_harness: BrowserHarness) -> None:
    """隔离测试数据库中实测操作/登录日志查询、单条删除与清空。"""
    view = SystemPage()
    await view.setup(browser_harness)
    # 真实缓存刷新产生操作日志；setup 的真实登录产生登录日志。
    response = await view.api.delete('/system/config/refreshCache')
    assert response.ok
    assert (await response.json())['code'] == HTTPStatus.OK
    for route, resource, field, identity in [
        ('operlog', '/monitor/operlog', '操作人员', 'operId'),
        ('logininfor', '/monitor/logininfor', '用户名称', 'infoId'),
    ]:
        await view.open(f'/system/log/{route}', f'{resource}/list')
        found = await view.search({field: 'admin'})
        assert found['total'] > 0, f'{route} 必须包含真实操作产生的记录'
        assert all(record['operName' if route == 'operlog' else 'userName'] == 'admin' for record in found['rows'])
        target = found['rows'][0]
        record_id = target[identity]
        row = view.rows.filter(has=view.page.locator('td:nth-child(2)').get_by_text(str(record_id), exact=True))
        await expect(row).to_have_count(1)
        if route == 'operlog':
            await view.button(row, '详细').click()
            dialog = view.dialog
            await expect(dialog).to_contain_text('操作日志详细')
            await expect(dialog).to_contain_text(target['operName'])
            await dialog.locator('.el-dialog__headerbtn').click()
            await expect(dialog).to_have_count(0)
        await row.locator('.el-checkbox').click()
        await view.button(view.page, '删除').click()
        deleted = await view.confirm_refresh(f'{resource}/{record_id}')
        assert all(record[identity] != record_id for record in deleted['rows'])
        await expect(row).to_have_count(0)
        await view.reset()
        await expect(view.input(view.form, field)).to_have_value('')
        await view.button(view.page, '清空').click()
        await view.confirm_refresh(f'{resource}/clean')
        if route == 'operlog':
            cleaned = await wait_for_audit(view, '/monitor/operlog/clean')
            assert cleaned['total'] > 0, '清空操作本身必须留下审计记录'
            assert all(
                re.search(r'/monitor/operlog/(?:clean|[0-9,]+)$', record['operUrl']) for record in cleaned['rows']
            )
            assert any(record['operUrl'].endswith('/monitor/operlog/clean') for record in cleaned['rows'])
        else:
            cleaned = await view.search()
            assert cleaned['total'] == 0
            await expect(view.rows).to_have_count(0)
