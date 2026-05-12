import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]


def test_bootstrap_import_does_not_eagerly_load_heavy_runtime_modules() -> None:
    """
    校验导入 `cli.bootstrap` 时不会提前加载重依赖模块。

    :return: None
    """
    script = """
import json
import sys

sys.path.insert(0, '.')
for module_name in [
    'cli.bootstrap',
    'config.database',
    'config.get_redis',
    'config.get_scheduler',
    'module_admin.service.server_service',
    'utils.transport_crypto_util',
]:
    sys.modules.pop(module_name, None)

import cli.bootstrap

print(json.dumps({
    'config.database': 'config.database' in sys.modules,
    'config.get_redis': 'config.get_redis' in sys.modules,
    'config.get_scheduler': 'config.get_scheduler' in sys.modules,
    'module_admin.service.server_service': 'module_admin.service.server_service' in sys.modules,
    'utils.transport_crypto_util': 'utils.transport_crypto_util' in sys.modules,
}, ensure_ascii=False))
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)

    assert payload == {
        'config.database': False,
        'config.get_redis': False,
        'config.get_scheduler': False,
        'module_admin.service.server_service': False,
        'utils.transport_crypto_util': False,
    }


def test_build_cli_does_not_eagerly_load_heavy_runtime_dependencies() -> None:
    """
    校验构建 CLI 根应用时不会提前加载 DB、Redis、Scheduler 和业务服务依赖。

    :return: None
    """
    script = """
import json
import sys

sys.path.insert(0, '.')
for module_name in [
    'cli.main',
    'config.env',
    'config.database',
    'config.get_redis',
    'config.get_scheduler',
    'cli.tui.app',
    'module_admin.service.server_service',
    'module_admin.service.job_service',
    'module_admin.service.config_service',
    'module_generator.service.gen_service',
    'textual',
    'utils.transport_crypto_util',
]:
    sys.modules.pop(module_name, None)

import cli.main

cli.main.CLI_APPLICATION_BUILDER.build()

print(json.dumps({
    'config.env': 'config.env' in sys.modules,
    'config.database': 'config.database' in sys.modules,
    'config.get_redis': 'config.get_redis' in sys.modules,
    'config.get_scheduler': 'config.get_scheduler' in sys.modules,
    'cli.tui.app': 'cli.tui.app' in sys.modules,
    'module_admin.service.server_service': 'module_admin.service.server_service' in sys.modules,
    'module_admin.service.job_service': 'module_admin.service.job_service' in sys.modules,
    'module_admin.service.config_service': 'module_admin.service.config_service' in sys.modules,
    'module_generator.service.gen_service': 'module_generator.service.gen_service' in sys.modules,
    'textual': 'textual' in sys.modules,
    'utils.transport_crypto_util': 'utils.transport_crypto_util' in sys.modules,
}, ensure_ascii=False))
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)

    assert payload == {
        'config.env': False,
        'config.database': False,
        'config.get_redis': False,
        'config.get_scheduler': False,
        'cli.tui.app': False,
        'module_admin.service.server_service': False,
        'module_admin.service.job_service': False,
        'module_admin.service.config_service': False,
        'module_generator.service.gen_service': False,
        'textual': False,
        'utils.transport_crypto_util': False,
    }


def test_build_wizard_app_does_not_eagerly_load_flow_modules() -> None:
    """
    校验构建 `wizard` 子应用时不会提前加载各个 flow 模块。

    :return: None
    """
    script = """
import json
import sys

sys.path.insert(0, '.')
for module_name in [
    'cli.wizard.commands',
    'cli.wizard.flows.app_run',
    'cli.wizard.flows.db_upgrade',
    'cli.wizard.flows.cache_clear',
    'cli.wizard.flows.gen_export',
    'cli.wizard.flows.gen_import',
    'cli.wizard.flows.prod_check',
]:
    sys.modules.pop(module_name, None)

from cli.wizard.commands import WIZARD_COMMAND_BUILDER

WIZARD_COMMAND_BUILDER.build()

print(json.dumps({
    'cli.wizard.flows.app_run': 'cli.wizard.flows.app_run' in sys.modules,
    'cli.wizard.flows.db_upgrade': 'cli.wizard.flows.db_upgrade' in sys.modules,
    'cli.wizard.flows.cache_clear': 'cli.wizard.flows.cache_clear' in sys.modules,
    'cli.wizard.flows.gen_export': 'cli.wizard.flows.gen_export' in sys.modules,
    'cli.wizard.flows.gen_import': 'cli.wizard.flows.gen_import' in sys.modules,
    'cli.wizard.flows.prod_check': 'cli.wizard.flows.prod_check' in sys.modules,
}, ensure_ascii=False))
"""
    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)

    assert payload == {
        'cli.wizard.flows.app_run': False,
        'cli.wizard.flows.db_upgrade': False,
        'cli.wizard.flows.cache_clear': False,
        'cli.wizard.flows.gen_export': False,
        'cli.wizard.flows.gen_import': False,
        'cli.wizard.flows.prod_check': False,
    }
