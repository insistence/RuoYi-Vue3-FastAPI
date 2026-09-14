from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from config.env import AppConfig, OidcConfig
from middlewares.handle import handle_middleware
from middlewares.oidc_cors_middleware import OidcCorsMiddleware


@pytest.fixture(autouse=True)
def _mock_snapshot_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('middlewares.oidc_cors_middleware.OidcRuntimeService.ensure_cors_snapshot', AsyncMock())


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_cors_allowed_origins', 'https://allowed.example')
    app = FastAPI()

    @app.get('/.well-known/openid-configuration')
    async def discovery() -> dict[str, str]:
        return {'issuer': 'https://auth.example.com'}

    @app.get('/oauth2/authorize')
    async def authorize() -> dict[str, bool]:
        return {'ok': True}

    @app.post('/oauth2/token')
    async def token() -> Response:
        return Response(
            content='{"access_token":"token"}',
            media_type='application/json',
            headers={'Vary': 'Accept-Encoding, Origin'},
        )

    @app.get('/business')
    async def business() -> dict[str, bool]:
        return {'ok': True}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.add_middleware(OidcCorsMiddleware)
    return TestClient(app)


def test_authorize_disallows_cors_but_discovery_remains_public(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    origin = {'Origin': 'https://external.example'}

    discovery = client.get('/.well-known/openid-configuration', headers=origin)
    authorize = client.get('/oauth2/authorize', headers=origin)

    assert discovery.status_code == status.HTTP_200_OK
    assert discovery.headers['access-control-allow-origin'] == origin['Origin']
    assert authorize.status_code == status.HTTP_403_FORBIDDEN
    assert 'access-control-allow-origin' not in authorize.headers


def test_token_preflight_requires_explicit_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    allowed = client.options(
        '/oauth2/token',
        headers={
            'Origin': 'https://allowed.example',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Authorization, Content-Type',
        },
    )
    denied = client.options(
        '/oauth2/token',
        headers={
            'Origin': 'https://denied.example',
            'Access-Control-Request-Method': 'POST',
        },
    )

    assert allowed.status_code == status.HTTP_200_OK
    assert allowed.headers['access-control-allow-origin'] == 'https://allowed.example'
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert 'access-control-allow-origin' not in denied.headers


def test_token_form_post_from_disallowed_origin_is_rejected_before_downstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch).post(
        '/oauth2/token',
        data={'grant_type': 'authorization_code', 'code': 'opaque-code'},
        headers={'Origin': 'https://denied.example', 'Content-Type': 'application/x-www-form-urlencoded'},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert 'access-control-allow-origin' not in response.headers


def test_allowed_response_preserves_non_origin_vary_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    response = client.post('/oauth2/token', headers={'Origin': 'https://allowed.example'})

    assert response.status_code == status.HTTP_200_OK
    assert response.headers['access-control-allow-origin'] == 'https://allowed.example'
    assert 'accept-encoding' in response.headers.get('vary', '').lower()
    assert 'origin' in response.headers.get('vary', '').lower()


def test_existing_business_cors_remains_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch).get('/business', headers={'Origin': 'https://current-web.example'})

    assert response.status_code == status.HTTP_200_OK
    baseline_client = _client(monkeypatch)
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', False)
    baseline = baseline_client.get('/business', headers={'Origin': 'https://current-web.example'})
    assert response.headers['access-control-allow-origin'] == baseline.headers['access-control-allow-origin']
    assert response.headers['access-control-allow-credentials'] == baseline.headers['access-control-allow-credentials']


def test_runtime_registered_origin_is_exact_and_does_not_allow_similar_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """协议层注册缓存可扩展白名单，但相近 Host、路径和尾点仍拒绝。"""
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_cors_allowed_origins', '')
    app = FastAPI()
    app.state.oidc_registered_cors_origins = frozenset({'https://registered.example'})

    @app.post('/oauth2/token')
    async def token() -> Response:
        return Response('{}', media_type='application/json')

    app.add_middleware(OidcCorsMiddleware)
    client = TestClient(app)
    allowed = client.post('/oauth2/token', headers={'Origin': 'https://registered.example'})
    similar = client.post('/oauth2/token', headers={'Origin': 'https://registered.example.evil'})
    trailing = client.post('/oauth2/token', headers={'Origin': 'https://registered.example.'})
    path = client.post('/oauth2/token', headers={'Origin': 'https://registered.example/path'})
    assert allowed.status_code == status.HTTP_200_OK
    assert similar.status_code == status.HTTP_403_FORBIDDEN
    assert trailing.status_code == status.HTTP_403_FORBIDDEN
    assert path.status_code == status.HTTP_403_FORBIDDEN


def test_interaction_api_requires_exact_issuer_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """交互登录、改密和完成接口不继承全局宽松 CORS。"""
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example.com/oidc')
    app = FastAPI()

    @app.post('/auth/interaction/i-1/login')
    async def login() -> Response:
        return Response('{}', media_type='application/json')

    @app.get('/auth/interaction/i-1/complete')
    async def complete() -> Response:
        return Response('{}', media_type='application/json')

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.add_middleware(OidcCorsMiddleware)
    client = TestClient(app)

    allowed = client.post('/auth/interaction/i-1/login', headers={'Origin': 'https://auth.example.com'})
    denied = client.post('/auth/interaction/i-1/login', headers={'Origin': 'https://evil.example'})
    port_spoof = client.post('/auth/interaction/i-1/login', headers={'Origin': 'https://auth.example.com:443'})
    scheme_spoof = client.get('/auth/interaction/i-1/complete', headers={'Origin': 'http://auth.example.com'})

    assert allowed.status_code == status.HTTP_200_OK
    assert allowed.headers['access-control-allow-origin'] == 'https://auth.example.com'
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert port_spoof.status_code == status.HTTP_403_FORBIDDEN
    assert scheme_spoof.status_code == status.HTTP_403_FORBIDDEN
    assert '*' not in allowed.headers.get('access-control-allow-origin', '')


def test_interaction_preflight_rejects_cross_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """交互接口的预检不能被内层宽松 CORS 伪造成功。"""
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example.com')
    app = FastAPI()

    @app.post('/auth/interaction/i-1/change-password')
    async def change_password() -> Response:
        return Response('{}')

    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'])
    app.add_middleware(OidcCorsMiddleware)
    response = TestClient(app).options(
        '/auth/interaction/i-1/change-password',
        headers={'Origin': 'https://evil.example', 'Access-Control-Request-Method': 'POST'},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert 'access-control-allow-origin' not in response.headers


def test_oidc_cors_is_bypassed_when_provider_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭认证中心时 OIDC 路径不得被专用 CORS 中间件拦截。"""
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', False)
    app = FastAPI()

    @app.post('/oauth2/token')
    async def token() -> Response:
        return Response('{}', media_type='application/json')

    app.add_middleware(OidcCorsMiddleware)
    response = TestClient(app).post('/oauth2/token', headers={'Origin': 'https://denied.example'})

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.parametrize('enabled', [False, True])
def test_global_registration_follows_oidc_switch(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    """全局中间件注册应与 OIDC_ENABLED 开关保持一致。"""
    monkeypatch.setattr(AppConfig, 'app_demo_mode', False)
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', enabled)

    app = FastAPI()
    handle_middleware(app)

    registered = any(item.cls is OidcCorsMiddleware for item in app.user_middleware)
    assert registered is enabled
