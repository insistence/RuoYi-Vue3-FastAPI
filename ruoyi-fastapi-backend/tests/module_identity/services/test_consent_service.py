"""Authorization Consent 服务测试。"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.constant import OidcAuditEvent
from exceptions.exception import OAuthProtocolException
from module_admin.entity.do.user_do import SysUser
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.entity.do.oauth_audit_do import SysOAuthAuditLog
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant
from module_identity.service.authorization_service import (
    AuthorizationContext,
    ClientSnapshot,
    ScopeSnapshot,
)
from module_identity.service.consent_service import ConsentResult, ConsentService


def _context(*, prompt: str | None = None, trusted_client: int = 0) -> AuthorizationContext:
    """构造同意服务所需的已验证上下文。"""
    client = ClientSnapshot(
        client_pk=8001,
        client_id='consent-client',
        grant_types=('authorization_code',),
        response_types=('code',),
        policy_version=5,
        require_pkce=True,
        require_consent=True,
        trusted_client=bool(trusted_client),
    )
    scopes = (
        ScopeSnapshot(
            scope_pk=8101,
            scope_code='openid',
            scope_type='identity',
            resource_pk=None,
            consent_required=True,
        ),
        ScopeSnapshot(
            scope_pk=8102,
            scope_code='profile',
            scope_type='identity',
            resource_pk=None,
            consent_required=True,
        ),
        ScopeSnapshot(
            scope_pk=8103,
            scope_code='server-required',
            scope_type='identity',
            resource_pk=None,
            consent_required=False,
        ),
    )
    return AuthorizationContext(
        client=client,
        redirect_uri='https://portal.example/callback',
        scopes=('openid', 'profile', 'server-required'),
        scope_models=scopes,
        pre_authorized_scopes=frozenset(),
        resource=None,
        state='opaque-state',
        nonce='opaque-nonce',
        code_challenge='A' * 43,
        code_challenge_method='S256',
        prompt=prompt,
        max_age=None,
        required_scopes=frozenset({'openid', 'server-required'}),
    )


def test_submission_cannot_expand_scope_or_cancel_required_scope() -> None:
    """验证提交范围只能是原请求子集且必需 Scope 不可取消。"""
    context = _context()
    with pytest.raises(OAuthProtocolException) as expanded:
        ConsentService.validate_submission(context, True, ['openid', 'profile', 'admin'])
    assert expanded.value.error == 'invalid_scope'
    assert expanded.value.can_redirect is True

    with pytest.raises(OAuthProtocolException) as cancelled:
        ConsentService.validate_submission(context, True, ['profile'])
    assert cancelled.value.error == 'invalid_scope'
    assert cancelled.value.can_redirect is True


def test_denial_is_a_verified_redirect_and_trusted_client_does_not_skip_consent() -> None:
    """验证拒绝错误可安全重定向，trusted_client 不会自动预授权。"""
    context = _context(trusted_client=1)
    with pytest.raises(OAuthProtocolException) as denied:
        ConsentService.validate_submission(context, False, ['openid', 'profile', 'server-required'])
    assert denied.value.error == 'access_denied'
    assert denied.value.can_redirect is True
    assert context.requires_consent is True


def test_prompt_consent_disables_grant_based_skip() -> None:
    """验证 prompt=consent 强制显示同意页，即使已有 Grant 也不能静默跳过。"""
    context = _context(prompt='consent')
    now = datetime.now(timezone.utc)
    grant = SysOAuthGrant(
        grant_id='consent-grant',
        user_id=8001,
        subject_id='subject-8001',
        client_pk=8001,
        granted_scopes=['openid', 'profile', 'server-required'],
        granted_resources=[],
        client_policy_version=5,
        status='active',
        consented_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    assert ConsentService.consent_is_satisfied(context, grant) is False


@pytest.mark.asyncio
@pytest.mark.parametrize('remembered', [True, False])
async def test_remember_consent_merges_grant_without_commit(data_session: AsyncSession, remembered: bool) -> None:
    """验证 rememberConsent 使用 Grant DAO 合并，提交事务由调用方控制。"""
    initial = _context()
    context = replace(
        initial,
        scopes=(*initial.scopes, 'offline_access'),
        scope_models=(*initial.scope_models, ScopeSnapshot(8104, 'offline_access', 'identity', None, True)),
    )
    data_session.add(
        SysUser(user_id=8001, user_name='consent-user', nick_name='Consent User', status='0', del_flag='0')
    )
    data_session.add(
        SysOAuthClient(
            client_pk=8001,
            client_id='consent-client',
            client_name='Consent Client',
            client_type='public',
            token_endpoint_auth_method='none',
            grant_types=['authorization_code'],
            response_types=['code'],
            trusted_client=1,
            policy_version=5,
            status='0',
        )
    )
    await data_session.flush()

    result = await ConsentService.submit_consent(
        data_session,
        context,
        approved=True,
        scopes=list(context.scopes),
        remember_consent=remembered,
        user_id=8001,
        subject_id='subject-8001',
    )
    assert result.approved is True
    assert result.grant is not None
    assert result.grant.granted_scopes == list(context.scopes)
    assert ConsentService.consent_is_satisfied(context, result.grant) is remembered
    assert result.grant.remembered_scopes == (list(context.scopes) if remembered else [])
    assert data_session.in_transaction()
    await data_session.flush()

    # 后续记住更小的权限范围时，不得将此前仅供离线续期的权限一并记住
    smaller = replace(context, scopes=('openid', 'server-required'))
    updated = await ConsentService.submit_consent(
        data_session,
        smaller,
        approved=True,
        scopes=list(smaller.scopes),
        remember_consent=True,
        user_id=8001,
        subject_id='subject-8001',
    )
    assert updated.grant.grant_id == result.grant.grant_id
    assert set(updated.grant.granted_scopes) == set(context.scopes)
    assert ConsentService.consent_is_satisfied(context, updated.grant) is remembered
    assert ConsentService.consent_is_satisfied(smaller, updated.grant) is True


@pytest.mark.asyncio
async def test_compensation_does_not_restore_concurrently_revoked_grant(data_session: AsyncSession) -> None:
    """补偿 CAS 不得覆盖管理员在提交后执行的 Grant 撤销。"""
    now = datetime.now(timezone.utc)
    user = SysUser(user_id=8002, user_name='race-user', nick_name='Race User', status='0', del_flag='0')
    client = SysOAuthClient(
        client_pk=8002,
        client_id='race-client',
        client_name='Race Client',
        client_type='public',
        token_endpoint_auth_method='none',
        grant_types=['authorization_code'],
        response_types=['code'],
        policy_version=5,
        status='0',
    )
    grant = SysOAuthGrant(
        grant_id='race-grant',
        user_id=8002,
        subject_id='subject-8002',
        client_pk=8002,
        granted_scopes=['openid'],
        granted_resources=[],
        client_policy_version=5,
        status='active',
        consented_at=now,
    )
    data_session.add_all([user, client, grant])
    await data_session.commit()

    previous = OAuthGrantDao.snapshot(grant)
    grant.granted_scopes = ['openid', 'profile']
    grant.consented_at = now + timedelta(seconds=1)
    await data_session.flush()
    persisted = OAuthGrantDao.snapshot(grant)
    await data_session.commit()

    session_factory = async_sessionmaker(data_session.bind, expire_on_commit=False)
    async with session_factory() as concurrent_session:
        assert await OAuthGrantDao.revoke(concurrent_session, grant.grant_id, reason='administrator') is True
        await concurrent_session.commit()
    await ConsentService.compensate_persisted_grant(
        data_session,
        ConsentResult(
            approved=True,
            scopes=('openid', 'profile'),
            grant=grant,
            previous_grant=previous,
            persisted_grant=persisted,
        ),
    )
    await data_session.refresh(grant)
    assert grant.status == 'revoked'
    assert grant.revoke_reason == 'administrator'
    audit = (
        await data_session.execute(
            select(SysOAuthAuditLog).where(SysOAuthAuditLog.failure_code == 'consent_compensation_conflict')
        )
    ).scalar_one()
    assert audit.event_type == OidcAuditEvent.CONSENT_GRANTED
    assert audit.risk_level == 'high'


@pytest.mark.asyncio
async def test_compensation_does_not_revoke_concurrently_updated_new_grant(data_session: AsyncSession) -> None:
    """新建 Grant 的撤销补偿不得覆盖另一会话的更新，并记录高风险审计。"""
    now = datetime.now(timezone.utc)
    user = SysUser(user_id=8003, user_name='new-race-user', nick_name='New Race User', status='0', del_flag='0')
    client = SysOAuthClient(
        client_pk=8003,
        client_id='new-race-client',
        client_name='New Race Client',
        client_type='public',
        token_endpoint_auth_method='none',
        grant_types=['authorization_code'],
        response_types=['code'],
        policy_version=5,
        status='0',
    )
    grant = SysOAuthGrant(
        grant_id='new-race-grant',
        user_id=8003,
        subject_id='subject-8003',
        client_pk=8003,
        granted_scopes=['openid'],
        granted_resources=[],
        client_policy_version=5,
        status='active',
        consented_at=now,
    )
    data_session.add_all([user, client, grant])
    await data_session.commit()
    persisted = OAuthGrantDao.snapshot(grant)

    session_factory = async_sessionmaker(data_session.bind, expire_on_commit=False)
    async with session_factory() as concurrent_session:
        await concurrent_session.execute(
            SysOAuthGrant.__table__.update()
            .where(SysOAuthGrant.grant_id == grant.grant_id)
            .values(granted_scopes=['openid', 'admin'], subject_id='concurrent-subject')
        )
        await concurrent_session.commit()

    await ConsentService.compensate_persisted_grant(
        data_session,
        ConsentResult(
            approved=True,
            scopes=('openid',),
            grant=grant,
            persisted_grant=persisted,
        ),
    )
    await data_session.rollback()
    await data_session.refresh(grant)
    assert grant.status == 'active'
    assert grant.granted_scopes == ['openid', 'admin']
    assert grant.subject_id == 'concurrent-subject'
    audit = (
        await data_session.execute(
            select(SysOAuthAuditLog).where(SysOAuthAuditLog.failure_code == 'consent_compensation_conflict')
        )
    ).scalar_one()
    assert audit.event_type == OidcAuditEvent.CONSENT_GRANTED
    assert audit.risk_level == 'high'
