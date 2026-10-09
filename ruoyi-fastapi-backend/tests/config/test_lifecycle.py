from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Column, Integer, MetaData, Table

from config.database import Base
from config.lifecycle import init_create_table


@pytest.mark.asyncio
async def test_init_create_table_uses_registry_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = SimpleNamespace(run_sync=AsyncMock())

    @asynccontextmanager
    async def connection_context() -> AsyncGenerator[object, None]:
        yield connection

    registry = SimpleNamespace(connection=connection_context)
    monkeypatch.setattr('config.lifecycle.DataSourceRegistry', registry)

    await init_create_table(log_success_enabled=False)

    connection.run_sync.assert_awaited_once_with(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_startup_excludes_artifact_tables_from_implicit_schema_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = MetaData()
    platform_table = Table('platform', metadata, Column('id', Integer, primary_key=True))
    Table('signed_plugin_data', metadata, Column('id', Integer, primary_key=True), info={'plugin_artifact': 'demo'})
    connection = SimpleNamespace(run_sync=AsyncMock())

    @asynccontextmanager
    async def connection_context() -> AsyncGenerator[object, None]:
        yield connection

    monkeypatch.setattr('config.lifecycle.DataSourceRegistry', SimpleNamespace(connection=connection_context))
    monkeypatch.setattr('config.lifecycle.Base', SimpleNamespace(metadata=metadata))
    await init_create_table(stage='plugin_entities', log_success_enabled=False)
    connection.run_sync.assert_awaited_once_with(metadata.create_all, tables=[platform_table])
