import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Request, status

from config.env import AppConfig, OidcConfig
from exceptions.exception import OAuthProtocolException
from module_identity.controller.authorization_controller import _enforce_authorization_rate_limit, logout
from module_identity.controller.interaction_controller import captcha, login_endpoint
from module_identity.entity.vo.interaction_vo import CaptchaResponseModel
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.infrastructure_service import OidcRateLimiter
from module_identity.service.interaction_service import (
    CaptchaOutcome,
    InteractionFlowService,
    InteractionLoginOutcome,
    InteractionLoginService,
)
from module_identity.service.logout_confirmation_service import LogoutConfirmationService

_PEPPER = 'client-ip-regression-pepper-' + 'x' * 32
_PROXY_IP = '10.0.0.2'
_USER_IP = '198.51.100.23'


def _request(peer: str | None, headers: dict[str, str]) -> Request:
    body = json.dumps({'userName': 'alice', 'password': 'test-password'}).encode()

    async def receive() -> dict[str, object]:
        return {'type': 'http.request', 'body': body, 'more_body': False}

    return Request(
        {
            'type': 'http',
            'http_version': '1.1',
            'method': 'GET',
            'scheme': 'https',
            'path': '/',
            'query_string': b'',
            'headers': [
                (name.lower().encode(), value.encode())
                for name, value in {'content-type': 'application/json', **headers}.items()
            ],
            'client': (peer, 12345) if peer is not None else None,
            'server': ('auth.example', 443),
            'app': SimpleNamespace(state=SimpleNamespace(redis=object())),
        },
        receive,
    )


@pytest.fixture
def oidc_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example')
    monkeypatch.setattr(OidcConfig, 'oidc_token_hash_pepper', _PEPPER)
    monkeypatch.setattr(AppConfig, 'app_trusted_proxy_ips', _PROXY_IP)


@pytest.fixture(
    params=[
        (_PROXY_IP, 1, {'X-Forwarded-For': _USER_IP, 'X-Real-IP': '203.0.113.9'}, _USER_IP),
        (_PROXY_IP, 1, {'X-Real-IP': _USER_IP}, _USER_IP),
        (_USER_IP, 1, {'X-Forwarded-For': '203.0.113.9', 'X-Real-IP': '203.0.113.9'}, _USER_IP),
        (_PROXY_IP, 0, {'X-Forwarded-For': _USER_IP}, _PROXY_IP),
        (_PROXY_IP, 1, {}, _PROXY_IP),
    ],
    ids=['trusted-forwarded-for', 'trusted-real-ip', 'untrusted-forged-headers', 'proxy-disabled', 'no-proxy-header'],
)
def client_request(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, oidc_enabled: None
) -> tuple[Request, str]:
    peer, hops, headers, expected = request.param
    monkeypatch.setattr(AppConfig, 'app_trusted_proxy_hops', hops)
    return _request(peer, headers), expected


@pytest.mark.asyncio
async def test_login_passes_resolved_ip_to_credentials_and_session_flow(
    client_request: tuple[Request, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    request, expected = client_request
    request.scope['method'] = 'POST'
    login = AsyncMock(return_value=InteractionLoginOutcome(failure_message='认证信息无效'))
    monkeypatch.setattr(InteractionLoginService, 'login', login)

    await login_endpoint(request, 'interaction-1', object(), 'csrf')

    assert login.await_args.args[5] == expected


@pytest.mark.asyncio
async def test_captcha_uses_the_resolved_client_ip(
    client_request: tuple[Request, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    request, expected = client_request
    generate = AsyncMock(return_value=CaptchaOutcome(result=CaptchaResponseModel(captcha_enabled=False)))
    monkeypatch.setattr(InteractionFlowService, 'captcha', generate)

    await captcha(request, 'interaction-1')

    generate.assert_awaited_once_with(request.app.state.redis, 'interaction-1', expected)


@pytest.mark.asyncio
async def test_authorize_rate_limit_hashes_the_resolved_client_ip(
    client_request: tuple[Request, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    request, expected = client_request
    enforce = AsyncMock()
    monkeypatch.setattr(OidcRateLimiter, 'enforce', enforce)

    await _enforce_authorization_rate_limit(request, request.app.state.redis)

    digest = hmac.new(_PEPPER.encode(), expected.encode(), hashlib.sha256).hexdigest()
    assert enforce.await_args.args[1] == OidcRedisKey.authorize_ip_rate_limit(digest)


@pytest.mark.asyncio
async def test_logout_rate_limit_hashes_the_resolved_client_ip(
    client_request: tuple[Request, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    request, expected = client_request
    enforce = AsyncMock()
    monkeypatch.setattr(OidcRateLimiter, 'enforce', enforce)
    monkeypatch.setattr(LogoutConfirmationService, 'issue', AsyncMock(return_value=('confirmation', 'nonce')))
    monkeypatch.setattr(LogoutConfirmationService, 'form_redirect_origin', AsyncMock(return_value=None))

    response = await logout(request, object())

    assert response.status_code == status.HTTP_200_OK
    digest = hmac.new(_PEPPER.encode(), expected.encode(), hashlib.sha256).hexdigest()
    assert enforce.await_args.args[1] == OidcRedisKey.logout_rate_limit(digest)


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_authorization_still_rejects_unknown_peer_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AppConfig, 'app_trusted_proxy_hops', 1)
    enforce = AsyncMock()
    monkeypatch.setattr(OidcRateLimiter, 'enforce', enforce)
    request = _request(None, {'X-Forwarded-For': _USER_IP})

    with pytest.raises(OAuthProtocolException) as error:
        await _enforce_authorization_rate_limit(request, request.app.state.redis)

    assert error.value.error == 'temporarily_unavailable'
    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    enforce.assert_not_awaited()
