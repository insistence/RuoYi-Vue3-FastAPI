"""OAuth Token、Revocation 和 Introspection Controller 测试。"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm

from exceptions.exception import OAuthProtocolException
from module_identity.controller import token_controller as controller
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.token_service import RefreshTokenReuseDetected, TokenResult, TokenService

_OK = 200
_BAD_REQUEST = 400
_UNSUPPORTED_MEDIA = 415
_UNAUTHORIZED = 401
_SERVER_ERROR = 500
_EXPECTED_CONTROLLER_COMMITS = 2


@pytest.fixture(autouse=True)
def _disable_rate_limit_for_controller_unit_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Controller 单元测试隔离 Redis 限流实现；限流器另行测试。"""

    async def allow(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(controller.OidcRateLimiter, 'enforce', allow)


class _Db:
    """记录 Controller 事务边界的最小异步会话替身。"""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _FailCommitDb(_Db):
    """提交失败并允许回滚的会话替身。"""

    async def commit(self) -> None:
        self.commits += 1
        raise RuntimeError('commit failed')


def _request() -> SimpleNamespace:
    """构造携带应用 Redis 状态的请求替身。"""
    return SimpleNamespace(
        headers={'authorization': 'Basic test'},
        app=SimpleNamespace(state=SimpleNamespace(redis=object())),
    )


@pytest.mark.asyncio
async def test_token_success_is_bare_json_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token 成功响应提交事务且带 no-store。"""
    db = _Db()
    monkeypatch.setattr(controller, 'read_form', lambda request: _async(_form()))
    monkeypatch.setattr(
        TokenService,
        'authenticate_client',
        lambda *args, **kwargs: _async((SimpleNamespace(), OAuthClientPrincipal('c', 'public', 'none'))),
    )
    monkeypatch.setattr(
        TokenService,
        'issue_token',
        lambda *args, **kwargs: _async(TokenResult('access', 60, scope='openid')),
    )
    response = await controller.token(_request(), db)
    assert response.status_code == _OK
    assert response.headers['cache-control'] == 'no-store'
    assert db.commits == 1
    assert db.rollbacks == 0


@pytest.mark.asyncio
async def test_token_invalid_client_has_basic_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token invalid_client 必须返回 RFC Basic challenge。"""
    db = _Db()
    monkeypatch.setattr(controller, 'read_form', lambda request: _async(_form()))

    async def invalid(*args: object, **kwargs: object) -> object:
        raise OAuthProtocolException('invalid_client', 'Client authentication failed', 401)

    monkeypatch.setattr(TokenService, 'authenticate_client', invalid)
    response = await controller.token(_request(), db)
    assert response.status_code == _UNAUTHORIZED
    assert response.headers['www-authenticate'] == 'Basic realm="oauth2/token"'


@pytest.mark.asyncio
async def test_token_rejects_oversized_or_basic_plus_body_secret_before_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token Endpoint 不允许绕过 Secret 长度、位置和互斥边界。"""
    db = _Db()
    authenticate = AsyncMock(side_effect=OAuthProtocolException('invalid_client', 'Client authentication failed', 401))
    issue = AsyncMock()
    monkeypatch.setattr(TokenService, 'authenticate_client', authenticate)
    monkeypatch.setattr(TokenService, 'issue_token', issue)
    monkeypatch.setattr(
        controller,
        'read_form',
        lambda request: _async({'grant_type': 'client_credentials', 'client_id': 'c', 'client_secret': 'x' * 513}),
    )
    response = await controller.token(_request(), db)
    assert response.status_code == _BAD_REQUEST
    authenticate.assert_not_awaited()

    authenticate.reset_mock()
    monkeypatch.setattr(
        controller,
        'read_form',
        lambda request: _async({'grant_type': 'client_credentials', 'client_id': 'c', 'client_secret': 'body'}),
    )
    response = await controller.token(_request(), db)
    assert response.status_code == _UNAUTHORIZED
    authenticate.assert_awaited_once()
    issue.assert_not_awaited()

    authenticate.reset_mock()
    request_without_basic = _request()
    request_without_basic.headers = {}
    response = await controller.token(request_without_basic, db)
    assert response.status_code == _UNAUTHORIZED
    authenticate.assert_awaited_once()
    assert authenticate.await_args.kwargs['authorization'] is None
    assert authenticate.await_args.kwargs['client_secret'] == 'body'
    issue.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_reuse_commits_family_before_invalid_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refresh 重放异常必须提交 Family 撤销，而非回滚。"""
    db = _Db()
    monkeypatch.setattr(controller, 'read_form', lambda request: _async(_form()))
    monkeypatch.setattr(
        TokenService,
        'authenticate_client',
        lambda *args, **kwargs: _async((SimpleNamespace(), OAuthClientPrincipal('c', 'public', 'none'))),
    )

    async def reuse(*args: object, **kwargs: object) -> TokenResult:
        raise RefreshTokenReuseDetected

    monkeypatch.setattr(TokenService, 'issue_token', reuse)
    response = await controller.token(_request(), db)
    assert response.status_code == _BAD_REQUEST
    assert response.body.startswith(b'{"error":"invalid_grant"')
    assert db.commits == 1
    assert db.rollbacks == 0


@pytest.mark.asyncio
async def test_refresh_reuse_commit_failure_is_server_error_and_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Family 提交失败时不得伪装成已落盘的 invalid_grant。"""
    db = _FailCommitDb()
    monkeypatch.setattr(controller, 'read_form', lambda request: _async(_form()))
    monkeypatch.setattr(
        TokenService,
        'authenticate_client',
        lambda *args, **kwargs: _async((SimpleNamespace(), OAuthClientPrincipal('c', 'public', 'none'))),
    )

    async def reuse(*args: object, **kwargs: object) -> TokenResult:
        raise RefreshTokenReuseDetected

    monkeypatch.setattr(TokenService, 'issue_token', reuse)
    response = await controller.token(_request(), db)
    assert response.status_code == _SERVER_ERROR
    assert b'invalid_grant' not in response.body
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_introspect_rejects_public_client_with_basic_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Introspection 在 Controller 边界拒绝公共 Client。"""
    db = _Db()
    monkeypatch.setattr(controller, 'read_form', lambda request: _async({'client_id': 'c', 'token': 'x'}))
    monkeypatch.setattr(
        TokenService,
        'authenticate_client',
        lambda *args, **kwargs: _async(
            (SimpleNamespace(client_type='public'), OAuthClientPrincipal('c', 'public', 'none'))
        ),
    )
    response = await controller.introspect(_request(), db)
    assert response.status_code == _UNAUTHORIZED
    assert response.headers['www-authenticate'] == 'Basic realm="oauth2/token"'
    assert db.rollbacks == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('status_code', [_BAD_REQUEST, _UNSUPPORTED_MEDIA])
async def test_introspect_form_boundary_preserves_http_error(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    """Introspection 的重复字段和媒体类型错误不得被转换为 500。"""
    db = _Db()

    async def invalid_form(request: object) -> dict[str, str]:
        raise HTTPException(status_code=status_code, detail='invalid input')

    monkeypatch.setattr(controller, 'read_form', invalid_form)
    response = await controller.introspect(_request(), db)
    assert response.status_code == status_code
    assert response.body == b'{"error":"invalid_request"}'
    assert db.rollbacks == 0


@pytest.mark.asyncio
async def test_revoke_and_introspect_receive_database_rsa_verification_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """撤销和内省路由把按 kid 从数据库加载的 RSA 公钥传给服务。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    record = SimpleNamespace(
        kid='kid-route',
        alg='RS256',
        status='active',
        publish_at=None,
        remove_from_jwks_at=None,
        public_jwk=json.loads(RSAAlgorithm.to_jwk(key.public_key())),
    )

    class KeyDb(_Db):
        async def scalar(self, statement: object) -> object:
            return record

    token = jwt.encode(
        {
            'iss': 'https://issuer.example',
            'sub': 'subject',
            'aud': ['https://issuer.example/oauth2/userinfo'],
            'exp': 2,
            'iat': 1,
            'jti': 'jti',
            'client_id': 'c',
            'scope': 'openid',
        },
        key,
        algorithm='RS256',
        headers={'kid': 'kid-route', 'typ': 'at+jwt'},
    )
    db = KeyDb()
    captured: list[object] = []
    monkeypatch.setattr('module_identity.dependencies.OidcKeyDao.get_verifying', lambda *args: _async(record))
    monkeypatch.setattr(controller, 'read_form', lambda request: _async({'client_id': 'c', 'token': token}))
    monkeypatch.setattr(
        TokenService,
        'authenticate_client',
        lambda *args, **kwargs: _async(
            (
                SimpleNamespace(client_type='confidential'),
                OAuthClientPrincipal('c', 'confidential', 'client_secret_basic'),
            )
        ),
    )

    async def revoke_service(*args: object, **kwargs: object) -> None:
        captured.append(kwargs['verification_key'])

    monkeypatch.setattr(controller.RevocationService, 'revoke', revoke_service)
    await controller.revoke(_request(), db)
    assert captured and captured[0].public_numbers() == key.public_key().public_numbers()

    captured.clear()

    async def introspect_service(*args: object, **kwargs: object) -> dict[str, bool]:
        captured.append(kwargs['verification_key'])
        return {'active': False}

    monkeypatch.setattr(controller.IntrospectionService, 'introspect', introspect_service)
    await controller.introspect(_request(), db)
    assert captured and captured[0].public_numbers() == key.public_key().public_numbers()
    assert db.commits == _EXPECTED_CONTROLLER_COMMITS


def _form() -> dict[str, str]:
    """构造 Controller 测试表单。"""
    return {'grant_type': 'client_credentials', 'client_id': 'c'}


def _async(value: object) -> Any:
    """构造异步测试结果。"""

    async def result() -> object:
        return value

    return result()
