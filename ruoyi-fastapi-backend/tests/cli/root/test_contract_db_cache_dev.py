import subprocess
from collections.abc import Callable
from pathlib import Path

from cli.exit_codes import DATABASE_ERROR, GUARD_REJECTED, REDIS_ERROR, RUNTIME_ERROR, SUCCESS

DB_HISTORY_TEST_LIMIT = 5


def test_dangerous_command_is_rejected_without_yes_in_non_interactive_mode(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('db', 'revision', '--env=dev', '--message=test-contract', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == GUARD_REJECTED
    assert payload['ok'] is False
    assert payload['message'] == '已取消危险命令执行：db revision'
    assert '--yes' in payload['hint']


def test_prod_dangerous_command_is_rejected_without_allow_prod(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('db', 'revision', '--env=prod', '--message=test-contract', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == GUARD_REJECTED
    assert payload['ok'] is False
    assert payload['message'] == '生产环境默认禁止直接执行危险命令：db revision'
    assert '--allow-prod' in payload['hint']
    assert '--yes' in payload['hint']


def test_dry_run_command_returns_structured_preview_payload(
    backend_dir: Path,
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'db',
        'upgrade',
        '--env=dev',
        '--revision=head',
        '--dry-run',
        '--yes',
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == 0
    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert isinstance(payload['command'], list)
    assert payload['command'][-2:] == ['upgrade', 'head']
    assert payload['cwd'] == str(backend_dir)


def test_db_heads_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('db', 'heads', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DATABASE_ERROR}
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    assert set(payload) == {'ok', 'message', 'count', 'items', 'env'}
    assert isinstance(payload['count'], int)
    assert isinstance(payload['items'], list)
    if payload['items']:
        first_item = payload['items'][0]
        assert set(first_item) == {'revision', 'downRevisions', 'branchLabels', 'dependsOn', 'doc', 'path'}
        assert isinstance(first_item['revision'], str)
        assert isinstance(first_item['downRevisions'], list)
        assert isinstance(first_item['branchLabels'], list)
        assert isinstance(first_item['dependsOn'], list)
        assert isinstance(first_item['doc'], str)
        assert isinstance(first_item['path'], str)


def test_db_history_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'db',
        'history',
        '--env=dev',
        f'--limit={DB_HISTORY_TEST_LIMIT}',
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DATABASE_ERROR}
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    assert set(payload) == {'ok', 'message', 'count', 'totalCount', 'limit', 'items', 'env'}
    assert payload['limit'] == DB_HISTORY_TEST_LIMIT
    assert isinstance(payload['count'], int)
    assert isinstance(payload['totalCount'], int)
    assert isinstance(payload['items'], list)


def test_cache_ttl_json_output_has_stable_contract_for_missing_key_or_redis_error(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'cache',
        'ttl',
        'sys_config',
        'definitely_missing_cli_key',
        '--env=dev',
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, REDIS_ERROR, RUNTIME_ERROR}
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert payload['message'] == '读取缓存剩余过期时间失败'
        assert isinstance(payload['error'], str)
        return

    assert set(payload) == {'ok', 'message', 'cacheName', 'cacheKey', 'fullCacheKey'}
    assert payload['ok'] is False
    assert payload['cacheName'] == 'sys_config'
    assert payload['cacheKey'] == 'definitely_missing_cli_key'
    assert payload['fullCacheKey'] == 'sys_config:definitely_missing_cli_key'


def test_dangerous_command_rejection_text_output_is_human_readable(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command('db', 'revision', '--env=dev', '--message=test-contract', '--output=text')

    assert completed.returncode == GUARD_REJECTED
    assert completed.stdout == (
        'FAIL FAILED\n'
        'message: 已取消危险命令执行：db revision\n'
        'hint: 当前命令需要交互确认；如需非交互执行，请传入 --yes\n'
    )


def test_dry_run_text_output_contains_preview_command_and_workdir(
    backend_dir: Path,
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command(
        'db',
        'upgrade',
        '--env=dev',
        '--revision=head',
        '--dry-run',
        '--yes',
        '--output=text',
    )

    assert completed.returncode == 0
    assert completed.stdout.startswith('OK SUCCESS\n')
    assert 'message: 数据库已升级到 head（dry-run）\n' in completed.stdout
    assert 'dry_run: true\n' in completed.stdout
    assert 'command:\n  - alembic\n  - -c\n' in completed.stdout
    assert f'  - {backend_dir / "alembic.ini"}\n' in completed.stdout
    assert f'cwd: {backend_dir}\n' in completed.stdout


def test_dev_lint_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'dev',
        'lint',
        'cli/groups/dev/command.py',
        '--env=dev',
        '--check-only',
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == SUCCESS
    assert payload['ok'] is True
    assert payload['message'] == '开发检查已完成'
    assert payload['env'] == 'dev'
    assert payload['checkOnly'] is True
    assert payload['fix'] is False
    assert payload['unsafeFixes'] is False
    assert payload['targets'] == ['cli/groups/dev/command.py']
    assert isinstance(payload['format'], dict)
    assert isinstance(payload['check'], dict)
    assert payload['format']['ok'] is True
    assert payload['check']['ok'] is True
    assert isinstance(payload['format']['command'], list)
    assert isinstance(payload['check']['command'], list)


def test_dev_test_text_output_has_stable_summary(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command(
        'dev',
        'test',
        'tests/cli/root/test_contract_cli.py',
        '--env=dev',
        '--keyword=test_root_help_shows_commands_without_completion_options',
        '--maxfail=1',
        '--quiet',
        '--output=text',
    )

    assert completed.returncode == SUCCESS
    assert completed.stdout.startswith('OK SUCCESS\n')
    assert 'ok: true\n' in completed.stdout
    assert 'env: dev\n' in completed.stdout
    assert 'keyword: test_root_help_shows_commands_without_completion_options\n' in completed.stdout
    assert 'maxfail: 1\n' in completed.stdout
    assert 'quiet: true\n' in completed.stdout
    assert 'targets:\n  - tests/cli/root/test_contract_cli.py\n' in completed.stdout
    assert 'test:\n  ok: true\n' in completed.stdout
    assert 'command: ' in completed.stdout
