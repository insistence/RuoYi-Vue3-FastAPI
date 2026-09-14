"""统一认证的授权绑定、令牌有效期和 SSO 会话回归测试。"""

from datetime import timedelta
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.role_do import SysRole
from module_admin.entity.do.user_do import SysUser, SysUserRole
from module_admin.service.user_service import UserService
from module_identity.controller.interaction_controller import _login_response
from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from module_identity.entity.do.oauth_client_do import SysOAuthClient, SysOAuthClientUri
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysSsoSession
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.entity.vo.interaction_vo import ChangePasswordModel, InteractionLoginModel
from module_identity.entity.vo.oauth_resource_vo import ScopeStatusModel
from module_identity.entity.vo.protocol_vo import AuthorizeRequest
from module_identity.redis_keys import OidcRedisKey
from module_identity.security.jwt_profile import decode_access_token
from module_identity.security.pkce import generate_code_challenge
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.authorization_service import AuthorizationCodeService, AuthorizationService
from module_identity.service.consent_service import ConsentService
from module_identity.service.identity_service import CredentialAuthenticationResult, CredentialAuthenticationService
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.interaction_service import InteractionLoginService, InteractionService
from module_identity.service.oauth_management_service import OAuthResourceManagementService
from module_identity.service.session_service import SsoSessionService
from module_identity.service.token_protocol_service import IntrospectionService
from module_identity.service.token_service import TokenResult, TokenService
from tests.module_identity.support.redis_fakes import FakeRedis
from utils.pwd_util import PwdUtil
from utils.time_util import TimezoneUtil

_PEPPER = 'authentication-regression-pepper-' + 'x' * 32
_VERIFIER = 'v' * 64
_REMEMBER_SECONDS = 7 * 24 * 60 * 60
_RESOURCE_SECONDS = 60
_CLIENT_SECONDS = 600


@pytest_asyncio.fixture
async def auth_flow(data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """配置一个业务客户端、机器客户端、资源服务和真实用户会话。"""

    now = TimezoneUtil.utc_now().replace(microsecond=0)
    monkeypatch.setattr(TimezoneUtil, 'utc_now', staticmethod(lambda: now))
    for name, value in {
        'oidc_enabled': True,
        'oidc_issuer': 'https://auth.example.com',
        'oidc_token_hash_pepper': _PEPPER,
        'oidc_access_token_ttl_seconds': _CLIENT_SECONDS,
        'oidc_max_access_token_ttl_seconds': 1800,
        'oidc_id_token_ttl_seconds': 300,
        'oidc_refresh_token_idle_seconds': 3600,
        'oidc_refresh_token_absolute_seconds': 7200,
        'oidc_sso_idle_seconds': 1800,
        'oidc_sso_absolute_seconds': 8 * 60 * 60,
        'oidc_sso_remember_absolute_seconds': _REMEMBER_SECONDS,
        'oidc_sso_cookie_name': '__Host-ruoyi-sso',
        'oidc_sso_cookie_secure': True,
        'oidc_sso_cookie_samesite': 'lax',
        'oidc_sso_cookie_domain': '',
    }.items():
        monkeypatch.setattr(OidcConfig, name, value)
    connection = await data_session.connection()
    await connection.run_sync(
        lambda sync: SysUser.metadata.create_all(
            sync, tables=[SysDept.__table__, SysRole.__table__, SysUserRole.__table__]
        )
    )
    user = SysUser(user_id=2001, user_name='alice', nick_name='Alice', status='0', del_flag='0')
    subject = SysIdentitySubject(identity_id=1, user_id=user.user_id, subject_id=str(uuid4()), auth_version=1)
    app = SysOAuthClient(
        client_pk=1,
        client_id='business-app',
        client_name='Business app',
        client_type='public',
        token_endpoint_auth_method='none',
        grant_types=['authorization_code', 'refresh_token'],
        response_types=['code'],
    )
    machine = SysOAuthClient(
        client_pk=2,
        client_id='machine',
        client_name='Machine',
        client_type='confidential',
        token_endpoint_auth_method='client_secret_basic',
        grant_types=['client_credentials'],
        response_types=[],
        access_token_ttl_seconds=_CLIENT_SECONDS,
    )
    resource_client = SysOAuthClient(
        client_pk=3,
        client_id='resource-server',
        client_name='Resource server',
        client_type='confidential',
        token_endpoint_auth_method='client_secret_basic',
        grant_types=['client_credentials'],
        response_types=[],
    )
    resource = SysOAuthResource(
        resource_pk=1,
        resource_id='business-api',
        resource_name='Business API',
        audience='https://api.example.com',
        introspection_client_pk=3,
        access_token_ttl_seconds=_RESOURCE_SECONDS,
        allowed_claims=['sub'],
        create_by='test',
        update_by='test',
    )
    scope = SysOAuthScope(
        scope_pk=2,
        scope_code='api.read',
        scope_name='Read API',
        scope_type='resource',
        resource_pk=1,
        claims=[],
        create_by='test',
        update_by='test',
    )
    data_session.add_all(
        [
            user,
            subject,
            app,
            machine,
            resource_client,
            resource,
            scope,
            SysOAuthClientUri(client_pk=1, uri_type='redirect', uri='https://app.example.com/callback'),
            SysOAuthScope(
                scope_pk=1,
                scope_code='openid',
                scope_name='OpenID',
                scope_type='identity',
                claims=['sub'],
                consent_required=0,
                create_by='test',
                update_by='test',
            ),
            SysOAuthScope(
                scope_pk=3,
                scope_code='offline_access',
                scope_name='Offline access',
                scope_type='identity',
                claims=[],
                create_by='test',
                update_by='test',
            ),
            SysOAuthClientScope(client_pk=1, scope_pk=1),
            SysOAuthClientScope(client_pk=1, scope_pk=2),
            SysOAuthClientScope(client_pk=1, scope_pk=3),
            SysOAuthClientScope(client_pk=2, scope_pk=2),
            SysOAuthClientResource(client_pk=1, resource_pk=1),
            SysOAuthClientResource(client_pk=2, resource_pk=1),
        ]
    )
    await data_session.commit()
    redis = FakeRedis()
    coordinator = AfterCommitCoordinator()
    cookie, session = await SsoSessionService.create(
        data_session,
        redis,
        user.user_id,
        subject.subject_id,
        subject.auth_version,
        'urn:ruoyi:acr:pwd',
        ('pwd',),
        pepper=_PEPPER,
        now=now,
        coordinator=coordinator,
    )
    await coordinator.commit(data_session)
    return SimpleNamespace(
        db=data_session,
        redis=redis,
        now=now,
        user=user,
        subject=subject,
        app=app,
        machine=machine,
        resource=resource,
        scope=scope,
        cookie=cookie,
        session=session,
        signer=rsa.generate_private_key(public_exponent=65537, key_size=2048),
        caller=OAuthClientPrincipal(resource_client.client_id, 'confidential', 'client_secret_basic'),
    )


def _authorize_request(flow: SimpleNamespace, *, offline: bool = False) -> dict[str, str]:
    """构造携带 PKCE 和 Resource 的授权请求。"""

    return {
        'client_id': flow.app.client_id,
        'redirect_uri': 'https://app.example.com/callback',
        'response_type': 'code',
        'scope': 'openid api.read' + (' offline_access' if offline else ''),
        'nonce': 'regression-nonce',
        'code_challenge': generate_code_challenge(_VERIFIER),
        'code_challenge_method': 'S256',
        'resource': flow.resource.audience,
    }


async def _user_token(
    flow: SimpleNamespace, *, remember: bool = False, offline: bool = False
) -> tuple[TokenResult, SysOAuthGrant | None]:
    """通过真实同意和授权码流程签发用户令牌。"""

    request = AuthorizeRequest(**_authorize_request(flow, offline=offline))
    context = await AuthorizationService.validate_request(flow.db, request)
    consent = await ConsentService.submit_consent(
        flow.db,
        context,
        True,
        context.scopes,
        remember,
        user_id=flow.user.user_id,
        subject_id=flow.subject.subject_id,
    )
    code = await AuthorizationCodeService.issue(
        flow.redis,
        {
            'clientPk': flow.app.client_pk,
            'redirectUri': request.redirect_uri,
            'userId': flow.user.user_id,
            'subjectId': flow.subject.subject_id,
            'authVersion': flow.subject.auth_version,
            'sid': flow.session.sid,
            'grantId': consent.grant.grant_id if consent.grant is not None else None,
            'scopes': list(consent.scopes),
            'resources': [flow.resource.audience],
            'nonce': request.nonce,
            'codeChallenge': request.code_challenge,
            'codeChallengeMethod': 'S256',
            'authTime': flow.now.isoformat(),
        },
        pepper=_PEPPER,
    )
    token = await TokenService.issue_token_request(
        flow.db,
        flow.redis,
        {
            'grant_type': 'authorization_code',
            'client_id': flow.app.client_id,
            'code': code,
            'redirect_uri': request.redirect_uri,
            'code_verifier': _VERIFIER,
        },
        client_id=flow.app.client_id,
        signing_key=flow.signer,
        kid='regression-key',
    )
    return token, consent.grant


async def _machine_token(flow: SimpleNamespace) -> TokenResult:
    """为已认证的机器 Client 签发 Resource 访问令牌。"""

    return await TokenService.client_credentials(
        flow.db,
        {'grant_type': 'client_credentials', 'scope': 'api.read', 'resource': flow.resource.audience},
        OAuthClientPrincipal(flow.machine.client_id, 'confidential', 'client_secret_basic'),
        signing_key=flow.signer,
        kid='regression-key',
        now=flow.now,
    )


async def _introspect(flow: SimpleNamespace, token: str) -> dict[str, object]:
    """使用独立 Resource Client 查询令牌的实时状态。"""

    return await IntrospectionService.introspect(
        flow.db,
        flow.redis,
        token,
        flow.caller,
        verification_key=flow.signer.public_key(),
        now=flow.now,
    )


def _claims(flow: SimpleNamespace, token: str) -> dict[str, object]:
    """验证 Access Token 的签名、Issuer 和 Resource Audience。"""

    return decode_access_token(
        token,
        verification_key=flow.signer.public_key(),
        issuer=OidcConfig.oidc_issuer,
        audience=flow.resource.audience,
    )


def _sign(flow: SimpleNamespace, claims: dict[str, object]) -> str:
    """签署指定 Claims，用于验证内省对授权来源的校验。"""

    return jwt.encode(
        claims,
        flow.signer,
        algorithm='RS256',
        headers={'kid': 'regression-key', 'typ': 'at+jwt'},
    )


@pytest.mark.asyncio
async def test_one_time_consent_is_active_without_creating_a_saved_grant(auth_flow: SimpleNamespace) -> None:
    """一次性同意不创建持久 Grant，签发的 Access Token 仍可正常内省。"""

    token, grant = await _user_token(auth_flow)
    assert grant is None and token.refresh_token is None
    assert await auth_flow.db.scalar(select(func.count()).select_from(SysOAuthGrant)) == 0
    result = await _introspect(auth_flow, token.access_token)
    assert result['active'] is True
    assert result['username'] == 'alice'


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_state', ['policy', 'scope', 'session', 'user', 'version', 'jti'])
async def test_one_time_consent_still_checks_current_security_state(
    auth_flow: SimpleNamespace,
    invalid_state: str,
) -> None:
    """一次性同意的 Access Token 仍受当前授权策略和用户安全状态约束。"""

    token, _ = await _user_token(auth_flow)
    assert (await _introspect(auth_flow, token.access_token))['active'] is True
    if invalid_state == 'policy':
        auth_flow.app.policy_version += 1
    elif invalid_state == 'scope':
        auth_flow.scope.status = '1'
    elif invalid_state == 'session':
        auth_flow.session.status = 'revoked'
    elif invalid_state == 'user':
        auth_flow.user.status = '1'
    elif invalid_state == 'version':
        auth_flow.subject.auth_version += 1
    else:
        await auth_flow.redis.set(OidcRedisKey.revoked_jti(_claims(auth_flow, token.access_token)['jti']), '1', ex=60)
    await auth_flow.db.commit()
    assert await _introspect(auth_flow, token.access_token) == {'active': False}


@pytest.mark.asyncio
@pytest.mark.parametrize('offline', [False, True])
async def test_saved_grant_revocation_cannot_be_bypassed_by_a_later_grant(
    auth_flow: SimpleNamespace,
    offline: bool,
) -> None:
    """持久 Grant 撤销后，再次同意不能恢复旧 Access Token。"""

    token, grant = await _user_token(auth_flow, remember=not offline, offline=offline)
    assert grant is not None
    if offline:
        assert token.refresh_token is not None
        token = await TokenService.issue_token_request(
            auth_flow.db,
            auth_flow.redis,
            {
                'grant_type': 'refresh_token',
                'client_id': auth_flow.app.client_id,
                'refresh_token': token.refresh_token,
            },
            client_id=auth_flow.app.client_id,
            signing_key=auth_flow.signer,
            kid='regression-key',
        )
    assert (await _introspect(auth_flow, token.access_token))['active'] is True
    grant.status = 'revoked'
    await auth_flow.db.commit()
    assert await _introspect(auth_flow, token.access_token) == {'active': False}
    new_token, new_grant = await _user_token(auth_flow, remember=True, offline=offline)
    assert new_grant.grant_id != grant.grant_id
    assert (await _introspect(auth_flow, new_token.access_token))['active'] is True
    assert await _introspect(auth_flow, token.access_token) == {'active': False}


@pytest.mark.asyncio
@pytest.mark.parametrize('remember', [False, True])
async def test_legacy_user_tokens_require_a_persisted_grant(auth_flow: SimpleNamespace, remember: bool) -> None:
    """没有授权来源 Claims 的存量用户令牌仍要求存在有效的持久 Grant。"""

    token, _ = await _user_token(auth_flow, remember=remember)
    claims = _claims(auth_flow, token.access_token)
    claims.pop('grant_id', None)
    claims.pop('client_policy_version', None)
    assert (await _introspect(auth_flow, _sign(auth_flow, claims)))['active'] is remember


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'invalid_context',
    ['missing_policy', 'missing_grant', 'boolean_policy', 'empty_grant', 'unknown_grant', 'offline_without_grant'],
)
async def test_incomplete_or_invalid_authorization_context_is_inactive(
    auth_flow: SimpleNamespace,
    invalid_context: str,
) -> None:
    """授权来源 Claims 缺失或不合法时，内省返回 inactive。"""

    token, _ = await _user_token(auth_flow)
    claims = _claims(auth_flow, token.access_token)
    claims.update(grant_id=None, client_policy_version=auth_flow.app.policy_version)
    if invalid_context == 'missing_policy':
        claims.pop('client_policy_version')
    elif invalid_context == 'missing_grant':
        claims.pop('grant_id')
    elif invalid_context == 'boolean_policy':
        claims['client_policy_version'] = True
    elif invalid_context == 'empty_grant':
        claims['grant_id'] = ''
    elif invalid_context == 'unknown_grant':
        claims['grant_id'] = str(uuid4())
    else:
        claims['scope'] += ' offline_access'
    assert await _introspect(auth_flow, _sign(auth_flow, claims)) == {'active': False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('client_ttl', 'resource_ttl', 'expected'),
    [(_CLIENT_SECONDS, _RESOURCE_SECONDS, _RESOURCE_SECONDS), (30, _RESOURCE_SECONDS, 30), (3000, 2400, 1800)],
)
async def test_machine_token_honours_client_resource_and_platform_ttl(
    auth_flow: SimpleNamespace,
    client_ttl: int,
    resource_ttl: int,
    expected: int,
) -> None:
    """机器令牌的响应有效期和 JWT 有效期均遵守 Client、Resource 及平台上限。"""

    auth_flow.machine.access_token_ttl_seconds = client_ttl
    auth_flow.resource.access_token_ttl_seconds = resource_ttl
    await auth_flow.db.commit()
    token = await _machine_token(auth_flow)
    claims = _claims(auth_flow, token.access_token)
    assert token.expires_in == expected
    assert claims['exp'] - claims['iat'] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy', [False, True])
async def test_scope_disable_immediately_invalidates_machine_tokens(auth_flow: SimpleNamespace, legacy: bool) -> None:
    """Scope 禁用立即使机器令牌失效，新版令牌在 Scope 恢复后仍受策略版本约束。"""

    token = (await _machine_token(auth_flow)).access_token
    if legacy:
        claims = _claims(auth_flow, token)
        claims.pop('client_policy_version', None)
        token = _sign(auth_flow, claims)
    assert (await _introspect(auth_flow, token))['active'] is True
    await OAuthResourceManagementService.change_scope_status(
        auth_flow.db,
        ScopeStatusModel(scope_code='api.read', status='1'),
        actor='test',
    )
    with pytest.raises(OAuthProtocolException) as exc:
        await _machine_token(auth_flow)
    assert exc.value.error == 'invalid_scope'
    assert await _introspect(auth_flow, token) == {'active': False}
    if not legacy:
        await OAuthResourceManagementService.change_scope_status(
            auth_flow.db,
            ScopeStatusModel(scope_code='api.read', status='0'),
            actor='test',
        )
        assert await _introspect(auth_flow, token) == {'active': False}
        assert (await _introspect(auth_flow, (await _machine_token(auth_flow)).access_token))['active'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['unbind', 'identity_scope', 'different_resource'])
async def test_machine_tokens_recheck_current_scope_bindings(auth_flow: SimpleNamespace, change: str) -> None:
    """机器令牌内省重新检查 Scope 的 Client 绑定、类型和所属 Resource。"""

    token = await _machine_token(auth_flow)
    assert (await _introspect(auth_flow, token.access_token))['active'] is True
    if change == 'unbind':
        await auth_flow.db.execute(
            delete(SysOAuthClientScope).where(SysOAuthClientScope.client_pk == auth_flow.machine.client_pk)
        )
    elif change == 'identity_scope':
        auth_flow.scope.scope_type = 'identity'
    else:
        auth_flow.scope.resource_pk = 99
    await auth_flow.db.commit()
    assert await _introspect(auth_flow, token.access_token) == {'active': False}


@pytest.mark.asyncio
async def test_authorize_slides_idle_timeout_but_never_extends_absolute_expiry(
    auth_flow: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """授权请求更新 SSO 空闲期限，并保留 Session 的绝对过期上限。"""

    flow = auth_flow
    absolute = flow.now + timedelta(minutes=40)
    flow.session.absolute_expires_at = absolute
    await flow.db.commit()
    for minutes in (25, 31):
        current = flow.now + timedelta(minutes=minutes)
        monkeypatch.setattr(TimezoneUtil, 'utc_now', staticmethod(lambda current=current: current))
        await AuthorizationService.process_authorization_request(
            flow.db,
            flow.redis,
            _authorize_request(flow),
            sso_cookie=flow.cookie,
        )
        await flow.db.refresh(flow.session)
        assert TimezoneUtil.to_utc(flow.session.idle_expires_at) == absolute
        assert TimezoneUtil.to_utc(flow.session.absolute_expires_at) == absolute
        assert TimezoneUtil.to_utc(flow.session.last_seen_at) == current
        assert flow.session.status == 'active'
    monkeypatch.setattr(TimezoneUtil, 'utc_now', staticmethod(lambda: absolute))
    coordinator = AfterCommitCoordinator()
    assert await AuthorizationService._load_sso_session(flow.db, flow.redis, flow.cookie, coordinator) is None
    await coordinator.commit(flow.db)


@pytest.mark.asyncio
@pytest.mark.parametrize('remember', [False, True])
@pytest.mark.parametrize('force_password_change', [False, True])
async def test_login_cookie_persistence_survives_forced_password_change(
    auth_flow: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    remember: bool,
    force_password_change: bool,
) -> None:
    """普通登录及强制改密后的 Cookie 持久化行为均遵守保持登录选项。"""

    flow = auth_flow
    context = await AuthorizationService.validate_request(flow.db, AuthorizeRequest(**_authorize_request(flow)))
    created = await InteractionService.create(flow.redis, context.to_internal_payload('cookie-test'), pepper=_PEPPER)
    flow.user.password = PwdUtil.get_password_hash('old-password')
    await flow.db.commit()
    monkeypatch.setattr(
        CredentialAuthenticationService,
        'authenticate_oidc',
        AsyncMock(
            return_value=CredentialAuthenticationResult(
                user=flow.user,
                dept=None,
                acr='urn:ruoyi:acr:pwd',
                amr=('pwd',),
                remember_me=remember,
                password_change_required=force_password_change,
                password_change_reason='initial_password' if force_password_change else None,
            )
        ),
    )
    outcome = await InteractionLoginService.login(
        flow.redis,
        created.interaction_id,
        InteractionLoginModel(userName='alice', password='old-password', rememberMe=remember),
        flow.db,
        created.csrf_token,
    )
    if force_password_change:
        assert outcome.cookie is None
        monkeypatch.setattr(UserService, 'validate_password_services', AsyncMock())
        outcome = await InteractionLoginService.change_password(
            flow.redis,
            created.interaction_id,
            ChangePasswordModel(
                oldPassword='old-password',
                newPassword='new-password-A1!',
                confirmPassword='new-password-A1!',
            ),
            flow.db,
            created.csrf_token,
        )
    assert outcome.failure_message is None
    response = _login_response(outcome)
    cookies = SimpleCookie()
    cookies.load(response.headers['set-cookie'])
    cookie = cookies[OidcConfig.oidc_sso_cookie_name]
    assert cookie['secure'] and cookie['httponly'] and cookie['samesite'] == 'lax' and cookie['path'] == '/'
    assert not cookie['domain']
    sid, _ = SsoSessionService.parse_cookie(cookie.value)
    session = await flow.db.get(SysSsoSession, sid)
    assert bool(session.remember_me) is remember
    if remember:
        remaining = int((TimezoneUtil.to_utc(session.absolute_expires_at) - flow.now).total_seconds())
        assert int(cookie['max-age']) == remaining == _REMEMBER_SECONDS
    else:
        assert not cookie['max-age'] and not cookie['expires']
