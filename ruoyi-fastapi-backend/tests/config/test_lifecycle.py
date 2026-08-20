from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
