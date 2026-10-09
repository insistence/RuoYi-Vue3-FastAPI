import asyncio
import json
import sys
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from starlette import status

from common.aspect.db_session import get_db_session_provider
from common.enums import RedisInitKeyConfig
from config.env import AppConfig, TransportCryptoConfig
from exceptions.exception import AuthException
from middlewares.transport_crypto_middleware import TransportCryptoMiddleware
from module_admin.dao.user_dao import UserDao
from module_admin.entity.do.user_do import SysUser
from module_admin.service.login_service import LoginService, oauth2_scheme
from module_plugin.controller.plugin_browser_controller import plugin_browser_controller
from plugins.core.discovery.registry import RegisteredPlugin
from plugins.core.discovery.scanner import PluginScanner
from plugins.core.runtime.browser_session import COOKIE_NAME_PREFIX, SESSION_KEY_PREFIX
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from utils.jwt_util import JwtUtil


class MemoryRedis:
    """实现本协议使用的原子 NX/expire，并允许明确模拟到期。"""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.deadlines: dict[str, float] = {}

    async def get(self, key: str) -> str | None:
        if self.deadlines.get(key, float('inf')) <= time.time():
            self.values.pop(key, None)
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int = 300, nx: bool = False) -> bool:
        if nx and await self.get(key) is not None:
            return False
        self.values[key] = value
        self.deadlines[key] = time.time() + ex
        return True

    async def expire(self, key: str, seconds: int) -> bool:
        if await self.get(key) is None:
            return False
        self.deadlines[key] = time.time() + seconds
        return True


SOURCE = """
from fastapi import FastAPI, Request
from plugins.core.sdk import PluginDefinition, plugin_endpoint

async def info(ctx):
    return {'pluginId': ctx.host.plugin_id, 'userId': ctx.user.user.user_id}

def create_plugin(host):
    def create_app(context):
        app = FastAPI()
        app.add_api_route('/api/info', plugin_endpoint(info, permission='browser_test:view'))
        @app.post('/api/echo')
        async def echo(request: Request):
            request.state.plugin_context.require_permission('browser_test:view')
            return await request.json()
        return app
    return PluginDefinition(app_factory=create_app)
"""


@pytest_asyncio.fixture
async def browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    directory = tmp_path / 'plugins' / 'browser_test'
    (directory / 'web' / 'dist' / 'assets').mkdir(parents=True)
    (directory / 'web' / 'dist' / 'index.html').write_text('<html><head></head><body>Bundle</body></html>')
    (directory / 'web' / 'dist' / 'assets' / 'app.js').write_text('export const plugin = true')
    (directory / '__init__.py').write_text(SOURCE)
    data = {
        'manifestVersion': 2,
        'id': 'browser_test',
        'name': 'Browser test',
        'version': '1.0.0',
        'backend': {
            'module': 'plugins.browser_test',
            'entrypoint': 'plugins.browser_test:create_plugin',
            'integration': 'asgi',
        },
        'frontend': {'delivery': {'type': 'bundle'}, 'bundle': {}},
        'permissions': ['browser_test:view'],
    }
    (directory / 'plugin.yaml').write_text(yaml.safe_dump(data))
    plugin = PluginScanner(directory.parent).load_manifest(directory / 'plugin.yaml')
    app = FastAPI()
    app.state.redis = redis = MemoryRedis()
    runtime = ExplicitPluginRuntime(SimpleNamespace(is_plugin_enabled=AsyncMock(return_value=True)))
    app.state.plugin_explicit_runtime = runtime
    user = SimpleNamespace(user=SimpleNamespace(user_id=7), permissions=['browser_test:view'])
    token = JwtUtil.encode({'user_id': '7', 'session_id': 'test-session', 'exp': int(time.time()) + 1800})
    main_key = f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:test-session'
    await redis.set(main_key, token, ex=1800)
    monkeypatch.setattr(AppConfig, 'app_same_time_login', True)
    monkeypatch.setattr(AppConfig, 'app_root_path', '')
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_enabled', False)

    async def current_user(token_value: str = Depends(oauth2_scheme)) -> object:
        if token_value != token:
            raise HTTPException(status_code=401)
        return user

    async def session_dependency() -> AsyncIterator[object]:
        yield object()

    @asynccontextmanager
    async def session() -> AsyncGenerator[object, None]:
        yield object()

    app.dependency_overrides[LoginService.get_current_user] = current_user
    app.dependency_overrides[get_db_session_provider(None)] = session_dependency
    login = AsyncMock(return_value=user)
    monkeypatch.setattr(LoginService, 'get_current_user', login)
    monkeypatch.setattr(LoginService, 'get_current_user_for_plugin_session', login)
    monkeypatch.setattr('plugins.core.runtime.explicit.DataSourceRegistry.session', session)
    app.include_router(plugin_browser_controller)

    @app.get('/system/private')
    async def private(token_value: Annotated[str, Depends(oauth2_scheme)]) -> dict:
        return {'authenticated': bool(token_value)}

    app.add_middleware(TransportCryptoMiddleware)
    runtime.prepare(RegisteredPlugin(plugin, None, True, 'installed'), app, startup_write_enabled=False)
    await runtime.activate('browser_test', app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://test') as client:
        try:
            yield SimpleNamespace(
                app=app,
                client=client,
                redis=redis,
                token=token,
                main_key=main_key,
                runtime=runtime,
                user=user,
                login=login,
                plugin=plugin,
            )
        finally:
            await runtime.shutdown()
    sys.modules.pop('plugins.browser_test', None)
    package = sys.modules.get('plugins')
    if package is not None and hasattr(package, 'browser_test'):
        delattr(package, 'browser_test')


async def issue(browser: SimpleNamespace) -> httpx.Response:
    return await browser.client.post(
        '/plugin/runtime/browser_test/session',
        headers={
            'Authorization': f'Bearer {browser.token}',
            'Origin': 'https://test',
        },
    )


@pytest.mark.asyncio
async def test_issued_cookie_loads_ui_and_api_but_never_host_api(browser: SimpleNamespace) -> None:
    client = browser.client
    assert (await client.get('/apps/browser_test/ui/')).status_code == status.HTTP_401_UNAUTHORIZED
    response = await issue(browser)
    assert response.status_code == status.HTTP_200_OK, response.text
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
    assert 'Path=/apps/browser_test/' in cookie
    assert browser.token not in response.text and browser.token not in cookie
    records = [raw for key, raw in browser.redis.values.items() if key.startswith(SESSION_KEY_PREFIX)]
    assert all(browser.token not in raw for raw in records)
    page = await client.get('/apps/browser_test/ui/reports/month', headers={'Accept': 'text/html'})
    assert page.status_code == status.HTTP_200_OK
    assert 'ruoyi-plugin-config' in page.text and browser.token not in page.text
    assert (await client.get('/apps/browser_test/ui/assets/app.js')).status_code == status.HTTP_200_OK
    api = await client.get('/apps/browser_test/api/info')
    assert api.json()['userId'] == browser.user.user.user_id
    assert browser.login.await_args.kwargs['token'] == browser.token
    # 即使手工把路径受限 Cookie 附到宿主端点，也不能替代主 Bearer。
    raw_cookie = f'{COOKIE_NAME_PREFIX}browser_test=' + client.cookies.get(f'{COOKIE_NAME_PREFIX}browser_test')
    assert (
        await client.get('/system/private', headers={'Cookie': raw_cookie})
    ).status_code == status.HTTP_401_UNAUTHORIZED
    assert (
        await client.post('/plugin/runtime/browser_test/session', headers={'Cookie': raw_cookie})
    ).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_multitab_renewal_reuses_cookie_and_csrf(browser: SimpleNamespace) -> None:
    first, second = await asyncio.gather(issue(browser), issue(browser))
    assert first.json()['data']['csrfToken'] == second.json()['data']['csrfToken']
    assert first.cookies == second.cookies
    assert len([key for key in browser.redis.values if key.startswith(SESSION_KEY_PREFIX)]) == 1


@pytest.mark.asyncio
async def test_cookie_writes_require_origin_and_csrf(browser: SimpleNamespace) -> None:
    response = await issue(browser)
    csrf = response.json()['data']['csrfToken']
    for headers in (
        {},
        {'Origin': 'https://evil.test', 'X-Plugin-CSRF': csrf},
        {'Origin': 'https://test'},
        {'Origin': 'https://test', 'X-Plugin-CSRF': 'wrong'},
    ):
        result = await browser.client.post('/apps/browser_test/api/echo', json={'value': 'safe'}, headers=headers)
        assert result.status_code == status.HTTP_403_FORBIDDEN
    result = await browser.client.post(
        '/apps/browser_test/api/echo', json={'value': 'safe'}, headers={'Origin': 'https://test', 'X-Plugin-CSRF': csrf}
    )
    assert result.json() == {'value': 'safe'}


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['logout', 'replaced', 'expired', 'disabled', 'permission', 'version', 'nonce'])
async def test_session_fails_closed_after_binding_or_access_changes(browser: SimpleNamespace, reason: str) -> None:
    await issue(browser)
    key = next(key for key in browser.redis.values if key.startswith(SESSION_KEY_PREFIX))
    if reason == 'logout':
        browser.redis.values.pop(browser.main_key)
    elif reason == 'replaced':
        browser.redis.values[browser.main_key] = 'new-main-token'
    elif reason == 'expired':
        browser.redis.deadlines[key] = 0
    elif reason == 'disabled':
        browser.runtime.route_state_gateway.is_plugin_enabled.return_value = False
    elif reason == 'permission':
        browser.user.permissions = []
    elif reason == 'version':
        browser.plugin.manifest.version = '2.0.0'
    else:
        record = json.loads(browser.redis.values[key])
        record['nonce'] = 'x' * 43
        browser.redis.values[key] = json.dumps(record)
    response = await browser.client.get('/apps/browser_test/api/info')
    assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
    page = await browser.client.get('/apps/browser_test/ui/', headers={'Accept': 'text/html'})
    assert page.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}


@pytest.mark.asyncio
async def test_cross_origin_issuance_and_unknown_plugin_rejected(browser: SimpleNamespace) -> None:
    headers = {'Authorization': f'Bearer {browser.token}', 'Origin': 'https://evil.test'}
    assert (
        await browser.client.post('/plugin/runtime/browser_test/session', headers=headers)
    ).status_code == status.HTTP_403_FORBIDDEN
    headers['Origin'] = 'https://test'
    assert (
        await browser.client.post('/plugin/runtime/unknown/session', headers=headers)
    ).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_required_encryption_bypasses_only_readonly_registered_ui(
    browser: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    await issue(browser)
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_enabled', True)
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_mode', 'required')
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_enabled_paths', '')
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_exclude_paths', '')
    for method in ('record_plain_request', 'record_required_rejected', 'record_plain_response'):
        monkeypatch.setattr(f'middlewares.transport_crypto_middleware.TransportCryptoMonitorUtil.{method}', AsyncMock())
    page = await browser.client.get('/apps/browser_test/ui/', headers={'Accept': 'text/html'})
    assert page.status_code == status.HTTP_200_OK
    assert (await browser.client.get('/apps/browser_test/ui/assets/app.js')).status_code == status.HTTP_200_OK
    for path in (
        '/apps/browser_test/api/info',
        '/apps/unknown/ui/',
        '/plugin/runtime/browser_test/session',
        '/apps/browser_test/uievil',
    ):
        response = await browser.client.get(path)
        assert response.headers['x-transport-crypto-status'] == 'required_missing'
    response = await browser.client.post('/apps/browser_test/ui/')
    assert response.headers['x-transport-crypto-status'] == 'required_missing'


@pytest.mark.asyncio
async def test_renewal_retries_if_record_expires_and_another_tab_replaces_it(
    browser: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await issue(browser)
    key = next(key for key in browser.redis.values if key.startswith(SESSION_KEY_PREFIX))
    replacement = json.loads(browser.redis.values[key])
    replacement.update(nonce='n' * 43, csrf='c' * 43)
    expire = browser.redis.expire
    replaced = False

    async def replace_before_expire(record_key: str, seconds: int) -> bool:
        nonlocal replaced
        if not replaced:
            replaced = True
            browser.redis.values.pop(record_key)
            # 另一标签在旧 GET 与 EXPIRE 之间成功写入新的 nonce/CSRF。
            assert await browser.redis.set(record_key, json.dumps(replacement), ex=seconds, nx=True)
        return await expire(record_key, seconds)

    monkeypatch.setattr(browser.redis, 'expire', replace_before_expire)
    renewed = await issue(browser)
    assert renewed.status_code == status.HTTP_200_OK
    assert renewed.json()['data']['csrfToken'] == replacement['csrf']
    assert renewed.json()['data']['csrfToken'] != first.json()['data']['csrfToken']
    cookie = renewed.cookies.get(f'{COOKIE_NAME_PREFIX}browser_test')
    assert cookie.endswith('.' + replacement['nonce'])
    assert (await browser.client.get('/apps/browser_test/api/info')).status_code == status.HTTP_200_OK


@pytest.mark.asyncio
@pytest.mark.parametrize('same_time_login', [True, False])
@pytest.mark.parametrize('logout_after_read', [True, False])
async def test_real_plugin_login_resolution_does_not_refresh_or_restore_main_session(
    monkeypatch: pytest.MonkeyPatch, same_time_login: bool, logout_after_read: bool
) -> None:
    monkeypatch.setattr(AppConfig, 'app_same_time_login', same_time_login)
    redis = MemoryRedis()
    app = FastAPI()
    app.state.redis = redis
    request = Request({'type': 'http', 'app': app})
    user_id = 7
    token = JwtUtil.encode({'user_id': str(user_id), 'session_id': 'read-only-session', 'exp': int(time.time()) + 1800})
    subject = 'read-only-session' if same_time_login else str(user_id)
    key = f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{subject}'
    await redis.set(key, token, ex=1800)
    deadline = redis.deadlines[key]
    original_get = redis.get

    async def get_with_concurrent_logout(record_key: str) -> str | None:
        value = await original_get(record_key)
        if record_key == key and logout_after_read:
            redis.values.pop(key, None)
        return value

    set_spy = AsyncMock(wraps=redis.set)
    monkeypatch.setattr(redis, 'get', get_with_concurrent_logout)
    monkeypatch.setattr(redis, 'set', set_spy)
    monkeypatch.setattr(
        UserDao,
        'get_user_by_id',
        AsyncMock(
            return_value={
                'user_basic_info': SysUser(
                    user_id=user_id, user_name='plugin-user', nick_name='Plugin', time_zone='auto'
                ),
                'user_role_info': [],
                'user_post_info': [],
                'user_dept_info': None,
                'user_menu_info': [SimpleNamespace(perms='demo:view')],
            }
        ),
    )
    # 不替换 _resolve_current_user，验证真实 JWT、用户模型和权限构造路径。
    user = await LoginService.get_current_user_for_plugin_session(request, token, object())
    assert user.user.user_id == user_id
    assert user.permissions == ['demo:view']
    set_spy.assert_not_awaited()
    assert redis.deadlines[key] == deadline
    if logout_after_read:
        assert key not in redis.values
        with pytest.raises(AuthException):
            await LoginService.get_current_user_for_plugin_session(request, token, object())
    else:
        assert redis.values[key] == token
