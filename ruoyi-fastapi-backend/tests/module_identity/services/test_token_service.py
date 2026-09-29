"""Token Endpoint 服务的授权绑定、JWT Profile 和 Refresh 轮换测试。"""

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.role_do import SysRole
from module_admin.entity.do.user_do import SysUser, SysUserRole
from module_identity.dao.oauth_access_policy_dao import OAuthAccessPolicyDao
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.security.client_auth import hash_client_secret
from module_identity.security.jwt_profile import decode_access_token, decode_id_token
from module_identity.security.opaque_token import generate_refresh_token, token_digest
from module_identity.security.pkce import generate_code_challenge
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.audit_service import AuditService
from module_identity.service.authorization_service import AuthorizationCodeReuseError, AuthorizationCodeService
from module_identity.service.token_service import RefreshTokenReuseDetected, TokenResult, TokenService
from tests.module_identity.support.redis_fakes import FakeRedis

_PEPPER = 'token-service-test-pepper-' + 'x' * 32
_VERIFIER = 'v' * 64
_CHALLENGE = generate_code_challenge(_VERIFIER)
_ACCESS_TTL = 120
_AUTH_VERSION = 4
_DEPT_ID = 7301
_DEFAULT_TTL = 600
_LONG_TTL = 1200
_RESOURCE_TTL = 900
_MAX_TTL = 1800


@pytest.mark.asyncio
async def test_confidential_auth_marks_only_matching_secret_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功 Basic 认证在同一事务标记匹配 Secret，错误 Secret 不更新。"""
    secret = 'cs1.' + 's' * 32
    client = _client(client_type='confidential', token_endpoint_auth_method='client_secret_basic')
    secret_row = SimpleNamespace(secret_id='secret-1', secret_hash=hash_client_secret(secret))
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.get_by_client_id', AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.list_secrets', AsyncMock(return_value=[secret_row])
    )
    mark_used = AsyncMock(return_value=True)
    monkeypatch.setattr('module_identity.service.token_service.OAuthClientDao.mark_secret_used', mark_used)
    db = object()
    header = 'Basic ' + base64.b64encode(f'{client.client_id}:{secret}'.encode()).decode()

    await TokenService.authenticate_client(db, authorization=header)

    mark_used.assert_awaited_once_with(db, 'secret-1')
    mark_used.reset_mock()
    bad_header = 'Basic ' + base64.b64encode(f'{client.client_id}:wrong-secret'.encode()).decode()
    with pytest.raises(OAuthProtocolException):
        await TokenService.authenticate_client(db, authorization=bad_header)
    mark_used.assert_not_awaited()


def _config() -> SimpleNamespace:
    """构造最小 JWT/TTL 配置快照。"""
    return SimpleNamespace(
        oidc_issuer='https://auth.example.com',
        oidc_access_token_ttl_seconds=600,
        oidc_max_access_token_ttl_seconds=1800,
        oidc_id_token_ttl_seconds=300,
        oidc_refresh_token_idle_seconds=3600,
        oidc_refresh_token_absolute_seconds=7200,
        oidc_token_hash_pepper=_PEPPER,
    )


@pytest.fixture(autouse=True)
def _configure_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """将全局 OIDC 配置固定为本文件测试所需的协议值。"""

    values = {
        'oidc_issuer': 'https://auth.example.com',
        'oidc_access_token_ttl_seconds': _DEFAULT_TTL,
        'oidc_max_access_token_ttl_seconds': _MAX_TTL,
        'oidc_id_token_ttl_seconds': 300,
        'oidc_refresh_token_idle_seconds': 3600,
        'oidc_refresh_token_absolute_seconds': 7200,
        'oidc_token_hash_pepper': _PEPPER,
    }
    for name, value in values.items():
        monkeypatch.setattr(OidcConfig, name, value)


def _client(**overrides: object) -> SimpleNamespace:
    """构造 Token 流程所需的 Client 标量快照。"""
    value: dict[str, object] = {
        'client_pk': 1001,
        'client_id': 'portal-client',
        'client_type': 'public',
        'grant_types': ['authorization_code', 'refresh_token'],
        'access_token_ttl_seconds': None,
        'refresh_token_idle_seconds': None,
        'refresh_token_absolute_seconds': None,
        'policy_version': 3,
        'status': '0',
    }
    value.update(overrides)
    return SimpleNamespace(**value)


def _code_payload(**overrides: object) -> dict[str, object]:
    """构造已由 AuthorizationCodeService 验证的 Code 绑定。"""
    value: dict[str, object] = {
        'clientPk': 1001,
        'redirectUri': 'https://portal.example/callback',
        'userId': 2001,
        'subjectId': 'subject-2001',
        'authVersion': 4,
        'sid': 'sid-2001',
        'grantId': 'grant-2001',
        'scopes': ['openid', 'profile'],
        'resources': [],
        'nonce': 'nonce-2001',
        'codeChallenge': _CHALLENGE,
        'codeChallengeMethod': 'S256',
        'authTime': '2026-08-24T04:00:00+00:00',
    }
    value.update(overrides)
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize('remembered', [True, False])
async def test_authorization_code_binds_client_redirect_and_pkce(
    monkeypatch: pytest.MonkeyPatch, remembered: bool
) -> None:
    """验证 Code 兑换严格绑定 Client、Redirect URI 和 S256 verifier。"""
    monkeypatch.setattr(OAuthAccessPolicyDao, 'lock_client', AsyncMock())
    monkeypatch.setattr(AuditService, 'record', AsyncMock())
    monkeypatch.setattr(AuditService, 'record_independent', AsyncMock())
    client = _client()
    payload = _code_payload()
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.get_by_client_id',
        lambda db, client_id, active_only=True: _async_value(client),
    )

    async def identity(*args: object, **kwargs: object) -> tuple[object, object]:
        return SimpleNamespace(user_id=2001, status='0', del_flag='0'), SimpleNamespace(
            subject_id='subject-2001', auth_version=4
        )

    async def session(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            sid='sid-2001',
            user_id=2001,
            subject_id='subject-2001',
            auth_version=4,
            status='active',
            auth_time=datetime.now(timezone.utc),
            acr='urn:test',
            amr=['pwd'],
        )

    monkeypatch.setattr('module_identity.service.token_service.SsoSessionDao.record_client', AsyncMock())
    monkeypatch.setattr(TokenService, '_require_user_identity', identity)
    monkeypatch.setattr(TokenService, '_require_session', session)
    monkeypatch.setattr(
        TokenService,
        '_require_grant',
        lambda *args, **kwargs: _async_value(
            SimpleNamespace(grant_id='grant-2001', remembered_scopes=['openid'] if remembered else [])
        ),
    )
    monkeypatch.setattr(
        TokenService,
        '_validate_client_scope_resource',
        lambda *args, **kwargs: _async_value((['openid', 'profile'], [], None)),
    )
    monkeypatch.setattr(
        TokenService,
        '_issue_access_token',
        lambda *args, **kwargs: _async_value(('access', 600)),
    )
    monkeypatch.setattr(TokenService, '_issue_id_token', lambda *args, **kwargs: _async_value('id'))

    redis = FakeRedis()
    code = await AuthorizationCodeService.issue(redis, payload, pepper=_PEPPER)
    result = await TokenService.authorization_code(
        object(),
        redis,
        {
            'grant_type': 'authorization_code',
            'client_id': 'portal-client',
            'code': code,
            'redirect_uri': 'https://portal.example/callback',
            'code_verifier': _VERIFIER,
        },
        OAuthClientPrincipal('portal-client', 'public', 'none'),
    )
    assert isinstance(result, TokenResult)
    assert result.access_token == 'access' and result.id_token == 'id'
    assert result.refresh_token is None
    assert await redis.get(f'oidc:authorization_code:{code.split(".")[1]}') is None

    with pytest.raises(OAuthProtocolException) as raised:
        await TokenService.authorization_code(
            object(),
            redis,
            {
                'grant_type': 'authorization_code',
                'client_id': 'portal-client',
                'code': code,
                'redirect_uri': 'https://portal.example/callback',
                'code_verifier': 'wrong-' + _VERIFIER,
            },
            OAuthClientPrincipal('portal-client', 'public', 'none'),
            token_pepper=_PEPPER,
        )
    assert raised.value.error == 'invalid_grant'

    with pytest.raises(OAuthProtocolException) as raised:
        await TokenService.authorization_code(
            object(),
            redis,
            {
                'grant_type': 'authorization_code',
                'client_id': 'portal-client',
                'code': code,
                'redirect_uri': 'https://portal.example/other',
                'code_verifier': _VERIFIER,
            },
            OAuthClientPrincipal('portal-client', 'public', 'none'),
            token_pepper=_PEPPER,
        )
    assert raised.value.error == 'invalid_grant'


@pytest.mark.asyncio
async def test_authorization_code_reuse_revokes_bound_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    """授权码重用必须撤销首次兑换关联的 Grant 和 Refresh Token。"""
    client = _client()
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.get_by_client_id',
        AsyncMock(return_value=client),
    )
    monkeypatch.setattr(
        AuthorizationCodeService,
        'consume',
        AsyncMock(side_effect=AuthorizationCodeReuseError()),
    )
    monkeypatch.setattr(
        AuthorizationCodeService,
        'consumed_payload',
        AsyncMock(return_value=_code_payload()),
    )
    revoke = AsyncMock(return_value=True)
    monkeypatch.setattr('module_identity.service.token_service.OAuthGrantDao.revoke', revoke)
    monkeypatch.setattr(AuditService, 'record_independent', AsyncMock())
    db = SimpleNamespace(execute=AsyncMock())

    with pytest.raises(AuthorizationCodeReuseError):
        await TokenService.authorization_code(
            db,
            FakeRedis(),
            {
                'grant_type': 'authorization_code',
                'client_id': 'portal-client',
                'code': 'ac1.code-id.code-secret',
                'redirect_uri': 'https://portal.example/callback',
                'code_verifier': _VERIFIER,
            },
            OAuthClientPrincipal('portal-client', 'public', 'none'),
        )

    revoke.assert_awaited_once_with(db, 'grant-2001', reason='authorization_code_reuse')


@pytest.mark.asyncio
async def test_client_credentials_is_machine_domain_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 Client Credentials 仅签发机器 sub，不产生用户 Session Claims。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = _client(
        client_type='confidential',
        grant_types=['client_credentials'],
    )
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.get_by_client_id',
        lambda db, client_id, active_only=True: _async_value(client),
    )
    monkeypatch.setattr(
        TokenService,
        '_validate_client_scope_resource',
        lambda *args, **kwargs: _async_value((['portal.service.read'], ['https://api.example'], None)),
    )
    monkeypatch.setattr(TokenService, '_resolve_signer', lambda *args, **kwargs: _async_value((key, 'kid-1')))
    result = await TokenService.client_credentials(
        object(),
        {'grant_type': 'client_credentials', 'scope': 'portal.service.read', 'resource': 'https://api.example'},
        OAuthClientPrincipal('portal-client', 'confidential', 'client_secret_basic'),
    )
    claims = decode_access_token(
        result.access_token,
        verification_key=key.public_key(),
        issuer='https://auth.example.com',
        audience='https://api.example',
    )
    assert claims['sub'] == 'client:portal-client'
    assert claims['gty'] == 'client_credentials'
    assert 'sid' not in claims
    assert 'ver' not in claims
    assert result.refresh_token is None
    assert result.id_token is None


@pytest.mark.asyncio
async def test_client_credentials_uses_real_async_dao_and_resource_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 Client Credentials 通过真实 AsyncSession 查询 Client/Scope/Resource 绑定。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    tables = [
        SysOAuthClient.__table__,
        SysOAuthResource.__table__,
        SysOAuthScope.__table__,
        SysOAuthClientScope.__table__,
        SysOAuthClientResource.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: SysOAuthClient.metadata.create_all(sync, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        db.add_all(
            [
                SysOAuthClient(
                    client_pk=9101,
                    client_id='real-machine',
                    client_name='Real Machine',
                    client_type='confidential',
                    token_endpoint_auth_method='client_secret_basic',
                    grant_types=['client_credentials'],
                    response_types=[],
                    status='0',
                    access_token_ttl_seconds=120,
                ),
                SysOAuthResource(
                    resource_pk=9102,
                    resource_id='real-api',
                    resource_name='Real API',
                    audience='https://real.api.example',
                    allowed_claims=[],
                    create_by='test',
                    update_by='test',
                    status='0',
                ),
                SysOAuthScope(
                    scope_pk=9103,
                    scope_code='real.service.read',
                    scope_name='Real Service Read',
                    scope_type='resource',
                    resource_pk=9102,
                    claims=[],
                    create_by='test',
                    update_by='test',
                    status='0',
                ),
                SysOAuthClientScope(client_pk=9101, scope_pk=9103),
                SysOAuthClientResource(client_pk=9101, resource_pk=9102),
            ]
        )
        await db.flush()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        monkeypatch.setattr(TokenService, '_resolve_signer', lambda *args, **kwargs: _async_value((key, 'kid-real')))
        result = await TokenService.client_credentials(
            db,
            {'grant_type': 'client_credentials', 'scope': 'real.service.read', 'resource': 'https://real.api.example'},
            OAuthClientPrincipal('real-machine', 'confidential', 'client_secret_basic'),
        )
        assert result.scope == 'real.service.read'
        assert result.refresh_token is None
        assert result.id_token is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_access_and_id_profiles_have_fixed_claims_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证用户 Access/ID Profile、audience、at_hash 和 TTL 上限。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = _config()
    client = _client(access_token_ttl_seconds=_ACCESS_TTL)
    user = SimpleNamespace(user_id=2001, user_name='user', nick_name='User', status='0', del_flag='0')
    subject = SimpleNamespace(subject_id='subject-2001', auth_version=4)
    now = datetime.now(timezone.utc)
    session = SimpleNamespace(
        sid='sid-2001',
        auth_time=now - timedelta(minutes=1),
        acr='urn:test:pwd',
        amr=['pwd'],
    )
    definition = SimpleNamespace(scope_pk=1, scope_code='openid', claims=['sub'], status='0')
    binding = SimpleNamespace(scope_pk=1, claim_filter=None)
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.list_scope_bindings',
        lambda *args, **kwargs: _async_value([binding]),
    )
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.list_scope_definitions',
        lambda *args, **kwargs: _async_value([definition]),
    )
    monkeypatch.setattr(
        'module_identity.service.token_service.ClaimService.load_roles_and_department',
        lambda *args, **kwargs: _async_value(([], None)),
    )
    monkeypatch.setattr(TokenService, '_resolve_signer', lambda *args, **kwargs: _async_value((key, 'kid-1')))
    access, expires = await TokenService._issue_access_token(
        object(),
        client,
        user,
        subject,
        session,
        ['openid'],
        [],
        None,
        grant_type='authorization_code',
        signing_key=key,
        kid='kid-1',
        now=now,
    )
    claims = decode_access_token(
        access,
        verification_key=key.public_key(),
        issuer=config.oidc_issuer,
        audience=f'{config.oidc_issuer}/oauth2/userinfo',
    )
    assert expires == _ACCESS_TTL
    assert claims['aud'] == [f'{config.oidc_issuer}/oauth2/userinfo']
    assert claims['ver'] == _AUTH_VERSION
    assert claims['sid'] == 'sid-2001'
    assert 'user_id' not in claims
    identity = await TokenService._issue_id_token(
        object(),
        client,
        user,
        subject,
        session,
        ['openid'],
        'nonce-2001',
        access,
        signing_key=key,
        kid='kid-1',
        now=now,
    )
    id_claims = decode_id_token(
        identity,
        verification_key=key.public_key(),
        issuer=config.oidc_issuer,
        audience=client.client_id,
        nonce='nonce-2001',
    )
    assert id_claims['nonce'] == 'nonce-2001'
    assert id_claims['at_hash'] == TokenService._at_hash(access)


@pytest.mark.asyncio
async def test_user_claims_load_real_roles_and_department_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 Claims 从真实角色、用户角色和部门行加载，并仍受三层白名单约束。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    tables = [SysUser.__table__, SysDept.__table__, SysRole.__table__, SysUserRole.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: SysUser.metadata.create_all(sync, tables=tables))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        user = SysUser(
            user_id=7201,
            user_name='claims-user',
            nick_name='Claims User',
            dept_id=_DEPT_ID,
            status='0',
            del_flag='0',
        )
        dept = SysDept(dept_id=_DEPT_ID, dept_name='Security', status='0', del_flag='0')
        role = SysRole(
            role_id=7401,
            role_name='Administrator',
            role_key='admin',
            role_sort=1,
            status='0',
            del_flag='0',
        )
        db.add_all([user, dept, role, SysUserRole(user_id=7201, role_id=7401)])
        await db.flush()
        client = _client(client_pk=7501)
        definitions = [
            SimpleNamespace(scope_pk=1, scope_code='roles', claims=['roles'], status='0'),
            SimpleNamespace(scope_pk=2, scope_code='dept', claims=['dept_id', 'dept_name'], status='0'),
        ]
        bindings = [
            SimpleNamespace(
                scope_pk=1, claim_filter={'claims': ['roles', 'dept_id', 'dept_name'], 'allowed_role_keys': ['admin']}
            ),
            SimpleNamespace(
                scope_pk=2, claim_filter={'claims': ['roles', 'dept_id', 'dept_name'], 'allowed_role_keys': ['admin']}
            ),
        ]
        monkeypatch.setattr(
            'module_identity.service.token_service.OAuthClientDao.list_scope_bindings',
            lambda *args, **kwargs: _async_value(bindings),
        )
        monkeypatch.setattr(
            'module_identity.service.token_service.OAuthClientDao.list_scope_definitions',
            lambda *args, **kwargs: _async_value(definitions),
        )
        claims = await TokenService._user_claims(
            db,
            client,
            user,
            SimpleNamespace(subject_id='subject-7201'),
            ['roles', 'dept'],
            None,
        )
        assert claims['roles'] == ['admin']
        assert claims['dept_id'] == _DEPT_ID
        assert claims['dept_name'] == 'Security'
    await engine.dispose()


def test_access_ttl_uses_overrides_and_global_cap() -> None:
    """验证默认、Client/Resource 覆盖和全局上限的最严格策略。"""
    assert TokenService._access_ttl(_client(), None) == _DEFAULT_TTL
    assert TokenService._access_ttl(_client(access_token_ttl_seconds=_LONG_TTL), None) == _LONG_TTL
    resource = SimpleNamespace(access_token_ttl_seconds=_RESOURCE_TTL)
    assert TokenService._access_ttl(_client(access_token_ttl_seconds=_LONG_TTL), resource) == _RESOURCE_TTL
    assert TokenService._access_ttl(_client(access_token_ttl_seconds=3000), None) == _MAX_TTL


@pytest.mark.asyncio
async def test_public_token_entrypoints_require_authenticated_principal() -> None:
    """验证公开 Token 流程拒绝 ORM 行和裸 Client ID。"""
    with pytest.raises(OAuthProtocolException) as raised:
        await TokenService.client_credentials(
            object(),
            {'grant_type': 'client_credentials'},
            'portal-client',
        )
    assert raised.value.error == 'invalid_client'


@pytest.mark.asyncio
async def test_signer_loads_private_key_from_same_active_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证签名私钥和返回 kid 来自同一轮 Active Key 查询。"""
    record = SimpleNamespace(kid='kid-stable')
    private_key = object()
    monkeypatch.setattr(
        'module_identity.service.token_service.OidcKeyDao.get_active',
        lambda *args, **kwargs: _async_value(record),
    )
    calls: list[object] = []

    async def load(value: object, **kwargs: object) -> object:
        calls.append(value)
        return private_key

    monkeypatch.setattr('module_identity.service.token_service.KeyService.load_private_key_async', load)
    key, kid = await TokenService._resolve_signer(object(), None, None, datetime.now(timezone.utc))
    assert key is private_key
    assert kid == 'kid-stable'
    assert calls == [record]


@pytest.mark.asyncio
async def test_refresh_scope_expansion_is_rejected_before_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 Refresh 请求不能扩大原 Token Scope。"""
    monkeypatch.setattr(OAuthAccessPolicyDao, 'lock_client', AsyncMock())
    client = _client(grant_types=['authorization_code', 'refresh_token'])
    row = SimpleNamespace(
        token_id='token-1',
        token_hash='',
        family_id='family-1',
        client_pk=1001,
        status='active',
        user_id=2001,
        subject_id='subject-2001',
        auth_version=4,
        sid='sid-2001',
        scopes=['openid'],
        resources=[],
        grant_id='grant-1',
        idle_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        absolute_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.get_by_client_id',
        lambda db, client_id, active_only=True: _async_value(client),
    )
    token = generate_refresh_token()
    row.token_hash = token_digest(token, _PEPPER)
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthTokenDao.get_by_token_id', lambda *a, **k: _async_value(row)
    )
    monkeypatch.setattr(
        TokenService,
        '_require_user_identity',
        lambda *args, **kwargs: _async_value(
            (SimpleNamespace(user_id=2001), SimpleNamespace(subject_id='subject-2001', auth_version=4))
        ),
    )
    monkeypatch.setattr(
        TokenService,
        '_require_session',
        lambda *args, **kwargs: _async_value(SimpleNamespace(sid='sid-2001')),
    )
    monkeypatch.setattr(
        TokenService,
        '_require_grant',
        lambda *args, **kwargs: _async_value(SimpleNamespace(grant_id='grant-1')),
    )
    with pytest.raises(OAuthProtocolException) as raised:
        await TokenService.refresh_token(
            object(),
            {
                'grant_type': 'refresh_token',
                'client_id': 'portal-client',
                'refresh_token': token,
                'scope': 'openid profile',
            },
            OAuthClientPrincipal('portal-client', 'public', 'none'),
            token_pepper=_PEPPER,
        )
    assert raised.value.error == 'invalid_grant'


@pytest.mark.asyncio
async def test_refresh_concurrent_rotation_has_one_success_and_reuse_revoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证并发轮换只有一个成功，失败请求触发 Family 重放处理。"""
    monkeypatch.setattr(OAuthAccessPolicyDao, 'lock_client', AsyncMock())
    monkeypatch.setattr(AuditService, 'record', AsyncMock())
    client = _client(grant_types=['authorization_code', 'refresh_token'])
    row = SimpleNamespace(
        token_id='token-1',
        token_hash='',
        family_id='family-1',
        client_pk=1001,
        status='active',
        user_id=2001,
        subject_id='subject-2001',
        auth_version=4,
        sid='sid-2001',
        scopes=['openid'],
        resources=[],
        grant_id='grant-1',
        idle_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        absolute_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    token = generate_refresh_token()
    row.token_hash = token_digest(token, _PEPPER)
    state = {'rotated': False, 'reuse': 0, 'mark_now': None}
    lock = asyncio.Lock()
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthClientDao.get_by_client_id',
        lambda db, client_id, active_only=True: _async_value(client),
    )
    monkeypatch.setattr(
        'module_identity.service.token_service.OAuthTokenDao.get_by_token_id', lambda *a, **k: _async_value(row)
    )
    monkeypatch.setattr(
        TokenService,
        '_require_user_identity',
        lambda *args, **kwargs: _async_value(
            (SimpleNamespace(user_id=2001), SimpleNamespace(subject_id='subject-2001', auth_version=4))
        ),
    )
    monkeypatch.setattr(
        TokenService,
        '_require_session',
        lambda *args, **kwargs: _async_value(SimpleNamespace(sid='sid-2001')),
    )
    monkeypatch.setattr(
        TokenService,
        '_require_grant',
        lambda *args, **kwargs: _async_value(SimpleNamespace(grant_id='grant-1')),
    )
    monkeypatch.setattr(
        TokenService,
        '_validate_client_scope_resource',
        lambda *args, **kwargs: _async_value((['openid'], [], None)),
    )

    async def mark_used(*args: object, **kwargs: object) -> bool:
        state['mark_now'] = kwargs.get('now')
        async with lock:
            if state['rotated']:
                return False
            state['rotated'] = True
            return True

    async def reuse(*args: object, **kwargs: object) -> int:
        state['reuse'] += 1
        return 1

    monkeypatch.setattr('module_identity.service.token_service.OAuthTokenDao.mark_used', mark_used)
    monkeypatch.setattr('module_identity.service.token_service.OAuthTokenDao.refresh_token_family_reuse', reuse)
    monkeypatch.setattr(TokenService, '_create_refresh_token', lambda *a, **k: _async_value(token))
    monkeypatch.setattr(TokenService, '_issue_access_token', lambda *a, **k: _async_value(('access', 600)))
    results = await asyncio.gather(
        TokenService.refresh_token(
            object(),
            {'grant_type': 'refresh_token', 'client_id': 'portal-client', 'refresh_token': token},
            OAuthClientPrincipal('portal-client', 'public', 'none'),
            token_pepper=_PEPPER,
        ),
        TokenService.refresh_token(
            object(),
            {'grant_type': 'refresh_token', 'client_id': 'portal-client', 'refresh_token': token},
            OAuthClientPrincipal('portal-client', 'public', 'none'),
            token_pepper=_PEPPER,
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(item, TokenResult) for item in results) == 1
    assert sum(isinstance(item, RefreshTokenReuseDetected) for item in results) == 1
    assert state['reuse'] == 1
    assert isinstance(state['mark_now'], datetime)
    assert state['mark_now'].tzinfo is timezone.utc


def _async_value(value: object) -> Any:
    """返回异步测试桩。"""

    async def result() -> object:
        return value

    return result()
