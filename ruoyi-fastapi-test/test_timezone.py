from datetime import datetime
from http import HTTPStatus
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = [pytest.mark.e2e, pytest.mark.smoke]


@pytest.mark.asyncio
@pytest.mark.parametrize('host_timezone', ['UTC', 'Asia/Shanghai', 'America/New_York'])
async def test_authenticated_profile_uses_user_timezone_and_cron_keeps_its_zone(
    browser_harness: BrowserHarness, host_timezone: str
) -> None:
    """验证真实登录、用户时区展示、请求头和独立cron时区。"""
    token = await browser_harness.login()
    api = await browser_harness.api_context(token)
    info = await (await api.get('/getInfo')).json()
    profile = await (await api.get('/system/user/profile')).json()
    created = profile['data']['createTime']
    assert created.endswith('Z')
    preference = info['user']['timeZone']
    display_timezone = host_timezone if preference == 'auto' else preference
    expected = (
        datetime.fromisoformat(created.replace('Z', '+00:00'))
        .astimezone(ZoneInfo(display_timezone))
        .strftime('%Y-%m-%d %H:%M:%S')
    )
    context = await browser_harness.new_context(token=token, timezone_id=host_timezone)
    page = await context.new_page()
    errors = []
    request_timezones = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on(
        'request',
        lambda request: (
            request_timezones.append(request.headers.get('x-timezone'))
            if urlparse(request.url).path.endswith('/system/user/profile')
            else None
        ),
    )
    await page.goto(Config.frontend_url + '/user/profile')
    created_at = page.get_by_role('listitem').filter(has_text='创建日期').locator('.pull-right')
    await expect(created_at).to_have_text(expected, timeout=30000)
    await expect(created_at).to_be_visible()
    assert not errors
    assert display_timezone in request_timezones

    preview = {
        'cronExpression': '0 30 2 * * ?',
        'timeZone': 'America/New_York',
        'startTime': '2026-03-07T00:00:00.000Z',
        'count': 3,
    }
    response = await api.post('/monitor/job/preview', data=preview, headers={'X-Timezone': 'Asia/Kathmandu'})
    assert response.status == HTTPStatus.OK
    payload = (await response.json())['data']
    assert payload['nextRunTimes'] == [
        '2026-03-07T07:30:00.000Z',
        '2026-03-09T06:30:00.000Z',
        '2026-03-10T06:30:00.000Z',
    ]
    bad_zone = await api.post('/monitor/job/preview', data={**preview, 'timeZone': 'Invalid/Zone'})
    assert bad_zone.status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (await bad_zone.json())['detail'][0]['loc'][-1] == 'timeZone'
    bad_range = await api.get('/system/config/list', params={'beginTime': '2026-02-30'})
    assert bad_range.status == HTTPStatus.UNPROCESSABLE_ENTITY
    single_bound = await api.get('/system/config/list', params={'beginTime': '2000-01-01'})
    assert single_bound.status == HTTPStatus.OK
    assert (await single_bound.json())['code'] == HTTPStatus.OK
    bad_request_zone = await api.get('/system/config/list', headers={'X-Timezone': 'UTC+8'})
    assert bad_request_zone.status == HTTPStatus.UNPROCESSABLE_ENTITY
