import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _ensure_backend_on_path() -> None:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def tui_base_modules() -> SimpleNamespace:
    _ensure_backend_on_path()
    sys.modules.pop('cli.main', None)
    sys.modules.pop('cli.tui.commands', None)
    sys.modules.pop('cli', None)

    dependency_error = importlib.import_module('cli.exit_codes').DEPENDENCY_ERROR
    cli_main = importlib.import_module('cli.main')
    cli_tui_commands = importlib.import_module('cli.tui.commands')

    return SimpleNamespace(
        BACKEND_DIR=BACKEND_DIR,
        DEPENDENCY_ERROR=dependency_error,
        cli_main=cli_main,
        cli_tui_commands=cli_tui_commands,
    )


@pytest.fixture
def tui_modules(tui_base_modules: SimpleNamespace) -> SimpleNamespace:
    pytest.importorskip('textual')
    _ensure_backend_on_path()
    for module_name in (
        'cli.tui.app',
        'cli.tui.screens.browser',
        'cli.tui.copy',
        'cli.tui.screens.dashboard',
        'cli.tui.screens.detail',
        'cli.tui.screens.interactions',
        'cli.tui.adapters',
        'cli.tui.search',
        'cli.tui.widgets',
        'cli',
    ):
        sys.modules.pop(module_name, None)

    return SimpleNamespace(
        **tui_base_modules.__dict__,
        cli_tui_app=importlib.import_module('cli.tui.app'),
        cli_tui_browser=importlib.import_module('cli.tui.screens.browser'),
        cli_tui_copy=importlib.import_module('cli.tui.copy'),
        cli_tui_dashboard=importlib.import_module('cli.tui.screens.dashboard'),
        cli_tui_detail=importlib.import_module('cli.tui.screens.detail'),
        cli_tui_interactions=importlib.import_module('cli.tui.screens.interactions'),
        cli_tui_adapters=importlib.import_module('cli.tui.adapters'),
        cli_tui_search=importlib.import_module('cli.tui.search'),
        cli_tui_widgets=importlib.import_module('cli.tui.widgets'),
    )
