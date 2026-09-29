"""Token Introspection 服务的安全边界测试。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config.env import OidcConfig
from module_identity.dao.oauth_access_policy_dao import OAuthAccessPolicyDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.security.opaque_token import token_digest
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.token_protocol_service import IntrospectionService
from tests.module_identity.support.redis_fakes import FakeRedis

_PEPPER = 'introspection-test-pepper-' + 'x' * 32
_AUTH_VERSION = 3


def _config() -> SimpleNamespace:
    """构造内省所需的最小配置。"""

    return SimpleNamespace(
        oidc_issuer='https://auth.example.com',
        oidc_allowed_clock_skew_seconds=60,
        oidc_token_hash_pepper=_PEPPER,
    )


@pytest.fixture(autouse=True)
def _configure_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """将全局 OIDC 配置固定为本文件测试所需的协议值。"""

    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example.com')
    monkeypatch.setattr(OidcConfig, 'oidc_allowed_clock_skew_seconds', 60)
    monkeypatch.setattr(OidcConfig, 'oidc_token_hash_pepper', _PEPPER)


def _client(client_type: str = 'confidential') -> SimpleNamespace:
    """构造已启用的 Client 数据快照。"""

    return SimpleNamespace(
        client_pk=10,
        client_id='introspector',
        client_type=client_type,
        status='0',
        policy_version=1,
        token_endpoint_auth_method='client_secret_basic' if client_type == 'confidential' else 'none',
        grant_types=['authorization_code', 'refresh_token'],
    )


def _principal(client_type: str = 'confidential') -> OAuthClientPrincipal:
    """构造完成认证的 Client Principal。"""

    return OAuthClientPrincipal('introspector', client_type, 'client_secret_basic')


@pytest.mark.asyncio
async def test_introspection_rejects_non_client_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """任意用户主体或普通对象都不能调用内省端点。"""

    result = await IntrospectionService.introspect(object(), FakeRedis(), 'not-a-token', object())

    assert result == {'active': False}


@pytest.mark.asyncio
async def test_introspection_rejects_public_or_inactive_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """内省调用方必须是数据库事实中的启用 Confidential Client。"""

    async def client_lookup(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _client('public')

    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', client_lookup)
    result = await IntrospectionService.introspect(object(), FakeRedis(), 'not-a-token', _principal())

    assert result == {'active': False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('client_type', 'db_method', 'principal_type', 'principal_method', 'expected'),
    [
        ('public', 'none', 'public', 'none', False),
        ('confidential', 'client_secret_basic', 'confidential', 'client_secret_basic', True),
        ('confidential', 'none', 'confidential', 'client_secret_basic', False),
        ('confidential', 'client_secret_basic', 'confidential', 'client_secret_post', False),
        ('confidential', 'client_secret_basic', 'public', 'none', False),
    ],
)
async def test_introspection_auth_method_pair_is_exact(
    monkeypatch: pytest.MonkeyPatch,
    client_type: str,
    db_method: str,
    principal_type: str,
    principal_method: str,
    expected: bool,
) -> None:
    """Introspection 仅接受数据库与 Principal 同时为 Confidential/Basic。"""

    client = _client(client_type)
    client.token_endpoint_auth_method = db_method
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _lookup(client)
    )

    result = await IntrospectionService._resolve_caller(
        object(), OAuthClientPrincipal('introspector', principal_type, principal_method)
    )

    assert (result is not None) is expected


@pytest.mark.asyncio
async def test_access_introspection_honours_revoked_jti_and_resource_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Access JWT 必须通过签名 Profile、撤销键和 Resource 内省授权。"""

    client = _client()

    async def client_lookup(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return client

    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', client_lookup)
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.decode_access_token',
        lambda *_args, **_kwargs: {
            'iss': 'https://auth.example.com',
            'sub': 'subject',
            'client_id': 'introspector',
            'aud': ['https://auth.example.com/oauth2/userinfo', 'https://api.example'],
            'scope': 'openid api.read',
            'iat': 100,
            'exp': 200,
            'jti': 'jti-1',
        },
    )
    monkeypatch.setattr(
        IntrospectionService,
        '_resources_owned_by_caller',
        classmethod(lambda cls, *_args, **_kwargs: _async_true()),
    )
    redis = FakeRedis()
    await redis.set('oidc:revoked_jti:jti-1', '1', ex=60)

    result = await IntrospectionService.introspect(
        object(), redis, 'signed-access', _principal(), now=datetime.now(timezone.utc)
    )

    assert result == {'active': False}


@pytest.mark.asyncio
async def test_business_client_a_is_introspected_by_independent_resource_client_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """业务 Client A 签发的 Token 可由 Resource 专用 Client B 内省。"""

    caller = _client()
    issuer = _client()
    issuer.client_pk = 20
    issuer.client_id = 'business-a'
    issuer.grant_types = ['authorization_code', 'refresh_token']

    async def client_lookup(_db: object, client_id: str, active_only: bool = True) -> SimpleNamespace:
        return caller if client_id == 'introspector' else issuer

    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', client_lookup)
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.decode_access_token',
        lambda *_args, **_kwargs: {
            'iss': 'https://auth.example.com',
            'sub': 'subject-a',
            'client_id': 'business-a',
            'aud': ['https://auth.example.com/oauth2/userinfo', 'https://api.example'],
            'scope': 'api.read',
            'gty': 'authorization_code',
            'ver': 3,
            'iat': 100,
            'exp': 500,
            'jti': 'jti-a',
        },
    )
    monkeypatch.setattr(IntrospectionService, '_resources_owned_by_caller', lambda *_args, **_kwargs: _async_true())
    monkeypatch.setattr(IntrospectionService, '_client_allows_access', lambda *_args, **_kwargs: _async_true())
    monkeypatch.setattr(IntrospectionService, '_access_user_state', lambda *_args, **_kwargs: _async_user())
    result = await IntrospectionService.introspect(object(), FakeRedis(), 'signed-access', _principal())

    assert result['active'] is True
    assert result['client_id'] == 'business-a'
    assert result['username'] == 'alice'
    assert result['gty'] == 'authorization_code'
    assert result['ver'] == _AUTH_VERSION


@pytest.mark.asyncio
async def test_independent_resource_client_b_is_rejected_for_wrong_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resource 不属于调用方 B 时，即使 Token 签名正确也必须拒绝。"""

    caller = _client()
    issuer = _client()
    issuer.client_pk = 20
    issuer.client_id = 'business-a'

    async def client_lookup(_db: object, client_id: str, active_only: bool = True) -> SimpleNamespace:
        return caller if client_id == 'introspector' else issuer

    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', client_lookup)
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.decode_access_token',
        lambda *_args, **_kwargs: {
            'iss': 'https://auth.example.com',
            'sub': 'subject-a',
            'client_id': 'business-a',
            'aud': ['https://api.example'],
            'scope': 'api.read',
            'iat': 100,
            'exp': 500,
            'jti': 'jti-a',
        },
    )
    monkeypatch.setattr(IntrospectionService, '_resources_owned_by_caller', lambda *_args, **_kwargs: _async_false())

    result = await IntrospectionService.introspect(object(), FakeRedis(), 'signed-access', _principal())

    assert result == {'active': False}


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_state', ['subject', 'user', 'session', 'grant'])
async def test_access_user_state_rejects_each_real_time_failure(
    monkeypatch: pytest.MonkeyPatch, invalid_state: str
) -> None:
    """用户 Access Token 的 Subject、用户、版本、Session、Grant 任一失效都拒绝。"""

    subject = SimpleNamespace(subject_id='subject-a', user_id=7, auth_version=3)
    user = SimpleNamespace(status='0', del_flag='0', user_name='alice')
    session = SimpleNamespace(user_id=7, subject_id='subject-a', auth_version=3)
    db = object()
    if invalid_state == 'subject':
        subject = None
    elif invalid_state == 'user':
        user.status = '1'
    elif invalid_state == 'session':
        session = None
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.IdentitySubjectDao.get_by_subject_id', _lookup(subject)
    )
    monkeypatch.setattr('module_identity.service.token_protocol_service.IdentityUserDao.get_user', _lookup(user))
    monkeypatch.setattr('module_identity.service.token_protocol_service.SsoSessionDao.get_active', _lookup(session))
    monkeypatch.setattr(OAuthAccessPolicyDao, 'is_blocked', _lookup(False))
    monkeypatch.setattr(OAuthGrantDao, 'get_by_grant_id', _lookup(None))
    claims = {
        'sub': 'subject-a',
        'ver': 3,
        'sid': 'sid-a',
        'scope': 'api.read',
        'grant_id': 'grant-a',
    }

    assert not await IntrospectionService._access_user_state(
        db, claims, _client(), ['https://api.example'], datetime.now(timezone.utc)
    )


@pytest.mark.asyncio
async def test_machine_access_token_uses_client_binding_without_user_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """client_credentials Token 校验机器 Subject/Grant 能力，不读取用户状态。"""

    caller = _client()
    issuer = _client()
    issuer.client_pk = 20
    issuer.client_id = 'machine-a'
    issuer.grant_types = ['client_credentials']

    async def client_lookup(_db: object, client_id: str, active_only: bool = True) -> SimpleNamespace:
        return caller if client_id == 'introspector' else issuer

    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', client_lookup)
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.list_resources',
        _lookup([SimpleNamespace(audience='https://api.example', status='0')]),
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.decode_access_token',
        lambda *_args, **_kwargs: {
            'iss': 'https://auth.example.com',
            'sub': 'client:machine-a',
            'client_id': 'machine-a',
            'aud': ['https://api.example'],
            'scope': 'api.read',
            'gty': 'client_credentials',
            'iat': 100,
            'exp': 500,
            'jti': 'machine-jti',
        },
    )
    monkeypatch.setattr(IntrospectionService, '_resources_owned_by_caller', lambda *_args, **_kwargs: _async_true())
    monkeypatch.setattr(IntrospectionService, '_client_allows_access', lambda *_args, **_kwargs: _async_true())

    result = await IntrospectionService.introspect(object(), FakeRedis(), 'machine-access', _principal())

    assert result['active'] is True


@pytest.mark.asyncio
async def test_invalid_refresh_shape_is_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refresh Token 内省必须验证完整 typed opaque token。"""

    async def client_lookup(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _client()

    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', client_lookup)
    result = await IntrospectionService.introspect(object(), FakeRedis(), 'rt1.token-id', _principal())

    assert result == {'active': False}


@pytest.mark.asyncio
@pytest.mark.parametrize('session_auth_version', [3, 4])
async def test_refresh_introspection_rechecks_identity_session_grant_and_resources(
    monkeypatch: pytest.MonkeyPatch, session_auth_version: int
) -> None:
    """Refresh 内省成功前重新检查用户版本、Session、Grant 和 Resource。"""
    monkeypatch.setattr(OAuthAccessPolicyDao, 'is_blocked', _lookup(False))

    caller = _client()
    client = _client()
    client.client_pk = 20
    client.client_id = 'business-a'
    token = 'rt1.token-0003.' + ('A' * 43)
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        token_id='token-0003',
        token_hash='',
        client_pk=20,
        family_id='family-3',
        status='active',
        user_id=7,
        subject_id='subject-7',
        auth_version=3,
        sid='sid-7',
        grant_id='grant-7',
        scopes=['api.read'],
        resources=['https://api.example'],
        issued_at=now - timedelta(minutes=1),
        idle_expires_at=now + timedelta(minutes=5),
        absolute_expires_at=now + timedelta(hours=1),
    )
    row.token_hash = token_digest(token, _PEPPER)
    grant = SimpleNamespace(
        user_id=7,
        subject_id='subject-7',
        client_pk=20,
        status='active',
        client_policy_version=1,
        expires_at=None,
        granted_scopes=['api.read'],
        granted_resources=['https://api.example'],
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _lookup(caller)
    )
    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthTokenDao.get_by_token_id', _lookup(row))
    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthClientDao.get_by_pk', _lookup(client))
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.IntrospectionService._refresh_family_active',
        lambda *_args, **_kwargs: _async_true(),
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.IdentitySubjectDao.get_by_user_id',
        _lookup(SimpleNamespace(subject_id='subject-7', auth_version=3)),
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.IdentityUserDao.get_user',
        _lookup(SimpleNamespace(status='0', del_flag='0', user_name='alice')),
    )
    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthGrantDao.get_by_grant_id', _lookup(grant))
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.SsoSessionDao.get_active',
        _lookup(SimpleNamespace(subject_id='subject-7', user_id=7, auth_version=session_auth_version)),
    )
    db = object()
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.IntrospectionService._resources_owned_by_caller',
        lambda *_args, **_kwargs: _async_true(),
    )

    result = await IntrospectionService.introspect(db, FakeRedis(), token, _principal(), now=now)

    assert result['active'] is (session_auth_version == _AUTH_VERSION)
    if session_auth_version == _AUTH_VERSION:
        assert result['client_id'] == 'business-a'


def _lookup(value: object) -> object:
    """返回固定值的异步查询桩。"""

    async def lookup(*_args: object, **_kwargs: object) -> object:
        return value

    return lookup


async def _async_true() -> bool:
    """返回异步 True，供类方法 monkeypatch 使用。"""

    return True


async def _async_user() -> SimpleNamespace:
    """返回带当前用户名的已验证用户快照。"""

    return SimpleNamespace(user_name='alice')


async def _async_false() -> bool:
    """返回异步 False，供失败路径 monkeypatch 使用。"""

    return False
