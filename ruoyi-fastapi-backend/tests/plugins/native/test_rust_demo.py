import asyncio
import inspect
import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import replace
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

import httpx
import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI
from starlette import status
from starlette.responses import JSONResponse

from common.aspect.db_session import get_db_session_provider
from config.scheduler.job_adapter import JobAdapter
from exceptions.exception import PermissionException
from module_admin.service.login_service import LoginService, oauth2_scheme
from plugins.core.discovery.registry import RegisteredPlugin
from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.lifecycle.jobs import PluginJobModelBuilder
from plugins.core.runtime.entrypoint import PluginEntrypointLoader
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from plugins.core.runtime.health import PluginHealthChecker
from plugins.core.runtime.job_dispatcher import dispatch_plugin_job
from plugins.core.sdk import PluginHostContext, PluginRequestContext, await_plugin_callback
from plugins.core.sdk.version import HOST_API_VERSION
from plugins.core.validation.structure import PluginStructureChecker

PLUGIN_DIRECTORY = os.environ.get('RUOYI_NATIVE_PLUGIN_DIR')
pytestmark = [
    pytest.mark.native,
    pytest.mark.skipif(not PLUGIN_DIRECTORY, reason='需先构建 Rust wheel 并设置 RUOYI_NATIVE_PLUGIN_DIR'),
]


@pytest.fixture(scope='module')
def plugin() -> DiscoveredPlugin:
    root = Path(PLUGIN_DIRECTORY).resolve()
    assert (root / 'plugin.yaml').is_file(), '指定的 Rust 交付目录不存在'
    return PluginScanner(root.parent).load_manifest(root / 'plugin.yaml')


def test_distribution_contains_native_business_code_and_passes_static_discovery(plugin: DiscoveredPlugin) -> None:
    check = PluginStructureChecker(plugin.backend_path.parents[1]).check(plugin, include_frontend=False)
    assert check.ok, check.failed_items
    files = [path for path in plugin.backend_path.rglob('*') if path.is_file()]
    assert any(any(path.name.endswith(suffix) for suffix in EXTENSION_SUFFIXES) for path in files)
    assert not any(path.suffix == '.rs' or path.name in {'Cargo.toml', 'Cargo.lock'} for path in files)
    assert all(path.name == '__init__.py' for path in files if path.suffix == '.py')
    archive_path = plugin.backend_path.parent / 'rust_demo-1.0.0.zip'
    with ZipFile(archive_path) as archive:
        names = archive.namelist()
    assert 'rust_demo/plugin.yaml' in names
    assert not any(name.endswith(('.rs', 'Cargo.toml')) for name in names)


@pytest.mark.asyncio
async def test_compiled_native_health_returns_rust_future(plugin: DiscoveredPlugin) -> None:
    loader = PluginEntrypointLoader(plugin)
    callback = loader.load_callable(plugin.manifest.backend.health.checker)
    assert not inspect.iscoroutinefunction(callback)
    result = await PluginHealthChecker(plugin).check()
    assert result.ok, result.error


@asynccontextmanager
async def fake_session() -> AsyncGenerator[object, None]:
    yield object()


@pytest.mark.asyncio
async def test_real_native_subapp_uses_host_auth_lifespan_and_python_service(plugin: DiscoveredPlugin) -> None:
    app = FastAPI()
    gateway = SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True))
    runtime = ExplicitPluginRuntime(gateway)
    user = SimpleNamespace(user=SimpleNamespace(user_id=7), permissions=['rust_demo:view', 'rust_demo:profile'])
    profile = SimpleNamespace(
        data=SimpleNamespace(user_id=7, user_name='rust-user', nick_name='Rust', avatar='', password='secret'),
        post_group='Engineering',
        role_group='Developer',
    )
    with (
        patch('plugins.core.runtime.explicit.DataSourceRegistry.session', fake_session),
        patch('plugins.core.runtime.explicit.LoginService.get_current_user', new=AsyncMock(return_value=user)),
        patch(
            'module_admin.service.user_service.UserService.user_profile_services', new=AsyncMock(return_value=profile)
        ) as service,
    ):
        runtime.prepare(RegisteredPlugin(plugin, None, True, 'installed'), app, startup_write_enabled=False)
        await runtime.activate('rust_demo', app)
        try:
            assert runtime.loaded['rust_demo'].lifespan.state == {'nativeReady': True}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                assert (await client.get('/apps/rust_demo/api/info')).status_code == status.HTTP_401_UNAUTHORIZED
                headers = {'Authorization': 'Bearer test-token'}
                response = await client.get('/apps/rust_demo/api/info', headers=headers)
                assert response.status_code == status.HTTP_200_OK, response.text
                assert response.json()['engine'] == 'rust'
                assert response.json()['hostApiVersion'] == HOST_API_VERSION
                assert response.json()['serverTime'].endswith('+00:00')
                response = await client.get('/apps/rust_demo/api/profile', headers=headers)
                assert response.json()['userName'] == 'rust-user'
                assert 'password' not in response.json()
                assert service.await_args.args[1] == user.user.user_id
                response = await client.post(
                    '/apps/rust_demo/api/echo/item-7?tag=first&tag=second',
                    headers=headers,
                    json={'message': '来自 Python 的请求体'},
                )
                assert response.status_code == status.HTTP_200_OK, response.text
                payload = response.json()
                assert payload['pathParams'] == {'item_id': 'item-7'}
                assert payload['query'] == {'tag': ['first', 'second']}
                assert payload['body'] == {'message': '来自 Python 的请求体'}
                assert payload['requestId']
                assert 'test-token' not in response.text
                user.permissions = ['rust_demo:view']
                response = await client.get('/apps/rust_demo/api/profile', headers=headers)
                assert response.status_code == status.HTTP_403_FORBIDDEN
                assert service.await_count == 1
                gateway.is_plugin_enabled.return_value = False
                response = await client.get('/apps/rust_demo/api/info', headers=headers)
                assert response.status_code == status.HTTP_403_FORBIDDEN
        finally:
            await runtime.shutdown()
    assert not runtime.loaded['rust_demo'].lifespan.ready


@pytest.mark.asyncio
async def test_native_python_coroutine_bridge_keeps_context_and_cancellation(plugin: DiscoveredPlugin) -> None:
    trace = ContextVar('native_test_trace', default='missing')
    started = asyncio.Event()
    closed = asyncio.Event()
    loop = asyncio.get_running_loop()

    async def service(context: PluginRequestContext) -> None:
        assert asyncio.get_running_loop() is loop
        assert trace.get() == 'current-request'
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    host = PluginHostContext('rust_demo', plugin.backend_path, services={'users.current_profile.v1': service})
    context = PluginRequestContext(host, object(), frozenset({'rust_demo:profile'}))
    native_profile = PluginEntrypointLoader(plugin).load_callable('ruoyi_plugin_rust_demo._native:profile')
    token = trace.set('current-request')
    try:
        task = asyncio.create_task(await_plugin_callback(native_profile, context))
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
    finally:
        trace.reset(token)


@pytest.mark.asyncio
async def test_native_python_service_exception_propagates(plugin: DiscoveredPlugin) -> None:
    async def failed_service(context: PluginRequestContext) -> None:
        raise ValueError('host-service-failed')

    host = PluginHostContext('rust_demo', plugin.backend_path, services={'users.current_profile.v1': failed_service})
    context = PluginRequestContext(host, object())
    native_profile = PluginEntrypointLoader(plugin).load_callable('ruoyi_plugin_rust_demo._native:profile')
    with pytest.raises(ValueError, match='host-service-failed'):
        await await_plugin_callback(native_profile, context)


@pytest.mark.asyncio
async def test_real_native_router_gets_host_context_and_permissions(plugin: DiscoveredPlugin) -> None:
    manifest = plugin.manifest.model_copy(deep=True)
    manifest.backend.integration = 'router'
    manifest.backend.asgi = None
    manifest.backend.entrypoint = 'ruoyi_plugin_rust_demo._native:create_router_plugin'
    router_plugin = replace(plugin, manifest=manifest)
    app = FastAPI()
    gateway = SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True))
    runtime = ExplicitPluginRuntime(gateway)
    user = SimpleNamespace(user=SimpleNamespace(user_id=7), permissions=['rust_demo:view', 'rust_demo:profile'])

    async def login(token: str = Depends(oauth2_scheme)) -> object:
        assert token == 'test-token'
        return user

    async def session() -> AsyncIterator[object]:
        yield object()

    app.dependency_overrides[LoginService.get_current_user] = login
    app.dependency_overrides[get_db_session_provider(None)] = session

    @app.exception_handler(PermissionException)
    async def permission_error(request: object, exc: PermissionException) -> JSONResponse:
        return JSONResponse({'detail': exc.message}, status_code=status.HTTP_403_FORBIDDEN)

    with patch('plugins.core.runtime.explicit.DataSourceRegistry.session', fake_session):
        runtime.prepare(RegisteredPlugin(router_plugin, None, True, 'installed'), app, startup_write_enabled=False)
    await runtime.activate('rust_demo', app)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            path = '/rust_demo/api/info'
            assert (await client.get(path)).status_code == status.HTTP_401_UNAUTHORIZED
            headers = {'Authorization': 'Bearer test-token'}
            response = await client.get(path, headers=headers)
            assert response.status_code == status.HTTP_200_OK, response.text
            assert response.json()['engine'] == 'rust'
            user.permissions = ['rust_demo:view']
            response = await client.get('/rust_demo/api/profile', headers=headers)
            assert response.status_code == status.HTTP_403_FORBIDDEN
            user.permissions = ['unrelated:view']
            assert (await client.get(path, headers=headers)).status_code == status.HTTP_403_FORBIDDEN
            gateway.is_plugin_enabled.return_value = False
            assert (await client.get(path, headers=headers)).status_code == status.HTTP_403_FORBIDDEN
            gateway.is_plugin_enabled.return_value = True
            user.permissions = ['rust_demo:view']
            await runtime.shutdown()
            assert (await client.get(path, headers=headers)).status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    finally:
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_real_scheduler_invokes_rust_awaitable_through_persistent_dispatcher(plugin: DiscoveredPlugin) -> None:
    app = FastAPI()
    gateway = SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True))
    runtime = ExplicitPluginRuntime(gateway)
    scheduler = AsyncIOScheduler()
    completed = asyncio.get_running_loop().create_future()

    def on_execution(event: object) -> None:
        if not completed.done():
            completed.set_result(event)

    scheduler.add_listener(on_execution, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    with patch('plugins.core.runtime.explicit.DataSourceRegistry.session', fake_session):
        runtime.prepare(RegisteredPlugin(plugin, None, True, 'installed'), app, startup_write_enabled=False)
    await runtime.activate('rust_demo', app)
    try:
        job = plugin.manifest.backend.jobs[0]
        assert not job.enabled
        options = JobAdapter.prepare(PluginJobModelBuilder.build('rust_demo', job, manifest=plugin.manifest))
        # 显式单次触发测试；不安装或启用真实数据库中的默认停用示例任务。
        options.pop('trigger')
        scheduler.add_job(trigger='date', **options)
        scheduler.start()
        event = await asyncio.wait_for(completed, 5)
        assert event.exception is None, event.exception
        assert event.retval == 'heartbeat'
        gateway.is_plugin_enabled.return_value = False
        with pytest.raises(PermissionError, match='未启用'):
            await dispatch_plugin_job('rust_demo', 'heartbeat', '1.0.0')
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
        await runtime.shutdown()
    with pytest.raises(RuntimeError, match='未就绪'):
        await dispatch_plugin_job('rust_demo', 'heartbeat', '1.0.0')
