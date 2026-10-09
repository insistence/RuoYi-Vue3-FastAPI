import asyncio
import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml
from fastapi import FastAPI
from starlette import status
from starlette.types import Receive, Scope, Send

from common.aspect.db_session import get_db_session_provider
from module_admin.service.login_service import LoginService
from plugins.core.discovery.registry import PluginRegistry, RegisteredPlugin
from plugins.core.discovery.scanner import PluginScanner
from plugins.core.runtime.application import PluginApplicationRuntime
from plugins.core.runtime.asgi import PluginLifespanManager
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from plugins.core.runtime.startup import PluginRuntimeStartupManager
from plugins.core.runtime.startup_coordination import PluginStartupGenerationResolver
from plugins.core.sdk import PluginDefinition

ASGI_SOURCE = """
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from plugins.core.sdk import PluginDefinition

events = []

@asynccontextmanager
async def lifespan(app):
    events.append('start')
    yield {'resource': 'ready'}
    events.append('stop')

def create_plugin(host):
    def create_app(context):
        app = FastAPI(lifespan=lifespan)
        @app.get('/api/info')
        async def info(request: Request):
            ctx = request.state.plugin_context
            ctx.require_permission('runtime_test:view')
            return {'plugin': ctx.host.plugin_id, 'resource': request.state.resource}
        return app
    return PluginDefinition(app_factory=create_app)
"""


@pytest.fixture(autouse=True)
def clear_modules() -> Generator[None, None, None]:
    yield
    for name in list(sys.modules):
        if name.startswith('plugins.runtime_test'):
            sys.modules.pop(name, None)
    package = sys.modules.get('plugins')
    if package is not None:
        for name in list(vars(package)):
            if name.startswith('runtime_test'):
                delattr(package, name)


def write_plugin(
    root: Path,
    *,
    plugin_id: str = 'runtime_test',
    source: str = ASGI_SOURCE,
    dependencies: list[str] | None = None,
    integration: str = 'asgi',
) -> RegisteredPlugin:
    directory = root / 'plugins' / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        'manifestVersion': 2,
        'id': plugin_id,
        'name': 'Test',
        'version': '1.0.0',
        'backend': {
            'module': f'plugins.{plugin_id}',
            'entrypoint': f'plugins.{plugin_id}:create_plugin',
            'integration': integration,
        },
        'permissions': [f'{plugin_id}:view'],
        'dependencies': {'plugins': dependencies or []},
    }
    (directory / 'plugin.yaml').write_text(yaml.safe_dump(manifest), encoding='utf-8')
    (directory / '__init__.py').write_text(source, encoding='utf-8')
    discovered = PluginScanner(directory.parent).load_manifest(directory / 'plugin.yaml')
    return RegisteredPlugin(discovered, None, True, 'installed')


@asynccontextmanager
async def fake_session() -> AsyncGenerator[object, None]:
    yield object()


@pytest.mark.asyncio
async def test_main_runtime_mounts_authenticates_and_stops_subapplication(tmp_path: Path) -> None:
    plugin = write_plugin(tmp_path)
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry([plugin])
    app.state.redis = object()
    gateway = SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True))
    manager = PluginRuntimeStartupManager(route_state_gateway=gateway, default_enabled_builtin_plugin_ids=set())
    login = AsyncMock(return_value=SimpleNamespace(permissions=['runtime_test:view']))
    with (
        patch('plugins.core.runtime.explicit.DataSourceRegistry.session', fake_session),
        patch('plugins.core.runtime.explicit.LoginService.get_current_user', login),
    ):
        await manager.prepare_explicit_plugins(app, startup_write_enabled=False)
        await manager.activate_explicit_plugins(app, startup_write_enabled=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            path = '/apps/runtime_test/api/info'
            assert (await client.get(path)).status_code == status.HTTP_401_UNAUTHORIZED
            response = await client.get(path, headers={'Authorization': 'Bearer test'})
            assert response.json() == {'plugin': 'runtime_test', 'resource': 'ready'}
            login.assert_awaited_once()
            assert login.call_args.kwargs['request'].app is app
            login.return_value = SimpleNamespace(permissions=['unrelated:view'])
            assert (
                await client.get(path, headers={'Authorization': 'Bearer test'})
            ).status_code == status.HTTP_403_FORBIDDEN
            gateway.is_plugin_enabled.return_value = False
            assert (
                await client.get(path, headers={'Authorization': 'Bearer test'})
            ).status_code == status.HTTP_403_FORBIDDEN
        await manager.shutdown(app, startup_write_enabled=False)
    assert sys.modules['plugins.runtime_test'].events == ['start', 'stop']


@pytest.mark.asyncio
async def test_router_requests_are_observed_after_fastapi_registration(tmp_path: Path) -> None:
    """Router 接入的实际路由也记录业务响应和接口权限拒绝。"""
    source = """
from fastapi import APIRouter, HTTPException, Request
from plugins.core.sdk import PluginDefinition
def create_plugin(host):
    router = APIRouter(prefix='/runtime_test')
    @router.get('/info')
    async def info(request: Request):
        return {'requestId': request.state.plugin_context.request_id}
    @router.get('/denied')
    async def denied():
        raise HTTPException(status_code=403, detail='denied')
    return PluginDefinition(routers=(router,))
"""
    plugin = write_plugin(tmp_path, source=source, integration='router')
    app = FastAPI()
    app.dependency_overrides[get_db_session_provider(None)] = object
    app.dependency_overrides[LoginService.get_current_user] = lambda: SimpleNamespace(permissions=['runtime_test:view'])
    runtime = ExplicitPluginRuntime(SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True)))
    runtime.prepare(plugin, app, startup_write_enabled=False)
    try:
        await runtime.activate('runtime_test', app)
        assert '/runtime_test/info' in app.openapi()['paths']
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/runtime_test/info')
            assert response.status_code == status.HTTP_200_OK
            assert response.json()['requestId']
            assert (await client.get('/runtime_test/denied')).status_code == status.HTTP_403_FORBIDDEN
        metric = runtime.metrics.snapshot().series[0]
        assert (metric.started, metric.active, metric.succeeded, metric.rejected) == (2, 0, 1, 1)
    finally:
        await runtime.shutdown()


def test_dependency_cycle_and_missing_dependency_do_not_block_independent_plugin(tmp_path: Path) -> None:
    first = write_plugin(tmp_path, plugin_id='runtime_test_a', dependencies=['runtime_test_b'])
    second = write_plugin(tmp_path, plugin_id='runtime_test_b', dependencies=['runtime_test_a'])
    missing = write_plugin(tmp_path, plugin_id='runtime_test_missing', dependencies=['absent'])
    independent = write_plugin(tmp_path, plugin_id='runtime_test_ok')
    ordered, errors = ExplicitPluginRuntime.dependency_order(PluginRegistry([first, second, missing, independent]))
    assert [plugin.plugin_id for plugin in ordered] == ['runtime_test_ok']
    assert set(errors) == {'runtime_test_a', 'runtime_test_b', 'runtime_test_missing'}


def test_dependency_order_starts_dependencies_first(tmp_path: Path) -> None:
    consumer = write_plugin(tmp_path, plugin_id='runtime_test_consumer', dependencies=['runtime_test_base'])
    base = write_plugin(tmp_path, plugin_id='runtime_test_base')
    ordered, errors = ExplicitPluginRuntime.dependency_order(PluginRegistry([consumer, base]))
    assert not errors
    assert [plugin.plugin_id for plugin in ordered] == ['runtime_test_base', 'runtime_test_consumer']


@pytest.mark.asyncio
async def test_failed_startup_leaves_no_mount_and_isolates_plugin(tmp_path: Path) -> None:
    plugin = write_plugin(
        tmp_path, source=ASGI_SOURCE.replace("events.append('start')", "raise RuntimeError('broken')")
    )
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry([plugin])
    manager = PluginRuntimeStartupManager(default_enabled_builtin_plugin_ids=set())
    await manager.prepare_explicit_plugins(app, startup_write_enabled=False)
    await manager.activate_explicit_plugins(app, startup_write_enabled=False)
    assert not app.state.plugin_registry.get_plugin('runtime_test').enabled
    assert all(getattr(route, 'path', '') != '/apps/runtime_test' for route in app.routes)
    await manager.shutdown(app, startup_write_enabled=False)


@pytest.mark.asyncio
async def test_health_failure_after_startup_shuts_down_child(tmp_path: Path) -> None:
    plugin = write_plugin(tmp_path, source=ASGI_SOURCE + '\nasync def check(context): return False\n')
    plugin.discovered_plugin.manifest.backend.health.checker = 'plugins.runtime_test:check'
    app = FastAPI()
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    runtime.prepare(plugin, app, startup_write_enabled=False)
    with pytest.raises(RuntimeError, match='健康检查'):
        await runtime.activate('runtime_test', app)
    assert sys.modules['plugins.runtime_test'].events == ['start', 'stop']
    assert all(getattr(route, 'path', '') != '/apps/runtime_test' for route in app.routes)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_at', ['metrics', 'connection', 'job', 'lifespan'])
async def test_shutdown_isolates_cleanup_failures_and_closes_in_reverse_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: str
) -> None:
    """一个清理步骤失败后继续其余资源及依赖插件，关闭开始即拒绝全部激活。"""
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    app = FastAPI()
    for plugin_id in ['runtime_test_base', 'runtime_test_consumer']:
        runtime.prepare(write_plugin(tmp_path, plugin_id=plugin_id), app, startup_write_enabled=False)
        await runtime.activate(plugin_id, app)
    order = []

    async def step(name: str, *, fails: bool = False) -> None:
        assert all(not loaded.active for loaded in runtime.loaded.values())
        with pytest.raises(RuntimeError, match='关闭阶段'):
            await runtime.activate('runtime_test_base', app)
        order.append(name)
        if fails:
            raise RuntimeError('cleanup failed')

    metrics_stop = AsyncMock(side_effect=lambda: None)
    if failure_at == 'metrics':
        metrics_stop.side_effect = RuntimeError('metrics failed')
    monkeypatch.setattr(runtime.metrics_reporter, 'stop', metrics_stop)
    consumer = runtime.loaded['runtime_test_consumer']
    actual_shutdown = consumer.lifespan.shutdown

    async def consumer_lifespan() -> None:
        await actual_shutdown()
        await step('consumer:lifespan', fails=failure_at == 'lifespan')

    async def consumer_connection() -> None:
        await step('consumer:connection', fails=failure_at == 'connection')

    async def consumer_jobs(binding: object) -> None:
        await step('consumer:job', fails=failure_at == 'job')

    monkeypatch.setattr(consumer.lifespan, 'shutdown', consumer_lifespan)
    monkeypatch.setattr(consumer.gateway, 'drain', consumer_connection)
    consumer.jobs = SimpleNamespace(tasks=set())
    monkeypatch.setattr('plugins.core.runtime.explicit.unbind_plugin_jobs', consumer_jobs)
    try:
        await runtime.shutdown()
        assert order == ['consumer:connection', 'consumer:job', 'consumer:lifespan']
        assert sys.modules['plugins.runtime_test_base'].events == ['start', 'stop']
        assert sys.modules['plugins.runtime_test_consumer'].events == ['start', 'stop']
        assert all(not loaded.lifespan.ready for loaded in runtime.loaded.values())
        metrics_stop.assert_awaited_once()
    finally:
        await actual_shutdown()
        await runtime.loaded['runtime_test_base'].lifespan.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize('integration', ['router', 'asgi'])
async def test_shutdown_during_health_check_cannot_publish_late_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, integration: str
) -> None:
    """关闭与激活并发时，健康检查完成不能重新发布路由或恢复 active。"""
    source = (
        ASGI_SOURCE
        if integration == 'asgi'
        else (
            'from plugins.core.sdk import PluginDefinition\n'
            'from fastapi import APIRouter\n'
            'def create_plugin(host):\n'
            '    router = APIRouter()\n'
            '    router.add_api_route("/runtime_test/info", lambda: {})\n'
            '    return PluginDefinition(routers=[router])\n'
        )
    )
    plugin = write_plugin(tmp_path, source=source, integration=integration)
    app = FastAPI()
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    runtime.prepare(plugin, app, startup_write_enabled=False)
    entered, release = asyncio.Event(), asyncio.Event()

    async def check(*args: object) -> None:
        entered.set()
        await release.wait()

    monkeypatch.setattr(runtime, '_check_health', check)
    activating = asyncio.create_task(runtime.activate('runtime_test', app))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        await runtime.shutdown()
        release.set()
        with pytest.raises(RuntimeError, match='关闭阶段'):
            await activating
        assert not runtime.loaded['runtime_test'].active
        assert all('runtime_test' not in getattr(route, 'path', '') for route in app.routes)
        if integration == 'asgi':
            assert sys.modules['plugins.runtime_test'].events == ['start', 'stop']
    finally:
        release.set()
        await asyncio.gather(activating, return_exceptions=True)
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_failed_activation_cannot_replace_pending_lifespan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """显式运行时保留启动失败的管理器，旧资源退出前不能创建第二个子应用。"""
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    app = FastAPI()
    runtime.prepare(write_plugin(tmp_path), app, startup_write_enabled=False)
    release = asyncio.Event()
    attempts = []

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        attempts.append(scope)
        await receive()
        if len(attempts) == 1:
            while not release.is_set():
                with suppress(asyncio.CancelledError):
                    await release.wait()
            raise RuntimeError('old resource stopped')
        await send({'type': 'lifespan.startup.complete'})
        await receive()
        await send({'type': 'lifespan.shutdown.complete'})

    loaded = runtime.loaded['runtime_test']
    loaded.definition = PluginDefinition(app_factory=lambda _: child)
    monkeypatch.setattr(
        'plugins.core.runtime.explicit.PluginLifespanManager',
        lambda child, **kwargs: PluginLifespanManager(child, timeout=0.01, cancel_timeout=0.01, **kwargs),
    )
    activating = asyncio.create_task(runtime.activate('runtime_test', app))
    try:
        await asyncio.wait({activating}, timeout=1)
        assert activating.done()
        with pytest.raises(TimeoutError):
            await activating
        assert loaded.lifespan.has_pending_task
        with pytest.raises(RuntimeError, match='上一次生命周期尚未退出'):
            await runtime.activate('runtime_test', app)
        assert len(attempts) == 1
        release.set()
        await asyncio.wait({loaded.lifespan._task}, timeout=1)
        await runtime.activate('runtime_test', app)
        assert loaded.active and loaded.lifespan.ready
        assert [scope['type'] for scope in attempts] == ['lifespan', 'lifespan']
        assert sum(getattr(route, 'path', '') == '/apps/runtime_test' for route in app.routes) == 1
    finally:
        release.set()
        await asyncio.gather(activating, return_exceptions=True)
        await runtime.shutdown()


@pytest.mark.asyncio
async def test_activation_cleanup_failure_preserves_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    app = FastAPI()
    plugin = write_plugin(tmp_path, source=ASGI_SOURCE.replace("events.append('stop')", "raise ValueError('cleanup')"))
    runtime.prepare(plugin, app, startup_write_enabled=False)
    monkeypatch.setattr(runtime, '_check_health', AsyncMock(side_effect=LookupError('primary health failure')))
    with pytest.raises(LookupError, match='primary health failure'):
        await runtime.activate('runtime_test', app)
    assert not runtime.loaded['runtime_test'].lifespan.has_pending_task


@pytest.mark.asyncio
async def test_cancelled_activation_closes_previously_started_children(tmp_path: Path) -> None:
    first = write_plugin(tmp_path, plugin_id='runtime_test_first')
    second = write_plugin(tmp_path, plugin_id='runtime_test_second')
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry([first, second])
    manager = PluginRuntimeStartupManager(default_enabled_builtin_plugin_ids=set())
    await manager.prepare_explicit_plugins(app, startup_write_enabled=False)
    runtime = app.state.plugin_explicit_runtime
    activate = runtime.activate

    async def cancel_second(plugin_id: str, target: FastAPI) -> None:
        if plugin_id == second.plugin_id:
            raise asyncio.CancelledError
        await activate(plugin_id, target)

    runtime.activate = cancel_second
    with pytest.raises(asyncio.CancelledError):
        await manager.activate_explicit_plugins(app, startup_write_enabled=False)
    assert sys.modules['plugins.runtime_test_first'].events == ['start', 'stop']
    assert not runtime.loaded[first.plugin_id].lifespan.ready


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [ConnectionError('ready write failed'), asyncio.CancelledError()])
async def test_ready_publication_failure_closes_started_children(tmp_path: Path, failure: BaseException) -> None:
    plugin = write_plugin(tmp_path)
    app = FastAPI()
    app.state.plugin_registry = PluginRegistry([plugin])
    app.state.redis = SimpleNamespace(
        get=AsyncMock(return_value=None), delete=AsyncMock(), set=AsyncMock(side_effect=failure)
    )
    manager = PluginRuntimeStartupManager(default_enabled_builtin_plugin_ids=set())
    runtime = PluginApplicationRuntime(manager, startup_generation='test-release')
    # 保留真实 ASGI 启停和 writer 协调，只替换数据库资源同步。
    with (
        patch.object(manager, 'prepare_enabled_plugins', manager.prepare_explicit_plugins),
        patch.object(manager, 'activate_enabled_plugins', manager.activate_explicit_plugins),
        pytest.raises(type(failure)),
    ):
        await runtime.startup(app, create_tables=AsyncMock())
    assert sys.modules['plugins.runtime_test'].events == ['start', 'stop']
    assert not app.state.plugin_explicit_runtime.loaded[plugin.plugin_id].lifespan.ready


@pytest.mark.asyncio
async def test_router_namespace_validation_is_atomic(tmp_path: Path) -> None:
    source = """
from fastapi import APIRouter
from plugins.core.sdk import PluginDefinition
def create_plugin(host):
    valid = APIRouter()
    invalid = APIRouter()
    valid.add_api_route('/runtime_test/data', lambda: {})
    invalid.add_api_route('/system/data', lambda: {})
    return PluginDefinition(routers=[valid, invalid])
"""
    plugin = write_plugin(tmp_path, source=source, integration='router')
    app = FastAPI()
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    runtime.prepare(plugin, app, startup_write_enabled=False)
    with pytest.raises(ValueError, match='命名空间'):
        await runtime.activate('runtime_test', app)
    assert all(getattr(route, 'path', '') != '/runtime_test/data' for route in app.routes)


def test_generation_covers_native_and_bundle_content(tmp_path: Path) -> None:
    plugin = write_plugin(tmp_path)
    root = plugin.backend_path
    resolver = PluginStartupGenerationResolver(tmp_path, release_id='')
    first = resolver.resolve()
    library = root / 'entry.pyd'
    library.write_bytes(b'version1')
    second = resolver.resolve()
    assert first != second
    library.write_bytes(b'version2')
    assert second != resolver.resolve()

    path = root / 'plugin.yaml'
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    data['frontend'] = {'delivery': {'type': 'bundle'}, 'bundle': {}}
    path.write_text(yaml.safe_dump(data), encoding='utf-8')
    asset = root / 'web' / 'dist' / 'assets' / 'app.js'
    asset.parent.mkdir(parents=True)
    asset.write_text('version1', encoding='utf-8')
    first = resolver.resolve()
    asset.write_text('version2', encoding='utf-8')
    second = resolver.resolve()
    assert first != second
    (root / 'web' / 'dist' / '__pycache__').mkdir()
    (root / 'web' / 'dist' / '__pycache__' / 'cache.pyc').write_bytes(b'cache')
    assert resolver.resolve() == second
