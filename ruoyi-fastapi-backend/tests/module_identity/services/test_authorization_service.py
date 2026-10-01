from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_identity.entity.do.oauth_client_do import SysOAuthClient, SysOAuthClientUri
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.entity.vo.protocol_vo import AuthorizeRequest
from module_identity.service.authorization_service import AuthorizationService

_CLIENT_PK = 7001
_RESOURCE_PK = 7101
_SECOND_RESOURCE_PK = 7102
_REDIRECT_URI = 'https://portal.example/callback?tenant=one'
_CHALLENGE = 'A' * 43


def _request(**overrides: object) -> AuthorizeRequest:
    """构造最小有效授权请求。"""
    values: dict[str, object] = {
        'response_type': 'code',
        'client_id': 'authorization-client',
        'redirect_uri': _REDIRECT_URI,
        'scope': 'openid profile',
        'nonce': 'nonce-value',
        'state': 'opaque-state',
        'code_challenge': _CHALLENGE,
        'code_challenge_method': 'S256',
    }
    values.update(overrides)
    return AuthorizeRequest(**values)


async def _seed_authorization_data(db: AsyncSession, *, second_resource_scope: bool = False) -> None:
    """写入授权服务测试所需的 Client、URI、Scope 和 Resource。"""
    client = SysOAuthClient(
        client_pk=_CLIENT_PK,
        client_id='authorization-client',
        client_name='Authorization Client',
        client_type='public',
        token_endpoint_auth_method='none',
        grant_types=['authorization_code'],
        response_types=['code'],
        require_pkce=1,
        require_consent=1,
        trusted_client=1,
        policy_version=3,
        status='0',
    )
    resource = SysOAuthResource(
        resource_pk=_RESOURCE_PK,
        resource_id='portal-api',
        resource_name='Portal API',
        audience='https://api.example',
        allowed_claims=[],
        create_by='test',
        update_by='test',
        status='0',
    )
    scopes = [
        SysOAuthScope(
            scope_pk=7201,
            scope_code='openid',
            scope_name='OpenID',
            scope_type='identity',
            claims=['sub'],
            consent_required=1,
            status='0',
            create_by='test',
            update_by='test',
        ),
        SysOAuthScope(
            scope_pk=7202,
            scope_code='profile',
            scope_name='Profile',
            scope_type='identity',
            claims=['name'],
            consent_required=1,
            status='0',
            create_by='test',
            update_by='test',
        ),
        SysOAuthScope(
            scope_pk=7203,
            scope_code='server-required',
            scope_name='Server Required',
            scope_type='identity',
            claims=[],
            consent_required=0,
            status='0',
            create_by='test',
            update_by='test',
        ),
        SysOAuthScope(
            scope_pk=7204,
            scope_code='portal.read',
            scope_name='Portal Read',
            scope_type='resource',
            resource_pk=_RESOURCE_PK,
            claims=['sub'],
            consent_required=1,
            status='0',
            create_by='test',
            update_by='test',
        ),
    ]
    bindings = [
        SysOAuthClientScope(
            client_pk=_CLIENT_PK,
            scope_pk=scope.scope_pk,
            pre_authorized=scope.scope_code == 'openid',
        )
        for scope in scopes
    ]
    db.add_all(
        [
            client,
            SysOAuthClientUri(client_pk=_CLIENT_PK, uri_type='redirect', uri=_REDIRECT_URI, status='0'),
            resource,
            SysOAuthClientResource(client_pk=_CLIENT_PK, resource_pk=_RESOURCE_PK, is_default=0),
            *scopes,
            *bindings,
        ]
    )
    if second_resource_scope:
        db.add(
            SysOAuthScope(
                scope_pk=7205,
                scope_code='other.read',
                scope_name='Other Read',
                scope_type='resource',
                resource_pk=_SECOND_RESOURCE_PK,
                claims=[],
                consent_required=1,
                status='0',
                create_by='test',
                update_by='test',
            )
        )
        db.add(SysOAuthClientScope(client_pk=_CLIENT_PK, scope_pk=7205))
    await db.flush()


@pytest.fixture
def oidc_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """为服务测试开启安全的 OIDC 配置。"""
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    monkeypatch.setattr(OidcConfig, 'oidc_pkce_methods', 'S256')
    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example.com')


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
@pytest.mark.parametrize(
    'redirect_uri',
    [
        'https://PORTAL.example/callback?tenant=one',
        'https://portal.example/callback?tenant=two',
        'https://portal.example/Callback?tenant=one',
    ],
)
async def test_redirect_uri_must_match_case_path_and_query_exactly(
    data_session: AsyncSession, redirect_uri: str
) -> None:
    """验证回调地址任一大小写、路径或查询差异都不能进入重定向错误路径。"""
    await _seed_authorization_data(data_session)
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationService.validate_request(data_session, _request(redirect_uri=redirect_uri))
    assert raised.value.can_redirect is False
    assert raised.value.redirect_uri is None


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_scope_and_resource_policy_errors_are_redirectable_only_after_uri_validation(
    data_session: AsyncSession,
) -> None:
    """验证 Scope 越权和 Resource 归属错误带已验证 Redirect。"""
    await _seed_authorization_data(data_session)
    with pytest.raises(OAuthProtocolException) as scope_error:
        await AuthorizationService.validate_request(data_session, _request(scope='openid admin'))
    assert scope_error.value.error == 'invalid_scope'
    assert scope_error.value.can_redirect is True
    assert scope_error.value.state == 'opaque-state'

    with pytest.raises(OAuthProtocolException) as resource_error:
        await AuthorizationService.validate_request(
            data_session, _request(scope='openid portal.read', resource='https://other.example')
        )
    assert resource_error.value.error == 'invalid_target'
    assert resource_error.value.can_redirect is True


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_plain_pkce_method_is_rejected_after_redirect_validation(data_session: AsyncSession) -> None:
    """验证 43 位 challenge 也不能绕过 S256 方法校验。"""
    await _seed_authorization_data(data_session)
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationService.validate_request(data_session, _request(code_challenge_method='plain'))
    assert raised.value.error == 'invalid_request'
    assert raised.value.can_redirect is True
    assert raised.value.redirect_uri == _REDIRECT_URI


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_unsupported_response_type_is_a_safe_redirect_error(data_session: AsyncSession) -> None:
    """验证不支持的 response_type 只在 Redirect 已验证后重定向。"""
    await _seed_authorization_data(data_session)
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationService.validate_request(data_session, _request(response_type='token'))
    assert raised.value.error == 'unsupported_response_type'
    assert raised.value.can_redirect is True


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_resource_scopes_cannot_cross_resource_ownership(data_session: AsyncSession) -> None:
    """验证多个 Resource Scope 不能借一个 audience 混合授权。"""
    await _seed_authorization_data(data_session, second_resource_scope=True)
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationService.validate_request(
            data_session, _request(scope='openid portal.read other.read', resource='https://api.example')
        )
    assert raised.value.error == 'invalid_target'
    assert raised.value.can_redirect is True


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_resource_scope_without_resource_uses_only_unique_default_binding(data_session: AsyncSession) -> None:
    """验证未传 resource 时只能采用唯一显式默认 Resource。"""
    await _seed_authorization_data(data_session)
    with pytest.raises(OAuthProtocolException) as no_default:
        await AuthorizationService.validate_request(data_session, _request(scope='openid portal.read'))
    assert no_default.value.error == 'invalid_target'

    binding = await data_session.get(SysOAuthClientResource, (_CLIENT_PK, _RESOURCE_PK))
    assert binding is not None
    binding.is_default = 1
    await data_session.flush()
    context = await AuthorizationService.validate_request(data_session, _request(scope='openid portal.read'))
    assert context.resources == ('https://api.example',)


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_multiple_default_resources_fail_closed(data_session: AsyncSession) -> None:
    """验证多个默认 Resource 时拒绝隐式 audience 选择。"""
    await _seed_authorization_data(data_session)
    second = SysOAuthResource(
        resource_pk=_SECOND_RESOURCE_PK,
        resource_id='other-api',
        resource_name='Other API',
        audience='https://other-api.example',
        allowed_claims=[],
        create_by='test',
        update_by='test',
        status='0',
    )
    data_session.add_all(
        [
            second,
            SysOAuthClientResource(client_pk=_CLIENT_PK, resource_pk=_SECOND_RESOURCE_PK, is_default=1),
        ]
    )
    binding = await data_session.get(SysOAuthClientResource, (_CLIENT_PK, _RESOURCE_PK))
    assert binding is not None
    binding.is_default = 1
    await data_session.flush()
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationService.validate_request(data_session, _request(scope='openid portal.read'))
    assert raised.value.error == 'invalid_target'


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_prompt_none_preserves_context_and_requires_valid_grant(data_session: AsyncSession) -> None:
    """验证 prompt=none 不扩大静默权限，必须由有效 Grant 才能跳过同意。"""
    await _seed_authorization_data(data_session)
    context = await AuthorizationService.validate_request(data_session, _request(prompt='none'))
    assert context.prompt == 'none'
    assert context.requires_consent is True
    assert AuthorizationService.consent_is_satisfied(context, None) is False

    now = datetime.now(timezone.utc)
    grant = SysOAuthGrant(
        grant_id='authorization-grant',
        user_id=7001,
        subject_id='subject-7001',
        client_pk=_CLIENT_PK,
        granted_scopes=['openid', 'profile'],
        remembered_scopes=['openid', 'profile'],
        remembered_resources=[],
        granted_resources=[],
        client_policy_version=3,
        status='active',
        consented_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    assert AuthorizationService.consent_is_satisfied(context, grant) is True
    grant.client_policy_version = 2
    assert AuthorizationService.consent_is_satisfied(context, grant) is False
    grant.client_policy_version = 3
    grant.expires_at = now - timedelta(seconds=1)
    assert AuthorizationService.consent_is_satisfied(context, grant) is False


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_require_consent_flag_and_prompt_override_do_not_use_trusted_client_as_expansion(
    data_session: AsyncSession,
) -> None:
    """验证 require_consent、trusted_client 和 prompt=consent 的三种组合。"""
    await _seed_authorization_data(data_session)
    client = await data_session.get(SysOAuthClient, _CLIENT_PK)
    assert client is not None

    client.require_consent = 0
    context = await AuthorizationService.validate_request(data_session, _request())
    assert context.client.trusted_client is True
    assert context.requires_consent is False
    assert AuthorizationService.consent_is_satisfied(context, None) is True

    client.require_consent = 1
    context = await AuthorizationService.validate_request(data_session, _request())
    assert context.requires_consent is True

    client.require_consent = 0
    context = await AuthorizationService.validate_request(data_session, _request(prompt='login consent'))
    assert context.requires_consent is True
    assert AuthorizationService.consent_is_satisfied(context, None) is False


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_unrequested_server_required_scope_does_not_block_consent(data_session: AsyncSession) -> None:
    """验证未请求的服务端必需 Scope 不会混入本次授权的不可取消集合。"""
    await _seed_authorization_data(data_session)
    context = await AuthorizationService.validate_request(data_session, _request(scope='openid profile'))
    assert context.required_scopes == frozenset({'openid'})
    assert AuthorizationService.consent_is_satisfied(context, None) is False


@pytest.mark.asyncio
@pytest.mark.usefixtures('oidc_enabled')
async def test_context_payload_excludes_state_and_nonce(data_session: AsyncSession) -> None:
    """验证交互页面载荷不泄漏 state、nonce 和未定义参数。"""
    await _seed_authorization_data(data_session)
    context = await AuthorizationService.validate_request(data_session, _request(login_hint='not-forwarded'))
    payload = context.to_interaction_payload('interaction-1')
    internal_payload = context.to_internal_payload('interaction-1')
    assert 'state' not in payload
    assert 'nonce' not in payload
    assert 'login_hint' not in payload
    assert 'clientPk' not in payload
    assert 'maxAge' not in payload
    assert 'redirectUri' not in payload
    assert internal_payload['redirectUri'] == _REDIRECT_URI
    assert internal_payload['state'] == 'opaque-state'
    assert internal_payload['nonce'] == 'nonce-value'
    assert internal_payload['codeChallenge'] == _CHALLENGE
