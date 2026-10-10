import re
from http import HTTPStatus
from urllib.parse import urlparse

import pytest
from playwright.async_api import Page, expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


async def assert_monitor_snapshot(page: Page, payload: dict) -> None:
    """核对同一响应中的启用状态、计数及环境配置。"""
    assert payload['code'] == HTTPStatus.OK, payload
    data = payload['data']
    cards = page.locator('.summary-card')
    await expect(cards.nth(0).locator('.el-tag')).to_have_text('已启用' if data['transportCryptoEnabled'] else '未启用')
    for index, key in enumerate(('requestsTotal', 'decryptSuccessTotal', 'encryptedResponsesTotal'), start=1):
        await expect(cards.nth(index).locator('.summary-value')).to_have_text(str(data.get(key) or 0))
    config = page.locator('.el-card').filter(has=page.get_by_text('当前配置', exact=True))
    for key in ('appEnv', 'currentKid'):
        await expect(config).to_contain_text(data.get(key) or '-')
    for kid in data.get('supportedKids', []):
        await expect(config).to_contain_text(kid)
    for path in data.get('excludePaths', []):
        await expect(config).to_contain_text(path)


@pytest.mark.asyncio
async def test_transport_crypto_page(browser_harness: BrowserHarness) -> None:
    """核对真实监控响应，并验证自动刷新开关与手动刷新请求。"""
    page = await browser_harness.new_page(authenticated=True)
    async with page.expect_response(
        lambda response: urlparse(response.url).path.endswith('/transport/crypto/monitor')
    ) as pending:
        await page.goto(Config.frontend_url + '/monitor/transportCrypto')
    await assert_monitor_snapshot(page, await (await pending.value).json())
    switch = page.locator('.card-actions .el-switch')
    await expect(switch).to_have_class(re.compile(r'is-checked'))
    await switch.click()
    await expect(switch).not_to_have_class(re.compile(r'is-checked'))
    async with page.expect_response(
        lambda response: urlparse(response.url).path.endswith('/transport/crypto/monitor')
    ) as pending:
        await page.get_by_role('button', name=re.compile(r'刷新$')).click()
    await assert_monitor_snapshot(page, await (await pending.value).json())
    await switch.click()
    await expect(switch).to_have_class(re.compile(r'is-checked'))
