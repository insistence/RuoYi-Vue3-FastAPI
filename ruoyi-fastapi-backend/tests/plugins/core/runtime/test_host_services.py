import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from starlette import status
from starlette.requests import Request

from plugins.core.runtime.host_services import build_host_services
from plugins.core.sdk import PluginHostContext, PluginRequestContext, plugin_endpoint, plugin_lifespan


@pytest.mark.asyncio
async def test_profile_facade_calls_existing_service_for_own_user_and_limits_fields(tmp_path: Path) -> None:
    events = []
    db = object()

    @asynccontextmanager
    async def session() -> AsyncGenerator[object, None]:
        events.append('open')
        try:
            yield db
        finally:
            events.append('close')

    services = build_host_services('demo', session)
    host = PluginHostContext('demo', tmp_path, services=services)
    context = PluginRequestContext(host, SimpleNamespace(user=SimpleNamespace(user_id=7)), frozenset({'demo:profile'}))
    profile = SimpleNamespace(
        data=SimpleNamespace(user_id=7, user_name='tester', nick_name='Tester', avatar='', password='never expose'),
        post_group='Engineering',
        role_group='User',
    )
    with patch(
        'module_admin.service.user_service.UserService.user_profile_services', new=AsyncMock(return_value=profile)
    ) as service:
        result = await host.service('users.current_profile.v1')(context)
    service.assert_awaited_once_with(db, 7)
    assert events == ['open', 'close']
    assert result == {
        'userId': 7,
        'userName': 'tester',
        'nickName': 'Tester',
        'avatar': '',
        'postGroup': 'Engineering',
        'roleGroup': 'User',
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['foreign_plugin', 'permission', 'identity'])
async def test_profile_facade_rejects_invalid_context_before_database(tmp_path: Path, invalid: str) -> None:
    session = AsyncMock()
    service = build_host_services('demo', session)['users.current_profile.v1']
    host = PluginHostContext('other' if invalid == 'foreign_plugin' else 'demo', tmp_path)
    permissions = frozenset() if invalid == 'permission' else frozenset({'demo:profile'})
    context = PluginRequestContext(
        host, SimpleNamespace(user=SimpleNamespace(user_id=0 if invalid == 'identity' else 7)), permissions
    )
    with pytest.raises(PermissionError):
        await service(context)
    session.assert_not_called()


@pytest.mark.asyncio
async def test_endpoint_adapter_enforces_permission_and_waits_native_style_result(tmp_path: Path) -> None:
    host = PluginHostContext('demo', tmp_path)
    callback = AsyncMock(return_value={'ok': True})

    def native_callback(context: PluginRequestContext) -> object:
        return callback(context)

    endpoint = plugin_endpoint(native_callback, permission='demo:view')
    context = PluginRequestContext(host, object(), frozenset({'demo:view'}))
    request = Request({'type': 'http', 'state': {'plugin_context': context}})
    assert await endpoint(request) == {'ok': True}
    callback.assert_awaited_once_with(context)
    request.state.plugin_context = PluginRequestContext(host, object())
    with pytest.raises(HTTPException) as denied:
        await endpoint(request)
    assert denied.value.status_code == status.HTTP_403_FORBIDDEN
    assert callback.await_count == 1


@pytest.mark.asyncio
async def test_endpoint_timeout_cancels_python_service(tmp_path: Path) -> None:
    closed = asyncio.Event()

    async def slow(context: PluginRequestContext) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    context = PluginRequestContext(PluginHostContext('demo', tmp_path), object(), frozenset({'demo:view'}))
    endpoint = plugin_endpoint(slow, permission='demo:view', timeout=0.01)
    with pytest.raises(HTTPException) as timeout:
        await endpoint(Request({'type': 'http', 'state': {'plugin_context': context}}))
    assert timeout.value.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert closed.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize('startup_failure', [False, True])
async def test_lifespan_adapter_closes_even_partial_startup(tmp_path: Path, startup_failure: bool) -> None:
    host = PluginHostContext('demo', tmp_path)
    startup = AsyncMock(return_value={'ready': True}, side_effect=RuntimeError('failed') if startup_failure else None)
    shutdown = AsyncMock()
    lifespan = plugin_lifespan(host, startup, shutdown)
    if startup_failure:
        with pytest.raises(RuntimeError, match='failed'):
            async with lifespan(FastAPI()):
                pytest.fail('failed startup cannot enter lifespan')
    else:
        async with lifespan(FastAPI()) as state:
            assert state == {'ready': True}
    shutdown.assert_awaited_once_with(host)
