from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_identity.dao.oauth_token_dao import OAuthTokenDao
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken, SysSsoSession

_REUSED_TOKEN_COUNT = 2


def _token(token_id: str, status: str, now: datetime, idle_expires_at: datetime) -> SysOAuthRefreshToken:
    """构造测试用 Refresh Token 元数据。"""
    return SysOAuthRefreshToken(
        token_id=token_id,
        token_hash=f'{token_id:0<64}',
        family_id='family-1',
        grant_id='grant-1',
        user_id=3001,
        subject_id='subject-1',
        auth_version=1,
        client_pk=3001,
        sid='sid-1',
        scopes=['openid'],
        resources=[],
        status=status,
        issued_at=now,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=now + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_refresh_family_lock_rotation_and_reuse_distribution(data_session: AsyncSession) -> None:
    """验证 Family 查询、单 Token 轮换和重放后的状态分布。"""
    now = datetime.now(timezone.utc)
    data_session.add_all(
        [
            SysUser(user_id=3001, user_name='refresh', nick_name='Refresh', status='0', del_flag='0'),
            SysOAuthClient(
                client_pk=3001,
                client_id='refresh-client',
                client_name='Refresh Client',
                client_type='confidential',
                token_endpoint_auth_method='client_secret_basic',
                grant_types=['authorization_code', 'refresh_token'],
                response_types=['code'],
            ),
            SysOAuthGrant(
                grant_id='grant-1',
                user_id=3001,
                subject_id='subject-1',
                client_pk=3001,
                granted_scopes=['openid'],
                granted_resources=[],
                client_policy_version=1,
                consented_at=now,
            ),
            SysSsoSession(
                sid='sid-1',
                session_secret_hash='a' * 64,
                user_id=3001,
                subject_id='subject-1',
                auth_version=1,
                auth_time=now,
                last_seen_at=now,
                idle_expires_at=now + timedelta(hours=1),
                absolute_expires_at=now + timedelta(days=1),
                acr='pwd',
                amr=['pwd'],
            ),
            _token('token-1', 'active', now, now + timedelta(hours=1)),
            _token('token-2', 'active', now + timedelta(seconds=1), now + timedelta(hours=1)),
        ]
    )
    await data_session.flush()

    family = await OAuthTokenDao.lock_family(data_session, 'family-1')
    assert [token.token_id for token in family] == ['token-1', 'token-2']
    injected_now = datetime(2026, 8, 24, 5, 6, 7, tzinfo=timezone.utc)
    assert await OAuthTokenDao.mark_used(data_session, 'token-1', 'token-2', now=injected_now)
    assert (await OAuthTokenDao.get_by_token_id(data_session, 'token-1')).last_used_at == injected_now
    changed = await OAuthTokenDao.refresh_token_family_reuse(data_session, 'family-1', 'token-1', now=injected_now)
    assert changed == _REUSED_TOKEN_COUNT
    await data_session.flush()
    statuses = {token.token_id: token.status for token in family}
    assert statuses == {'token-1': 'reuse_detected', 'token-2': 'revoked'}


@pytest.mark.asyncio
async def test_refresh_expire_due_handles_idle_and_absolute_expiry(data_session: AsyncSession) -> None:
    """验证闲置和绝对期限任一到期都会使 Active Token 过期。"""
    now = datetime.now(timezone.utc)
    data_session.add_all(
        [
            SysUser(user_id=3001, user_name='expire', nick_name='Expire', status='0', del_flag='0'),
            SysOAuthClient(
                client_pk=3001,
                client_id='expire-client',
                client_name='Expire Client',
                client_type='confidential',
                token_endpoint_auth_method='client_secret_basic',
                grant_types=['refresh_token'],
                response_types=['code'],
            ),
            SysOAuthGrant(
                grant_id='grant-1',
                user_id=3001,
                subject_id='subject-1',
                client_pk=3001,
                granted_scopes=['openid'],
                granted_resources=[],
                client_policy_version=1,
                consented_at=now,
            ),
            SysSsoSession(
                sid='sid-1',
                session_secret_hash='b' * 64,
                user_id=3001,
                subject_id='subject-1',
                auth_version=1,
                auth_time=now,
                last_seen_at=now,
                idle_expires_at=now + timedelta(hours=1),
                absolute_expires_at=now + timedelta(days=1),
                acr='pwd',
                amr=['pwd'],
            ),
            _token('token-idle', 'active', now, now - timedelta(seconds=1)),
        ]
    )
    await data_session.flush()
    assert await OAuthTokenDao.expire_due(data_session) == 1
    assert (await OAuthTokenDao.get_by_token_id(data_session, 'token-idle')).status == 'expired'
