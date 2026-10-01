from types import SimpleNamespace

import pytest
from starlette.requests import Request

from config.env import OidcConfig
from module_identity.controller import discovery_controller as controller
from module_identity.service.key_service import KeyServiceError

_HTTP_OK = 200
_HTTP_NOT_MODIFIED = 304
_HTTP_NOT_FOUND = 404
_HTTP_UNAVAILABLE = 503


def _request(headers: dict[str, str] | None = None, host: str = 'evil.example') -> Request:
    """创建带可控 Host 和缓存请求头的 Starlette 请求。"""
    raw_headers = [(b'host', host.encode())]
    raw_headers.extend((key.lower().encode(), value.encode()) for key, value in (headers or {}).items())
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': raw_headers})


def _enabled(monkeypatch: pytest.MonkeyPatch) -> OidcConfig:
    """将全局配置设为启用且固定 issuer。"""
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example.com')
    monkeypatch.setattr(controller, 'OidcConfig', OidcConfig)
    return OidcConfig


class _DiscoveryDb:
    """提供 Discovery 动态 Scope 查询的最小显式会话替身。"""

    class _Scalars:
        def all(self) -> list[str]:
            return []

    class _Result:
        def scalars(self) -> '_DiscoveryDb._Scalars':
            return _DiscoveryDb._Scalars()

    async def execute(self, statement: object) -> '_DiscoveryDb._Result':
        return _DiscoveryDb._Result()


@pytest.mark.asyncio
async def test_discovery_is_raw_static_and_supports_304(monkeypatch: pytest.MonkeyPatch) -> None:
    """发现响应使用静态 issuer、裸 JSON 和 ETag 304。"""
    _enabled(monkeypatch)
    response = await controller.openid_configuration(_request(host='attacker.example'), _DiscoveryDb())
    assert response.status_code == _HTTP_OK
    assert response.media_type == 'application/json'
    assert response.headers['cache-control'] == 'public, max-age=300'
    assert b'attacker.example' not in response.body
    not_modified = await controller.openid_configuration(
        _request({'If-None-Match': response.headers['etag']}), _DiscoveryDb()
    )
    assert not_modified.status_code == _HTTP_NOT_MODIFIED
    assert not not_modified.body
    listed = await controller.openid_configuration(
        _request({'If-None-Match': '"other", ' + response.headers['etag']}), _DiscoveryDb()
    )
    assert listed.status_code == _HTTP_NOT_MODIFIED
    wildcard = await controller.openid_configuration(_request({'If-None-Match': '*'}), _DiscoveryDb())
    assert wildcard.status_code == _HTTP_NOT_MODIFIED


@pytest.mark.asyncio
async def test_oauth_metadata_does_not_claim_oidc_only_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """RFC 8414 子集不要求 userinfo/end_session 等 OIDC 专属字段。"""
    _enabled(monkeypatch)
    response = await controller.oauth_authorization_server_metadata(_request(), _DiscoveryDb())
    assert response.status_code == _HTTP_OK
    assert b'userinfo_endpoint' not in response.body
    assert b'end_session_endpoint' not in response.body
    assert b'client_credentials' in response.body


@pytest.mark.asyncio
async def test_oidc_metadata_declares_implemented_machine_and_backchannel_flows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OIDC Discovery 声明当前已实现的机器授权和 Back-Channel 能力。"""
    _enabled(monkeypatch)
    response = await controller.openid_configuration(_request(), _DiscoveryDb())
    assert response.status_code == _HTTP_OK
    assert b'client_credentials' in response.body
    assert b'backchannel_logout_supported' in response.body
    assert b'backchannel_logout_session_supported' in response.body


@pytest.mark.asyncio
async def test_discovery_publishes_only_active_database_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery 应发布启用的 Resource Scope，并在停用后通过 ETag 变化。"""
    _enabled(monkeypatch)

    class _Scalars:
        def all(self) -> list[str]:
            return ['openid', 'orders.read', 'zzz.read']

    class _Result:
        def scalars(self) -> _Scalars:
            return _Scalars()

    class _Db:
        async def execute(self, statement: object) -> _Result:
            return _Result()

    response = await controller.openid_configuration(_request(), _Db())
    assert response.status_code == _HTTP_OK
    assert b'orders.read' in response.body
    assert response.headers['etag']


@pytest.mark.asyncio
async def test_discovery_scope_query_failure_is_no_store_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """动态 Scope 查询失败时不得发布静态或不完整元数据。"""
    _enabled(monkeypatch)

    class _FailingDb:
        async def execute(self, statement: object) -> object:
            raise RuntimeError('database unavailable')

    response = await controller.openid_configuration(_request(), _FailingDb())
    assert response.status_code == _HTTP_UNAVAILABLE
    assert response.headers['cache-control'] == 'no-store'
    assert response.body == b'{"error":"temporarily_unavailable"}'


@pytest.mark.asyncio
async def test_discovery_fails_closed_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """OIDC 关闭时所有 Discovery 请求均拒绝。"""
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', False)
    monkeypatch.setattr(controller, 'OidcConfig', OidcConfig)
    response = await controller.openid_configuration(_request(), SimpleNamespace())
    assert response.status_code == _HTTP_NOT_FOUND
    assert response.headers['cache-control'] == 'no-store'
    assert response.body == b'{"error":"not_found"}'


@pytest.mark.asyncio
async def test_jwks_is_raw_and_uses_key_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWKS 端点返回标准裸 keys JSON 和缓存头。"""
    _enabled(monkeypatch)

    async def build(*args: object, **kwargs: object) -> dict[str, list[dict[str, str]]]:
        return {'keys': [{'kty': 'RSA', 'use': 'sig', 'kid': 'k1', 'alg': 'RS256', 'n': 'n', 'e': 'AQAB'}]}

    monkeypatch.setattr(controller.KeyService, 'build_jwks', build)
    response = await controller.jwks(_request(), SimpleNamespace())
    assert response.status_code == _HTTP_OK
    assert response.headers['cache-control'] == 'public, max-age=300'
    assert response.body.startswith(b'{"keys"')


@pytest.mark.asyncio
async def test_jwks_fails_closed_on_invalid_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWKS 公钥记录非法时返回 503，不发布污染数据。"""
    _enabled(monkeypatch)

    async def build(*args: object, **kwargs: object) -> dict[str, list[dict[str, str]]]:
        raise KeyServiceError('public JWK RSA numbers are invalid')

    monkeypatch.setattr(controller.KeyService, 'build_jwks', build)
    response = await controller.jwks(_request(), SimpleNamespace())
    assert response.status_code == _HTTP_UNAVAILABLE
    assert response.headers['cache-control'] == 'no-store'
    assert response.body == b'{"error":"temporarily_unavailable"}'
