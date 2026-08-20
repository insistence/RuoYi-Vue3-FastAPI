import asyncio
import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(BACKEND_DIR))


class RuntimeQueryStub:
    """把现有负载工厂映射为新的异步进程内查询接口。"""

    def __init__(self, runner: Callable[..., object]) -> None:
        self.runner = runner

    def _payload(self, *arguments: str) -> object:
        return self.runner(*arguments, parse_json=True).payload

    async def get_app_env(self, env: str) -> object:
        return self._payload('app', 'env', f'--env={env}', '--output=json')

    async def get_app_config(self, env: str) -> object:
        return self._payload('app', 'config', f'--env={env}', '--output=json')

    async def get_app_routes(self, env: str) -> object:
        return self._payload('app', 'routes', f'--env={env}', '--output=json')

    async def get_doctor(self, env: str) -> object:
        return self._payload('app', 'doctor', f'--env={env}', '--output=json')

    async def get_completion_doctor(self) -> object:
        return self._payload('completion', 'doctor', '--output=json')

    async def get_completion_preview(self, shell: str) -> object:
        return self.runner('completion', 'show', f'--shell={shell}', parse_json=False)

    async def get_database_ping(self) -> object:
        return self._payload('ops', 'ping-db', '--output=json')

    async def get_database_current(self) -> object:
        return self._payload('db', 'current', '--output=json')

    async def get_database_heads(self) -> object:
        return self._payload('db', 'heads', '--output=json')

    async def get_database_history(self, *, limit: int = 8) -> object:
        return self._payload('db', 'history', f'--limit={limit}', '--output=json')

    async def get_redis_ping(self) -> object:
        return self._payload('ops', 'ping-redis', '--output=json')

    async def get_dependencies(self) -> object:
        return self._payload('ops', 'deps', '--output=json')

    async def get_server_info(self) -> object:
        return self._payload('ops', 'server-info', '--output=json')

    async def get_crypto_validation(self) -> object:
        return self._payload('crypto', 'validate', '--output=json')

    async def get_crypto_public_key(self) -> object:
        return self._payload('crypto', 'export-public', '--output=json')

    async def get_cache_stats(self) -> object:
        return self._payload('cache', 'stats', '--output=json')

    async def get_cache_keys(self, cache_name: str) -> object:
        return self._payload('cache', 'keys', cache_name, '--output=json')

    async def get_cache_value(self, cache_name: str, cache_key: str) -> object:
        return self._payload('cache', 'get', cache_name, cache_key, '--output=json')

    async def get_cache_ttl(self, cache_name: str, cache_key: str) -> object:
        return self._payload('cache', 'ttl', cache_name, cache_key, '--output=json')

    async def get_jobs(self) -> object:
        return self._payload('job', 'list', '--paged', '--page-size=8', '--output=json')

    async def get_job_logs(self, *, job_name: str = '', status: str | None = None, page_size: int = 20) -> object:
        arguments = ['job', 'logs', '--paged', f'--page-size={page_size}', '--output=json']
        if job_name:
            arguments.append(f'--job-name={job_name}')
        if status is not None:
            arguments.append(f'--status={status}')
        return self._payload(*arguments)

    async def get_job_detail(self, job_id: int) -> object:
        return self._payload('job', 'detail', str(job_id), '--output=json')

    async def get_gen_tables(self) -> object:
        return self._payload('gen', 'list', '--paged', '--page-size=8', '--output=json')

    async def get_gen_db_tables(self, *, table_name: str = '', page_size: int = 8) -> object:
        arguments = ['gen', 'db-list', '--paged', f'--page-size={page_size}', '--output=json']
        if table_name:
            arguments.append(f'--table-name={table_name}')
        return self._payload(*arguments)

    async def get_gen_detail(self, table_id: int) -> object:
        return self._payload('gen', 'detail', str(table_id), '--output=json')

    async def get_gen_preview(self, table_id: int) -> object:
        return self._payload('gen', 'preview', str(table_id), '--output=json')

    async def get_gen_export_dry_run(self, table_name: str) -> object:
        return self._payload('gen', 'export', table_name, '--dry-run', '--output=json')

    async def get_configs(self) -> object:
        return self._payload('config', 'list', '--paged', '--page-size=8', '--output=json')

    async def get_config_diagnostics(self) -> object:
        return self._payload('config', 'doctor', '--sample-limit=5', '--output=json')

    async def get_config_detail(self, config_key: str) -> object:
        return self._payload('config', 'get', config_key, '--source=both', '--output=json')


@pytest.fixture
def install_query_service() -> Callable[[ModuleType, Callable[..., object]], RuntimeQueryStub]:
    """向适配器及其采集/分区协作对象注入异步查询桩。"""

    def install(module: ModuleType, runner: Callable[..., object]) -> RuntimeQueryStub:
        query_service = RuntimeQueryStub(runner)
        visited: set[int] = set()

        def inject(target: object) -> None:
            if id(target) in visited:
                return
            visited.add(id(target))
            if hasattr(target, 'query_service'):
                target.query_service = query_service
            for attribute_name in ('snapshot_collector', 'section_builder'):
                child = getattr(target, attribute_name, None)
                if child is not None:
                    inject(child)

        for attribute_name in dir(module):
            if attribute_name.endswith(('_ADAPTER', '_COLLECTOR')):
                inject(getattr(module, attribute_name))
        return query_service

    return install


def _load_adapter_module(module_name: str) -> ModuleType:
    sys.modules.pop(module_name, None)
    sys.modules.pop('cli', None)
    return importlib.import_module(module_name)


@pytest.fixture
def app_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.app')


@pytest.fixture
def cache_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.cache')


@pytest.fixture
def crypto_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.crypto')


@pytest.fixture
def database_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.database')


@pytest.fixture
def jobs_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.jobs')


@pytest.fixture
def gen_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.gen')


@pytest.fixture
def configs_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.configs')


@pytest.fixture
def ops_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.ops')


@pytest.fixture
def health_adapter() -> ModuleType:
    return _load_adapter_module('cli.tui.adapters.health')


@pytest.fixture
def load_adapter_module() -> Callable[[str], ModuleType]:
    return _load_adapter_module


@pytest.fixture(autouse=True)
def dispose_async_db_engine_after_test() -> None:
    """
    在每个 TUI adapter 测试结束后尝试释放全局异步数据库连接池。

    这些适配器测试会按需导入运行时模块；若其中某些路径触发真实数据库访问，
    注册表中的引擎可能在测试进程结束前仍持有连接，从而在 GC 阶段产生
    SQLAlchemy 未归还连接告警。这里统一在测试后主动释放注册表资源，将清理职责
    收口到测试夹具而非业务代码。

    :return: None
    """
    yield
    database_module = sys.modules.get('config.database')
    if database_module is not None:
        asyncio.run(database_module.DataSourceRegistry.dispose_all())
