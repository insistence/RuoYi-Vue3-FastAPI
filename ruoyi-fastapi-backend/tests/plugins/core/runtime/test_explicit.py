import asyncio
import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml
from fastapi import FastAPI
from starlette import status

from plugins.core.discovery.registry import PluginRegistry, RegisteredPlugin
from plugins.core.discovery.scanner import PluginScanner
from plugins.core.runtime.application import PluginApplicationRuntime
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from plugins.core.runtime.startup import PluginRuntimeStartupManager
from plugins.core.runtime.startup_coordination import PluginStartupGenerationResolver

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
