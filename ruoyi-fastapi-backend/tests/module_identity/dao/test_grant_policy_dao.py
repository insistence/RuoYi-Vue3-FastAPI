from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant


@pytest.mark.asyncio
async def test_valid_grant_requires_active_unexpired_and_current_client_policy(
    data_session: AsyncSession,
) -> None:
    """验证 Grant 过期或 Client 策略版本变化后不再视为有效。"""
    now = datetime.now(timezone.utc)
    client = SysOAuthClient(
        client_pk=4101,
        client_id='grant-policy-client',
        client_name='Grant Policy Client',
        client_type='confidential',
        token_endpoint_auth_method='client_secret_basic',
        grant_types=['authorization_code'],
        response_types=['code'],
        policy_version=7,
    )
    data_session.add_all(
        [
            SysUser(user_id=4101, user_name='grant-user', nick_name='Grant User', status='0', del_flag='0'),
            client,
            SysOAuthGrant(
                grant_id='grant-policy-1',
                user_id=4101,
                subject_id='subject-policy-1',
                client_pk=4101,
                granted_scopes=['openid'],
                granted_resources=[],
                client_policy_version=7,
                status='active',
                consented_at=now,
            ),
        ]
    )
    await data_session.flush()
    assert await OAuthGrantDao.get_valid_for_user_client(data_session, 4101, 4101) is not None

    grant = await OAuthGrantDao.get_active_for_user_client(data_session, 4101, 4101)
    grant.expires_at = now - timedelta(seconds=1)
    await data_session.flush()
    assert await OAuthGrantDao.get_valid_for_user_client(data_session, 4101, 4101) is None

    grant.expires_at = None
    client.policy_version = 8
    await data_session.flush()
    assert await OAuthGrantDao.get_valid_for_user_client(data_session, 4101, 4101) is None
