from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.constant import OidcAuditEvent
from config.database import Base
from exceptions.exception import OAuthProtocolException
from module_admin.entity.do.user_do import SysUser
from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from module_identity.entity.do.oauth_audit_do import SysOAuthAuditLog
from module_identity.service.audit_service import AuditService
from module_identity.service.identity_service import IdentitySubjectService

_MISSING_SUBJECT_USER_ID = 1101
_ROLLBACK_USER_ID = 1105
_REPAIRED_SUBJECT_COUNT = 2
_NEXT_AUTH_VERSION = 2


@pytest_asyncio.fixture
async def service_session(tmp_path: Path) -> AsyncSession:
    """创建只包含主体服务所需表的真实 SQLite 会话。"""
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "subject-service.sqlite3"}')
    tables = [SysUser.__table__, SysIdentitySubject.__table__, SysOAuthAuditLog.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.info['service_engine'] = engine
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_missing_subject_fails_closed_and_records_integrity_audit(service_session: AsyncSession) -> None:
    """主体缺失时不能签发，并且必须留下高风险完整性事件。"""
    service_session.add(
        SysUser(
            user_id=_MISSING_SUBJECT_USER_ID,
            user_name='missing',
            nick_name='Missing',
            status='0',
            del_flag='0',
        )
    )
    await service_session.flush()

    with pytest.raises(OAuthProtocolException) as caught:
        await IdentitySubjectService.require_by_user_id(service_session, _MISSING_SUBJECT_USER_ID)

    assert caught.value.error == 'server_error'
    event = await service_session.execute(
        select(SysOAuthAuditLog).where(SysOAuthAuditLog.user_id == _MISSING_SUBJECT_USER_ID)
    )
    event = event.scalars().first()
    assert event is not None
    assert event.event_type == OidcAuditEvent.IDENTITY_SUBJECT_MISSING
    assert event.risk_level == 'high'
    assert event.result == 'failure'


@pytest.mark.asyncio
async def test_repair_single_and_batch_are_idempotent(service_session: AsyncSession) -> None:
    """单用户和批量修复重复执行都不会替换 Subject 或增加记录。"""
    service_session.add_all(
        [
            SysUser(user_id=1102, user_name='one', nick_name='One', status='0', del_flag='0'),
            SysUser(user_id=1103, user_name='two', nick_name='Two', status='0', del_flag='0'),
        ]
    )
    await service_session.flush()
    first = await IdentitySubjectService.repair_missing_subject(service_session, 1102)
    same = await IdentitySubjectService.repair_missing_subject(service_session, 1102)
    assert first.identity_id == same.identity_id
    rows = await IdentitySubjectService.repair_missing_subjects(service_session, [1102, 1103])
    assert len(rows) == 1
    assert await IdentitySubjectService.repair_missing_subjects(service_session, [1102, 1103]) == []
    assert len((await service_session.execute(select(SysIdentitySubject))).scalars().all()) == _REPAIRED_SUBJECT_COUNT


@pytest.mark.asyncio
async def test_auth_version_update_is_atomic(service_session: AsyncSession) -> None:
    """认证版本条件不匹配时不得更新。"""
    service_session.add(SysUser(user_id=1104, user_name='version', nick_name='Version', status='0', del_flag='0'))
    await service_session.flush()
    await IdentitySubjectService.repair_missing_subject(service_session, 1104)
    updated = await IdentitySubjectService.increment_auth_version(service_session, 1104, expected_version=1)
    assert updated.auth_version == _NEXT_AUTH_VERSION
    with pytest.raises(OAuthProtocolException):
        await IdentitySubjectService.increment_auth_version(service_session, 1104, expected_version=1)


@pytest.mark.asyncio
async def test_independent_audit_writer_survives_main_transaction_rollback(service_session: AsyncSession) -> None:
    """主事务回滚时，独立审计提交仍保留主体完整性告警。"""
    factory = async_sessionmaker(service_session.info['service_engine'], expire_on_commit=False)

    async def audit_writer(user_id: int) -> None:
        async with factory() as audit_session:
            await AuditService.record(
                audit_session,
                event_type=OidcAuditEvent.IDENTITY_SUBJECT_MISSING,
                result='failure',
                risk_level='high',
                user_id=user_id,
                failure_code='identity_integrity',
            )
            await audit_session.commit()

    with pytest.raises(OAuthProtocolException):
        await IdentitySubjectService.require_by_user_id(service_session, _ROLLBACK_USER_ID, audit_writer=audit_writer)
    service_session.add(
        SysUser(user_id=_ROLLBACK_USER_ID, user_name='rollback', nick_name='Rollback', status='0', del_flag='0')
    )
    await service_session.flush()
    await service_session.rollback()
    async with factory() as audit_session:
        event = (
            (await audit_session.execute(select(SysOAuthAuditLog).where(SysOAuthAuditLog.user_id == _ROLLBACK_USER_ID)))
            .scalars()
            .first()
        )
    assert event is not None
    assert event.risk_level == 'high'
    assert (
        await service_session.execute(select(SysUser).where(SysUser.user_id == _ROLLBACK_USER_ID))
    ).scalars().first() is None
