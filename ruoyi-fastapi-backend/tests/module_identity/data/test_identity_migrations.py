"""在隔离数据库验证升级流程及两种部署数据库的SQL编译"""

import importlib.util
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.do.user_do import SysUser
from module_identity.service.schema_service import IdentityMigrationRequired, IdentitySchemaService


def revision(name: str) -> ModuleType:
    path = Path(__file__).resolve().parents[3] / 'alembic' / 'versions' / name
    spec = importlib.util.spec_from_file_location(name.removesuffix('.py'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INITIAL = '20260824_add_unified_authentication_center.py'
UTC = '20260912_identity_utc.py'
CONSENT = '20260912_offline_consent.py'


def test_existing_users_are_backfilled_without_changing_user_table() -> None:
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        SysUser.__table__.create(connection)
        SysMenu.__table__.create(connection)
        connection.execute(
            SysUser.__table__.insert(),
            [
                {'user_id': 1, 'user_name': 'existing', 'nick_name': 'Existing', 'del_flag': '0'},
                {'user_id': 2, 'user_name': 'deleted', 'nick_name': 'Deleted', 'del_flag': '2'},
            ],
        )
        before = connection.execute(sa.text('SELECT * FROM sys_user ORDER BY user_id')).all()
        with pytest.raises(IdentityMigrationRequired, match='missing tables'):
            IdentitySchemaService.check(connection)
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision(INITIAL).upgrade()
            with pytest.raises(IdentityMigrationRequired, match='consent preference'):
                IdentitySchemaService.check(connection)
            revision(CONSENT).upgrade()
            IdentitySchemaService.check(connection)
            subjects = connection.execute(
                sa.text('SELECT user_id, subject_id FROM sys_identity_subject ORDER BY user_id')
            ).all()
            assert len(subjects) == len(before) and len({row.subject_id for row in subjects}) == len(before)
            revision(UTC).upgrade()
            assert (
                connection.execute(
                    sa.text('SELECT user_id, subject_id FROM sys_identity_subject ORDER BY user_id')
                ).all()
                == subjects
            )
            assert connection.execute(sa.text('SELECT * FROM sys_user ORDER BY user_id')).all() == before
            builtin_scope_count = 7
            assert connection.scalar(sa.text('SELECT COUNT(*) FROM sys_oauth_scope')) == builtin_scope_count
            with pytest.raises(RuntimeError, match='delete data'):
                revision(INITIAL).downgrade()
    engine.dispose()


@pytest.mark.parametrize('dialect, expected', [('mysql', 'DATETIME(3)'), ('postgresql', 'TIMESTAMP(3) WITH TIME ZONE')])
def test_initial_migration_compiles_utc_storage_for_both_databases(dialect: str, expected: str) -> None:
    output = StringIO()
    context = MigrationContext.configure(dialect_name=dialect, opts={'as_sql': True, 'output_buffer': output})
    with Operations.context(context):
        revision(INITIAL).upgrade()
    sql = output.getvalue()
    assert expected in sql.upper()
    assert 'replaced_by_token_id' in sql
    assert 'sys_identity_subject' in sql


def test_legacy_timezone_conversion_never_guesses_dst_fold_or_gap() -> None:
    migrate = revision(UTC)
    assert migrate._to_utc(datetime(2026, 9, 12, 10), ZoneInfo('Asia/Shanghai')) == datetime(
        2026, 9, 12, 2, tzinfo=timezone.utc
    )
    for wall in [datetime(2026, 3, 8, 2, 30), datetime(2026, 11, 1, 1, 30)]:
        with pytest.raises(RuntimeError, match='Ambiguous/nonexistent'):
            migrate._to_utc(wall, ZoneInfo('America/New_York'))


def test_consent_migration_preserves_old_choices_without_promoting_new_offline_grants() -> None:
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    legacy = sa.Table(
        'sys_oauth_grant',
        metadata,
        sa.Column('grant_id', sa.String, primary_key=True),
        sa.Column('granted_scopes', sa.JSON),
        sa.Column('granted_resources', sa.JSON),
    )
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            legacy.insert().values(grant_id='old', granted_scopes=['openid', 'profile'], granted_resources=[])
        )
        with Operations.context(MigrationContext.configure(connection)):
            revision(CONSENT).upgrade()
            grants = sa.Table('sys_oauth_grant', sa.MetaData(), autoload_with=connection)
            old = connection.execute(sa.select(grants)).mappings().one()
            assert old['remembered_scopes'] == ['openid', 'profile']
            connection.execute(
                grants.insert().values(
                    grant_id='new-offline',
                    granted_scopes=['openid', 'offline_access'],
                    granted_resources=[],
                    remembered_scopes=[],
                    remembered_resources=[],
                )
            )
            revision(CONSENT).upgrade()
            offline = connection.execute(sa.select(grants).where(grants.c.grant_id == 'new-offline')).mappings().one()
            assert offline['remembered_scopes'] == [] and offline['remembered_resources'] == []
    engine.dispose()
