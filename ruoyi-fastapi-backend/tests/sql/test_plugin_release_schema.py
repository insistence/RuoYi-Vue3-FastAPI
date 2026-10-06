import re
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.schema import CreateTable

from plugins.core.lifecycle.script import PluginLifecycleScriptHelper
from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease, SysPluginWorker

SQL_ROOT = Path(__file__).resolve().parents[2] / 'sql'


@pytest.mark.parametrize(
    ('initial', 'time_type'),
    [
        ('ruoyi-fastapi.sql', 'datetime(3)'),
        ('ruoyi-fastapi-pg.sql', 'timestamp(3) with time zone'),
    ],
)
def test_initial_release_schema_matches_models(initial: str, time_type: str) -> None:
    initialization = (SQL_ROOT / initial).read_text(encoding='utf-8')
    statements = PluginLifecycleScriptHelper.split_sql_statements(initialization)
    for table in (SysPluginArtifact.__table__, SysPluginRelease.__table__, SysPluginWorker.__table__):
        table_statements = [
            statement
            for statement in statements
            if re.match(rf'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table.name}\s*\(', statement, re.IGNORECASE)
        ]
        assert len(table_statements) == 1
        ddl = table_statements[0].lower()
        normalized_ddl = ' '.join(ddl.split())
        assert time_type in ddl
        for column in table.columns:
            assert re.search(rf'^\s*{column.name}\s+\w+', ddl, re.MULTILINE)
        primary_keys = ', '.join(column.name for column in table.primary_key.columns)
        assert f'primary key ({primary_keys})' in normalized_ddl
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                assert f'constraint {constraint.name} check ({constraint.sqltext})' in normalized_ddl
        for index in table.indexes:
            columns = ', '.join(column.name for column in index.columns)
            if initial == 'ruoyi-fastapi-pg.sql':
                assert f'create index if not exists {index.name} on {table.name} ({columns})' in statements
            else:
                assert f'key {index.name} ({columns})' in normalized_ddl


@pytest.mark.parametrize('dialect', [mysql.dialect(), postgresql.dialect()])
def test_release_orm_schema_compiles_for_supported_database_dialects(dialect: object) -> None:
    for model in (SysPluginArtifact, SysPluginRelease, SysPluginWorker):
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect))
        assert model.__tablename__ in ddl
        assert 'PRIMARY KEY' in ddl
