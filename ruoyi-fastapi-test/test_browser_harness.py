from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from common.browser_harness import BrowserHarness, artifact_directory
from common.config import Config
from prepare_e2e_compose import isolate_compose

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Browser, Playwright

pytestmark = pytest.mark.harness


def login_response(status: HTTPStatus, *, retry_after: str | None = None, payload: dict | None = None) -> MagicMock:
    """构造登录协议响应，保留 HTTP 状态、响应头和异步 JSON 读取语义。"""
    return MagicMock(
        status=status,
        ok=status == HTTPStatus.OK,
        headers={'retry-after': retry_after} if retry_after is not None else {},
        json=AsyncMock(return_value=payload or {}),
    )


def login_harness(tmp_path: Path, responses: list[object]) -> tuple[BrowserHarness, AsyncMock]:
    """仅替换网络边界，直接运行实际登录重试逻辑。"""
    api = AsyncMock()
    api.post.side_effect = responses
    playwright = MagicMock()
    playwright.request.new_context = AsyncMock(return_value=api)
    return BrowserHarness(playwright, MagicMock(), tmp_path), api


def login_page(responses: list[MagicMock]) -> MagicMock:
    """模拟浏览器响应事件边界，实际运行表单提交及跳转校验逻辑。"""
    page = MagicMock()
    page.get_by_placeholder.return_value.fill = AsyncMock()
    page.get_by_role.return_value.click = AsyncMock()
    page.wait_for_url = AsyncMock()
    events = []
    for response in responses:
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        event = MagicMock()
        event.__aenter__.return_value.value = future
        events.append(event)
    page.expect_response.side_effect = events
    return page


async def test_form_login_retries_rate_limit_without_replacing_admin_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """表单限流后必须再次真实点击，且副账号登录不污染管理员的 API 身份。"""
    harness, api = login_harness(tmp_path, [])
    harness.token = 'admin-token'
    page = login_page(
        [
            login_response(HTTPStatus.TOO_MANY_REQUESTS, retry_after='9'),
            login_response(HTTPStatus.OK, payload={'token': 'secondary-token'}),
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    assert await harness.login_through_page(page, 'secondary', 'secret') == 'secondary-token'
    assert harness.token == 'admin-token'
    sleep.assert_awaited_once_with(9)
    assert page.get_by_placeholder.return_value.fill.await_args_list == [call('secondary'), call('secret')]
    assert page.get_by_role.return_value.click.await_args_list == [call(timeout=15000), call(timeout=15000)]
    page.wait_for_url.assert_awaited_once_with('**/index', timeout=30000)
    api.post.assert_not_awaited()


async def test_form_login_does_not_retry_other_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """失败的 UI 登录不重试、不假定已进入首页。"""
    harness, _ = login_harness(tmp_path, [])
    page = login_page([login_response(HTTPStatus.UNAUTHORIZED, retry_after='1')])
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    with pytest.raises(AssertionError, match='登录 HTTP 状态异常'):
        await harness.login_through_page(page)
    page.get_by_role.return_value.click.assert_awaited_once()
    page.wait_for_url.assert_not_awaited()
    sleep.assert_not_awaited()


@pytest.mark.parametrize('retry_after', [17, 60])
async def test_login_obeys_retry_after_then_caches_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, retry_after: int
) -> None:
    """真实 Retry-After 秒数决定等待，成功后同一用例不再重新登录。"""
    limited = login_response(HTTPStatus.TOO_MANY_REQUESTS, retry_after=str(retry_after))
    success = login_response(HTTPStatus.OK, payload={'data': {'token': 'after-limit'}})
    harness, api = login_harness(tmp_path, [limited, success])
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    assert await harness.login() == 'after-limit'
    assert await harness.login() == 'after-limit'
    sleep.assert_awaited_once_with(retry_after)
    request = call('/login', form={'username': 'admin', 'password': 'admin123'})
    assert api.post.await_args_list == [request, request]
    limited.json.assert_not_awaited()
    success.json.assert_awaited_once()
    assert harness.api_contexts == [api]


@pytest.mark.parametrize('status', [HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN, HTTPStatus.INTERNAL_SERVER_ERROR])
async def test_login_does_not_retry_other_http_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: HTTPStatus
) -> None:
    """非 429 错误即使带有 Retry-After，也应立即暴露真实失败。"""
    response = login_response(status, retry_after='1')
    harness, api = login_harness(tmp_path, [response])
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    with pytest.raises(AssertionError, match=f'登录 HTTP 状态异常：{status}'):
        await harness.login()
    api.post.assert_awaited_once()
    sleep.assert_not_awaited()
    response.json.assert_not_awaited()
    assert harness.token is None


async def test_login_does_not_retry_business_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 200 包装的登录失败不能被当成限流或缓存一个无效令牌。"""
    response = login_response(HTTPStatus.OK, payload={'code': HTTPStatus.UNAUTHORIZED, 'msg': '凭据无效'})
    harness, api = login_harness(tmp_path, [response])
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    with pytest.raises(AssertionError, match='凭据无效'):
        await harness.login()
    api.post.assert_awaited_once()
    sleep.assert_not_awaited()
    assert harness.token is None


async def test_login_does_not_retry_transport_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """网络超时直接传播，不被重试掩盖。"""
    harness, api = login_harness(tmp_path, [TimeoutError('request timed out')])
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    with pytest.raises(TimeoutError, match='request timed out'):
        await harness.login()
    api.post.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.parametrize('retry_after', [None, '', 'invalid', '-1', '0.5', '61'])
async def test_login_rejects_invalid_or_excessive_retry_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, retry_after: str | None
) -> None:
    """不能猜测缺失的时间，或在服务端要求的等待结束前提前重试。"""
    harness, api = login_harness(tmp_path, [login_response(HTTPStatus.TOO_MANY_REQUESTS, retry_after=retry_after)])
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    with pytest.raises(AssertionError, match='Retry-After'):
        await harness.login()
    api.post.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_login_limits_attempts_even_with_zero_wait(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """持续 429 且 Retry-After 为零也只能发起三次请求。"""
    responses = [login_response(HTTPStatus.TOO_MANY_REQUESTS, retry_after='0') for _ in range(3)]
    harness, api = login_harness(tmp_path, responses)
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    with pytest.raises(AssertionError, match='最大尝试次数'):
        await harness.login()
    assert api.post.await_count == len(responses)
    assert sleep.await_args_list == [call(0), call(0)]
    assert harness.token is None


async def test_login_bounds_cumulative_wait(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """多次限流的等待总和也必须在预算内，而非仅约束单次等待。"""
    responses = [login_response(HTTPStatus.TOO_MANY_REQUESTS, retry_after=seconds) for seconds in ('40', '30')]
    harness, api = login_harness(tmp_path, responses)
    sleep = AsyncMock()
    monkeypatch.setattr('common.browser_harness.asyncio.sleep', sleep)

    with pytest.raises(AssertionError, match='累计等待上限'):
        await harness.login()
    assert api.post.await_count == len(responses)
    sleep.assert_awaited_once_with(40)


def test_artifact_paths_cannot_escape_output(tmp_path: Path) -> None:
    first = artifact_directory(tmp_path, '../../a/test_login.py::test_a[UTC]')
    second = artifact_directory(tmp_path, '../../b/test_login.py::test_a[UTC]')
    assert first.parent == second.parent == tmp_path
    assert first != second
    assert ':' not in first.name


async def test_contexts_share_browser_but_not_authentication(
    e2e_browser: tuple[Playwright, Browser], tmp_path: Path
) -> None:
    first = BrowserHarness(*e2e_browser, tmp_path / 'first')
    second = BrowserHarness(*e2e_browser, tmp_path / 'second')
    try:
        signed_in = await first.new_context(token='test-token')
        anonymous = await second.new_context()
        assert signed_in.browser is anonymous.browser is e2e_browser[1]
        assert (await signed_in.cookies(Config.frontend_url))[0]['value'] == 'test-token'
        assert await anonymous.cookies(Config.frontend_url) == []
    finally:
        await first.finish(failed=False)
        await second.finish(failed=False)
    assert e2e_browser[1].contexts == []


async def test_failed_case_keeps_trace_screenshot_and_console(
    e2e_browser: tuple[Playwright, Browser], tmp_path: Path
) -> None:
    harness = BrowserHarness(*e2e_browser, tmp_path)
    page = await harness.new_page()
    await page.set_content('<h1>Failure diagnostics</h1>')
    await page.evaluate("console.error('diagnostic-sentinel')")
    await harness.finish(failed=True)
    assert await asyncio.to_thread((tmp_path / 'context-0-page-0.png').is_file)
    assert await asyncio.to_thread((tmp_path / 'context-0-trace.zip').is_file)
    events = json.loads(await asyncio.to_thread((tmp_path / 'browser-events.json').read_text, encoding='utf-8'))
    assert {'kind': 'error', 'message': 'diagnostic-sentinel'} in events
    assert e2e_browser[1].contexts == []


def test_compose_isolation_removes_shared_resources() -> None:
    config = {
        'services': {
            'ruoyi-frontend': {'build': {'context': '/frontend'}, 'container_name': 'shared', 'ports': ['80:80']},
            'ruoyi-backend-my': {'build': {'context': '/backend'}, 'ports': ['9099:9099']},
            'ruoyi-mysql': {'image': 'mysql:8.0', 'container_name': 'shared-db', 'ports': ['3306:3306']},
        },
        'networks': {'default': {'name': 'shared-network', 'external': True}},
        'volumes': {'data': {'name': 'shared-data', 'external': True}},
    }
    isolated = isolate_compose(config, 'ruoyi-ci-test', '3.12')
    assert config['services']['ruoyi-mysql']['container_name'] == 'shared-db'
    assert all('container_name' not in service for service in isolated['services'].values())
    assert isolated['services']['ruoyi-mysql']['ports'] == []
    assert isolated['services']['ruoyi-frontend']['ports'][0]['host_ip'] == '127.0.0.1'
    assert isolated['services']['ruoyi-frontend']['ports'][0]['published'] == '0'
    assert isolated['networks']['default'] == {'name': 'ruoyi-ci-test-default'}
    assert isolated['volumes']['data'] == {'name': 'ruoyi-ci-test-data'}


def test_compose_requires_dedicated_project_prefix() -> None:
    with pytest.raises(ValueError, match='ruoyi-ci-'):
        isolate_compose({'services': {}}, 'production', '3.12')
