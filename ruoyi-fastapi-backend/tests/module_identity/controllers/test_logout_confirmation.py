import re
from collections.abc import AsyncIterator, Iterator
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from common.aspect.db_session import get_db_session_provider
from config.env import OidcConfig
from middlewares.oidc_cors_middleware import OidcCorsMiddleware
from module_identity.controller.authorization_controller import authorization_controller
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dependencies import require_oidc_protocol_ready
from module_identity.service.infrastructure_service import OidcRateLimiter
from module_identity.service.logout_confirmation_service import LogoutConfirmationService
from module_identity.service.session_service import LogoutResult, LogoutService


class ConfirmationRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float]] = {}

    async def set(self, key: str, value: str, *, ex: int, nx: bool = False) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = (value, monotonic() + ex)
        return True

    async def eval(self, _script: str, _count: int, key: str) -> str | None:
        value, expires = self.values.pop(key, (None, 0))
        return value if expires > monotonic() else None


@pytest.fixture
def logout_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, AsyncMock]]:
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example')
    monkeypatch.setattr(OidcConfig, 'oidc_token_hash_pepper', 'logout-confirmation-test-' + 'x' * 32)
    monkeypatch.setattr(OidcRateLimiter, 'enforce', AsyncMock())
    monkeypatch.setattr(LogoutConfirmationService, 'form_redirect_origin', AsyncMock(return_value='https://rp.example'))
    app = FastAPI()
    app.add_middleware(OidcCorsMiddleware)
    app.state.redis = ConfirmationRedis()
    app.include_router(authorization_controller)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    async def get_db() -> AsyncIterator[SimpleNamespace]:
        yield db

    app.dependency_overrides[get_db_session_provider(None)] = get_db
    app.dependency_overrides[require_oidc_protocol_ready] = lambda: None
    execute = AsyncMock(return_value=LogoutResult('https://rp.example/done', 'state-1', True))
    monkeypatch.setattr(LogoutService, 'execute_logout', execute)
    with TestClient(app, base_url='https://auth.example', follow_redirects=False) as client:
        yield client, execute


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_standard_logout_requires_confirmation_then_redirects(
    logout_client: tuple[TestClient, AsyncMock], method: str
) -> None:
    client, execute = logout_client
    parameters = {
        'id_token_hint': 'private-hint',
        'post_logout_redirect_uri': 'https://rp.example/done',
        'state': 'state-1',
    }
    response = (
        client.get('/oauth2/logout', params=parameters)
        if method == 'GET'
        else client.post('/oauth2/logout', data=parameters)
    )
    assert response.status_code == status.HTTP_200_OK
    assert '确认退出' in response.text
    assert 'private-hint' not in response.text
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert "form-action 'self' https://rp.example;" in response.headers['content-security-policy']
    execute.assert_not_awaited()
    token = re.search(r'name="confirmation" value="([^"]+)"', response.text).group(1)
    response = client.post(
        '/oauth2/logout/confirm',
        data={'confirmation': token, 'decision': 'confirm'},
        headers={'Origin': 'https://auth.example'},
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers['location'] == 'https://rp.example/done?state=state-1'
    assert execute.await_args.kwargs['confirmed'] is True
    assert execute.await_args.kwargs['id_token_hint'] == 'private-hint'
    execute.reset_mock()
    replay = client.post(
        '/oauth2/logout/confirm',
        data={'confirmation': token, 'decision': 'confirm'},
        headers={'Origin': 'https://auth.example'},
    )
    assert replay.status_code == status.HTTP_400_BAD_REQUEST
    execute.assert_not_awaited()


def test_cancel_keeps_sso_cookie_and_never_calls_revocation(logout_client: tuple[TestClient, AsyncMock]) -> None:
    client, execute = logout_client
    client.cookies.set(OidcConfig.oidc_sso_cookie_name, 'current-sso', domain='auth.example', path='/')
    page = client.get('/oauth2/logout')
    token = re.search(r'name="confirmation" value="([^"]+)"', page.text).group(1)
    response = client.post(
        '/oauth2/logout/confirm',
        data={'confirmation': token, 'decision': 'cancel'},
        headers={'Origin': 'https://auth.example'},
    )
    assert response.status_code == status.HTTP_200_OK
    assert '已取消退出' in response.text
    assert OidcConfig.oidc_sso_cookie_name + '=' not in response.headers.get('set-cookie', '')
    execute.assert_not_awaited()


@pytest.mark.parametrize('attack', ['origin', 'cookie', 'expired'])
def test_confirmation_rejects_wrong_origin_browser_or_expiry(
    logout_client: tuple[TestClient, AsyncMock], attack: str
) -> None:
    client, execute = logout_client
    page = client.get('/oauth2/logout')
    token = re.search(r'name="confirmation" value="([^"]+)"', page.text).group(1)
    origin = 'https://evil.example' if attack == 'origin' else 'https://auth.example'
    if attack == 'cookie':
        client.cookies.clear()
    if attack == 'expired':
        redis = client.app.state.redis
        redis.values = {key: (value, 0) for key, (value, _expires) in redis.values.items()}
    response = client.post(
        '/oauth2/logout/confirm', data={'confirmation': token, 'decision': 'confirm'}, headers={'Origin': origin}
    )
    assert response.status_code in {400, 403}
    execute.assert_not_awaited()


def test_cross_site_post_may_omit_lax_sso_cookie_until_confirmation(
    logout_client: tuple[TestClient, AsyncMock],
) -> None:
    """跨站POST不携带Lax Cookie，同源确认请求可携带会话Cookie。"""
    client, execute = logout_client
    page = client.post('/oauth2/logout', data={'state': 'cross-site'})
    assert page.headers['referrer-policy'] == 'strict-origin'
    token = re.search(r'name="confirmation" value="([^"]+)"', page.text).group(1)
    client.cookies.set(OidcConfig.oidc_sso_cookie_name, 'current-sso', domain='auth.example', path='/')
    response = client.post(
        '/oauth2/logout/confirm',
        data={'confirmation': token, 'decision': 'confirm'},
        headers={'Origin': 'https://auth.example'},
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert execute.await_args.kwargs['cookie'] == 'current-sso'


def test_changing_an_initially_bound_sso_cookie_rejects_confirmation(
    logout_client: tuple[TestClient, AsyncMock],
) -> None:
    client, execute = logout_client
    client.cookies.set(OidcConfig.oidc_sso_cookie_name, 'first-sso', domain='auth.example', path='/')
    page = client.get('/oauth2/logout')
    token = re.search(r'name="confirmation" value="([^"]+)"', page.text).group(1)
    client.cookies.set(OidcConfig.oidc_sso_cookie_name, 'second-sso', domain='auth.example', path='/')
    response = client.post(
        '/oauth2/logout/confirm',
        data={'confirmation': token, 'decision': 'confirm'},
        headers={'Origin': 'https://auth.example'},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('registered', [True, False])
async def test_confirmation_csp_allows_only_verified_registered_redirect(
    monkeypatch: pytest.MonkeyPatch, registered: bool
) -> None:
    monkeypatch.setattr(
        LogoutService, '_validate_id_token_hint', AsyncMock(return_value=({}, SimpleNamespace(client_pk=1)))
    )
    monkeypatch.setattr(
        OAuthClientDao,
        'find_exact_uri',
        AsyncMock(return_value=SimpleNamespace(status='0') if registered else None),
    )
    origin = await LogoutConfirmationService.form_redirect_origin(
        object(), {'id_token_hint': 'valid-hint', 'post_logout_redirect_uri': 'https://rp.example:9443/done'}
    )
    assert origin == ('https://rp.example:9443' if registered else None)
    monkeypatch.setattr(LogoutService, '_validate_id_token_hint', AsyncMock(side_effect=ValueError('invalid hint')))
    assert (
        await LogoutConfirmationService.form_redirect_origin(
            object(), {'id_token_hint': 'invalid-hint', 'post_logout_redirect_uri': 'https://rp.example/done'}
        )
        is None
    )
