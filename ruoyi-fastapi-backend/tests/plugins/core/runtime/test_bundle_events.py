import asyncio
from types import SimpleNamespace

import httpx
import pytest
from starlette import status
from starlette.middleware.gzip import GZipMiddleware

from config.env import TransportCryptoConfig
from plugins.examples.python.bundle_demo.events import register_event_routes
from tests.plugins.core.runtime.test_browser_session import browser, issue  # noqa: F401
from tests.plugins.core.runtime.test_bundle_transport import _decrypt_response, _envelope, crypto  # noqa: F401


@pytest.mark.asyncio
async def test_authenticated_events_are_incremental_and_disconnect_stops_response(
    browser: SimpleNamespace,  # noqa: F811
) -> None:
    """事件经过真实门禁、传输和压缩中间件后仍逐条送出，客户端断开时提前结束。"""
    app = browser.app
    app.add_middleware(GZipMiddleware, minimum_size=1)
    register_event_routes(
        browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view', interval=0.01
    )
    issued = await issue(browser)
    cookie = issued.headers['set-cookie'].split(';')[0]
    count = 20
    incoming: asyncio.Queue = asyncio.Queue()
    await incoming.put({'type': 'http.request', 'body': b'', 'more_body': False})
    first_event = asyncio.Event()
    chunks = []

    async def send(message: dict) -> None:
        """
        保存实际 ASGI 响应片段并通知首条事件已到达。

        :param message: ASGI 响应消息
        :return: None
        """
        if message['type'] == 'http.response.body' and message.get('body'):
            chunks.append(message['body'])
            first_event.set()

    task = asyncio.create_task(
        app(
            {
                'type': 'http',
                'asgi': {'version': '3.0', 'spec_version': '2.3'},
                'http_version': '1.1',
                'method': 'GET',
                'scheme': 'https',
                'server': ('test', 443),
                'client': ('127.0.0.1', 12345),
                'path': '/apps/browser_test/api/events',
                'query_string': f'count={count}'.encode(),
                'root_path': '',
                'headers': [(b'host', b'test'), (b'cookie', cookie.encode()), (b'accept-encoding', b'gzip')],
            },
            incoming.get,
            send,
        )
    )
    try:
        await asyncio.wait_for(first_event.wait(), timeout=2)
        assert not task.done()
        assert chunks[0].startswith(b'id: 1\n')
        await incoming.put({'type': 'http.disconnect'})
        await asyncio.wait_for(task, timeout=2)
        assert len(chunks) < count
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_event_stream_authentication_cursor_and_bounded_input(browser: SimpleNamespace) -> None:  # noqa: F811
    """真实门禁保护事件流，游标补发后续编号，非法查询在打开流前拒绝。"""
    register_event_routes(
        browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view', interval=0
    )
    await issue(browser)
    path = '/apps/browser_test/api/events'
    response = await browser.client.get(path, params={'count': 3}, headers={'Last-Event-ID': '1'})
    assert response.status_code == status.HTTP_200_OK
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-accel-buffering'] == 'no'
    assert 'id: 1\n' not in response.text
    assert [line for line in response.text.splitlines() if line.startswith('id:')] == ['id: 2', 'id: 3']
    assert 'id: 2\n' in response.text and 'id: 3\n' in response.text
    assert (await browser.client.get(path, params={'count': 1}, headers={'Last-Event-ID': '1'})).text == ''
    for cursor in ('-1', '1.5', 'abc', '21', '001'):
        rejected = await browser.client.get(path, headers={'Last-Event-ID': cursor})
        assert rejected.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    for count in (0, 21):
        assert (
            await browser.client.get(path, params={'count': count})
        ).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=browser.app), base_url='https://test') as anonymous:
        assert (await anonymous.get(path)).status_code == status.HTTP_401_UNAUTHORIZED
    browser.user.permissions = []
    assert (await browser.client.get(path)).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_required_transport_needs_explicit_event_endpoint_exclusion(
    browser: SimpleNamespace,  # noqa: F811
    crypto: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """仅配置事件流接口例外后允许明文 SSE，普通 JSON 接口仍强制加密。"""
    register_event_routes(
        browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view', interval=0
    )
    session_path = '/plugin/runtime/browser_test/session'
    envelope, key = _envelope(crypto, 'POST', session_path, {})
    issued = await browser.client.post(
        session_path,
        json=envelope,
        headers={'Authorization': f'Bearer {browser.token}', 'Origin': 'https://test', 'X-Transport-Encrypt': '1'},
    )
    assert _decrypt_response(issued, key, method='POST', path=session_path)['data']['csrfToken']
    path = '/apps/browser_test/api/events'
    blocked = await browser.client.get(path)
    assert blocked.headers['x-transport-crypto-status'] == 'required_missing'
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_exclude_paths', path)
    response = await browser.client.get(path, params={'count': 1})
    assert response.status_code == status.HTTP_200_OK and 'id: 1\n' in response.text
    assert (await browser.client.get('/apps/browser_test/api/info')).headers[
        'x-transport-crypto-status'
    ] == 'required_missing'
