from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import pytest
from playwright.async_api import expect

from common.page_catalog import MENU_PAGES, PageCase

if TYPE_CHECKING:
    from common.browser_harness import BrowserHarness

pytestmark = pytest.mark.e2e


def builtin_routes(routes: list[dict[str, Any]], parent: str = '') -> set[str]:
    """列出服务端真实返回的内置页面，忽略外链和独立插件路由。"""
    paths = set()
    for route in routes:
        segment = route['path']
        if segment.startswith(('http://', 'https://')):
            continue
        path = segment if segment.startswith('/') else f'{parent}/{segment}'
        if children := route.get('children'):
            paths.update(builtin_routes(children, path))
        elif route.get('component', '').startswith(('system/', 'monitor/', 'tool/')):
            paths.add(path)
    return paths


async def test_every_builtin_menu_has_a_page_case(browser_harness: BrowserHarness) -> None:
    """新增或遗漏内置菜单时让完整 E2E 明确失败，防止页面覆盖再次缩减。"""
    api = await browser_harness.api_context(await browser_harness.login())
    response = await api.get('/getRouters')
    assert response.ok
    payload = await response.json()
    assert payload['code'] == HTTPStatus.OK
    assert builtin_routes(payload['data']) == {case.path for case in MENU_PAGES}


@pytest.mark.parametrize('case', MENU_PAGES, ids=lambda case: case.path)
async def test_builtin_menu_loads_data_and_content(browser_harness: BrowserHarness, case: PageCase) -> None:
    """每个真实菜单都必须加载业务内容及成功的后端响应，而不是只显示导航标题。"""
    page = await browser_harness.new_page(authenticated=True)
    if case.api:
        async with page.expect_response(
            lambda response: (
                urlparse(response.url).path.endswith(case.api)
                and response.request.method == 'GET'
                and response.request.resource_type in {'xhr', 'fetch'}
            )
        ) as pending:
            await page.goto(case.path)
        response = await pending.value
        assert response.ok, f'{case.path}: HTTP {response.status}'
        payload = await response.json()
        assert payload['code'] == HTTPStatus.OK, f'{case.path}: {payload.get("msg")}'
    else:
        await page.goto(case.path)
    main = page.locator('.app-main')
    await expect(main.locator(case.selector).first).to_be_visible()
    if case.content:
        await expect(main).to_contain_text(case.content)
    await expect(page.locator('.tags-view-item.active')).to_contain_text(case.title)
    assert urlparse(page.url).path == case.path
    assert not [event for event in browser_harness.events if event['kind'] == 'pageerror']


@pytest.mark.parametrize('case', MENU_PAGES, ids=lambda case: case.path)
async def test_builtin_menu_requires_authentication(browser_harness: BrowserHarness, case: PageCase) -> None:
    """两个框架的每个内置管理菜单均由真实路由守卫保护。"""
    page = await browser_harness.new_page()
    await page.goto(case.path)
    await page.wait_for_url('**/login**')
    await expect(page.get_by_placeholder('账号')).to_be_visible()
    await expect(page.locator('.app-main')).to_have_count(0)


@pytest.mark.smoke
async def test_dashboard_page(browser_harness: BrowserHarness) -> None:
    """验证首页组件渲染完成。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/index')
    await expect(page.locator('.app-main')).to_be_visible()
    await expect(page.locator('.tags-view-item.active')).to_contain_text('首页')


async def test_druid_page(browser_harness: BrowserHarness) -> None:
    """验证数据监控页面主体。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/monitor/druid')
    await expect(page.locator('.app-main')).to_contain_text('我是数据监控')


async def test_build_page(browser_harness: BrowserHarness) -> None:
    """验证表单构建器主体，而非仅匹配菜单标题。"""
    page = await browser_harness.new_page(authenticated=True)
    await page.goto('/tool/build')
    await expect(page.locator('.app-main')).to_contain_text('Form Generator')
