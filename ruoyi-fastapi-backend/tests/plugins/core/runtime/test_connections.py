import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from starlette import status
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from plugins.core.runtime.asgi import PluginGatewayASGI, PluginLifespanManager
from plugins.core.runtime.connections import AUTH_RECHECK_KEY, CONNECTION_OUTCOME_KEY, STREAM_CLOSED_EVENT
from plugins.core.runtime.metrics import PluginObservedASGI, PluginRuntimeMetrics
from plugins.core.sdk import PluginHostContext, PluginRequestContext


async def open_connection(tmp_path: Path, *, kind: str = 'http', listen: bool = False) -> SimpleNamespace:
    """
    建立可控的真实网关连接，保留首条事件、取消及指标证据。

    :param tmp_path: 测试资源目录
    :param kind: HTTP 事件流或 WebSocket
    :param listen: 是否等待客户端断开消息
    :return: 当前连接的网关、任务和可变测试状态
    """
    case = SimpleNamespace(
        calls=[],
        messages=[],
        permissions=frozenset({'demo:view', 'demo:edit'}),
        user_id=7,
        error=None,
        delay=0,
        ready=asyncio.Event(),
        released=asyncio.Event(),
        finish=asyncio.Event(),
        incoming=asyncio.Queue(),
    )
    host = PluginHostContext('demo', tmp_path)

    async def authorize(scope: Scope) -> PluginRequestContext:
        """按当前测试状态返回权限快照或触发指定失败。"""
        case.calls.append(dict(scope))
        if case.delay:
            await asyncio.sleep(case.delay)
        if case.error:
            raise case.error
        return PluginRequestContext(
            host, SimpleNamespace(user=SimpleNamespace(user_id=case.user_id)), permissions=case.permissions
        )

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        """发送首条业务消息，并在退出时记录清理结果。"""
        case.context = scope['state']['plugin_context']
        try:
            if kind == 'websocket':
                await send({'type': 'websocket.accept'})
                await send({'type': 'websocket.send', 'text': 'first'})
            else:
                await send(
                    {'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'text/event-stream')]}
                )
                await send({'type': 'http.response.body', 'body': b'data: first\n\n', 'more_body': True})
            scope['path'] = '/changed-by-child'
            case.ready.set()
            if listen:
                await receive()
                await asyncio.Event().wait()
            else:
                await case.finish.wait()
                if kind == 'websocket':
                    await send({'type': 'websocket.close', 'code': status.WS_1000_NORMAL_CLOSURE})
                else:
                    await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
        finally:
            case.released.set()

    async def send(message: Message) -> None:
        """保留协议输出以验证单次关闭及敏感字段不外泄。"""
        case.messages.append(message)

    manager = PluginLifespanManager(child, managed=False)
    await manager.startup()
    case.gateway = PluginGatewayASGI(
        child, manager, authorize, recheck_interval=0.01, recheck_timeout=0.03, cancel_timeout=0.05
    )
    case.manager = manager
    case.metrics = PluginRuntimeMetrics()
    case.metrics.register('demo', '1.0.0', None, None)
    observed = PluginObservedASGI(case.gateway, case.metrics, 'demo')
    case.scope = {'type': kind, 'path': '/api/events', 'headers': [], 'method': 'GET'}
    case.task = asyncio.create_task(observed(case.scope, case.incoming.get, send))
    await asyncio.wait_for(case.ready.wait(), timeout=1)
    return case


async def finish_case(case: SimpleNamespace) -> None:
    """回收用例中的连接和生命周期任务。"""
    await case.gateway.drain()
    if not case.task.done():
        case.task.cancel()
    await asyncio.gather(case.task, return_exceptions=True)
    await case.manager.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['http', 'websocket'])
@pytest.mark.parametrize(
    ('change', 'reason', 'outcome'),
    [
        ('login', 'session_expired', 'rejected'),
        ('permission', 'access_revoked', 'rejected'),
        ('reduced', 'access_revoked', 'rejected'),
        ('identity', 'access_revoked', 'rejected'),
        ('unavailable', 'authorization_unavailable', 'failed'),
        ('timeout', 'authorization_timeout', 'failed'),
        ('lifespan', 'authorization_unavailable', 'failed'),
    ],
)
async def test_revalidation_terminates_stream_and_records_reason(
    tmp_path: Path, kind: str, change: str, reason: str, outcome: str
) -> None:
    """已接受的连接在权限或身份变化后关闭，指标不把已发送 200 的 SSE 计为成功。"""
    case = await open_connection(tmp_path, kind=kind)
    try:
        if change == 'login':
            case.error = LookupError('secret credential')
        elif change == 'permission':
            case.error = PermissionError('secret permission source')
        elif change == 'reduced':
            case.permissions = frozenset({'demo:view'})
        elif change == 'identity':
            case.user_id += 1
        elif change == 'unavailable':
            case.error = RuntimeError('secret database')
        elif change == 'timeout':
            case.delay = 10
        else:
            case.manager.started = False
        await asyncio.wait_for(case.task, timeout=1)
        assert case.released.is_set()
        assert not case.gateway.connections.connections
        assert case.scope[CONNECTION_OUTCOME_KEY].reason == reason
        if kind == 'http':
            last = case.messages[-1]
            assert last['more_body'] is False
            assert f'event: {STREAM_CLOSED_EVENT}\n'.encode() in last['body']
            assert reason.encode() in last['body']
        else:
            assert case.messages[-1]['type'] == 'websocket.close'
            assert case.messages[-1]['code'] == (
                status.WS_1008_POLICY_VIOLATION if outcome == 'rejected' else status.WS_1011_INTERNAL_ERROR
            )
        assert 'secret' not in str(case.messages)
        sample = next(item for item in case.metrics.snapshot().series if item.operation == kind)
        assert sample.active == 0 and sample.succeeded == 0
        assert getattr(sample, outcome) == 1
        assert sample.timed_out == int(change == 'timeout')
        assert sample.last_error_type == f'PluginConnection:{reason}'
        for call in case.calls[1:]:
            assert call[AUTH_RECHECK_KEY] is True
            assert call['path'] == '/api/events'
    finally:
        await finish_case(case)


@pytest.mark.asyncio
@pytest.mark.parametrize('permissions', [frozenset({'demo:view', 'demo:edit', 'demo:extra'}), frozenset({'*:*:*'})])
async def test_added_permissions_do_not_mutate_existing_context(tmp_path: Path, permissions: frozenset[str]) -> None:
    """权限增加不会打断连接，也不会给原请求快照隐式增加权限。"""
    case = await open_connection(tmp_path)
    try:
        original = case.context.permissions
        case.permissions = permissions
        await asyncio.sleep(0.06)
        assert not case.task.done()
        assert len(case.calls) > 1
        assert case.context.permissions == original
        case.finish.set()
        await asyncio.wait_for(case.task, timeout=1)
        assert CONNECTION_OUTCOME_KEY not in case.scope
        assert case.metrics.snapshot().series[0].succeeded == 1
        calls = len(case.calls)
        await asyncio.sleep(0.03)
        assert len(case.calls) == calls
        assert not case.gateway.connections.connections
    finally:
        await finish_case(case)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['http', 'websocket'])
async def test_client_disconnect_and_external_cancel_release_tasks(tmp_path: Path, kind: str) -> None:
    """客户端断开或服务器取消时回收业务和复核任务，不再发送关闭消息。"""
    for external_cancel in (False, True):
        case = await open_connection(tmp_path, kind=kind, listen=True)
        try:
            sent = list(case.messages)
            if external_cancel:
                case.task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await case.task
            else:
                await case.incoming.put({'type': f'{kind}.disconnect'})
                await asyncio.wait_for(case.task, timeout=1)
            assert case.messages == sent
            assert case.released.is_set()
            assert not case.gateway.connections.connections
            assert next(item for item in case.metrics.snapshot().series if item.operation == kind).cancelled == 1
        finally:
            await finish_case(case)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['http', 'websocket'])
async def test_drain_closes_connections_and_rejects_new_requests(tmp_path: Path, kind: str) -> None:
    """先结束业务连接再返回关闭流程，后续请求得到未就绪响应。"""
    case = await open_connection(tmp_path, kind=kind)
    try:
        await case.gateway.drain()
        assert case.task.done() and case.released.is_set()
        assert case.scope[CONNECTION_OUTCOME_KEY].reason == 'plugin_shutdown'
        assert next(item for item in case.metrics.snapshot().series if item.operation == kind).cancelled == 1
        if kind == 'websocket':
            assert case.messages[-1]['code'] == status.WS_1012_SERVICE_RESTART
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=case.gateway), base_url='http://test') as client:
            assert (await client.get('/api/info')).status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        await case.gateway.drain()
    finally:
        await finish_case(case)


@pytest.mark.asyncio
async def test_regular_json_response_never_creates_revalidation_task(tmp_path: Path) -> None:
    """普通 JSON 请求沿用一次鉴权，不创建周期复核或控制事件。"""
    calls = []

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        await asyncio.sleep(0.03)
        await JSONResponse({'ok': True})(scope, receive, send)

    async def authorize(scope: Scope) -> PluginRequestContext:
        calls.append(scope)
        return PluginRequestContext(PluginHostContext('demo', tmp_path), None)

    manager = PluginLifespanManager(child, managed=False)
    await manager.startup()
    gateway = PluginGatewayASGI(child, manager, authorize, recheck_interval=0.01)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url='http://test') as client:
        assert (await client.get('/api/info')).json() == {'ok': True}
    assert len(calls) == 1
    assert not gateway.connections.connections
    await manager.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('external_cancel', [False, True])
async def test_cancel_resistant_application_cannot_send_late_events(tmp_path: Path, external_cancel: bool) -> None:
    """业务忽略首次取消也无法继续输出，关闭等待有界且迟到任务最终被回收。"""
    opened, release, released, fenced = (asyncio.Event() for _ in range(4))
    messages = []

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await send(
                {'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'text/event-stream')]}
            )
            opened.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                try:
                    await send({'type': 'http.response.body', 'body': b'secret late data', 'more_body': True})
                except asyncio.CancelledError:
                    fenced.set()
        finally:
            released.set()

    async def authorize(scope: Scope) -> PluginRequestContext:
        return PluginRequestContext(PluginHostContext('demo', tmp_path), None)

    async def send(message: Message) -> None:
        messages.append(message)

    manager = PluginLifespanManager(child, managed=False)
    await manager.startup()
    gateway = PluginGatewayASGI(child, manager, authorize, cancel_timeout=0.01)
    task = asyncio.create_task(gateway({'type': 'http', 'headers': []}, None, send))
    try:
        await asyncio.wait_for(opened.wait(), timeout=1)
        if external_cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await asyncio.wait_for(gateway.drain(), timeout=1)
            await task
        assert gateway.connections._unfinished
        assert 'secret' not in str(messages)
        release.set()
        await asyncio.wait_for(released.wait(), timeout=1)
        await asyncio.sleep(0)
        assert fenced.is_set()
        assert not gateway.connections._unfinished
        if not external_cancel:
            assert json.loads(messages[-1]['body'].decode().split('data: ')[1])['reason'] == 'plugin_shutdown'
    finally:
        release.set()
        await gateway.drain()
        await asyncio.gather(task, return_exceptions=True)
        await manager.shutdown()
