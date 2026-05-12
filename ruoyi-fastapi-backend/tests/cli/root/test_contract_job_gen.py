import subprocess
from collections.abc import Callable

from cli.exit_codes import ARGUMENT_ERROR, DATABASE_ERROR, GUARD_REJECTED, RUNTIME_ERROR, SUCCESS

GEN_TEST_TABLE_NAME = 'demo_table'
GEN_CREATE_SQL = 'CREATE TABLE demo_cli_test (id bigint);'
MISSING_JOB_ID = 999999999
MISSING_GEN_TABLE_ID = 999999999


def test_job_detail_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    list_completed = run_cli_command('job', 'list', '--env=dev', '--output=json')
    list_payload = parse_json_stdout(list_completed)
    job_id = MISSING_JOB_ID
    if list_payload.get('ok') and isinstance(list_payload.get('items'), list) and list_payload['items']:
        first_job = list_payload['items'][0]
        if isinstance(first_job, dict) and isinstance(first_job.get('jobId'), int):
            job_id = first_job['jobId']

    completed = run_cli_command('job', 'detail', str(job_id), '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DATABASE_ERROR, RUNTIME_ERROR}
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    if payload['ok'] is False:
        assert set(payload) == {'ok', 'message', 'jobId'}
        assert payload['jobId'] == job_id
        return

    assert set(payload) == {'ok', 'job'}
    assert isinstance(payload['job'], dict)
    assert payload['job']['jobId'] == job_id
    assert isinstance(payload['job'].get('jobName'), str)
    assert isinstance(payload['job'].get('invokeTarget'), str)


def test_job_logs_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('job', 'logs', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DATABASE_ERROR}
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    assert set(payload) == {'ok', 'filters', 'count', 'items'}
    assert isinstance(payload['filters'], dict)
    assert isinstance(payload['count'], int)
    assert isinstance(payload['items'], list)
    if payload['items']:
        first_item = payload['items'][0]
        assert isinstance(first_item, dict)
        assert isinstance(first_item.get('jobLogId'), int)
        assert isinstance(first_item.get('jobName'), str | None)
        assert isinstance(first_item.get('jobMessage'), str | None)


def test_gen_list_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('gen', 'list', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DATABASE_ERROR}
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    assert set(payload) == {'ok', 'filters', 'count', 'items', 'env'}
    assert isinstance(payload['filters'], dict)
    assert isinstance(payload['count'], int)
    assert isinstance(payload['items'], list)
    if payload['items']:
        first_item = payload['items'][0]
        assert isinstance(first_item, dict)
        assert isinstance(first_item.get('tableId'), int)
        assert isinstance(first_item.get('tableName'), str)


def test_gen_db_list_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('gen', 'db-list', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DATABASE_ERROR}
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    assert set(payload) == {'ok', 'filters', 'count', 'items', 'env'}
    assert isinstance(payload['filters'], dict)
    assert isinstance(payload['count'], int)
    assert isinstance(payload['items'], list)
    if payload['items']:
        first_item = payload['items'][0]
        assert isinstance(first_item, dict)
        assert isinstance(first_item.get('tableName'), str)


def test_gen_detail_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    list_completed = run_cli_command('gen', 'list', '--env=dev', '--output=json')
    list_payload = parse_json_stdout(list_completed)
    table_id = MISSING_GEN_TABLE_ID
    if list_payload.get('ok') and isinstance(list_payload.get('items'), list) and list_payload['items']:
        first_item = list_payload['items'][0]
        if isinstance(first_item, dict) and isinstance(first_item.get('tableId'), int):
            table_id = first_item['tableId']

    completed = run_cli_command('gen', 'detail', str(table_id), '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DATABASE_ERROR, RUNTIME_ERROR}
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    if payload['ok'] is False:
        assert set(payload) == {'ok', 'message', 'tableId', 'env'}
        assert payload['tableId'] == table_id
        return

    assert set(payload) == {'ok', 'tableId', 'tableName', 'columnCount', 'tableCount', 'detail', 'env'}
    assert payload['tableId'] == table_id
    assert isinstance(payload['tableName'], str)
    assert isinstance(payload['columnCount'], int)
    assert isinstance(payload['tableCount'], int)
    assert isinstance(payload['detail'], dict)
    assert isinstance(payload['detail'].get('info'), dict)
    assert isinstance(payload['detail'].get('rows'), list)
    assert isinstance(payload['detail'].get('tables'), list)


def test_gen_sync_db_is_rejected_without_yes_in_non_interactive_mode(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('gen', 'sync-db', 'demo_table', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == GUARD_REJECTED
    assert payload['ok'] is False
    assert payload['message'] == '已取消危险命令执行：gen sync-db'
    assert '--yes' in payload['hint']


def test_gen_export_dry_run_text_output_has_stable_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command(
        'gen',
        'export',
        GEN_TEST_TABLE_NAME,
        '--env=dev',
        '--dry-run',
        '--yes',
        '--output=text',
    )

    assert completed.returncode == SUCCESS
    assert completed.stdout.startswith('OK SUCCESS\n')
    assert 'env: dev\n' in completed.stdout
    assert 'mode: zip\n' in completed.stdout
    assert 'dry_run: true\n' in completed.stdout
    assert 'message: 代码导出演练完成，未执行实际导出\n' in completed.stdout
    assert 'table_names:\n' in completed.stdout
    assert f'  - {GEN_TEST_TABLE_NAME}\n' in completed.stdout
    assert 'output_file:' in completed.stdout
    assert f'gen_code_{GEN_TEST_TABLE_NAME}.zip' in completed.stdout


def test_gen_export_dry_run_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'gen',
        'export',
        GEN_TEST_TABLE_NAME,
        '--env=dev',
        '--dry-run',
        '--yes',
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == SUCCESS
    assert payload['ok'] is True
    assert payload['env'] == 'dev'
    assert payload['dryRun'] is True
    assert payload['mode'] == 'zip'
    assert payload['message'] == '代码导出演练完成，未执行实际导出'
    assert payload['tableNames'] == [GEN_TEST_TABLE_NAME]
    assert isinstance(payload['outputFile'], str)
    assert payload['outputFile'].endswith(f'gen_code_{GEN_TEST_TABLE_NAME}.zip')


def test_gen_create_table_dry_run_text_output_has_stable_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command(
        'gen',
        'create-table',
        '--env=dev',
        '--dry-run',
        '--yes',
        '--sql',
        GEN_CREATE_SQL,
        '--output=text',
    )

    assert completed.returncode == SUCCESS
    assert completed.stdout.startswith('OK SUCCESS\n')
    assert 'env: dev\n' in completed.stdout
    assert 'message: 建表语句演练完成，未执行实际建表\n' in completed.stdout
    assert 'dry_run: true\n' in completed.stdout
    assert 'statement_count: 1\n' in completed.stdout
    assert 'table_names:\n' in completed.stdout
    assert '  - demo_cli_test\n' in completed.stdout
    assert f'sql: {GEN_CREATE_SQL}\n' in completed.stdout


def test_gen_create_table_dry_run_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'gen',
        'create-table',
        '--env=dev',
        '--dry-run',
        '--yes',
        '--sql',
        GEN_CREATE_SQL,
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == SUCCESS
    assert payload['ok'] is True
    assert payload['env'] == 'dev'
    assert payload['dryRun'] is True
    assert payload['message'] == '建表语句演练完成，未执行实际建表'
    assert payload['statementCount'] == 1
    assert payload['tableNames'] == ['demo_cli_test']
    assert payload['sql'] == GEN_CREATE_SQL


def test_gen_create_table_rejects_non_create_sql_in_text_output(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command(
        'gen',
        'create-table',
        '--env=dev',
        '--dry-run',
        '--yes',
        '--sql',
        'DROP TABLE demo_cli_test;',
        '--output=text',
    )

    assert completed.returncode == ARGUMENT_ERROR
    assert completed.stdout == (
        'FAIL FAILED\nmessage: 创建表结构失败\nerror: 建表语句不合法，仅允许 CREATE TABLE 语句\nenv: dev\n'
    )


def test_gen_create_table_rejects_non_create_sql_in_json_output(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'gen',
        'create-table',
        '--env=dev',
        '--dry-run',
        '--yes',
        '--sql',
        'DROP TABLE demo_cli_test;',
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == ARGUMENT_ERROR
    assert payload == {
        'ok': False,
        'message': '创建表结构失败',
        'error': '建表语句不合法，仅允许 CREATE TABLE 语句',
        'env': 'dev',
    }


def test_gen_create_table_rejects_conflicting_sql_inputs_in_text_output(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command(
        'gen',
        'create-table',
        '--env=dev',
        '--dry-run',
        '--yes',
        '--sql',
        GEN_CREATE_SQL,
        '--sql-file',
        'fake.sql',
        '--output=text',
    )

    assert completed.returncode == ARGUMENT_ERROR
    assert completed.stdout == (
        'FAIL FAILED\nmessage: 创建表结构失败\nerror: 必须且只能传入 --sql 或 --sql-file 其中一种方式\nenv: dev\n'
    )


def test_gen_create_table_rejects_conflicting_sql_inputs_in_json_output(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command(
        'gen',
        'create-table',
        '--env=dev',
        '--dry-run',
        '--yes',
        '--sql',
        GEN_CREATE_SQL,
        '--sql-file',
        'fake.sql',
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == ARGUMENT_ERROR
    assert payload == {
        'ok': False,
        'message': '创建表结构失败',
        'error': '必须且只能传入 --sql 或 --sql-file 其中一种方式',
        'env': 'dev',
    }
