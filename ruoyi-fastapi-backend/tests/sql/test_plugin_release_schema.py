from pathlib import Path

import pytest
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.schema import CreateTable

from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease, SysPluginWorker

SQL_ROOT = Path(__file__).resolve().parents[2] / 'sql'


@pytest.mark.parametrize(
    ('initial', 'upgrade', 'time_type'),
    [
        ('ruoyi-fastapi.sql', 'upgrade_plugin_artifact_mysql.sql', 'datetime(3)'),
        ('ruoyi-fastapi-pg.sql', 'upgrade_plugin_artifact_postgresql.sql', 'timestamp(3) with time zone'),
    ],
)
def test_incremental_and_initial_release_schema_match(initial: str, upgrade: str, time_type: str) -> None:
    initialization = (SQL_ROOT / initial).read_text(encoding='utf-8')
    migration = (SQL_ROOT / upgrade).read_text(encoding='utf-8')
    migration_body = '\n'.join(line for line in migration.splitlines() if not line.lstrip().startswith('--'))
    initialization_body = '\n'.join(line for line in initialization.splitlines() if not line.lstrip().startswith('--'))
    assert ' '.join(migration_body.split()) in ' '.join(initialization_body.split())
    assert 'drop table' not in migration.lower()
    assert 'alter table' not in migration.lower()
    assert time_type in migration
    for table in (SysPluginArtifact.__table__, SysPluginRelease.__table__, SysPluginWorker.__table__):
        assert f'create table if not exists {table.name} (' in migration
        for column in table.columns:
            assert column.name in migration
    for constraint in ('ck_sys_plugin_release_workers', 'ck_sys_plugin_release_prepare', 'ck_sys_plugin_worker_state'):
        assert constraint in migration


@pytest.mark.parametrize('dialect', [mysql.dialect(), postgresql.dialect()])
def test_release_orm_schema_compiles_for_supported_database_dialects(dialect: object) -> None:
    for model in (SysPluginArtifact, SysPluginRelease, SysPluginWorker):
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect))
        assert model.__tablename__ in ddl
        assert 'PRIMARY KEY' in ddl
