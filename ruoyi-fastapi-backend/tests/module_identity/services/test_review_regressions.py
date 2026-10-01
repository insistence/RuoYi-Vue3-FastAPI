import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_admin.entity.do.user_do import SysUser
from module_identity.controller.oidc_key_controller import list_oidc_keys
from module_identity.dao.oauth_token_dao import OAuthTokenDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken, SysSsoSession
from module_identity.entity.do.oauth_resource_do import SysOAuthClientScope, SysOAuthScope
from module_identity.entity.vo.oauth_client_vo import ClientViewModel
from module_identity.security.opaque_token import parse_opaque_token
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.identity_service import ClaimService
from module_identity.service.session_service import LogoutService
from module_identity.service.token_service import RefreshTokenReuseDetected, TokenResult, TokenService
from utils.oidc_util import OidcUtil
from utils.response_util import ResponseUtil

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
PEPPER = 'regression-refresh-pepper-' + 'x' * 32


async def seed_refresh(db: AsyncSession, monkeypatch: pytest.MonkeyPatch, *, expired: bool = False) -> str:
    # 显式确认外键校验已启用，避免SQLite默认配置掩盖原有问题
    await db.execute(text('PRAGMA foreign_keys=ON'))
    assert await db.scalar(text('PRAGMA foreign_keys')) == 1
    monkeypatch.setattr(OidcConfig, 'oidc_token_hash_pepper', PEPPER)
    monkeypatch.setattr(TokenService, '_issue_access_token', AsyncMock(return_value=('signed-access', 600)))
    user = SysUser(user_id=9901, user_name='refresh-regression', nick_name='Refresh', status='0', del_flag='0')
    client = SysOAuthClient(
        client_pk=9901,
        client_id='refresh-regression',
        client_name='Refresh regression',
        client_type='public',
        token_endpoint_auth_method='none',
        grant_types=['authorization_code', 'refresh_token'],
        response_types=['code'],
        policy_version=1,
        status='0',
    )
    db.add_all([user, client])
    await db.flush()
    subject = SysIdentitySubject(user_id=user.user_id, subject_id='subject-9901', auth_version=1)
    grant = SysOAuthGrant(
        grant_id='grant-9901',
        user_id=user.user_id,
        subject_id=subject.subject_id,
        client_pk=client.client_pk,
        granted_scopes=['openid', 'offline_access'],
        granted_resources=[],
        client_policy_version=1,
        consented_at=NOW,
        status='active',
    )
    session = SysSsoSession(
        sid='99010000-0000-4000-8000-000000000001',
        session_secret_hash='a' * 64,
        user_id=user.user_id,
        subject_id=subject.subject_id,
        auth_version=1,
        auth_time=NOW - timedelta(days=1),
        last_seen_at=NOW - timedelta(hours=1),
        idle_expires_at=NOW + timedelta(minutes=-30 if expired else 30),
        absolute_expires_at=NOW + timedelta(hours=-1 if expired else 8),
        acr='pwd',
        amr=['pwd'],
        status='expired' if expired else 'active',
    )
    scopes = [
        SysOAuthScope(
            scope_pk=9901,
            scope_code='openid',
            scope_name='OpenID',
            scope_type='identity',
            claims=['sub'],
            create_by='test',
            update_by='test',
        ),
        SysOAuthScope(
            scope_pk=9902,
            scope_code='offline_access',
            scope_name='Offline',
            scope_type='identity',
            claims=[],
            create_by='test',
            update_by='test',
        ),
    ]
    db.add_all([subject, grant, session, *scopes])
    await db.flush()
    db.add_all([SysOAuthClientScope(client_pk=9901, scope_pk=s.scope_pk) for s in scopes])
    await db.flush()
    token = await TokenService._create_refresh_token(
        db,
        client,
        grant,
        user,
        subject,
        session,
        ['openid', 'offline_access'],
        [],
        NOW,
        token_pepper=PEPPER,
    )
    await db.commit()
    return token


async def refresh(db: AsyncSession, token: str) -> TokenResult:
    return await TokenService.refresh_token(
        db,
        {'grant_type': 'refresh_token', 'client_id': 'refresh-regression', 'refresh_token': token},
        OAuthClientPrincipal('refresh-regression', 'public', 'none'),
        token_pepper=PEPPER,
        now=NOW,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('expired', [False, True])
async def test_rotation_with_real_foreign_keys_and_replay_revocation(
    data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, expired: bool
) -> None:
    old = await seed_refresh(data_session, monkeypatch, expired=expired)
    result = await refresh(data_session, old)
    await data_session.commit()
    old_row = await OAuthTokenDao.get_by_token_id(data_session, parse_opaque_token(old, 'rt1').token_id)
    new_id = parse_opaque_token(result.refresh_token, 'rt1').token_id
    successor = await OAuthTokenDao.get_by_token_id(data_session, new_id)
    assert old_row.status == 'used'
    assert old_row.replaced_by_token_id == new_id
    assert successor.parent_token_id == old_row.token_id
    assert successor.absolute_expires_at == old_row.absolute_expires_at
    with pytest.raises(RefreshTokenReuseDetected):
        await refresh(data_session, old)
    await data_session.commit()
    assert successor.status == 'revoked'


@pytest.mark.asyncio
async def test_failed_signing_rolls_back_both_rotation_rows(
    data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = await seed_refresh(data_session, monkeypatch)
    monkeypatch.setattr(TokenService, '_issue_access_token', AsyncMock(side_effect=RuntimeError('signer unavailable')))
    with pytest.raises(RuntimeError, match='signer unavailable'):
        await refresh(data_session, old)
    await data_session.rollback()
    assert await data_session.scalar(select(func.count()).select_from(SysOAuthRefreshToken)) == 1
    old_row = await OAuthTokenDao.get_by_token_id(data_session, parse_opaque_token(old, 'rt1').token_id)
    assert old_row.status == 'active'
    assert old_row.replaced_by_token_id is None


@pytest.mark.asyncio
async def test_explicit_revocation_still_blocks_offline_refresh(
    data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = await seed_refresh(data_session, monkeypatch, expired=True)
    assert await SsoSessionDao.revoke(
        data_session, '99010000-0000-4000-8000-000000000001', reason='rp_initiated_logout', now=NOW
    )
    await data_session.commit()
    with pytest.raises(OAuthProtocolException):
        await refresh(data_session, old)


@pytest.mark.asyncio
async def test_real_key_list_readiness_and_client_response_are_rfc3339(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', False)
    monkeypatch.setattr(
        'module_identity.controller.oidc_key_controller.OidcKeyManagementService.list_page',
        AsyncMock(return_value=([], 0)),
    )
    response = await list_oidc_keys(object(), status=None, page_num=1, page_size=10)
    assert json.loads(response.body)['readinessCheckedAt'].endswith('Z')
    model = ClientViewModel(
        client_id='public',
        client_name='Public',
        client_type='public',
        token_endpoint_auth_method='none',
        redirect_uris=['https://client.example/callback'],
        update_time=NOW,
    )
    assert json.loads(ResponseUtil.success(rows=[model]).body)['rows'][0]['updateTime'] == '2026-09-12T10:00:00.000Z'


def test_role_values_require_an_explicit_client_allowlist() -> None:
    user = {'subject_id': 'sub-1'}
    for policy, expected in [
        ({'roles': True}, []),
        ({'roles': {'claims': ['roles'], 'allowed_role_keys': ['analyst']}}, ['analyst']),
    ]:
        claims = ClaimService.build_claims(
            user,
            ['roles'],
            policy,
            ['roles'],
            roles=['admin', 'analyst', 'finance-internal'],
        )
        assert claims['roles'] == expected


@pytest.mark.asyncio
async def test_confirmed_logout_revokes_offline_grant_with_expired_owned_cookie(
    data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = await seed_refresh(data_session, monkeypatch, expired=True)
    monkeypatch.setattr(OidcConfig, 'oidc_enabled', True)
    sid = '99010000-0000-4000-8000-000000000001'
    session = await SsoSessionDao.get_by_sid(data_session, sid)
    secret = 's' * 43
    session.session_secret_hash = OidcUtil.session_secret_digest(secret, PEPPER)
    await data_session.commit()
    result = await LogoutService.execute_logout(
        data_session,
        AsyncMock(),
        confirmed=True,
        cookie=f'ss1.{sid}.{secret}',
        now=NOW,
    )
    assert result.session_revoked is True
    assert (await SsoSessionDao.get_by_sid(data_session, sid)).status == 'revoked'
    assert (
        await OAuthTokenDao.get_by_token_id(data_session, parse_opaque_token(old, 'rt1').token_id)
    ).status == 'revoked'
