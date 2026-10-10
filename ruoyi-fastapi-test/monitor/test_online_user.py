import re
from http import HTTPStatus
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_online_user_page(browser_harness: BrowserHarness) -> None:
    """登录临时账号，界面强退后验证列表和原登录令牌均失效。"""
    api = await browser_harness.api_context(await browser_harness.login())
    username = f'e2e_online_{uuid4().hex[:10]}'
    created = await api.post(
        '/system/user',
        data={
            'userName': username,
            'nickName': username,
            'password': 'Test123456!',
            'status': '0',
            'deptId': 100,
            'roleIds': [2],
            'postIds': [],
        },
    )
    assert (await created.json())['code'] == HTTPStatus.OK
    user_id = None
    try:
        listed = await api.get('/system/user/list', params={'userName': username})
        users = (await listed.json())['rows']
        assert len(users) == 1
        user_id = users[0]['userId']
        secondary = await browser_harness.new_page()
        await secondary.goto(Config.frontend_url + '/login')
        secondary_token = await browser_harness.login_through_page(secondary, username, 'Test123456!')
        page = await browser_harness.new_page(authenticated=True)
        await page.goto(Config.frontend_url + '/monitor/online')
        await page.locator('.el-form-item').filter(has_text='用户名称').locator('input').fill(username)
        async with page.expect_response(lambda response: urlparse(response.url).path.endswith('/monitor/online/list')):
            await page.get_by_role('button', name=re.compile(r'搜索$')).click()
        rows = page.locator('.el-table__body-wrapper tbody tr').filter(has=page.get_by_text(username, exact=True))
        await expect(rows).to_have_count(1)
        await rows.get_by_role('button', name=re.compile(r'强退$')).click()
        async with page.expect_response(
            lambda response: response.request.method == 'DELETE' and '/monitor/online/' in response.url
        ) as forced:
            await page.get_by_role('button', name=re.compile(r'确定$')).click()
        assert (await (await forced.value).json())['code'] == HTTPStatus.OK
        await expect(rows).to_have_count(0)
        revoked = await browser_harness.api_context(secondary_token)
        response = await revoked.get('/getInfo')
        assert response.status == HTTPStatus.UNAUTHORIZED or (await response.json())['code'] == HTTPStatus.UNAUTHORIZED
        await secondary.reload()
        await secondary.wait_for_url('**/login?**')
    finally:
        if user_id is not None:
            deleted = await api.delete(f'/system/user/{user_id}')
            assert (await deleted.json())['code'] == HTTPStatus.OK
