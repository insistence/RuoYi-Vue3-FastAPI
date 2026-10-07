import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket
from starlette import status
from starlette.types import Message

from module_admin.service.login_service import LoginService
from plugins.core.runtime.browser_session import SESSION_KEY_PREFIX
from plugins.examples.python.bundle_demo.events import register_event_routes
from tests.plugins.core.runtime.test_browser_session import browser, issue  # noqa: F401


async def start_stream(runtime_browser: SimpleNamespace, *, bearer: bool = False) -> SimpleNamespace:
    """
    通过完整挂载、插件门禁和真实 Cookie 记录接收首条事件。

    :param runtime_browser: 隔离的宿主运行时和账号查询替身
    :param bearer: 是否使用主 Bearer 替代插件 Cookie
    :return: 可观察逐条输出及主动断开的请求状态
    """
    loaded = runtime_browser.runtime.loaded['browser_test']
    loaded.gateway.connections.recheck_interval = 0.01
    register_event_routes(loaded.lifespan.app, permission='browser_test:view', interval=0.01)
    response = await issue(runtime_browser)
    cookie = response.headers['set-cookie'].split(';')[0]
    headers = [(b'host', b'test')]
    headers.append(
        (b'authorization', f'Bearer {runtime_browser.token}'.encode()) if bearer else (b'cookie', cookie.encode())
    )
    result = SimpleNamespace(incoming=asyncio.Queue(), first=asyncio.Event(), chunks=[], messages=[])
    await result.incoming.put({'type': 'http.request', 'body': b'', 'more_body': False})

    async def send(message: Message) -> None:
        """保留流输出并在首个响应片段到达时继续测试。"""
        result.messages.append(message)
        if message['type'] == 'http.response.body' and message.get('body'):
            result.chunks.append(message['body'])
            result.first.set()

    result.task = asyncio.create_task(
        runtime_browser.app(
            {
                'type': 'http',
                'asgi': {'version': '3.0', 'spec_version': '2.3'},
                'http_version': '1.1',
                'method': 'GET',
                'scheme': 'https',
                'server': ('test', 443),
                'client': ('127.0.0.1', 12345),
                'path': '/apps/browser_test/api/events',
                'query_string': b'count=20',
                'root_path': '',
                'headers': headers,
            },
            result.incoming.get,
            send,
        )
    )
    await asyncio.wait_for(result.first.wait(), timeout=2)
    assert result.chunks[0].startswith(b'id: 1\n')
    assert not result.task.done()
    return result


async def finish_stream(stream: SimpleNamespace) -> None:
    """回收测试连接，保证失败分支也不会遗留请求任务。"""
    await stream.incoming.put({'type': 'http.disconnect'})
    if not stream.task.done():
        stream.task.cancel()
    await asyncio.gather(stream.task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('origin', ['https://test', 'https://outside.test'])
async def test_websocket_cookie_origin_and_live_login_revocation(
    browser: SimpleNamespace,  # noqa: F811
    origin: str,
) -> None:
    """WebSocket 保留精确 Origin 门禁，已握手的连接在主登录失效后关闭。"""
    loaded = browser.runtime.loaded['browser_test']
    loaded.gateway.connections.recheck_interval = 0.01
    opened = asyncio.Event()
    messages = []
    incoming: asyncio.Queue = asyncio.Queue()

    @loaded.lifespan.app.websocket('/ws/events')
    async def events(websocket: WebSocket) -> None:
        websocket.state.plugin_context.require_permission('browser_test:view')
        await websocket.accept()
        opened.set()
        await websocket.receive_text()

    response = await issue(browser)
    cookie = response.headers['set-cookie'].split(';')[0]
    await incoming.put({'type': 'websocket.connect'})

    async def send(message: Message) -> None:
        """保留 WebSocket 接受及关闭消息。"""
        messages.append(message)

    task = asyncio.create_task(
        browser.app(
            {
                'type': 'websocket',
                'asgi': {'version': '3.0', 'spec_version': '2.3'},
                'scheme': 'wss',
                'server': ('test', 443),
                'client': ('127.0.0.1', 12345),
                'path': '/apps/browser_test/ws/events',
                'query_string': b'',
                'root_path': '',
                'subprotocols': [],
                'headers': [(b'host', b'test'), (b'cookie', cookie.encode()), (b'origin', origin.encode())],
            },
            incoming.get,
            send,
        )
    )
    try:
        if origin == 'https://test':
            await asyncio.wait_for(opened.wait(), timeout=1)
            browser.redis.values.pop(browser.main_key)
        await asyncio.wait_for(task, timeout=1)
        assert opened.is_set() == (origin == 'https://test')
        assert messages[-1]['type'] == 'websocket.close'
        assert messages[-1]['code'] == status.WS_1008_POLICY_VIOLATION
        assert not loaded.gateway.connections.connections
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['logout', 'replaced_login', 'cookie_expired', 'permission', 'disabled'])
async def test_live_cookie_connection_rechecks_real_session_records(
    browser: SimpleNamespace,  # noqa: F811
    change: str,
) -> None:
    """实际 Cookie 门禁会复核登录记录、插件会话、权限和启用状态。"""
    stream = await start_stream(browser)
    try:
        if change == 'logout':
            browser.redis.values.pop(browser.main_key)
        elif change == 'replaced_login':
            browser.redis.values[browser.main_key] = 'different-token'
        elif change == 'cookie_expired':
            for key in list(browser.redis.values):
                if key.startswith(SESSION_KEY_PREFIX):
                    browser.redis.values.pop(key)
        elif change == 'permission':
            browser.user.permissions = []
        else:
            browser.runtime.route_state_gateway.is_plugin_enabled.return_value = False
        await asyncio.wait_for(stream.task, timeout=2)
        body = b''.join(stream.chunks)
        assert b'event: ruoyi.plugin.closed' in body
        assert (
            b'session_expired' if change in {'logout', 'replaced_login', 'cookie_expired'} else b'access_revoked'
        ) in body
        assert b'id: 20\n' not in body
        assert browser.token.encode() not in body
        assert not browser.runtime.loaded['browser_test'].gateway.connections.connections
    finally:
        await finish_stream(stream)


@pytest.mark.asyncio
async def test_runtime_closes_connections_before_lifespan_resources(
    browser: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式运行时关闭先结束连接，再交给插件释放生命周期资源。"""
    stream = await start_stream(browser)
    loaded = browser.runtime.loaded['browser_test']
    original = loaded.lifespan.shutdown
    closed = []

    async def shutdown() -> None:
        """在关闭资源前检查请求及连接登记已经回收。"""
        assert stream.task.done()
        assert not loaded.gateway.connections.connections
        closed.append(True)
        await original()

    monkeypatch.setattr(loaded.lifespan, 'shutdown', shutdown)
    try:
        await browser.runtime.shutdown()
        assert closed == [True]
        assert b'plugin_shutdown' in b''.join(stream.chunks)
    finally:
        await finish_stream(stream)


@pytest.mark.asyncio
async def test_recheck_uses_fresh_closed_db_sessions_and_does_not_refresh_bearer(
    browser: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """周期复核使用独立短会话和不续期登录的查询，原 Bearer 仅在接入时使用普通登录查询。"""
    sessions = SimpleNamespace(active=0, opened=0)
    checked = asyncio.Event()

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        """统计独立数据库会话在复核之间全部关闭。"""
        sessions.active += 1
        sessions.opened += 1
        try:
            yield object()
        finally:
            sessions.active -= 1

    async def read_user(**kwargs: object) -> object:
        """记录只读登录验证并返回固定账号。"""
        checked.set()
        return browser.user

    initial = AsyncMock(return_value=browser.user)
    readonly = AsyncMock(side_effect=read_user)
    monkeypatch.setattr('plugins.core.runtime.explicit.DataSourceRegistry.session', session)
    monkeypatch.setattr(LoginService, 'get_current_user', initial)
    monkeypatch.setattr(LoginService, 'get_current_user_for_plugin_session', readonly)
    stream = await start_stream(browser, bearer=True)
    try:
        await asyncio.wait_for(checked.wait(), timeout=1)
        await asyncio.sleep(0)
        assert sessions.active == 0 and sessions.opened > 1
        initial.assert_awaited_once()
        assert readonly.await_count > 0
        assert readonly.await_args.kwargs['token'] == browser.token
    finally:
        await finish_stream(stream)
