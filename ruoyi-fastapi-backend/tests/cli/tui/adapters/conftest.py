import asyncio
import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(BACKEND_DIR))


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
    模块级 `async_engine` 可能在测试进程结束前仍持有连接，从而在 GC 阶段产生
    SQLAlchemy 未归还连接告警。这里统一在测试后主动 `dispose()`，将清理职责收口
    到测试夹具而非业务代码。

    :return: None
    """
    yield
    database_module = sys.modules.get('config.database')
    async_engine = getattr(database_module, 'async_engine', None) if database_module is not None else None
    if async_engine is not None:
        asyncio.run(async_engine.dispose())
