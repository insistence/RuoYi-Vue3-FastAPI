import base64
from datetime import timedelta
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from exceptions.exception import OAuthProtocolException
from exceptions.handle import handle_exception
from module_identity.controller.authorization_controller import authorization_controller
from module_identity.controller.oauth_session_controller import oauth_grant_controller
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysSsoSessionClient
from module_identity.entity.vo.oauth_session_vo import (
    AccessPolicyPageQueryModel,
    GrantPageQueryModel,
    SessionPageQueryModel,
)
from module_identity.entity.vo.protocol_vo import AuthorizeRequest
from module_identity.service.audit_service import AuditService
from module_identity.service.authorization_service import AuthorizationCodeService, AuthorizationService
from module_identity.service.consent_service import ConsentService
from module_identity.service.infrastructure_service import AfterCommitCoordinator, OidcRateLimiter
from module_identity.service.oauth_management_service import OAuthClientManagementService
from module_identity.service.oauth_session_management_service import OAuthSessionManagementService
from module_identity.service.session_service import LogoutService, SsoSessionService
from module_identity.service.token_protocol_service import IntrospectionService, RevocationService
from module_identity.service.token_service import TokenService
from tests.module_identity.services.test_authentication_regressions import (
    _PEPPER,
    _VERIFIER,
    _authorize_request,
    _introspect,
    _user_token,
)
from tests.module_identity.services.test_authentication_regressions import (
    auth_flow as _auth_flow_fixture,
)

# 复用真实认证夹具，避免不同回归场景使用不一致的授权配置。
auth_flow = _auth_flow_fixture


def _basic(client_id: str, secret: str) -> str:
    """生成符合协议编码要求的机密客户端认证头。"""

    return 'Basic ' + base64.b64encode(f'{quote_plus(client_id)}:{quote_plus(secret)}'.encode()).decode()


async def _confidential_token(flow: SimpleNamespace) -> tuple:
    """通过机密客户端的真实授权码流程签发离线令牌。"""

    flow.app.client_type = 'confidential'
    flow.app.token_endpoint_auth_method = 'client_secret_basic'
    secret = await OAuthClientManagementService._new_secret(flow.db, flow.app, 'admin', flow.now, not_before=flow.now)
    await flow.db.commit()
    authorization = _basic(flow.app.client_id, secret.client_secret)
    request = AuthorizeRequest(**_authorize_request(flow, offline=True))
    context = await AuthorizationService.validate_request(flow.db, request)
    consent = await ConsentService.submit_consent(
        flow.db,
        context,
        True,
        context.scopes,
        True,
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
            'grantId': consent.grant.grant_id,
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
            'code': code,
            'redirect_uri': request.redirect_uri,
            'code_verifier': _VERIFIER,
        },
        authorization=authorization,
        signing_key=flow.signer,
        kid='regression-key',
    )
    return token, secret, authorization


@pytest.mark.asyncio
@pytest.mark.parametrize('stored_status', ['active', 'expired'])
async def test_revoke_user_terminates_expired_offline_sessions(auth_flow: SimpleNamespace, stored_status: str) -> None:
    """自然过期不影响离线续期，但管理员按用户撤销必须终止该能力。"""

    flow = auth_flow
    token, _ = await _user_token(flow, offline=True)
    flow.session.idle_expires_at = flow.now - timedelta(seconds=1)
    flow.session.status = stored_status
    await flow.db.commit()
    assert (await _introspect(flow, token.refresh_token))['active'] is True
    count = await OAuthSessionManagementService.revoke_user(
        flow.db, flow.redis, flow.user.user_id, 'admin', '终止该用户的全部外部会话'
    )
    assert count == 1
    assert flow.session.status == 'revoked'
    assert await _introspect(flow, token.access_token) == {'active': False}
    assert await _introspect(flow, token.refresh_token) == {'active': False}
    with pytest.raises(OAuthProtocolException) as error:
        await TokenService.issue_token_request(
            flow.db,
            flow.redis,
            {
                'grant_type': 'refresh_token',
                'client_id': 'business-app',
                'refresh_token': token.refresh_token,
            },
            client_id='business-app',
            signing_key=flow.signer,
            kid='regression-key',
        )
    assert error.value.error == 'invalid_grant'


@pytest.mark.asyncio
async def test_secret_rotation_and_revocation_preserve_existing_authorization(auth_flow: SimpleNamespace) -> None:
    """凭据轮换只改变客户端认证，旧授权可通过新凭据继续续期。"""

    flow = auth_flow
    token, old_secret, old_header = await _confidential_token(flow)
    policy_version = flow.app.policy_version
    secret = await OAuthClientManagementService.rotate_secret(flow.db, 'business-app', 'admin', now=flow.now)
    assert flow.app.policy_version == policy_version
    assert (await _introspect(flow, token.access_token))['active'] is True
    assert (await TokenService.authenticate_client(flow.db, authorization=old_header))[1].client_id == 'business-app'
    new_header = _basic('business-app', secret.client_secret)
    refreshed = await TokenService.issue_token_request(
        flow.db,
        flow.redis,
        {
            'grant_type': 'refresh_token',
            'refresh_token': token.refresh_token,
        },
        authorization=old_header,
        signing_key=flow.signer,
        kid='regression-key',
    )
    await OAuthClientManagementService.revoke_secret(flow.db, 'business-app', old_secret.secret_id, 'admin')
    assert flow.app.policy_version == policy_version
    assert (await _introspect(flow, refreshed.access_token))['active'] is True
    with pytest.raises(OAuthProtocolException) as error:
        await TokenService.authenticate_client(flow.db, authorization=old_header)
    assert error.value.error == 'invalid_client'
    renewed = await TokenService.issue_token_request(
        flow.db,
        flow.redis,
        {
            'grant_type': 'refresh_token',
            'refresh_token': refreshed.refresh_token,
        },
        authorization=new_header,
        signing_key=flow.signer,
        kid='regression-key',
    )
    assert (await _introspect(flow, renewed.access_token))['active'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['access_token', 'refresh_token'])
@pytest.mark.parametrize('hint', [None, 'access_token', 'refresh_token', 'unknown_hint'])
async def test_token_hint_does_not_override_real_token_type(
    auth_flow: SimpleNamespace, kind: str, hint: str | None
) -> None:
    """内省和撤销均忽略不匹配或未知的可选令牌类型提示。"""

    flow = auth_flow
    token, _ = await _user_token(flow, offline=True)
    value = getattr(token, kind)
    result = await IntrospectionService.introspect(
        flow.db,
        flow.redis,
        value,
        flow.caller,
        verification_key=flow.signer.public_key(),
        now=flow.now,
        token_type_hint=hint,
    )
    assert result['active'] is True
    assert await RevocationService.revoke_request(
        flow.db,
        flow.redis,
        value,
        client_id='business-app',
        verification_key=flow.signer.public_key(),
        token_type_hint=hint,
    )
    assert await _introspect(flow, value) == {'active': False}


@pytest.mark.asyncio
@pytest.mark.parametrize('expiry', ['idle', 'absolute'])
async def test_effective_expiry_matches_list_count_detail_without_mutating_state(
    auth_flow: SimpleNamespace, expiry: str
) -> None:
    """列表筛选、总数和详情采用相同有效状态，读取不改变离线凭据语义。"""

    flow = auth_flow
    _, grant = await _user_token(flow)
    setattr(flow.session, f'{expiry}_expires_at', flow.now - timedelta(seconds=1))
    grant.expires_at = flow.now - timedelta(seconds=1)
    await flow.db.commit()
    sessions, count = await OAuthSessionManagementService.list_sessions(
        flow.db, SessionPageQueryModel(status='expired')
    )
    grants, grant_count = await OAuthSessionManagementService.list_grants(
        flow.db, GrantPageQueryModel(status='expired')
    )
    assert count == grant_count == 1
    assert sessions[0].status == grants[0].status == 'expired'
    assert sessions[0].client_ids == ['business-app']
    assert (await OAuthSessionManagementService.get_session(flow.db, flow.session.sid)).status == 'expired'
    assert (await OAuthSessionManagementService.get_grant(flow.db, grant.grant_id)).status == 'expired'
    assert await OAuthSessionManagementService.list_sessions(flow.db, SessionPageQueryModel(status='active')) == ([], 0)
    assert await OAuthSessionManagementService.list_grants(flow.db, GrantPageQueryModel(status='active')) == ([], 0)
    assert flow.session.status == grant.status == 'active'
    flow.session.status = grant.status = 'revoked'
    await flow.db.commit()
    assert await OAuthSessionManagementService.list_sessions(flow.db, SessionPageQueryModel(status='expired')) == (
        [],
        0,
    )
    assert await OAuthSessionManagementService.list_grants(flow.db, GrantPageQueryModel(status='expired')) == ([], 0)


@pytest.mark.asyncio
async def test_online_authorization_records_exact_session_participation(
    auth_flow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """没有刷新令牌的授权也记录应用，其他设备的参与应用不混入当前登出。"""

    flow = auth_flow
    token, _ = await _user_token(flow)
    await _user_token(flow)
    assert token.refresh_token is None
    assert await flow.db.scalar(select(func.count()).select_from(SysSsoSessionClient)) == 1
    coordinator = AfterCommitCoordinator()
    _, other = await SsoSessionService.create(
        flow.db,
        flow.redis,
        flow.user.user_id,
        flow.subject.subject_id,
        flow.subject.auth_version,
        'urn:ruoyi:acr:pwd',
        ('pwd',),
        pepper=_PEPPER,
        now=flow.now,
        coordinator=coordinator,
    )
    await SsoSessionDao.record_client(flow.db, other.sid, flow.machine.client_pk, flow.now)
    await coordinator.commit(flow.db)
    assert await SsoSessionDao.client_ids_for_sid(flow.db, flow.session.sid) == ['business-app']
    assert await SsoSessionDao.client_ids_for_sid(flow.db, other.sid) == ['machine']
    register = AsyncMock()
    monkeypatch.setattr(LogoutService, '_register_backchannel', register)
    coordinator = AfterCommitCoordinator()
    result = await LogoutService._logout(
        flow.db,
        flow.redis,
        cookie=flow.cookie,
        confirmed=True,
        coordinator=coordinator,
        now=flow.now,
    )
    assert result.session_revoked is True
    assert register.call_args.args[3] == {flow.app.client_pk}
    await coordinator.commit(flow.db)
    assert other.status == 'active'


@pytest.mark.asyncio
async def test_legacy_refresh_binding_is_an_exact_session_fallback(auth_flow: SimpleNamespace) -> None:
    """升级前的离线凭据仍可恢复精确会话参与者，不依赖同用户授权时间推断。"""

    flow = auth_flow
    await _user_token(flow, offline=True)
    await flow.db.execute(delete(SysSsoSessionClient))
    await flow.db.commit()
    assert await SsoSessionDao.client_ids_for_sid(flow.db, flow.session.sid) == ['business-app']


@pytest.mark.asyncio
async def test_failed_token_transaction_rolls_back_session_participation(
    auth_flow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """令牌签发事务失败时不能残留成功登录关联记录。"""

    record = AuditService.record

    async def fail_token_audit(db: AsyncSession, event_type: str, *args: object, **kwargs: object) -> object:
        if event_type == OidcAuditEvent.TOKEN_ISSUED:
            raise RuntimeError('audit unavailable')
        return await record(db, event_type, *args, **kwargs)

    monkeypatch.setattr(AuditService, 'record', fail_token_audit)
    with pytest.raises(RuntimeError, match='audit unavailable'):
        await _user_token(auth_flow)
    assert await auth_flow.db.scalar(select(func.count()).select_from(SysSsoSessionClient)) == 0


@pytest.mark.asyncio
async def test_access_policy_without_grant_is_queryable_and_unblocking_does_not_create_grant(
    auth_flow: SimpleNamespace,
) -> None:
    """首次授权前的禁止策略独立可见，解除后也不凭空恢复授权。"""

    flow = auth_flow
    await OAuthSessionManagementService.set_access(
        flow.db, flow.user.user_id, 'business-app', True, 'admin', '预先禁止'
    )
    query = AccessPolicyPageQueryModel(
        user_id=flow.user.user_id, client_id='business-app', access_status='blocked', page_size=1
    )
    rows, count = await OAuthSessionManagementService.list_access_policies(flow.db, query)
    assert count == 1 and len(rows) == 1
    assert rows[0].user_name == 'alice' and rows[0].client_name == 'Business app'
    assert rows[0].reason == '预先禁止'
    assert await flow.db.scalar(select(func.count()).select_from(SysOAuthGrant)) == 0
    query.page_num = 2
    assert await OAuthSessionManagementService.list_access_policies(flow.db, query) == ([], 1)
    await OAuthSessionManagementService.set_access(
        flow.db, flow.user.user_id, 'business-app', False, 'admin', '允许重新授权'
    )
    query.page_num = 1
    assert await OAuthSessionManagementService.list_access_policies(flow.db, query) == ([], 0)
    query.access_status = 'allowed'
    assert (await OAuthSessionManagementService.list_access_policies(flow.db, query))[1] == 1
    assert await flow.db.scalar(select(func.count()).select_from(SysOAuthGrant)) == 0


def _http_app(flow: SimpleNamespace, router: APIRouter) -> FastAPI:
    """挂载真实路由并将数据库依赖定向到隔离测试库。"""

    app = FastAPI()
    app.state.redis = flow.redis
    app.include_router(router)
    handle_exception(app)
    for route in router.routes:
        if isinstance(route, APIRoute):
            for dependency in route.dependant.dependencies:
                if dependency.name == 'query_db':
                    app.dependency_overrides[dependency.call] = lambda: flow.db
                else:
                    app.dependency_overrides[dependency.call] = lambda: None
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['GET', 'POST'])
async def test_authorize_accepts_query_response_mode_on_both_methods(
    auth_flow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """标准授权方法均进入真实交互流程，未登录时保持 prompt=none 的标准错误。"""

    monkeypatch.setattr(OidcRateLimiter, 'enforce', AsyncMock())
    values = {**_authorize_request(auth_flow), 'response_mode': 'query', 'prompt': 'none', 'state': 'test-state'}
    app = _http_app(auth_flow, authorization_controller)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='https://auth.example.com') as client:
        response = await client.request(
            method, '/oauth2/authorize', **({'params': values} if method == 'GET' else {'data': values})
        )
    assert response.status_code == HTTPStatus.SEE_OTHER
    location = urlsplit(response.headers['location'])
    assert location.netloc == 'app.example.com'
    assert parse_qs(location.query)['error'] == ['login_required']
    assert parse_qs(location.query)['state'] == ['test-state']
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['duplicate', 'query_and_body', 'json', 'bad_escape', 'oversize'])
async def test_authorize_post_rejects_ambiguous_or_invalid_forms(auth_flow: SimpleNamespace, case: str) -> None:
    """支持 POST 不放宽重复参数、编码、媒体类型和体积限制。"""

    body = urlencode(_authorize_request(auth_flow))
    url = '/oauth2/authorize'
    media_type = 'application/x-www-form-urlencoded'
    expected = 400
    if case == 'duplicate':
        body += '&client_id=other'
    elif case == 'query_and_body':
        url += '?client_id=other'
    elif case == 'json':
        body, media_type, expected = '{}', 'application/json', 415
    elif case == 'bad_escape':
        body += '&state=%XX'
    else:
        body += '&state=' + 'x' * 70000
        expected = 413
    async with AsyncClient(
        transport=ASGITransport(app=_http_app(auth_flow, authorization_controller)), base_url='https://auth.example.com'
    ) as client:
        response = await client.post(url, content=body, headers={'content-type': media_type})
    assert response.status_code == expected
    assert response.json()['error'] == 'invalid_request'
    assert 'location' not in response.headers


@pytest.mark.asyncio
async def test_unsupported_response_mode_is_only_redirected_to_verified_client(auth_flow: SimpleNamespace) -> None:
    """不支持的响应模式只能向已登记回调返回错误。"""

    values = {**_authorize_request(auth_flow), 'response_mode': 'fragment'}
    with pytest.raises(OAuthProtocolException) as error:
        await AuthorizationService._parse_request(auth_flow.db, values)
    assert error.value.error == 'unsupported_response_mode' and error.value.can_redirect
    values['redirect_uri'] = 'https://attacker.example/callback'
    with pytest.raises(OAuthProtocolException) as error:
        await AuthorizationService._parse_request(auth_flow.db, values)
    assert not error.value.can_redirect


@pytest.mark.asyncio
async def test_access_policy_list_route_returns_camel_case_without_grants(auth_flow: SimpleNamespace) -> None:
    """独立策略列表路由返回规范字段，不被授权详情路径截获。"""

    flow = auth_flow
    await OAuthSessionManagementService.set_access(
        flow.db, flow.user.user_id, 'business-app', True, 'admin', '预先禁止'
    )
    app = _http_app(flow, oauth_grant_controller)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get(
            '/system/oauth/grant/access/list', params={'accessStatus': 'blocked', 'pageSize': 10}
        )
    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload['total'] == 1 and payload['rows'][0]['accessStatus'] == 'blocked'
    assert payload['rows'][0]['clientId'] == 'business-app'
