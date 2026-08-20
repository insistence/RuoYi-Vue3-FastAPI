from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import URL
from sqlalchemy.exc import OperationalError

from common.aspect.db_seesion import DBSessionDependency, get_db_session_provider
from config import database
from exceptions.exception import DataSourceInitializationException, DataSourceUnavailableException

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _source(*, required: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        db_type='mysql',
        db_host='db.example',
        db_port=3306,
        db_username='user',
        db_password='p@ss/w0rd',
        db_database='application',
        db_echo=False,
        db_connect_timeout=7,
        db_max_overflow=1,
        db_pool_size=1,
        db_pool_recycle=60,
        db_pool_timeout=2,
        db_required=required,
    )


def test_database_urls_use_structured_url_and_hide_password() -> None:
    config = _source()
    async_url = database.build_async_sqlalchemy_database_url(config)
    sync_url = database.build_sync_sqlalchemy_database_url(config)

    assert isinstance(async_url, URL)
    assert async_url.drivername == 'mysql+asyncmy'
    assert sync_url.drivername == 'mysql+pymysql'
    assert async_url.password == 'p@ss/w0rd'
    assert 'p@ss' not in repr(async_url)


@pytest.mark.parametrize(
    ('db_type', 'db_port', 'async_timeout_key', 'sync_timeout_key'),
    [
        ('mysql', 3306, 'connect_timeout', 'connect_timeout'),
        ('postgresql', 5432, 'timeout', 'connect_timeout'),
    ],
)
def test_engine_factories_use_driver_specific_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
    db_type: str,
    db_port: int,
    async_timeout_key: str,
    sync_timeout_key: str,
) -> None:
    config = _source()
    config.db_type = db_type
    config.db_port = db_port
    async_engine = object()
    sync_engine = object()
    captured_options: dict[str, dict[str, object]] = {}

    def create_async_engine(_url: URL, **options: object) -> object:
        captured_options['async'] = options
        return async_engine

    def create_sync_engine(_url: URL, **options: object) -> object:
        captured_options['sync'] = options
        return sync_engine

    monkeypatch.setattr(database, 'create_async_engine', create_async_engine)
    monkeypatch.setattr(database, 'create_engine', create_sync_engine)

    assert database.create_async_db_engine(config=config) is async_engine
    assert database.create_sync_db_engine(config=config) is sync_engine
    assert captured_options['async']['connect_args'] == {async_timeout_key: 7}
    assert captured_options['sync']['connect_args'] == {sync_timeout_key: 7}
    assert captured_options['async']['pool_use_lifo'] is True
    assert captured_options['sync']['pool_use_lifo'] is True


def test_async_session_factory_disables_expiration_after_commit() -> None:
    factory = database.create_async_session_factory(MagicMock())

    assert factory.kw['expire_on_commit'] is False


class _Begin:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    async def __aenter__(self) -> _Begin:
        if self.should_fail:
            raise RuntimeError('password=secret')
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def execute(self, _statement: object) -> None:
        return None


class _Engine:
    def __init__(self) -> None:
        self.should_fail = True
        self.dispose = AsyncMock()

    def begin(self) -> _Begin:
        return _Begin(self.should_fail)


@pytest.mark.asyncio
async def test_initialize_can_suppress_worker_startup_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    primary_engine = _Engine()
    primary_engine.should_fail = False
    optional_engine = _Engine()
    monkeypatch.setattr(
        database,
        'create_async_db_engine',
        lambda config: primary_engine if config.db_required else optional_engine,
    )
    registry = database._DataSourceRegistry(
        SimpleNamespace(
            db_default_source='primary',
            db_sources={'primary': _source(), 'reporting': _source(required=False)},
        )
    )
    source_logger = MagicMock()
    monkeypatch.setattr(database, 'logger', source_logger)

    await registry.initialize(log_enabled=False)

    source_logger.bind.assert_not_called()
    assert registry._runtimes['primary'].available
    assert not registry._runtimes['reporting'].available

    optional_engine.should_fail = False
    registry._runtimes['reporting'].next_retry_at = None
    async with registry.connection('reporting'):
        pass
    source_logger.bind.assert_not_called()
    await registry.dispose_all()


@pytest.mark.asyncio
async def test_initialize_logs_source_name(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _Engine()
    engine.should_fail = False
    monkeypatch.setattr(database, 'create_async_db_engine', lambda config: engine)
    registry = database._DataSourceRegistry(
        SimpleNamespace(db_default_source='primary', db_sources={'primary': _source()})
    )
    source_logger = MagicMock()
    monkeypatch.setattr(database, 'logger', source_logger)

    await registry.initialize()

    source_logger.bind.assert_called_once_with(data_source='primary', database_type='mysql', required=True)
    source_logger.bind.return_value.info.assert_called_once_with('✅ 数据源 primary 初始化成功')
    await registry.dispose_all()


@pytest.mark.asyncio
async def test_optional_source_recovers_after_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    primary_engine = _Engine()
    primary_engine.should_fail = False
    optional_engine = _Engine()
    monkeypatch.setattr(
        database,
        'create_async_db_engine',
        lambda config: primary_engine if config.db_required else optional_engine,
    )
    settings = SimpleNamespace(
        db_default_source='primary',
        db_sources={'primary': _source(), 'reporting': _source(required=False)},
    )
    registry = database._DataSourceRegistry(settings)

    await registry.initialize()
    assert not registry._runtimes['reporting'].available
    optional_engine.should_fail = False
    runtime = registry._runtimes['reporting']
    runtime.next_retry_at = None
    async with registry.connection('reporting'):
        pass
    assert runtime.available
    await registry.dispose_all()


@pytest.mark.asyncio
async def test_optional_engine_creation_failure_degrades_and_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    primary_config = _source()
    optional_config = _source(required=False)
    primary_engine = _Engine()
    primary_engine.should_fail = False
    optional_engine = _Engine()
    optional_engine.should_fail = False
    optional_creation_fails = True

    def create_engine(config: SimpleNamespace) -> _Engine:
        nonlocal optional_creation_fails
        if config is optional_config and optional_creation_fails:
            raise ModuleNotFoundError('driver is not installed')
        return optional_engine if config is optional_config else primary_engine

    monkeypatch.setattr(database, 'create_async_db_engine', create_engine)
    registry = database._DataSourceRegistry(
        SimpleNamespace(
            db_default_source='primary',
            db_sources={'primary': primary_config, 'reporting': optional_config},
        )
    )

    await registry.initialize()
    runtime = registry._runtimes['reporting']
    assert runtime.async_engine is None
    assert not runtime.available

    optional_creation_fails = False
    runtime.next_retry_at = None
    async with registry.connection('reporting'):
        pass

    assert runtime.async_engine is optional_engine
    assert runtime.available
    await registry.dispose_all()


@pytest.mark.asyncio
async def test_required_engine_creation_failure_disposes_other_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    primary_config = _source()
    optional_config = _source(required=False)
    optional_engine = _Engine()
    optional_engine.should_fail = False

    def create_engine(config: SimpleNamespace) -> _Engine:
        if config is primary_config:
            raise ModuleNotFoundError('required driver is not installed')
        return optional_engine

    monkeypatch.setattr(database, 'create_async_db_engine', create_engine)
    registry = database._DataSourceRegistry(
        SimpleNamespace(
            db_default_source='primary',
            db_sources={'primary': primary_config, 'reporting': optional_config},
        )
    )

    with pytest.raises(DataSourceInitializationException):
        await registry.initialize()

    optional_engine.dispose.assert_awaited_once_with()
    assert registry._runtimes == {}


@pytest.mark.asyncio
async def test_runtime_operational_error_marks_source_down_then_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _Engine()
    engine.should_fail = False
    monkeypatch.setattr(database, 'create_async_db_engine', lambda config: engine)
    registry = database._DataSourceRegistry(
        SimpleNamespace(db_default_source='primary', db_sources={'primary': _source()})
    )
    await registry.initialize()
    runtime = registry._runtimes['primary']
    session_closed = False

    @asynccontextmanager
    async def session_factory() -> AsyncGenerator[object, None]:
        nonlocal session_closed
        try:
            yield object()
        finally:
            session_closed = True

    runtime.async_session_factory = session_factory
    with pytest.raises(DataSourceUnavailableException):
        async with registry.session():
            raise OperationalError('SELECT 1', {}, RuntimeError('connection lost'))

    assert session_closed
    assert not runtime.available
    with pytest.raises(DataSourceUnavailableException):
        async with registry.session():
            pass

    runtime.next_retry_at = None
    async with registry.session() as session:
        assert session is not None
    assert runtime.available
    await registry.dispose_all()


@pytest.mark.asyncio
async def test_multiple_sources_have_independent_engines_and_factories(monkeypatch: pytest.MonkeyPatch) -> None:
    primary_config = _source()
    reporting_config = _source(required=False)
    engines = {id(primary_config): _Engine(), id(reporting_config): _Engine()}
    for engine in engines.values():
        engine.should_fail = False
    monkeypatch.setattr(database, 'create_async_db_engine', lambda config: engines[id(config)])
    registry = database._DataSourceRegistry(
        SimpleNamespace(
            db_default_source='primary',
            db_sources={'primary': primary_config, 'reporting': reporting_config},
        )
    )

    await registry.initialize()

    assert registry.get_async_engine() is engines[id(primary_config)]
    assert registry.get_async_engine('reporting') is engines[id(reporting_config)]
    assert (
        registry._runtimes['primary'].async_session_factory is not registry._runtimes['reporting'].async_session_factory
    )
    await registry.dispose_all()


@pytest.mark.asyncio
async def test_dispose_all_releases_sync_and_async_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _Engine()
    engine.should_fail = False
    sync_engine = MagicMock()
    monkeypatch.setattr(database, 'create_async_db_engine', lambda config: engine)
    monkeypatch.setattr(database, 'create_sync_db_engine', lambda config: sync_engine)
    registry = database._DataSourceRegistry(
        SimpleNamespace(db_default_source='primary', db_sources={'primary': _source()})
    )
    await registry.initialize()
    assert registry.get_sync_engine() is sync_engine

    await registry.dispose_all()

    sync_engine.dispose.assert_called_once_with()
    engine.dispose.assert_awaited_once_with()
    assert registry._runtimes == {}


def test_dependency_provider_is_cached_per_source() -> None:
    get_db_session_provider.cache_clear()
    assert get_db_session_provider('reporting') is get_db_session_provider('reporting')
    assert get_db_session_provider('reporting') is not get_db_session_provider('archive')
    assert DBSessionDependency('reporting').dependency is get_db_session_provider('reporting')
