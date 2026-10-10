from http import HTTPStatus
from urllib.parse import urlparse

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_swagger_page(browser_harness: BrowserHarness) -> None:
    """验证内嵌文档的真实 HTTP 响应与配置对应的可用状态。"""
    page = await browser_harness.new_page(authenticated=True)
    async with page.expect_response(lambda response: urlparse(response.url).path.endswith('/proxy-docs')) as pending:
        await page.goto(Config.frontend_url + '/tool/swagger')
    response = await pending.value
    assert response.status == HTTPStatus.OK
    assert 'text/html' in response.headers['content-type']
    await expect(page.locator('iframe')).to_be_visible()
    frame = page.frame_locator('iframe')
    if Config.swagger_disabled:
        await expect(frame.locator('h1')).to_have_text('Swagger UI has been disabled. Please enable it first.')
        await expect(frame.locator('.swagger-ui')).to_have_count(0)
    else:
        await expect(frame.locator('.swagger-ui .info .title')).to_contain_text('RuoYi')
        operation = frame.locator('.opblock').filter(has=frame.locator('[data-path="/login"]'))
        await expect(operation).to_be_visible()
        await operation.locator('.opblock-summary-control').click()
        await expect(operation.locator('.opblock-body')).to_be_visible()
