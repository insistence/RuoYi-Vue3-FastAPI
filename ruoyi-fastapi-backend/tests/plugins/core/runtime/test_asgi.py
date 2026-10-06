import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette import status
from starlette.types import Message, Receive, Scope, Send

from plugins.core.runtime.asgi import PluginGatewayASGI, PluginLifespanManager
from plugins.core.sdk import PluginHostContext, PluginRequestContext


@pytest.mark.asyncio
async def test_mounted_app_lifespan_state_root_path_and_shutdown(tmp_path: Path) -> None:
    events = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[dict[str, str], None]:
        events.append('start')
        yield {'resource': 'ready'}
        events.append('stop')

    child = FastAPI(lifespan=lifespan)

    @child.get('/api/state')
    async def state(request: Request) -> dict[str, str]:
        return {
            'resource': request.state.resource,
            'plugin': request.state.plugin_context.host.plugin_id,
            'root_path': request.scope['root_path'],
        }

    async def authorize(scope: Scope) -> PluginRequestContext:
        return PluginRequestContext(PluginHostContext('demo', tmp_path), user=None)

    manager = PluginLifespanManager(child)
    parent = FastAPI()
    parent.mount('/apps/demo', PluginGatewayASGI(child, manager, authorize))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=parent), base_url='http://test') as client:
        assert (await client.get('/apps/demo/api/state')).status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        await manager.startup()
        await manager.startup()
        response = await client.get('/apps/demo/api/state')
        assert response.json() == {'resource': 'ready', 'plugin': 'demo', 'root_path': '/apps/demo'}
        await manager.shutdown()
        await manager.shutdown()
        assert (await client.get('/apps/demo/api/state')).status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert events == ['start', 'stop']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [PermissionError, LookupError])
async def test_gateway_rejects_http_and_websocket_without_invoking_plugin(failure: type[Exception]) -> None:
    reached = []

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(scope)

    async def authorize(scope: Scope) -> PluginRequestContext:
        raise failure()

    manager = PluginLifespanManager(child, managed=False)
    await manager.startup()
    gateway = PluginGatewayASGI(child, manager, authorize)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url='http://test') as client:
        response = await client.get('/ui/index.html')
        assert response.status_code == (403 if failure is PermissionError else 401)
    messages = []

    async def send(message: Message) -> None:
        messages.append(message)

    await gateway({'type': 'websocket', 'path': '/ws'}, None, send)
    assert messages[0]['type'] == 'websocket.close'
    assert not reached


@pytest.mark.asyncio
async def test_failed_or_unsupported_lifespan_cleans_up() -> None:
    stopped = asyncio.Event()

    async def failed(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await receive()
            await send({'type': 'lifespan.startup.failed', 'message': 'broken resource'})
            await asyncio.Event().wait()
        finally:
            stopped.set()

    manager = PluginLifespanManager(failed)
    with pytest.raises(RuntimeError, match='broken resource'):
        await manager.startup()
    assert stopped.is_set()
    assert not manager.started

    async def unsupported(scope: Scope, receive: Receive, send: Send) -> None:
        return

    with pytest.raises(RuntimeError, match='确认前退出'):
        await PluginLifespanManager(unsupported).startup()


@pytest.mark.asyncio
async def test_lifespan_timeout_cancels_task() -> None:
    stopped = asyncio.Event()

    async def hangs(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    manager = PluginLifespanManager(hangs, timeout=0.02)
    with pytest.raises(TimeoutError):
        await manager.startup()
    assert stopped.is_set()
