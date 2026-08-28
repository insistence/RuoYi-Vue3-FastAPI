"""身份安全事件到 OIDC 状态失效的事务测试。"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.database import Base
from module_admin.entity.do.user_do import SysUser, SysUserRole
from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from module_identity.entity.do.oauth_audit_do import SysOAuthAuditLog
from module_identity.entity.do.oauth_grant_do import SysOAuthRefreshToken, SysSsoSession
from module_identity.service.identity_service import (
    IdentitySecurityEventError,
    IdentitySecurityEventService,
)

_NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)
_INITIAL_VERSION = 3
_PASSWORD_REFRESH_COUNT = 2
_CLAIM_USER_ID = 8
_ROLE_REFRESH_COUNT = 4


@pytest_asyncio.fixture
async def security_session() -> AsyncSession:
    """创建身份安全事件涉及表的真实异步数据库会话。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    tables = [
        SysUser.__table__,
        SysUserRole.__table__,
        SysIdentitySubject.__table__,
        SysSsoSession.__table__,
        SysOAuthRefreshToken.__table__,
        SysOAuthAuditLog.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_user(session: AsyncSession, user_id: int, *, with_subject: bool = True) -> None:
    """写入一个用户及其可撤销的 Session、Refresh。"""
    session.add(SysUser(user_id=user_id, user_name=f'user-{user_id}', nick_name='User'))
    if with_subject:
        session.add(
            SysIdentitySubject(
                user_id=user_id,
                subject_id=f'00000000-0000-4000-8000-{user_id:012d}',
                auth_version=_INITIAL_VERSION,
                create_time=_NOW,
            )
        )
    for index in range(2):
        sid = f'sid-{user_id}-{index}'
        session.add(
            SysSsoSession(
                sid=sid,
                session_secret_hash=str(index) * 64,
                user_id=user_id,
                subject_id=f'00000000-0000-4000-8000-{user_id:012d}',
                auth_version=_INITIAL_VERSION,
                auth_time=_NOW,
                last_seen_at=_NOW,
                idle_expires_at=_NOW + timedelta(hours=1),
                absolute_expires_at=_NOW + timedelta(hours=2),
                acr='urn:ruoyi:acr:pwd',
                amr=['pwd'],
                status='active',
                create_time=_NOW,
            )
        )
        session.add(
            SysOAuthRefreshToken(
                token_id=f'token-{user_id}-{index}',
                token_hash=f'{user_id:02d}{index}' * 16,
                family_id=f'family-{user_id}-{index}',
                grant_id=f'grant-{user_id}',
                user_id=user_id,
                subject_id=f'00000000-0000-4000-8000-{user_id:012d}',
                auth_version=_INITIAL_VERSION,
                client_pk=100,
                sid=sid,
                scopes=['openid'],
                resources=[],
                status='active',
                issued_at=_NOW,
                idle_expires_at=_NOW + timedelta(days=1),
                absolute_expires_at=_NOW + timedelta(days=7),
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_password_change_increments_version_and_keeps_only_current_session(
    security_session: AsyncSession,
) -> None:
    """修改密码应递增版本、撤销全部 Refresh，并可保留当前交互 Session。"""
    await _seed_user(security_session, 7)
    result = await IdentitySecurityEventService.handle_user_event(
        security_session,
        7,
        'password_changed',
        actor='admin',
        exclude_sid='sid-7-0',
        now=_NOW + timedelta(minutes=1),
    )
    assert result.revoked_sessions == 1
    assert result.revoked_refresh_tokens == _PASSWORD_REFRESH_COUNT
    assert (await security_session.get(SysIdentitySubject, 1)).auth_version == _INITIAL_VERSION + 1
    sessions = (await security_session.execute(select(SysSsoSession).order_by(SysSsoSession.sid))).scalars().all()
    assert [row.status for row in sessions] == ['active', 'revoked']
    tokens = (
        (await security_session.execute(select(SysOAuthRefreshToken).order_by(SysOAuthRefreshToken.token_id)))
        .scalars()
        .all()
    )
    assert all(row.status == 'revoked' for row in tokens)
    audit = (await security_session.execute(select(SysOAuthAuditLog))).scalar_one()
    assert audit.detail['event'] == 'password_changed'
    assert audit.detail['actor'] == 'admin'
    assert audit.risk_level == 'high'


@pytest.mark.asyncio
async def test_claim_change_keeps_sso_by_default_and_transaction_can_rollback(
    security_session: AsyncSession,
) -> None:
    """角色/部门变化默认保留 SSO，且全部安全写入服从调用方事务。"""
    await _seed_user(security_session, _CLAIM_USER_ID)
    await IdentitySecurityEventService.handle_user_event(
        security_session,
        _CLAIM_USER_ID,
        'role_assignment_changed',
        now=_NOW + timedelta(minutes=2),
    )
    assert all(
        row.status == 'active' for row in (await security_session.execute(select(SysSsoSession))).scalars().all()
    )
    assert all(
        row.status == 'revoked'
        for row in (await security_session.execute(select(SysOAuthRefreshToken))).scalars().all()
    )
    await security_session.rollback()
    subject = await security_session.scalar(
        select(SysIdentitySubject).where(SysIdentitySubject.user_id == _CLAIM_USER_ID)
    )
    assert subject is not None and subject.auth_version == _INITIAL_VERSION
    assert all(
        row.status == 'active' for row in (await security_session.execute(select(SysOAuthRefreshToken))).scalars().all()
    )
    assert not (await security_session.execute(select(SysOAuthAuditLog))).scalars().all()


@pytest.mark.asyncio
async def test_missing_subject_fails_before_revocation(security_session: AsyncSession) -> None:
    """主体映射缺失必须 fail closed，且不能先撤销部分凭据。"""
    await _seed_user(security_session, 9, with_subject=False)
    with pytest.raises(IdentitySecurityEventError, match='mapping is missing'):
        await IdentitySecurityEventService.handle_user_event(security_session, 9, 'user_disabled', now=_NOW)
    assert all(
        row.status == 'active' for row in (await security_session.execute(select(SysSsoSession))).scalars().all()
    )
    assert all(
        row.status == 'active' for row in (await security_session.execute(select(SysOAuthRefreshToken))).scalars().all()
    )


@pytest.mark.asyncio
async def test_role_event_updates_all_current_members(security_session: AsyncSession) -> None:
    """角色停用应按成员集合批量更新版本与 Refresh。"""
    await _seed_user(security_session, 10)
    await _seed_user(security_session, 11)
    security_session.add_all([SysUserRole(user_id=10, role_id=5), SysUserRole(user_id=11, role_id=5)])
    await security_session.commit()
    result = await IdentitySecurityEventService.handle_role_event(
        security_session,
        5,
        'role_disabled',
        actor='admin',
        now=_NOW + timedelta(minutes=3),
    )
    assert result.affected_users == (10, 11)
    assert result.revoked_refresh_tokens == _ROLE_REFRESH_COUNT
    assert result.revoked_sessions == 0
    versions = (
        (await security_session.execute(select(SysIdentitySubject.auth_version).order_by(SysIdentitySubject.user_id)))
        .scalars()
        .all()
    )
    assert versions == [_INITIAL_VERSION + 1, _INITIAL_VERSION + 1]
