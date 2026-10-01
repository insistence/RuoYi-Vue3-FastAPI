from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode
from starlette.requests import Request

from config.env import OidcConfig
from module_identity.controller import authorization_controller as controller
from module_identity.redis_keys import OidcRedisKey
from module_identity.security.backchannel_transport import PinnedHttpxTransport
from module_identity.security.jwt_profile import (
    JwtProfileError,
    decode_id_token,
    decode_logout_token,
    encode_id_token,
)
from module_identity.service.infrastructure_service import AfterCommitCoordinator, OidcRateLimiter
from module_identity.service.session_service import (
    LogoutResult,
    LogoutService,
    LogoutServiceError,
)
from tests.module_identity.support.redis_fakes import FakeRedis
from utils.oidc_util import OidcUtil

_ISSUER = 'https://auth.example.com'
_NOW = datetime.now(timezone.utc)
_PEPPER = 'logout-test-pepper-' + 'x' * 32
_MAX_ATTEMPTS = 3
_HTTP_OK = 200
_HTTP_SERVICE_UNAVAILABLE = 503
_HTTP_NOT_FOUND = 404
_HTTP_SEE_OTHER = 303


@pytest.fixture(autouse=True)
def _disable_logout_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Logout Controller 单元测试隔离 Redis 限流器。"""

    async def allow(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(OidcRateLimiter, 'enforce', allow)


def _config() -> SimpleNamespace:
    """构造 Logout 测试配置。"""

    return SimpleNamespace(
        oidc_enabled=True,
        oidc_issuer=_ISSUER,
        oidc_allowed_clock_skew_seconds=60,
        oidc_token_hash_pepper=_PEPPER,
    )


@pytest.fixture(autouse=True)
def _configure_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """将全局 OIDC 配置固定为 Logout 测试所需的协议值。"""

    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_issuer', _ISSUER)
    monkeypatch.setattr(OidcConfig, 'oidc_allowed_clock_skew_seconds', 60)
    monkeypatch.setattr(OidcConfig, 'oidc_token_hash_pepper', _PEPPER)


def _key_record(private_key: object, kid: str = 'key-1') -> SimpleNamespace:
    """构造本地数据库公开 JWK 记录。"""

    numbers = private_key.public_key().public_numbers()
    public_jwk = {
        'kty': 'RSA',
        'use': 'sig',
        'kid': kid,
        'alg': 'RS256',
        'n': base64url_encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, 'big')).decode(),
        'e': base64url_encode(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, 'big')).decode(),
    }
    return SimpleNamespace(
        kid=kid,
        key_use='sig',
        alg='RS256',
        public_jwk=public_jwk,
        status='active',
        publish_at=_NOW,
        remove_from_jwks_at=None,
    )


def _id_token(private_key: object, *, kid: str = 'key-1', aud: str = 'portal') -> str:
    """签发用于测试的真实 ID Token。"""

    return encode_id_token(
        {
            'iss': _ISSUER,
            'sub': 'subject-1',
            'aud': aud,
            'exp': int(_NOW.timestamp()) + 300,
            'iat': int(_NOW.timestamp()),
            'auth_time': int(_NOW.timestamp()),
            'nonce': 'nonce-1',
            'sid': 'sid-1',
            'acr': 'urn:test',
            'amr': ['pwd'],
        },
        private_key,
        kid,
    )


@pytest.mark.asyncio
async def test_id_token_hint_uses_local_rsa_kid_and_rejects_remote_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ID Token Hint 仅使用本地 DB JWK，远程 header 参数直接拒绝。"""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = SimpleNamespace(client_pk=20, client_id='portal', status='0')
    monkeypatch.setattr(
        'module_identity.service.session_service.OAuthClientDao.get_by_client_id', _async_return(client)
    )
    monkeypatch.setattr(
        'module_identity.service.session_service.OidcKeyDao.get_verifying',
        _async_return(_key_record(private_key)),
    )
    db = SimpleNamespace()
    token = _id_token(private_key, aud='portal')

    claims, resolved = await LogoutService._validate_id_token_hint(db, token, _NOW)

    assert claims['sid'] == 'sid-1'
    assert resolved.client_id == 'portal'
    unsafe = jwt.encode(
        jwt.decode(token, options={'verify_signature': False}) | {'nonce': 'nonce-1'},
        private_key,
        algorithm='RS256',
        headers={'kid': 'key-1', 'typ': 'JWT', 'jku': 'https://evil.example/jwks'},
    )
    with pytest.raises(ValueError):
        await LogoutService._validate_id_token_hint(db, unsafe, _NOW)


@pytest.mark.asyncio
async def test_pending_signing_key_cannot_validate_id_token_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """待激活签名密钥只能发布，不能用于验证 ID Token Hint。"""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = SimpleNamespace(client_pk=20, client_id='portal', status='0')
    monkeypatch.setattr(
        'module_identity.service.session_service.OAuthClientDao.get_by_client_id', _async_return(client)
    )
    key = _key_record(private_key)
    key.status = 'pending'
    monkeypatch.setattr('module_identity.service.session_service.OidcKeyDao.get_verifying', _async_return(key))
    db = SimpleNamespace()
    token = _id_token(private_key, aud='portal')

    with pytest.raises(LogoutServiceError):
        await LogoutService._validate_id_token_hint(db, token, _NOW)


@pytest.mark.asyncio
async def test_logout_redirect_and_backchannel_are_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """已注册 Redirect 安全附加 state，通知只在 commit 后执行。"""

    client = SimpleNamespace(client_pk=20, client_id='portal', status='0')
    session = SimpleNamespace(sid='sid-1', status='active', subject_id='subject-1')
    monkeypatch.setattr(
        LogoutService, '_validate_id_token_hint', _async_return(({'sid': 'sid-1', 'sub': 'subject-1'}, client))
    )
    monkeypatch.setattr('module_identity.service.session_service.SsoSessionDao.get_by_sid', _async_return(session))
    monkeypatch.setattr(
        'module_identity.service.session_service.OAuthClientDao.find_exact_uri',
        _async_return(SimpleNamespace(uri='https://portal.example/logged-out', status='0')),
    )
    monkeypatch.setattr(LogoutService, '_lock_session_refresh_tokens', _async_return([]))
    monkeypatch.setattr(LogoutService, '_revoke_session_state', _async_noop)
    sent: list[tuple[str, str]] = []

    async def register_backchannel(*args: object, **kwargs: object) -> None:
        coordinator = kwargs['coordinator']

        async def notify() -> None:
            sent.append(('https://portal.example/oidc/backchannel-logout', 'logout-token'))

        await coordinator.register(notify)

    monkeypatch.setattr(LogoutService, '_register_backchannel', register_backchannel)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    coordinator = AfterCommitCoordinator()

    monkeypatch.setattr(
        'module_identity.service.session_service.SsoSessionDao.client_ids_for_sid', AsyncMock(return_value=[])
    )
    result = await LogoutService._logout(
        db,
        object(),
        id_token_hint='opaque-input-not-logged',
        post_logout_redirect_uri='https://portal.example/logged-out',
        state='opaque-state',
        now=_NOW,
        coordinator=coordinator,
        confirmed=True,
    )

    assert result.redirect_uri == 'https://portal.example/logged-out'
    assert result.state == 'opaque-state'
    assert sent == []
    await coordinator.rollback(db)
    assert sent == []

    coordinator = AfterCommitCoordinator()
    result = await LogoutService._logout(
        db,
        object(),
        id_token_hint='opaque-input-not-logged',
        post_logout_redirect_uri='https://portal.example/logged-out',
        state='opaque-state',
        now=_NOW,
        coordinator=coordinator,
        confirmed=True,
    )
    await coordinator.commit(db)
    assert result.is_local is False
    assert sent == [('https://portal.example/oidc/backchannel-logout', 'logout-token')]


@pytest.mark.asyncio
async def test_invalid_hint_with_valid_cookie_still_revokes_server_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无效 Hint 不得重定向，但有效 Cookie 仍必须撤销服务端 Session。"""

    session = SimpleNamespace(sid='sid-1', status='active', subject_id='subject-1')

    async def invalid_hint(*_args: object, **_kwargs: object) -> object:
        raise LogoutServiceError('invalid id_token_hint')

    monkeypatch.setattr(LogoutService, '_validate_id_token_hint', invalid_hint)
    monkeypatch.setattr(
        'module_identity.service.session_service.SsoSessionService.validate_logout_cookie', _async_return(session)
    )
    monkeypatch.setattr(LogoutService, '_lock_session_refresh_tokens', _async_return([]))
    revoked = AsyncMock()
    monkeypatch.setattr(LogoutService, '_revoke_session_state', revoked)
    monkeypatch.setattr(LogoutService, '_register_backchannel', _async_noop)
    coordinator = AfterCommitCoordinator()
    monkeypatch.setattr(
        'module_identity.service.session_service.SsoSessionDao.client_ids_for_sid', AsyncMock(return_value=[])
    )
    result = await LogoutService._logout(
        SimpleNamespace(),
        object(),
        id_token_hint='bad-hint',
        cookie='ss1.valid-cookie',
        post_logout_redirect_uri='https://portal.example/logged-out',
        state='must-not-echo',
        now=_NOW,
        coordinator=coordinator,
        confirmed=True,
    )

    assert result.session_revoked is True
    assert result.is_local is True
    revoked.assert_awaited_once()


@pytest.mark.asyncio
async def test_unsafe_or_unregistered_redirect_falls_back_to_local_and_logout_token_is_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未注册 URI 不开放重定向；生成的 Logout Token 使用专用 Profile。"""

    client = SimpleNamespace(client_pk=20, client_id='portal', status='0')
    session = SimpleNamespace(sid='sid-1', status='active', subject_id='subject-1')
    monkeypatch.setattr(
        LogoutService, '_validate_id_token_hint', _async_return(({'sid': 'sid-1', 'sub': 'subject-1'}, client))
    )
    monkeypatch.setattr('module_identity.service.session_service.SsoSessionDao.get_by_sid', _async_return(session))
    monkeypatch.setattr(
        'module_identity.service.session_service.OAuthClientDao.find_exact_uri',
        _async_return(SimpleNamespace(uri='https://evil.example/redirect#fragment', status='0')),
    )
    monkeypatch.setattr(LogoutService, '_lock_session_refresh_tokens', _async_return([]))
    monkeypatch.setattr(LogoutService, '_revoke_session_state', _async_noop)
    monkeypatch.setattr(LogoutService, '_register_backchannel', _async_noop)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    coordinator = AfterCommitCoordinator()

    monkeypatch.setattr(
        'module_identity.service.session_service.SsoSessionDao.client_ids_for_sid', AsyncMock(return_value=[])
    )
    result = await LogoutService._logout(
        db,
        object(),
        id_token_hint='hint',
        post_logout_redirect_uri='https://evil.example/redirect#fragment',
        state='do-not-echo',
        now=_NOW,
        coordinator=coordinator,
        confirmed=True,
    )

    assert result.is_local
    assert result.state is None
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = await LogoutService._make_logout_token(
        'portal',
        'sid-1',
        now=_NOW,
        signing_key=private_key,
        signing_kid='key-1',
        db=db,
    )
    claims = decode_logout_token(token, verification_key=private_key.public_key(), issuer=_ISSUER, audience='portal')
    assert claims['sid'] == 'sid-1'
    assert claims['exp'] == claims['iat'] + 120
    assert claims['events']['http://schemas.openid.net/event/backchannel-logout'] == {}
    assert 'nonce' not in claims
    subject_token = await LogoutService._make_logout_token(
        'portal',
        'sid-1',
        subject_id='subject-1',
        include_sid=False,
        event_jti='event-constant',
        now=_NOW,
        signing_key=private_key,
        signing_kid='key-1',
        db=db,
    )
    subject_claims = decode_logout_token(
        subject_token, verification_key=private_key.public_key(), issuer=_ISSUER, audience='portal'
    )
    assert subject_claims['sub'] == 'subject-1' and 'sid' not in subject_claims
    assert subject_claims['jti'] == 'event-constant'


@pytest.mark.asyncio
@pytest.mark.parametrize('address', ['10.0.0.9', '::1', '169.254.169.254'])
async def test_backchannel_dns_private_and_ipv6_addresses_are_rejected(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    """Back-Channel DNS 解析到内网、IPv6 回环或 metadata 地址时拒绝发送。"""

    monkeypatch.setattr(
        'module_identity.security.uri_validator.socket.getaddrinfo',
        lambda *_args, **_kwargs: [(2, 1, 6, '', (address, 443))],
    )

    assert await LogoutService._safe_backchannel_uri('https://client.example/logout') is False


@pytest.mark.asyncio
async def test_backchannel_retry_queue_and_structured_audit_exclude_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Back-Channel 失败有限重试、入队和审计均不携带 Logout Token。"""

    attempts = 0
    queued: list[tuple[str, str, str]] = []
    audited: list[tuple[str, str, str, str]] = []

    async def fail(_uri: str, _token: str) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError('network down')

    async def queue(
        uri: str,
        client_id: str,
        sid: str,
        *,
        event_jti: str | None = None,
        subject_id: str | None = None,
        include_sid: bool = True,
    ) -> None:
        del event_jti, subject_id, include_sid
        queued.append((uri, client_id, sid))

    async def audit(event: str, uri: str, client_id: str, sid: str, *, failure_code: str | None = None) -> None:
        del failure_code
        audited.append((event, uri, client_id, sid))

    monkeypatch.setattr('module_identity.service.session_service._BACKCHANNEL_RETRY_DELAY_SECONDS', 0)
    callback = LogoutService._notification_callback(
        'https://client.example/logout',
        'logout.secret.must.not.persist',
        fail,
        client_id='portal',
        sid='sid-1',
        retry_queue=queue,
        audit_writer=audit,
    )
    await callback()

    assert attempts == _MAX_ATTEMPTS
    assert queued == [('https://client.example/logout', 'portal', 'sid-1')]
    assert audited == [('backchannel_logout_failed', 'https://client.example/logout', 'portal', 'sid-1')]
    assert all('logout.secret' not in repr(item) for item in (*queued, *audited))


@pytest.mark.asyncio
async def test_backchannel_retry_metadata_reuses_event_jti_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """延迟任务只保存 event_jti 等元数据，重试不得生成新事件 ID。"""
    metadata: list[dict[str, object]] = []

    async def fail(_uri: str, _token: str) -> None:
        raise RuntimeError('network down')

    async def queue(
        _uri: str,
        _client_id: str,
        _sid: str,
        **kwargs: object,
    ) -> None:
        metadata.append(kwargs)

    monkeypatch.setattr('module_identity.service.session_service._BACKCHANNEL_RETRY_DELAY_SECONDS', 0)
    callback = LogoutService._notification_callback(
        'https://client.example/logout',
        'logout.secret.must.not.persist',
        fail,
        client_id='portal',
        sid='sid-1',
        event_jti='event-constant',
        retry_queue=queue,
    )
    await callback()

    assert metadata == [{'event_jti': 'event-constant', 'subject_id': None, 'include_sid': True}]
    assert all('token' not in item for item in metadata[0])


@pytest.mark.asyncio
async def test_backchannel_permanent_http_4xx_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 4xx（408/429 除外）直接失败审计，不进入重试队列。"""
    attempts = 0
    audited: list[str] = []

    async def permanent(_uri: str, _token: str) -> None:
        nonlocal attempts
        attempts += 1
        request = httpx.Request('POST', 'https://client.example/logout')
        raise httpx.HTTPStatusError('bad request', request=request, response=httpx.Response(400, request=request))

    async def audit(event: str, _uri: str, _client_id: str, _sid: str, **kwargs: object) -> None:
        audited.append(f'{event}:{kwargs.get("failure_code")}')

    monkeypatch.setattr('module_identity.service.session_service._BACKCHANNEL_RETRY_DELAY_SECONDS', 0)
    callback = LogoutService._notification_callback(
        'https://client.example/logout',
        'logout-token',
        permanent,
        client_id='portal',
        sid='sid-1',
        audit_writer=audit,
    )
    await callback()

    assert attempts == 1
    assert audited == ['backchannel_logout_failed:http_400']


@pytest.mark.asyncio
async def test_malformed_retry_payload_goes_to_safe_dead_letter_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """损坏队列数据不静默丢弃，也不把原始正文写入 dead-letter。"""
    redis = FakeRedis()
    await redis.rpush(OidcRedisKey.backchannel_retry_queue(), b'{not-json')
    audited: list[str] = []

    async def audit(event: str, _uri: str, _client_id: str, _sid: str, **kwargs: object) -> None:
        audited.append(f'{event}:{kwargs.get("failure_code")}')

    monkeypatch.setattr(LogoutService, '_audit_writer', lambda _db: audit)
    assert await LogoutService.consume_backchannel_retry(object(), redis) == 1
    dead = await redis.lpop(OidcRedisKey.backchannel_retry_queue() + ':dead')
    assert dead == '{"error":"invalid_retry_payload"}'
    assert audited == ['backchannel_logout_failed:invalid retry payload']


@pytest.mark.asyncio
async def test_pinned_transport_uses_approved_ip_and_preserves_origin_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pinned transport 只拨批准 IP，同时保留注册域名的 Host 和 TLS SNI。"""

    class NetworkStream:
        def __init__(self) -> None:
            self.writes: list[bytes] = []
            self.server_hostname: str | None = None
            self.response_sent = False

        async def read(self, _max_bytes: int, timeout: float | None = None) -> bytes:
            if self.response_sent:
                return b''
            self.response_sent = True
            return b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK'

        async def write(self, buffer: bytes, timeout: float | None = None) -> None:
            self.writes.append(buffer)

        async def start_tls(
            self,
            ssl_context: object,
            server_hostname: str | None = None,
            timeout: float | None = None,
        ) -> 'NetworkStream':
            self.server_hostname = server_hostname
            return self

        async def aclose(self) -> None:
            return None

        def get_extra_info(self, _info: str) -> None:
            return None

    stream = NetworkStream()
    transport = PinnedHttpxTransport('client.example', {'203.0.113.7'})
    backend = transport._pool._network_backend
    connect = AsyncMock(return_value=stream)
    monkeypatch.setattr(backend._backend, 'connect_tcp', connect)

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post('https://client.example/logout', data={'logout_token': 'opaque'})

    assert response.content == b'OK'
    assert connect.await_args.args[:2] == ('203.0.113.7', 443)
    assert stream.server_hostname == 'client.example'
    assert b'host: client.example\r\n' in b''.join(stream.writes).lower()


@pytest.mark.asyncio
async def test_pinned_transport_stops_oversized_response_stream() -> None:
    """远端超大响应在流读取时主动中止，不在内存中无限累积。"""

    class Stream:
        async def __aiter__(self) -> Any:
            yield b'x' * (70 * 1024)

        async def aclose(self) -> None:
            return None

    response = SimpleNamespace(status=200, headers=[], stream=Stream(), extensions={}, aclose=AsyncMock())
    transport = PinnedHttpxTransport('client.example', {'203.0.113.7'})
    transport._pool.handle_async_request = AsyncMock(return_value=response)
    result = await transport.handle_async_request(httpx.Request('POST', 'https://client.example/logout'))
    with pytest.raises(OSError, match='响应大小超过限制'):
        async for _chunk in result.aiter_bytes():
            pass
    response.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_backchannel_retry_consumer_revalidates_uri_and_reissues_short_lived_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重试消费者不保存 Token，重验注册 URI 后重新签发并成功出队。"""
    redis = FakeRedis()
    queue_key = 'oidc:backchannel:retry'
    await redis.rpush(
        queue_key,
        '{"uri":"https://client.example/logout","client_id":"portal","sid":"sid-1",'
        '"event_jti":"event-1","include_sid":true,"attempt":1}',
    )
    client = SimpleNamespace(client_pk=20, client_id='portal', status='0')
    registered = SimpleNamespace(uri='https://client.example/logout', status='0')
    monkeypatch.setattr(
        'module_identity.service.session_service.OAuthClientDao.get_by_client_id', _async_return(client)
    )
    monkeypatch.setattr(
        'module_identity.service.session_service.OAuthClientDao.find_exact_uri', _async_return(registered)
    )
    monkeypatch.setattr(LogoutService, '_safe_backchannel_uri', _async_return(True))
    monkeypatch.setattr(LogoutService, '_make_logout_token', _async_return('fresh.logout.token'))
    sent: list[tuple[str, str]] = []

    async def notify(uri: str, token: str) -> None:
        sent.append((uri, token))

    result = await LogoutService.consume_backchannel_retry(object(), redis, notifier=notify)

    assert result == 1
    assert sent == [('https://client.example/logout', 'fresh.logout.token')]
    assert await redis.lpop(queue_key) is None


@pytest.mark.asyncio
async def test_logout_endpoint_disabled_is_local_404_without_legacy_pre_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OIDC 关闭时直接返回裸 404，不执行数据库或 Legacy PreAuth。"""

    config = SimpleNamespace(oidc_enabled=False)
    monkeypatch.setattr(controller, 'OidcConfig', config)
    response = await controller.logout(_request(), object())

    assert response.status_code == _HTTP_NOT_FOUND


@pytest.mark.asyncio
async def test_logout_endpoint_prepares_confirmation_without_clearing_sso_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """初次退出只建立确认，不清理 SSO Cookie 或撤销登录。"""

    config = SimpleNamespace(
        oidc_enabled=True,
        oidc_sso_cookie_name='__Host-ruoyi-sso',
        oidc_sso_cookie_secure=True,
        oidc_sso_cookie_domain=None,
        oidc_sso_cookie_samesite='lax',
    )
    monkeypatch.setattr(controller, 'OidcConfig', config)

    async def fake_logout(*_args: object, **_kwargs: object) -> LogoutResult:
        return LogoutResult('https://portal.example/logged-out', 'state-1', True)

    monkeypatch.setattr(controller.LogoutService, 'execute_logout', fake_logout)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(controller.LogoutConfirmationService, 'issue', AsyncMock(return_value=('t' * 43, 'n' * 43)))
    execute = AsyncMock()
    monkeypatch.setattr(controller.LogoutService, 'execute_logout', execute)
    response = await controller.logout(_request(), db)

    assert response.status_code == _HTTP_OK
    assert controller.LogoutConfirmationService.COOKIE_NAME in response.headers['set-cookie']
    assert '__Host-ruoyi-sso=' not in response.headers['set-cookie']
    assert '确认退出'.encode() in response.body
    execute.assert_not_awaited()
    assert OidcUtil.append_state('https://portal.example/logged-out?state=old&next=1', 'state-1') == (
        'https://portal.example/logged-out?next=1&state=state-1'
    )


@pytest.mark.asyncio
async def test_logout_endpoint_unexpected_service_error_returns_503_without_clearing_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logout Service 异常时返回 503，避免清理仍有效的认证 Cookie。"""

    config = SimpleNamespace(
        oidc_enabled=True,
        oidc_sso_cookie_name='__Host-ruoyi-sso',
        oidc_sso_cookie_secure=True,
        oidc_sso_cookie_domain=None,
        oidc_sso_cookie_samesite='lax',
    )
    monkeypatch.setattr(controller, 'OidcConfig', config)

    async def fail(*_args: object, **_kwargs: object) -> LogoutResult:
        raise RuntimeError('unexpected failure')

    monkeypatch.setattr(controller.LogoutConfirmationService, 'issue', fail)
    request = _request(headers=[(b'cookie', b'__Host-ruoyi-sso=valid-cookie')])
    response = await controller.logout(request, SimpleNamespace())

    assert response.status_code == _HTTP_SERVICE_UNAVAILABLE
    assert 'set-cookie' not in response.headers


@pytest.mark.asyncio
async def test_logout_endpoint_post_form_forwards_logout_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST application/x-www-form-urlencoded 正确解析并转发 Logout 参数。"""

    config = SimpleNamespace(
        oidc_enabled=True,
        oidc_sso_cookie_name='__Host-ruoyi-sso',
        oidc_sso_cookie_secure=True,
        oidc_sso_cookie_domain=None,
        oidc_sso_cookie_samesite='lax',
    )
    monkeypatch.setattr(controller, 'OidcConfig', config)
    monkeypatch.setattr('module_identity.dependencies.OidcConfig', config)
    captured: dict[str, object] = {}

    async def prepare(_redis: object, parameters: dict[str, str], _cookie: str | None) -> tuple[str, str]:
        captured.update(parameters)
        return 't' * 43, 'n' * 43

    monkeypatch.setattr(controller.LogoutConfirmationService, 'issue', prepare)
    body = b'id_token_hint=hint-value&post_logout_redirect_uri=https%3A%2F%2Fportal.example%2Fdone&state=state-1'
    request = _request(
        method='POST',
        headers=[
            (b'content-type', b'application/x-www-form-urlencoded'),
            (b'content-length', str(len(body)).encode()),
        ],
        body=body,
    )

    response = await controller.logout(request, SimpleNamespace())

    assert response.status_code == _HTTP_OK
    assert captured['id_token_hint'] == 'hint-value'
    assert captured['post_logout_redirect_uri'] == 'https://portal.example/done'
    assert captured['state'] == 'state-1'


def _request(
    *,
    method: str = 'GET',
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b'',
) -> Request:
    """构造带最小 Redis 状态的 Starlette Request。"""

    app = SimpleNamespace(state=SimpleNamespace(redis=object()))

    async def receive() -> dict[str, object]:
        return {'type': 'http.request', 'body': body, 'more_body': False}

    return Request(
        {
            'type': 'http',
            'method': method,
            'path': '/oauth2/logout',
            'headers': headers or [],
            'query_string': b'',
            'app': app,
        },
        receive,
    )


def _async_return(value: object) -> object:
    """构造固定值异步桩。"""

    async def return_value(*_args: object, **_kwargs: object) -> object:
        return value

    return return_value


async def _async_noop(*_args: object, **_kwargs: object) -> None:
    """构造无副作用异步桩。"""


@pytest.mark.asyncio
async def test_expired_id_token_is_accepted_only_as_logout_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = jwt.decode(_id_token(private_key), options={'verify_signature': False})
    payload.update(iat=int(_NOW.timestamp()) - 1200, exp=int(_NOW.timestamp()) - 600)
    token = encode_id_token(payload, private_key, 'key-1')
    monkeypatch.setattr(
        'module_identity.service.session_service.OAuthClientDao.get_by_client_id',
        _async_return(SimpleNamespace(client_pk=20, client_id='portal', status='0')),
    )
    monkeypatch.setattr(
        'module_identity.service.session_service.OidcKeyDao.get_verifying',
        _async_return(_key_record(private_key)),
    )
    claims, _ = await LogoutService._validate_id_token_hint(object(), token, _NOW)
    assert claims['sid'] == 'sid-1'
    with pytest.raises(JwtProfileError):
        decode_id_token(token, verification_key=private_key.public_key(), issuer=_ISSUER, audience='portal')


@pytest.mark.asyncio
async def test_confirmed_logout_does_not_revoke_another_accounts_hint_session(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(client_pk=20, client_id='portal', status='0')
    other = SimpleNamespace(sid='other-sid', subject_id='other-subject', status='active')
    current = SimpleNamespace(sid='current-sid', subject_id='current-subject', status='active')
    monkeypatch.setattr(
        LogoutService, '_validate_id_token_hint', _async_return(({'sid': other.sid, 'sub': other.subject_id}, client))
    )
    monkeypatch.setattr('module_identity.service.session_service.SsoSessionDao.get_by_sid', _async_return(other))
    monkeypatch.setattr(
        'module_identity.service.session_service.SsoSessionService.validate_logout_cookie', _async_return(current)
    )
    monkeypatch.setattr(LogoutService, '_lock_session_refresh_tokens', _async_return([]))
    revoked = AsyncMock()
    monkeypatch.setattr(LogoutService, '_revoke_session_state', revoked)
    monkeypatch.setattr(LogoutService, '_register_backchannel', _async_noop)
    monkeypatch.setattr(
        'module_identity.service.session_service.SsoSessionDao.client_ids_for_sid', AsyncMock(return_value=[])
    )
    result = await LogoutService._logout(
        object(),
        object(),
        id_token_hint='signed-other-account',
        cookie='current-cookie',
        confirmed=True,
        coordinator=AfterCommitCoordinator(),
        now=_NOW,
    )
    assert revoked.await_args.args[2] == 'current-sid'
    assert result.redirect_uri is None
