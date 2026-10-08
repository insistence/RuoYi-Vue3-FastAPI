import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from cli.exit_codes import ARGUMENT_ERROR, DEPENDENCY_ERROR, SUCCESS
from cli.groups.plugin.commands.sdk import register_sdk_commands

BACKEND = Path(__file__).resolve().parents[3]
FRONTEND = BACKEND.parent / 'ruoyi-fastapi-frontend'


def sdk_app() -> typer.Typer:
    """
    构造独立 SDK 命令入口，保留真实参数解析和结果输出。

    :return: 包含 sdk 子命令的 Typer 应用
    """
    app = typer.Typer()
    register_sdk_commands(app)
    return app


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """
    创建未跟踪 SDK 的旧 bundle 工程，避免读取业务插件。

    :param tmp_path: 隔离测试目录
    :return: 工程根目录
    """
    root = tmp_path / 'example'
    vendor = root / 'web' / 'vendor'
    vendor.mkdir(parents=True)
    (root / 'plugin.yaml').write_text(
        'manifestVersion: 2\nid: example\nname: Example\nversion: 1.0.0\n'
        'backend:\n  module: plugins.example\n  entrypoint: plugins.example:create_plugin\n  integration: asgi\n'
        'frontend:\n  delivery:\n    type: bundle\n',
        encoding='utf-8',
    )
    (root / '__init__.py').write_text('raise RuntimeError("must never import this project")\n', encoding='utf-8')
    for name in ('pluginBridge.js', 'pluginBridge.d.ts'):
        (vendor / name).write_text('old untracked SDK\n', encoding='utf-8')
    return root


def invoke_sdk(operation: str, project: Path, *options: str) -> tuple[int, dict]:
    """
    使用真实离线 SDK 服务执行命令并解析结构化结果。

    :param operation: check 或 update
    :param project: 待检查工程目录
    :param options: 额外 CLI 选项
    :return: 退出码和 JSON 结果
    """
    result = CliRunner().invoke(
        sdk_app(), ['sdk', operation, str(project), '--frontend-root', str(FRONTEND), '--output', 'json', *options]
    )
    assert result.stdout, result.exception
    return result.exit_code, json.loads(result.stdout)


def test_sdk_cli_requires_explicit_force_for_untracked_copy_and_dry_run_does_not_write(project: Path) -> None:
    """
    验证旧工程纳管前可预演，默认拒绝写入且强制更新只修改 SDK。

    :param project: 未跟踪 SDK 的隔离工程
    :return: None
    """
    before = {path.relative_to(project): path.read_bytes() for path in project.rglob('*') if path.is_file()}
    code, payload = invoke_sdk('check', project)
    assert code == DEPENDENCY_ERROR and payload['status'] == 'untracked'
    code, payload = invoke_sdk('update', project)
    assert code == DEPENDENCY_ERROR and not payload['ok']
    code, payload = invoke_sdk('update', project, '--force', '--dry-run')
    assert code == SUCCESS and payload['dryRun']
    assert before == {path.relative_to(project): path.read_bytes() for path in project.rglob('*') if path.is_file()}
    code, payload = invoke_sdk('update', project, '--force')
    assert code == SUCCESS and payload['ok']
    assert (project / '__init__.py').read_bytes() == before[Path('__init__.py')]
    assert (project / '.plugin-sdk-backups').is_dir()
    code, payload = invoke_sdk('check', project)
    assert code == SUCCESS and payload['status'] == 'current'
    assert payload['sdkVersion'] == payload['currentSdkVersion'] == '1.0.0'


def test_sdk_cli_bad_source_is_json_and_nonzero(project: Path, tmp_path: Path) -> None:
    """
    验证来源 SDK 缺失时返回单份 JSON 和非零状态。

    :param project: 独立测试工程
    :param tmp_path: 不包含 SDK 的来源目录
    :return: None
    """
    result = CliRunner().invoke(
        sdk_app(), ['sdk', 'check', str(project), '--frontend-root', str(tmp_path), '--output', 'json']
    )
    assert result.exit_code != SUCCESS
    assert json.loads(result.stdout)['ok'] is False


def test_sdk_cli_invalid_output_is_argument_error(project: Path) -> None:
    """
    验证 SDK 子命令复用 CLI 输出格式约束。

    :param project: 独立测试工程
    :return: None
    """
    result = CliRunner().invoke(sdk_app(), ['sdk', 'check', str(project), '--output', 'xml'])
    assert result.exit_code == ARGUMENT_ERROR


def test_sdk_check_cold_process_does_not_load_host_configuration_or_project(project: Path) -> None:
    """
    验证实际根命令能在无宿主配置条件下离线运行，不导入业务或数据库。

    :param project: 包含禁止执行代码的独立工程
    :return: None
    """
    script = """
import json, sys
from typer.testing import CliRunner
from cli.main import CLI_MAIN_RUNNER
app = CLI_MAIN_RUNNER.build_cli()
result = CliRunner().invoke(app, ['plugin', 'sdk', 'check', sys.argv[1], '--output', 'json'])
for name in ('config.env', 'config.database', 'plugins.core.runtime.explicit', 'plugins.example'):
    assert name not in sys.modules, name
print(json.dumps({'exitCode': result.exit_code, 'payload': json.loads(result.stdout)}))
"""
    environment = {**os.environ, 'RUOYI_PLUGIN_FRONTEND_ROOT': str(FRONTEND), 'DB_SOURCES': 'invalid-do-not-read'}
    result = subprocess.run(
        [sys.executable, '-X', 'utf8', '-c', script, str(project)],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=30,
        check=False,
    )
    assert result.returncode == SUCCESS, result.stderr
    observed = json.loads(result.stdout)
    assert observed['exitCode'] == DEPENDENCY_ERROR
    assert observed['payload']['status'] == 'untracked'
