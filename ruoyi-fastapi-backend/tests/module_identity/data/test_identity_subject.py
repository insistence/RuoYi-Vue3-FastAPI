import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_identity.dao.identity_subject_dao import IdentitySubjectDao

_NEXT_AUTH_VERSION = 2
_BACKFILL_COUNT = 2


@pytest.mark.asyncio
async def test_subject_is_stable_and_auth_version_is_atomic(data_session: AsyncSession) -> None:
    """验证幂等创建、稳定 Subject 与乐观版本条件。"""
    data_session.add(SysUser(user_id=1001, user_name='alice', nick_name='Alice', status='0', del_flag='0'))
    await data_session.flush()

    first = await IdentitySubjectDao.create_for_user(data_session, 1001, subject_id='stable-subject')
    second = await IdentitySubjectDao.create_for_user(data_session, 1001, subject_id='different-subject')
    assert first.identity_id == second.identity_id
    assert second.subject_id == 'stable-subject'
    assert await IdentitySubjectDao.increment_auth_version(data_session, 1001, expected_version=1)
    assert not await IdentitySubjectDao.increment_auth_version(data_session, 1001, expected_version=1)
    loaded = await IdentitySubjectDao.get_by_subject_id(data_session, 'stable-subject')
    assert loaded is not None
    assert loaded.auth_version == _NEXT_AUTH_VERSION


@pytest.mark.asyncio
async def test_backfill_is_idempotent_and_reports_missing_users(data_session: AsyncSession) -> None:
    """验证主体回填不重复创建并能发现未关联用户。"""
    data_session.add_all(
        [
            SysUser(user_id=1002, user_name='bob', nick_name='Bob', status='0', del_flag='0'),
            SysUser(user_id=1003, user_name='carol', nick_name='Carol', status='0', del_flag='0'),
        ]
    )
    await data_session.flush()
    assert await IdentitySubjectDao.list_missing_user_ids(data_session, [1002, 1003]) == [1002, 1003]
    rows = await IdentitySubjectDao.backfill_for_users(data_session, [1002, 1003])
    assert len(rows) == _BACKFILL_COUNT
    assert await IdentitySubjectDao.backfill_for_users(data_session, [1002, 1003]) == []
    assert await IdentitySubjectDao.list_missing_user_ids(data_session, [1002, 1003]) == []
