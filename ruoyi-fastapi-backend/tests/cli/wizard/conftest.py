import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _load_module(module_name: str) -> ModuleType:
    sys.modules.pop(module_name, None)
    sys.modules.pop('cli', None)
    return importlib.import_module(module_name)


@pytest.fixture
def backend_dir() -> Path:
    return BACKEND_DIR


@pytest.fixture
def load_module() -> Callable[[str], ModuleType]:
    return _load_module


@pytest.fixture
def cli_main(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.main')


@pytest.fixture
def app_run_flow(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.wizard.flows.app_run')


@pytest.fixture
def cache_clear_flow(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.wizard.flows.cache_clear')


@pytest.fixture
def db_upgrade_flow(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.wizard.flows.db_upgrade')


@pytest.fixture
def gen_export_flow(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.wizard.flows.gen_export')


@pytest.fixture
def gen_import_flow(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.wizard.flows.gen_import')


@pytest.fixture
def prod_check_flow(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.wizard.flows.prod_check')


@pytest.fixture
def exit_codes(load_module: Callable[[str], ModuleType]) -> ModuleType:
    return load_module('cli.exit_codes')
