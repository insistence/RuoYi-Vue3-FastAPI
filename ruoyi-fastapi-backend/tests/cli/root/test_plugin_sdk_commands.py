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

pytestmark = pytest.mark.contract
BACKEND = Path(__file__).resolve().parents[3]
FRONTEND = BACKEND.parent / 'ruoyi-fastapi-frontend' / 'vue3' / 'web'


def sdk_app() -> typer.Typer:
    """
    构造独立 SDK 命令入口，保留真实参数解析和结果输出。

    :return: 包含 sdk 子命令的 Typer 应用
    """
    app = typer.Typer()
    register_sdk_commands(app)
    return app


@pytest.fixture
def project(untracked_bundle_project: Path) -> Path:
    """
    创建未跟踪 SDK 的旧 bundle 工程，避免读取业务插件。

    :param untracked_bundle_project: 共用的隔离 bundle 工程
    :return: 工程根目录
    """
    return untracked_bundle_project


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


@pytest.mark.parametrize(('framework', 'selected_framework'), [('auto', 'vue3'), ('vue2', 'vue2'), ('vue3', 'vue3')])
def test_sdk_cli_selects_supported_framework_from_frontend_container(
    project: Path, framework: str, selected_framework: str
) -> None:
    """校验 SDK 更新和检查命令均接受三个固定框架选项。"""
    result = CliRunner().invoke(
        sdk_app(),
        [
            'sdk',
            'update',
            str(project),
            '--frontend-root',
            str(FRONTEND.parents[1]),
            '--frontend-framework',
            framework,
            '--force',
            '--output',
            'json',
        ],
    )
    assert result.exit_code == SUCCESS, result.stdout
    metadata = json.loads((project / 'web/vendor/pluginBridge.sdk.json').read_text(encoding='utf-8'))
    assert metadata['source']['directory'] == f'ruoyi-fastapi-frontend/{selected_framework}/web/src/utils'
    check_result = CliRunner().invoke(
        sdk_app(),
        [
            'sdk',
            'check',
            str(project),
            '--frontend-root',
            str(FRONTEND.parents[1]),
            '--frontend-framework',
            framework,
            '--output',
            'json',
        ],
    )
    assert check_result.exit_code == SUCCESS, check_result.stdout
    assert json.loads(check_result.stdout)['status'] == 'current'


@pytest.mark.parametrize('operation', ['check', 'update'])
@pytest.mark.parametrize('framework', ['react', 'custom_ui-1', '../react', 'Vue3'])
def test_sdk_cli_rejects_unsupported_framework_before_file_operations(
    project: Path, operation: str, framework: str
) -> None:
    """校验 SDK 命令在参数解析阶段拒绝固定选项之外的框架且不修改工程。"""
    before = {path.relative_to(project): path.read_bytes() for path in project.rglob('*') if path.is_file()}
    result = CliRunner().invoke(
        sdk_app(),
        [
            'sdk',
            operation,
            str(project),
            '--frontend-framework',
            framework,
            '--output',
            'json',
        ],
    )
    assert result.exit_code == ARGUMENT_ERROR
    assert 'Invalid value' in result.output
    assert framework in result.output
    assert 'auto' in result.output and 'vue2' in result.output and 'vue3' in result.output
    assert before == {path.relative_to(project): path.read_bytes() for path in project.rglob('*') if path.is_file()}


@pytest.mark.parametrize('operation', ['check', 'update'])
def test_sdk_cli_help_displays_fixed_frontend_framework_choices(operation: str) -> None:
    """校验两个 SDK 命令的帮助均展示固定框架选项。"""
    result = CliRunner().invoke(sdk_app(), ['sdk', operation, '--help'], terminal_width=160)
    assert result.exit_code == SUCCESS
    assert 'auto|vue2|vue3' in result.output


def test_sdk_cli_rejects_removed_frontend_version_option(project: Path) -> None:
    """校验旧版本选项已移除，不保留兼容别名。"""
    result = CliRunner().invoke(sdk_app(), ['sdk', 'check', str(project), '--frontend-version', 'vue3'])
    assert result.exit_code == ARGUMENT_ERROR


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
