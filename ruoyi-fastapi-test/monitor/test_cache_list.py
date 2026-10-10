from http import HTTPStatus
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_cache_list_page(browser_harness: BrowserHarness) -> None:
    """新增专用参数，查看缓存值并只清除此用例的键。"""
    token = await browser_harness.login()
    api = await browser_harness.api_context(token)
    key = f'e2e.cache.{uuid4().hex[:12]}'
    value = f'缓存测试-{uuid4().hex}'
    created = await api.post(
        '/system/config',
        data={'configName': key, 'configKey': key, 'configValue': value, 'configType': 'N'},
    )
    assert (await created.json())['code'] == HTTPStatus.OK
    config_id = None
    try:
        listed = await api.get('/system/config/list', params={'configKey': key})
        configs = (await listed.json())['rows']
        assert len(configs) == 1
        config_id = configs[0]['configId']
        page = await browser_harness.new_page(authenticated=True)
        await page.goto(Config.frontend_url + '/monitor/cacheList')
        names = page.locator('.el-card').filter(has=page.get_by_text('缓存列表', exact=True))
        await names.locator('tbody tr').filter(has_text='sys_config').click()
        keys = page.locator('.el-card').filter(has=page.get_by_text('键名列表', exact=True))
        row = keys.locator('tbody tr').filter(has=page.get_by_text(key, exact=True))
        async with page.expect_response(
            lambda response: '/monitor/cache/getValue/' in urlparse(response.url).path
        ) as pending:
            await row.click()
        payload = await (await pending.value).json()
        assert payload['code'] == HTTPStatus.OK, payload
        assert payload['data']['cacheValue'] == value
        await expect(page.locator('.el-form-item').filter(has_text='缓存内容:').locator('textarea')).to_have_value(
            value
        )
        async with page.expect_response(
            lambda response: (
                response.request.method == 'DELETE' and '/monitor/cache/clearCacheKey/' in urlparse(response.url).path
            )
        ) as pending:
            await row.get_by_role('button').click()
        assert (await (await pending.value).json())['code'] == HTTPStatus.OK
        await expect(row).to_have_count(0)
        cached = await api.get('/monitor/cache/getKeys/sys_config:')
        assert f'sys_config:{key}' not in (await cached.json())['data']
        async with page.expect_response(lambda response: '/monitor/cache/getKeys/' in urlparse(response.url).path):
            await keys.locator('.el-card__header').get_by_role('button').click()
        await expect(row).to_have_count(0)
    finally:
        if config_id is not None:
            deleted = await api.delete(f'/system/config/{config_id}')
            assert (await deleted.json())['code'] == HTTPStatus.OK
