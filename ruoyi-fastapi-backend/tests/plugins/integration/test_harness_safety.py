import asyncio
import json
import os
import threading
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from fnmatch import fnmatchcase
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from scripts import plugin_release_integration as harness


@pytest.fixture
def run_spec(tmp_path: Path) -> harness.RunSpec:
    return harness.RunSpec('mysql', '0123456789abcdef' * 2, str(tmp_path))


@pytest.mark.parametrize('engine', ['mysql', 'postgresql'])
def test_main_without_opt_in_never_opens_database_or_redis(
    engine: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(harness.OPT_IN, raising=False)
    database_engine = Mock(side_effect=AssertionError('Database access is forbidden'))
    redis_client = Mock(side_effect=AssertionError('Redis access is forbidden'))
    monkeypatch.setattr(harness, 'database_engine', database_engine)
    monkeypatch.setattr(harness, 'redis_client', redis_client)

    with pytest.raises(ValueError, match='disabled'):
        harness.require_opt_in(engine)
    assert harness.main(['--engine', engine]) == 1
    database_engine.assert_not_called()
    redis_client.assert_not_called()
    assert 'Real-service tests are disabled' in capsys.readouterr().out


@pytest.mark.parametrize(
    'engine,password', [('mysql', 'RUOYI_IT_MYSQL_PASSWORD'), ('postgresql', 'RUOYI_IT_PG_PASSWORD')]
)
def test_opt_in_requires_explicit_password_environment(
    engine: str, password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(harness.OPT_IN, '1')
    monkeypatch.delenv(password, raising=False)
    monkeypatch.delenv('RUOYI_IT_REDIS_PASSWORD', raising=False)
    with pytest.raises(ValueError, match=password):
        harness.require_opt_in(engine)
    monkeypatch.setenv(password, '')
    with pytest.raises(ValueError, match='RUOYI_IT_REDIS_PASSWORD'):
        harness.require_opt_in(engine)
    monkeypatch.setenv('RUOYI_IT_REDIS_PASSWORD', '')
    harness.require_opt_in(engine)


@pytest.mark.parametrize('engine', ['mysql', 'postgresql'])
def test_cli_wait_environment_targets_only_the_isolated_database_without_mutating_parent(
    engine: str, run_spec: harness.RunSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = harness.RunSpec(engine, run_spec.run_id, run_spec.root)
    prefix = 'RUOYI_IT_MYSQL' if engine == 'mysql' else 'RUOYI_IT_PG'
    monkeypatch.setenv(harness.OPT_IN, '1')
    monkeypatch.setenv(f'{prefix}_PASSWORD', 'integration-only-test-secret')
    monkeypatch.setenv('RUOYI_IT_REDIS_PASSWORD', '')
    monkeypatch.setenv('DB_SOURCES', '{"foreign": {}}')
    monkeypatch.setenv('APP_ENV', 'parent-config-must-remain')
    parent = os.environ.copy()

    child = harness.cli_wait_environment(spec)

    assert dict(os.environ) == parent
    assert child['APP_ENV'] == f'plugin_it_{spec.run_id}'
    sources = json.loads(child['DB_SOURCES'])
    assert set(sources) == {'primary'}
    assert sources['primary']['db_database'] == spec.database
    assert sources['primary']['db_type'] == engine
    assert sources['primary']['db_password'] == 'integration-only-test-secret'
    assert sources['primary']['db_echo'] is False
    assert child['PLUGIN_ARTIFACT_STORE'] == str(Path(spec.root) / 'store')
    assert child['PLUGIN_ARTIFACT_TRUST_FILE'] == str(Path(spec.root) / 'trusted.json')
    assert child['LOG_FILE_ENABLED'] == 'false'


@pytest.mark.parametrize(
    'run_id',
    ['', 'a' * 31, 'a' * 33, 'A' * 32, 'g' * 32, '../production', 'a' * 31 + ';', 'a' * 31 + "'", 'a' * 32 + '\n'],
)
def test_run_spec_rejects_unsafe_database_and_redis_identity(run_id: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='identity'):
        harness.RunSpec('mysql', run_id, str(tmp_path)).validate()


def test_run_spec_rejects_other_engine_or_relative_root(tmp_path: Path, run_spec: harness.RunSpec) -> None:
    with pytest.raises(ValueError, match='identity'):
        harness.RunSpec('sqlite', run_spec.run_id, str(tmp_path)).validate()
    with pytest.raises(ValueError, match='absolute'):
        harness.RunSpec('mysql', run_spec.run_id, 'relative-output').validate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'engine,initial_filename', [('mysql', 'ruoyi-fastapi.sql'), ('postgresql', 'ruoyi-fastapi-pg.sql')]
)
async def test_prepare_schema_uses_initial_sql_without_drop_or_seed_data(
    engine: str, initial_filename: str, run_spec: harness.RunSpec
) -> None:
    spec = harness.RunSpec(engine, run_spec.run_id, run_spec.root)
    connection = SimpleNamespace(exec_driver_sql=AsyncMock(), execute=AsyncMock(return_value=SimpleNamespace(all=list)))

    @asynccontextmanager
    async def begin() -> AsyncGenerator[Any, None]:
        yield connection

    await harness.prepare_schema(spec, SimpleNamespace(begin=begin))

    statements = [call.args[0] for call in connection.exec_driver_sql.await_args_list]
    base_tables = (
        'sys_menu',
        'sys_job',
        'sys_plugin',
        'sys_plugin_menu',
        'sys_plugin_migration',
        'sys_plugin_config',
        'sys_plugin_operation_log',
    )
    release_tables = ('sys_plugin_artifact', 'sys_plugin_release', 'sys_plugin_worker')
    expected_indexes = (
        [
            'create index if not exists idx_sys_plugin_artifact_plugin on sys_plugin_artifact (plugin_id, version)',
            'create index if not exists idx_sys_plugin_worker_plugin on sys_plugin_worker (plugin_id, heartbeat_time)',
        ]
        if engine == 'postgresql'
        else []
    )
    initial_sql = (harness.BACKEND_ROOT / 'sql' / initial_filename).read_text('utf-8')
    expected_count = len(base_tables) + len(release_tables) + len(expected_indexes)
    assert len(statements) == expected_count
    for table_name, statement in zip(base_tables, statements[: len(base_tables)], strict=True):
        assert statement.lower().startswith(f'create table {table_name} (')
    release_statements = statements[len(base_tables) : len(base_tables) + len(release_tables)]
    for table_name, statement in zip(release_tables, release_statements, strict=True):
        assert statement.lower().startswith(f'create table if not exists {table_name} (')
    assert statements[len(base_tables) + len(release_tables) :] == expected_indexes
    for statement in statements:
        assert statement in initial_sql
    assert "default ''''''" not in statements[0]
    checked_tables = {call.args[0].get_final_froms()[0].name for call in connection.execute.await_args_list}
    assert checked_tables == {'sys_plugin_artifact', 'sys_plugin_release', 'sys_plugin_worker'}


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_schema', ['missing', 'duplicate'])
@pytest.mark.parametrize('table_name', ['sys_menu', 'sys_plugin_release'])
async def test_prepare_schema_rejects_incomplete_or_duplicate_host_ddl_before_execution(
    invalid_schema: str, table_name: str, run_spec: harness.RunSpec, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial_sql = (harness.BACKEND_ROOT / 'sql' / 'ruoyi-fastapi.sql').read_text('utf-8')
    if invalid_schema == 'missing':
        initial_sql = initial_sql.replace(f'{table_name} (', f'unused_{table_name} (')
    else:
        initial_sql += f'\ncreate table if not exists {table_name} (id bigint);'
    sql_root = tmp_path / 'sql'
    sql_root.mkdir()
    (sql_root / 'ruoyi-fastapi.sql').write_text(initial_sql, encoding='utf-8')
    monkeypatch.setattr(harness, 'BACKEND_ROOT', tmp_path)
    engine = SimpleNamespace(begin=Mock(side_effect=AssertionError('DDL must not run')))

    with pytest.raises(AssertionError, match=r'Incomplete host table DDL|Duplicate host table DDL'):
        await harness.prepare_schema(run_spec, engine)

    engine.begin.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('engine,quote', [('mysql', '`'), ('postgresql', '"')])
async def test_database_ddl_only_addresses_validated_run_database(
    engine: str, quote: str, run_spec: harness.RunSpec
) -> None:
    spec = harness.RunSpec(engine, run_spec.run_id, run_spec.root)
    connection = SimpleNamespace(exec_driver_sql=AsyncMock())

    @asynccontextmanager
    async def connect() -> AsyncGenerator[Any, None]:
        yield connection

    admin = SimpleNamespace(connect=Mock(side_effect=connect))
    await harness.create_isolated_database(spec, admin)
    await harness.drop_isolated_database(spec, admin)
    statements = [call.args[0] for call in connection.exec_driver_sql.await_args_list]
    assert statements[0].startswith(f'CREATE DATABASE {quote}{spec.database}{quote}')
    assert 'IF NOT EXISTS' not in statements[0].upper()
    assert statements[1] == f'DROP DATABASE {quote}{spec.database}{quote}'

    unsafe = harness.RunSpec(engine, 'production', spec.root)
    for operation in (harness.create_isolated_database, harness.drop_isolated_database):
        with pytest.raises(ValueError, match='identity'):
            await operation(unsafe, admin)
    expected_ddl_connection_count = 2
    assert admin.connect.call_count == expected_ddl_connection_count


@pytest.mark.asyncio
@pytest.mark.parametrize('created', [False, True])
async def test_run_drops_database_only_after_successful_create(
    created: bool, run_spec: harness.RunSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = SimpleNamespace(dispose=AsyncMock())
    engine = SimpleNamespace(dispose=AsyncMock())
    factory = Mock(side_effect=[admin, engine])
    create = AsyncMock(side_effect=None if created else RuntimeError('database already exists'))
    schema = AsyncMock(side_effect=RuntimeError('stop after successful create'))
    drop = AsyncMock()
    monkeypatch.setattr(harness, 'configure_process', Mock())
    monkeypatch.setattr(harness, 'database_engine', factory)
    monkeypatch.setattr(harness, 'create_isolated_database', create)
    monkeypatch.setattr(harness, 'prepare_schema', schema)
    monkeypatch.setattr(harness, 'clear_own_redis_keys', AsyncMock(return_value=0))
    monkeypatch.setattr(harness, 'drop_isolated_database', drop)
    monkeypatch.setattr(harness, 'emit', Mock())

    with pytest.raises(RuntimeError, match='stop after successful create' if created else 'database already exists'):
        await harness.run(run_spec)

    admin.dispose.assert_awaited_once()
    if created:
        drop.assert_awaited_once_with(run_spec, admin)
        engine.dispose.assert_awaited_once()
        expected_engine_count = 2
        assert factory.call_count == expected_engine_count
    else:
        drop.assert_not_awaited()
        schema.assert_not_awaited()
        engine.dispose.assert_not_awaited()
        assert factory.call_count == 1


@pytest.mark.asyncio
async def test_run_continues_owned_cleanup_after_engine_dispose_error(
    run_spec: harness.RunSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = SimpleNamespace(dispose=AsyncMock())
    engine = SimpleNamespace(dispose=AsyncMock(side_effect=RuntimeError('engine disposal failed')))
    clear = AsyncMock(return_value=0)
    drop = AsyncMock()
    monkeypatch.setattr(harness, 'configure_process', Mock())
    monkeypatch.setattr(harness, 'database_engine', Mock(side_effect=[admin, engine]))
    monkeypatch.setattr(harness, 'create_isolated_database', AsyncMock())
    monkeypatch.setattr(harness, 'prepare_schema', AsyncMock())
    monkeypatch.setattr(harness, 'exercise_release', AsyncMock())
    monkeypatch.setattr(harness, 'clear_own_redis_keys', clear)
    monkeypatch.setattr(harness, 'drop_isolated_database', drop)
    monkeypatch.setattr(harness, 'emit', Mock())

    with pytest.raises(RuntimeError, match='engine disposal failed'):
        await harness.run(run_spec)

    clear.assert_awaited_once_with(run_spec)
    drop.assert_awaited_once_with(run_spec, admin)
    admin.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_cleanup_scans_and_deletes_only_its_run_prefix(
    run_spec: harness.RunSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    own_keys = {f'{run_spec.redis_prefix}ready:generation', f'{run_spec.redis_prefix}lifecycle:global'}
    foreign_keys = {'plugin:lifecycle:lock:global', f'ruoyi_plugin_it:{"f" * 32}:ready:generation'}
    keys = own_keys | foreign_keys
    scans = []

    async def scan_iter(**kwargs: Any) -> AsyncIterator[str]:
        scans.append(kwargs['match'])
        for key in sorted(keys):
            if fnmatchcase(key, kwargs['match']):
                yield key

    async def delete(key: str) -> int:
        keys.remove(key)
        return 1

    client = SimpleNamespace(scan_iter=scan_iter, delete=AsyncMock(side_effect=delete), aclose=AsyncMock())
    monkeypatch.setattr(harness, 'redis_client', Mock(return_value=client))

    assert await harness.clear_own_redis_keys(run_spec) == len(own_keys)
    assert keys == foreign_keys
    assert scans == [f'{run_spec.redis_prefix}*', f'{run_spec.redis_prefix}*']
    assert {call.args[0] for call in client.delete.await_args_list} == own_keys
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_cleanup_refuses_foreign_key_even_if_scan_returns_it(
    run_spec: harness.RunSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scan_iter(**kwargs: Any) -> AsyncIterator[str]:
        yield 'plugin:lifecycle:lock:global'

    client = SimpleNamespace(scan_iter=scan_iter, delete=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(harness, 'redis_client', Mock(return_value=client))
    with pytest.raises(AssertionError, match='outside this run prefix'):
        await harness.clear_own_redis_keys(run_spec)
    client.delete.assert_not_awaited()
    client.aclose.assert_awaited_once()


def test_safe_error_redacts_explicit_credentials_and_bounds_output(monkeypatch: pytest.MonkeyPatch) -> None:
    password = 'db-password-unique-92ab'
    secret = 'redis-secret-unique-57ef'
    monkeypatch.setenv('RUOYI_IT_MYSQL_PASSWORD', password)
    monkeypatch.setenv('RUOYI_IT_REDIS_PASSWORD', secret)
    result = harness.safe_error(RuntimeError(f'failed auth {password}; {secret}; ' + 'x' * 7000))
    assert password not in result
    assert secret not in result
    assert '<redacted>' in result
    assert result.startswith('RuntimeError:')
    max_error_length = 6000
    assert len(result) <= max_error_length


def test_workers_pass_independent_stop_events_to_spawned_processes(
    run_spec: harness.RunSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [SimpleNamespace(set=Mock()), SimpleNamespace(set=Mock())]
    queue = SimpleNamespace(close=Mock(), join_thread=Mock())
    context = SimpleNamespace(
        Queue=Mock(return_value=queue),
        Event=Mock(side_effect=events),
        Process=Mock(side_effect=[Mock(), Mock()]),
    )
    get_context = Mock(return_value=context)
    monkeypatch.setattr(harness.multiprocessing, 'get_context', get_context)

    workers = harness.Workers(run_spec, one_fails=True)

    get_context.assert_called_once_with('spawn')
    assert context.Event.call_count == len(events)
    first_args, second_args = [call.kwargs['args'] for call in context.Process.call_args_list]
    assert first_args[-1] is events[0]
    assert second_args[-1] is events[1]
    assert first_args[-1] is not second_args[-1]
    assert workers.stops == events
    assert first_args[-2] == {'launch': workers.launch, 'fail': False}
    assert second_args[-2] == {'launch': workers.launch, 'fail': True}


@pytest.mark.asyncio
@pytest.mark.parametrize('second_state', ['killed', 'dead'])
async def test_workers_close_skips_killed_or_dead_stop_event_but_stops_healthy_worker(second_state: str) -> None:
    healthy_stop = SimpleNamespace(set=Mock())
    unusable_stop = SimpleNamespace(set=Mock(side_effect=AssertionError('Terminated waiter poisoned this event')))
    healthy = SimpleNamespace(pid=101, exitcode=0, is_alive=Mock(return_value=True), terminate=Mock())
    second = SimpleNamespace(
        pid=102,
        exitcode=-15 if second_state == 'killed' else 0,
        is_alive=Mock(return_value=second_state == 'killed'),
        terminate=Mock(),
    )

    def join_healthy(timeout: float) -> None:
        healthy_stop.set.assert_called_once()
        healthy.is_alive.return_value = False

    def join_second(timeout: float) -> None:
        second.is_alive.return_value = False

    healthy.join = Mock(side_effect=join_healthy)
    second.join = Mock(side_effect=join_second)
    workers = harness.Workers.__new__(harness.Workers)
    workers.stops = [healthy_stop, unusable_stop]
    workers.processes = [healthy, second]
    workers.killed = {1} if second_state == 'killed' else set()
    workers.queue = SimpleNamespace(close=Mock(), join_thread=Mock())

    await workers.close()

    healthy_stop.set.assert_called_once()
    unusable_stop.set.assert_not_called()
    healthy.join.assert_called_once()
    second.join.assert_called_once()
    healthy.terminate.assert_not_called()
    second.terminate.assert_not_called()
    workers.queue.close.assert_called_once()
    workers.queue.join_thread.assert_called_once()


def _wait_for_isolated_stop(stop: Any, ready: Any, index: int) -> None:
    """子进程入口不导入应用模块，也不访问外部服务。"""
    ready.put(index)
    if not stop.wait(30):
        raise RuntimeError('Offline event waiter exceeded its safety timeout')


def test_real_spawn_terminated_waiter_does_not_block_other_worker_shutdown() -> None:
    context = harness.multiprocessing.get_context('spawn')
    workers = harness.Workers.__new__(harness.Workers)
    workers.stops = [context.Event(), context.Event()]
    workers.queue = context.Queue()
    workers.killed = set()
    workers.processes = [
        context.Process(target=_wait_for_isolated_stop, args=(workers.stops[index], workers.queue, index))
        for index in range(2)
    ]
    failures: list[BaseException] = []

    async def stop_group() -> None:
        await workers.kill_failed_worker()
        await workers.close()

    def close_in_guarded_thread() -> None:
        try:
            asyncio.run(stop_group())
        except BaseException as exc:
            failures.append(exc)

    # Event.set() 回归时会同步阻塞，无法依靠 asyncio 超时中断。
    # 保持测试线程可用，确保能终止两个子进程。
    closer = threading.Thread(target=close_in_guarded_thread, daemon=True)
    try:
        for process in workers.processes:
            process.start()
        assert {workers.queue.get(timeout=15) for _ in workers.processes} == {0, 1}
        closer.start()
        closer.join(timeout=15)
        assert not closer.is_alive(), 'Worker shutdown blocked on a terminated process event'
        assert not failures, [repr(error) for error in failures]
        assert workers.killed == {1}
        assert workers.processes[0].exitcode == 0
        assert workers.processes[1].exitcode not in (None, 0)
        assert not any(process.is_alive() for process in workers.processes)
    finally:
        for process in workers.processes:
            if process.pid is None:
                continue
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
        workers.queue.close()
        workers.queue.join_thread()
