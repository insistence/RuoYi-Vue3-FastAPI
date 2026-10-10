import re
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
from zipfile import ZipFile

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_oauth_audit_page(browser_harness: BrowserHarness) -> None:
    """创建真实客户端审计事件，按应用筛选、查看详情并验证导出内容。"""
    api = await browser_harness.api_context(await browser_harness.login())
    client_name = f'e2e-audit-{uuid4().hex[:12]}'
    created = await api.post(
        '/system/oauth/client',
        data={
            'clientName': client_name,
            'clientType': 'public',
            'tokenEndpointAuthMethod': 'none',
            'redirectUris': ['http://127.0.0.1:8080/callback'],
        },
    )
    payload = await created.json()
    assert payload['code'] == HTTPStatus.OK, payload
    client_id = payload['data']['clientId']
    try:
        page = await browser_harness.new_page(authenticated=True)
        async with page.expect_response(
            lambda response: urlparse(response.url).path.endswith('/monitor/oauth/audit/list')
        ):
            await page.goto(Config.frontend_url + '/monitor/oauthAudit')
        await page.get_by_placeholder('应用编号', exact=True).fill(client_id)
        async with page.expect_response(
            lambda response: (
                urlparse(response.url).path.endswith('/monitor/oauth/audit/list')
                and parse_qs(urlparse(response.url).query).get('clientId') == [client_id]
            )
        ) as pending:
            await page.get_by_role('button', name=re.compile(r'查找$')).click()
        result = await (await pending.value).json()
        assert result['code'] == HTTPStatus.OK, result
        events = result['rows']
        assert len(events) == 1 and events[0]['eventType'] == 'client_created', result
        row = page.locator('.el-table__body-wrapper tbody tr')
        await expect(row).to_have_count(1)
        await expect(row).to_contain_text('应用已注册')
        await expect(row).to_contain_text('已完成')
        await page.locator('.el-table tbody tr').get_by_role('button', name=re.compile(r'查看$')).click()
        drawer = page.locator('.el-drawer:visible')
        await expect(drawer).to_contain_text(client_id)
        await drawer.get_by_text('查看排障信息', exact=True).click()
        await expect(drawer.get_by_text('事件 ID', exact=True).locator('xpath=following-sibling::dd[1]')).to_have_text(
            str(events[0]['auditId'])
        )
        await expect(drawer).to_contain_text('client_created')
        await drawer.locator('.el-drawer__close-btn').click()
        async with page.expect_download() as pending:
            async with page.expect_response(
                lambda response: urlparse(response.url).path.endswith('/monitor/oauth/audit/export')
            ) as exported:
                await page.get_by_role('button', name=re.compile(r'导出当前结果$')).click()
            response = await exported.value
            assert response.status == HTTPStatus.OK
            assert 'spreadsheetml.sheet' in response.headers.get('content-type', ''), await response.text()
        download = await pending.value
        assert download.suggested_filename.endswith('.xlsx')
        with ZipFile(Path(await download.path())) as workbook:
            xml = ''.join(workbook.read(name).decode('utf-8') for name in workbook.namelist() if name.endswith('.xml'))
        assert client_id in xml and 'client_created' in xml
        async with page.expect_response(
            lambda response: (
                urlparse(response.url).path.endswith('/monitor/oauth/audit/list')
                and 'clientId' not in parse_qs(urlparse(response.url).query)
            )
        ):
            await page.get_by_role('button', name=re.compile(r'清空$')).click()
        await expect(page.get_by_placeholder('应用编号', exact=True)).to_have_value('')
    finally:
        disabled = await api.delete(f'/system/oauth/client/{client_id}')
        assert (await disabled.json())['code'] == HTTPStatus.OK
