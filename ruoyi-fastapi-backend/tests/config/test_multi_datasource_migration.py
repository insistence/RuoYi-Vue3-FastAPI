import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / 'alembic' / 'versions' / '2026_08_19_0001_add_generator_data_source.py'
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location('multi_datasource_migration', MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_data_source_migration_is_idempotent() -> None:
    module = _load_migration()
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('create table gen_table (table_id integer primary key, table_name varchar(200))'))
        module.op = Operations(MigrationContext.configure(connection))

        module.upgrade()
        module.upgrade()

        inspector = inspect(connection)
        assert 'data_source_name' in {column['name'] for column in inspector.get_columns('gen_table')}


def test_generator_data_source_migration_allows_empty_database() -> None:
    module = _load_migration()
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
