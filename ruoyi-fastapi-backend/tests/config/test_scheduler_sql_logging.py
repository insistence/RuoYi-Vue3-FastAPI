import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

import pytest
import pytest_asyncio
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from config.database import DataSourceRegistry, _DataSourceRegistry, quiet_sql_engine
from config.scheduler.job_execution import JobExecutionStore
from config.scheduler.manager import SchedulerManager
from module_admin.entity.do.job_runtime_do import SysJobExecution, SysJobSync


def _sql_logs(caplog: pytest.LogCaptureFixture) -> str:
    return '\n'.join(record.getMessage() for record in caplog.records if record.name.startswith('sqlalchemy.engine.'))


@pytest_asyncio.fixture
async def sql_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "scheduler.sqlite"}', logging_name=request.node.name)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    registry = _DataSourceRegistry()
    runtime = registry._runtime()
    runtime.async_engine = engine
    runtime.async_session_factory = sessions
    runtime.available = True
    monkeypatch.setattr('config.scheduler.resources.DataSourceRegistry', registry)
    metadata = MetaData()
    SysJobExecution.__table__.to_metadata(metadata)
    SysJobSync.__table__.to_metadata(metadata)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dispatch_poll_suppresses_sql_parameters_and_transactions(
    sql_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sql_engine.echo = 'debug'
    monkeypatch.setattr(SchedulerManager, '_is_leader', True)
    monkeypatch.setattr(SchedulerManager._dispatcher, 'lock', asyncio.Lock())
    monkeypatch.setattr(SchedulerManager._synchronizer, 'applied_jobs', {1: {'appliedVersion': 1}})
    monkeypatch.setattr(SchedulerManager._dispatcher, '_observed_at', 0, raising=False)
    caplog.clear()
    capsys.readouterr()

    # 调用实际轮询和DAO；包含恢复UPDATE、待执行SELECT、提交及会话退出回滚。
    await SchedulerManager._drain_execution_requests()
    await SchedulerManager._drain_execution_requests()

    assert not [record for record in caplog.records if record.name.startswith('sqlalchemy.engine.')]
    assert capsys.readouterr().out == ''
    assert sql_engine.echo == 'debug'


@pytest.mark.asyncio
async def test_business_task_spawned_during_internal_session_keeps_sql_logging(
    sql_engine: AsyncEngine, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    sql_engine.echo = 'debug'

    async def business_query() -> None:
        async with async_sessionmaker(sql_engine)() as db:
            assert await db.scalar(text("SELECT 'business_sql_visible'")) == 'business_sql_visible'
            await db.commit()

    caplog.clear()
    capsys.readouterr()
    async with SchedulerManager._resources.session() as db:
        assert db.bind.pool is sql_engine.pool
        assert await db.scalar(text("SELECT 'internal_sql_hidden'")) == 'internal_sql_hidden'
        await asyncio.create_task(business_query())
        await db.commit()
        await db.execute(text("SELECT 'internal_rollback_hidden'"))

    output = capsys.readouterr().out
    for logs in (_sql_logs(caplog), output):
        assert 'business_sql_visible' in logs
        assert 'COMMIT' in logs
        assert 'internal_sql_hidden' not in logs
        assert 'internal_rollback_hidden' not in logs
        assert 'ROLLBACK' not in logs
    assert sql_engine.get_execution_options().get('logging_token') is None


@pytest.mark.asyncio
@pytest.mark.parametrize('exception_type', [RuntimeError, asyncio.CancelledError])
async def test_failed_or_cancelled_internal_session_keeps_errors_and_subsequent_sql(
    sql_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    exception_type: type[BaseException],
) -> None:
    sql_engine.echo = 'debug'
    caplog.clear()
    with pytest.raises(exception_type):
        async with SchedulerManager._resources.session() as db:
            await db.execute(text("SELECT 'failed_internal_sql_hidden'"))
            token = db.bind.get_execution_options()['logging_token']
            engine_logger = logging.getLogger(f'sqlalchemy.engine.Engine.{sql_engine.sync_engine.logging_name}')
            engine_logger.warning('[%s] internal_warning_visible', token)
            engine_logger.error('[%s] internal_error_visible', token)
            raise exception_type()

    async with async_sessionmaker(sql_engine)() as db:
        await db.execute(text("SELECT 'after_failure_visible'"))

    logs = _sql_logs(caplog)
    assert 'failed_internal_sql_hidden' not in logs
    assert 'internal_warning_visible' in logs
    assert 'internal_error_visible' in logs
    assert 'after_failure_visible' in logs


@pytest.mark.parametrize('echo', [True, 'debug'])
@pytest.mark.parametrize('logging_name', [None, 'scheduler_sync'])
def test_execution_lease_sql_is_quiet_without_muting_shared_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    echo: bool | Literal['debug'],
    logging_name: str | None,
) -> None:
    logger_name = 'sqlalchemy.engine.Engine' + (f'.{logging_name}' if logging_name else '')
    engine_logger = logging.getLogger(logger_name)
    original_handlers = engine_logger.handlers[:]
    engine = create_engine(f'sqlite:///{tmp_path / "lease.sqlite"}', logging_name=logging_name)
    SysJobExecution.__table__.create(engine)
    engine.echo = echo
    monkeypatch.setattr(DataSourceRegistry, 'get_sync_engine', lambda _name: engine)
    caplog.clear()
    capsys.readouterr()
    try:
        # 续租线程使用相同的同步会话入口；空记录也实际执行UPDATE和COMMIT。
        assert JobExecutionStore.renew('missing-execution', 'missing-token') is False
        assert caplog.records == []
        assert capsys.readouterr().out == ''
        with JobExecutionStore.session() as db:
            assert db.bind.pool is engine.pool
        with Session(engine) as db:
            db.execute(text("SELECT 'sync_business_sql_visible'"))
        assert 'sync_business_sql_visible' in caplog.text
        assert 'sync_business_sql_visible' in capsys.readouterr().out
        assert engine.echo == echo
        assert engine.get_execution_options().get('logging_token') is None
    finally:
        engine.dispose()
        for handler in engine_logger.handlers[:]:
            if handler not in original_handlers:
                engine_logger.removeHandler(handler)


def test_sql_filter_is_idempotent_and_retains_tagged_warnings(caplog: pytest.LogCaptureFixture) -> None:
    engine = create_engine('sqlite://', logging_name='quiet_filter')
    engine_logger = logging.getLogger('sqlalchemy.engine.Engine.quiet_filter')
    try:
        quiet_engine = quiet_sql_engine(engine)
        filters = engine_logger.filters[:]
        quiet_sql_engine(engine)
        assert engine_logger.filters == filters
        prefix = f'[{quiet_engine.get_execution_options()["logging_token"]}] '
        engine_logger.warning(prefix + 'warning_retained')
        engine_logger.error(prefix + 'error_retained')
        assert 'warning_retained' in caplog.text
        assert 'error_retained' in caplog.text
    finally:
        engine.dispose()
