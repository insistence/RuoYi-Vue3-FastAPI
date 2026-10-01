"""认证中心协议依赖测试。"""

import time
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from exceptions.exception import OAuthProtocolException
from module_identity import dependencies
from module_identity.controller.token_controller import token_controller

_BAD_REQUEST = 400
_UNSUPPORTED_MEDIA = 415
_UNAUTHORIZED = 401
_PAYLOAD_TOO_LARGE = 413
_SERVICE_UNAVAILABLE = 503
_MAX_FORM_BYTES = 16 * 1024


def _request(
    body: bytes,
    content_type: str = 'application/x-www-form-urlencoded',
    declared_length: int | None = None,
    include_content_length: bool = True,
) -> Request:
    """构造最小 URL encoded 请求。"""
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {'type': 'http.disconnect'}
        sent = True
        return {'type': 'http.request', 'body': body, 'more_body': False}

    headers = [(b'content-type', content_type.encode())]
    if include_content_length:
        headers.append((b'content-length', str(len(body) if declared_length is None else declared_length).encode()))
    return Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/oauth2/token',
            'headers': headers,
        },
        receive,
    )


@pytest.mark.asyncio
async def test_read_form_rejects_duplicate_and_wrong_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """重复字段与非表单请求必须 fail closed。"""
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    with pytest.raises(HTTPException) as duplicate:
        await dependencies.read_form(_request(b'client_id=a&client_id=b'))
    assert duplicate.value.status_code == _BAD_REQUEST
    with pytest.raises(HTTPException) as media:
        await dependencies.read_form(_request(b'client_id=a', 'application/json'))
    assert media.value.status_code == _UNSUPPORTED_MEDIA


@pytest.mark.asyncio
async def test_read_form_rejects_oversized_and_misdeclared_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """协议表单在读取前后均限制 16KiB，不能用伪造 Content-Length 绕过。"""
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    oversized = _request(b'a' * (_MAX_FORM_BYTES + 1))
    with pytest.raises(HTTPException) as too_large:
        await dependencies.read_form(oversized)
    assert too_large.value.status_code == _PAYLOAD_TOO_LARGE
    mismatched = _request(b'client_id=a', declared_length=1)
    with pytest.raises(HTTPException) as mismatch:
        await dependencies.read_form(mismatched)
    assert mismatch.value.status_code == _PAYLOAD_TOO_LARGE


@pytest.mark.asyncio
async def test_read_form_accepts_chunked_body_without_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺少 Content-Length 的合法 chunked 表单按实际流大小读取。"""
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    request = _request(b'client_id=chunked', include_content_length=False)
    assert await dependencies.read_form(request) == {'client_id': 'chunked'}


@pytest.mark.asyncio
async def test_read_form_rejects_malformed_percent_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    """表单百分号转义必须完整且为十六进制。"""
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    with pytest.raises(HTTPException) as raised:
        await dependencies.read_form(_request(b'client_id=%ZZ'))
    assert raised.value.status_code == _BAD_REQUEST


@pytest.mark.asyncio
async def test_access_key_helper_rejects_remote_key_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """kid 验证只允许本地公钥，拒绝 jku/x5u/jwk/x5c。"""
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {'iss': 'https://issuer.example', 'sub': 'subject'},
        key,
        algorithm='RS256',
        headers={'kid': 'kid-1', 'typ': 'at+jwt', 'jku': 'https://evil.example/jwks'},
    )
    with pytest.raises(dependencies.JwtProfileError):
        await dependencies.load_access_verification_key(token, object())


@pytest.mark.asyncio
@pytest.mark.parametrize('scheme', ['Bearer', 'bearer', 'BEARER', 'bEaReR'])
async def test_userinfo_accepts_case_insensitive_scheme_without_changing_token(
    monkeypatch: pytest.MonkeyPatch, scheme: str
) -> None:
    """方案名大小写不影响真实签名令牌，凭据原文必须保持不变。"""
    issuer = 'https://issuer.example'
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_issuer', issuer)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    claims = {
        'iss': issuer,
        'sub': 'subject-1',
        'aud': f'{issuer}/oauth2/userinfo',
        'iat': now,
        'nbf': now,
        'exp': now + 600,
        'jti': 'jti-1',
        'client_id': 'client-1',
        'sid': 'session-1',
        'scope': 'openid',
        'ver': 1,
        'gty': 'authorization_code',
        'grant_id': 'grant-1',
        'client_policy_version': 1,
        'auth_time': now,
        'acr': 'pwd',
        'amr': ['pwd'],
    }
    token = jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'kid-1', 'typ': 'at+jwt'})
    monkeypatch.setattr(dependencies, 'load_access_verification_key', lambda *args: _async(key.public_key()))
    request = Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': '/oauth2/userinfo',
            'headers': [(b'authorization', f'{scheme} {token}'.encode())],
        }
    )
    context = await dependencies.get_oidc_access_token(request, object())
    assert context.token == token
    assert context.claims['sub'] == 'subject-1'


@pytest.mark.asyncio
@pytest.mark.parametrize('prefix', ['', 'Basic ', 'BearerX ', ' Bearer ', 'Bearer\t'])
async def test_userinfo_rejects_other_schemes_and_missing_space(monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    request = Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': '/oauth2/userinfo',
            'headers': [(b'authorization', f'{prefix}header.payload.signature'.encode())],
        }
    )
    with pytest.raises(HTTPException) as raised:
        await dependencies.get_oidc_access_token(request, object())
    assert raised.value.status_code == _UNAUTHORIZED


@pytest.mark.asyncio
async def test_client_dependency_invalid_client_has_basic_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client Authentication 依赖的 invalid_client 必须带 Basic challenge。"""
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(dependencies, 'read_form', lambda request: _async({'client_id': 'client-1'}))

    async def invalid(*args: object, **kwargs: object) -> object:
        raise OAuthProtocolException('invalid_client', 'Client authentication failed', 401)

    monkeypatch.setattr(dependencies.TokenService, 'authenticate_client', invalid)
    request = SimpleNamespace(headers={})
    with pytest.raises(HTTPException) as raised:
        await dependencies.get_oidc_client(request, object())
    assert raised.value.status_code == _UNAUTHORIZED
    assert raised.value.headers == {'WWW-Authenticate': 'Basic realm="oauth2/token"'}


def test_protocol_routers_have_no_legacy_preauth_dependency() -> None:
    """协议路由不得自动挂载 Legacy PreAuth。"""
    assert all(
        all(
            getattr(dependency.dependency, '__name__', '') == 'require_oidc_protocol_ready'
            for dependency in route.dependencies
        )
        for route in token_controller.routes
    )


@pytest.mark.asyncio
async def test_protocol_readiness_dependency_returns_503_without_active_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """协议已开启但签名密钥未就绪时返回稳定 OAuth 503。"""
    monkeypatch.setattr(dependencies.OidcConfig, 'oidc_enabled', True)
    not_ready = SimpleNamespace(ready=False)
    monkeypatch.setattr(
        dependencies.OidcRuntimeService,
        'cached_readiness',
        lambda *args: _async(not_ready),
    )
    request = SimpleNamespace(app=SimpleNamespace())
    with pytest.raises(OAuthProtocolException) as raised:
        await dependencies.require_oidc_protocol_ready(request, object())
    assert raised.value.error == 'temporarily_unavailable'
    assert raised.value.status_code == _SERVICE_UNAVAILABLE


def test_invalid_token_challenge_is_standard_bearer() -> None:
    """Access Token 依赖的失败响应不泄漏验签细节。"""
    error = dependencies._invalid_token()
    assert error.status_code == _UNAUTHORIZED
    assert error.headers['WWW-Authenticate'] == 'Bearer error="invalid_token"'


def _async(value: object) -> Any:
    """构造异步测试结果。"""

    async def result() -> object:
        return value

    return result()
