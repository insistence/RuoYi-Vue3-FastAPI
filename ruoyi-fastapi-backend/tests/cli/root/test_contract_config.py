import subprocess
from collections.abc import Callable

from cli.exit_codes import DATABASE_ERROR, REDIS_ERROR, RUNTIME_ERROR, SUCCESS


def test_config_doctor_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('config', 'doctor', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, REDIS_ERROR, DATABASE_ERROR, RUNTIME_ERROR}
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    if 'error' in payload:
        assert isinstance(payload['message'], str)
        assert isinstance(payload['error'], str)
        return

    assert set(payload) == {
        'ok',
        'message',
        'databaseCount',
        'cacheCount',
        'missingInCacheCount',
        'orphanInCacheCount',
        'mismatchCount',
        'sampleLimit',
        'missingInCache',
        'orphanInCache',
        'mismatchKeys',
        'env',
    }
    assert isinstance(payload['databaseCount'], int)
    assert isinstance(payload['cacheCount'], int)
    assert isinstance(payload['missingInCache'], list)
    assert isinstance(payload['orphanInCache'], list)
    assert isinstance(payload['mismatchKeys'], list)
