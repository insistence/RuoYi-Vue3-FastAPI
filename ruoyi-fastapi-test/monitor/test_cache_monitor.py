from http import HTTPStatus
from urllib.parse import urlparse

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_cache_monitor_page(browser_harness: BrowserHarness) -> None:
    """核对实际 Redis 指标和图表，不假定本机使用默认端口。"""
    page = await browser_harness.new_page(authenticated=True)
    async with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith('/monitor/cache')
            and response.request.resource_type in {'xhr', 'fetch'}
        )
    ) as pending:
        await page.goto(Config.frontend_url + '/monitor/cache')
    response = await pending.value
    assert response.status == HTTPStatus.OK
    payload = await response.json()
    assert payload['code'] == HTTPStatus.OK, payload
    data = payload['data']
    info = data['info']
    metrics = {
        'Redis版本': info['redis_version'],
        '运行模式': '单机' if info['redis_mode'] == 'standalone' else '集群',
        '端口': info['tcp_port'],
        '客户端数': info['connected_clients'],
        '运行时间(天)': info['uptime_in_days'],
        '使用内存': info['used_memory_human'],
        '内存配置': info['maxmemory_human'],
        'RDB是否成功': info['rdb_last_bgsave_status'],
        'Key数量': data['dbSize'],
    }
    for label, value in metrics.items():
        cell = page.get_by_text(label, exact=True).locator('xpath=ancestor::td/following-sibling::td[1]')
        await expect(cell).to_have_text(str(value))
    for heading in ('命令统计', '内存信息'):
        card = page.locator('.el-card').filter(has=page.get_by_text(heading, exact=True))
        await expect(card.locator('canvas').first).to_be_visible()
