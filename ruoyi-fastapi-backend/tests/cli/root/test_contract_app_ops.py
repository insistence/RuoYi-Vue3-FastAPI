import subprocess
from collections.abc import Callable

from cli.exit_codes import DEPENDENCY_ERROR, SUCCESS


def test_app_config_json_output_is_pure_json(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('app', 'config', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == 0
    assert completed.stderr == ''
    assert payload['ok'] is True
    assert payload['env'] == 'dev'
    assert isinstance(payload['config'], dict)
    assert '\u001b[' not in completed.stdout
    assert '✅' not in completed.stdout
    assert '❌' not in completed.stdout


def test_app_config_text_output_has_stable_section_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command('app', 'config', '--env=dev', '--output=text')

    assert completed.returncode == SUCCESS
    assert '\x1b[' not in completed.stdout
    assert '✅' not in completed.stdout
    assert completed.stdout.startswith('OK SUCCESS\n')
    assert 'env: dev\n' in completed.stdout
    assert 'application:\n' in completed.stdout
    assert 'database:\n' in completed.stdout
    assert 'redis:\n' in completed.stdout
    assert 'logging:\n' in completed.stdout
    assert 'transport_crypto:\n' in completed.stdout


def test_app_env_text_output_has_stable_section_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command('app', 'env', '--env=dev', '--output=text')

    assert completed.returncode == SUCCESS
    assert completed.stdout.startswith('OK SUCCESS\n')
    assert 'env: dev\n' in completed.stdout
    assert 'runtime:\n' in completed.stdout
    assert 'cli_env: dev\n' in completed.stdout
    assert 'config_env:' in completed.stdout
    assert 'app_env: dev\n' in completed.stdout
    assert 'env_file: .env.dev\n' in completed.stdout
    assert 'env_file_exists:' in completed.stdout
    assert 'backend_dir:' in completed.stdout
    assert 'python_executable:' in completed.stdout


def test_app_doctor_text_output_has_stable_check_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command('app', 'doctor', '--env=dev', '--output=text')

    assert completed.returncode in {SUCCESS, DEPENDENCY_ERROR}
    assert '\x1b[' not in completed.stdout
    assert '✅' not in completed.stdout
    assert completed.stdout.startswith(('OK SUCCESS\n', 'FAIL FAILED\n'))
    assert 'env: dev\n' in completed.stdout
    assert 'checks:\n' in completed.stdout
    assert 'database:' in completed.stdout
    assert 'redis:' in completed.stdout
    assert 'crypto:' in completed.stdout


def test_app_doctor_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
    assert_check_payload_contract: Callable[[dict, bool], None],
) -> None:
    completed = run_cli_command('app', 'doctor', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DEPENDENCY_ERROR}
    assert completed.stderr == ''
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    assert set(payload) == {'env', 'database', 'redis', 'crypto', 'ok'}
    assert_check_payload_contract(payload['database'], True)
    assert_check_payload_contract(payload['redis'], True)
    assert_check_payload_contract(payload['crypto'], False)


def test_app_env_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('app', 'env', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == SUCCESS
    assert payload['ok'] is True
    assert payload['env'] == 'dev'
    assert set(payload) == {'ok', 'env', 'runtime'}
    assert isinstance(payload['runtime'], dict)
    assert set(payload['runtime']) == {
        'cliEnv',
        'configEnv',
        'appEnv',
        'envFile',
        'envFilePath',
        'envFileExists',
        'backendDir',
        'pythonExecutable',
    }
    assert payload['runtime']['cliEnv'] == 'dev'
    assert payload['runtime']['appEnv'] == 'dev'
    assert payload['runtime']['envFile'] == '.env.dev'
    assert isinstance(payload['runtime']['envFileExists'], bool)


def test_app_routes_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('app', 'routes', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == 0
    assert payload['ok'] is True
    assert payload['env'] == 'dev'
    assert isinstance(payload['count'], int)
    assert payload['count'] > 0
    assert payload['groupedRoutes'] is None
    assert payload['filters'] == {
        'pathPrefix': '',
        'method': '',
        'groupBy': 'none',
        'includeHidden': False,
    }
    assert isinstance(payload['routes'], list)
    assert payload['routes']

    first_route = payload['routes'][0]
    assert set(first_route) == {
        'path',
        'methods',
        'name',
        'summary',
        'operationId',
        'tags',
        'includeInSchema',
    }
    assert isinstance(first_route['path'], str)
    assert isinstance(first_route['methods'], list)
    assert first_route['methods']
    assert all(isinstance(method, str) for method in first_route['methods'])
    assert isinstance(first_route['name'], str | None)
    assert isinstance(first_route['summary'], str | None)
    assert isinstance(first_route['operationId'], str | None)
    assert isinstance(first_route['tags'], list)
    assert all(isinstance(tag, str) for tag in first_route['tags'])
    assert isinstance(first_route['includeInSchema'], bool)


def test_server_info_text_output_has_stable_section_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command('ops', 'server-info', '--env=dev')

    assert completed.returncode == 0
    assert '\x1b[' not in completed.stdout
    assert '✅' not in completed.stdout
    assert completed.stdout.startswith('OK SUCCESS\n')
    assert 'host:\n' in completed.stdout
    assert 'cpu:\n' in completed.stdout
    assert 'memory:\n' in completed.stdout
    assert 'python:\n' in completed.stdout
    assert 'disks:' in completed.stdout


def test_ops_health_text_output_has_stable_check_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command('ops', 'health', '--env=dev', '--output=text')

    assert completed.returncode in {SUCCESS, DEPENDENCY_ERROR}
    assert '\x1b[' not in completed.stdout
    assert '✅' not in completed.stdout
    assert completed.stdout.startswith(('OK SUCCESS\n', 'FAIL FAILED\n'))
    assert 'env: dev\n' in completed.stdout
    assert 'checks:\n' in completed.stdout
    assert 'database:' in completed.stdout
    assert 'redis:' in completed.stdout


def test_ops_deps_text_output_has_stable_structure(
    run_text_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_text_cli_command('ops', 'deps', '--env=dev', '--output=text')

    assert completed.returncode in {SUCCESS, DEPENDENCY_ERROR}
    assert completed.stdout.startswith(('OK SUCCESS\n', 'FAIL FAILED\n'))
    assert 'message:' in completed.stdout
    assert 'include_dev: false\n' in completed.stdout
    assert 'missing_required:' in completed.stdout
    assert 'packages:\n' in completed.stdout
    assert 'python:' in completed.stdout
    assert 'fastapi:' in completed.stdout
    assert 'typer:' in completed.stdout


def test_ops_health_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
    assert_check_payload_contract: Callable[[dict, bool], None],
) -> None:
    completed = run_cli_command('ops', 'health', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DEPENDENCY_ERROR}
    assert completed.stderr == ''
    assert payload['env'] == 'dev'
    assert isinstance(payload['ok'], bool)
    assert set(payload) == {'env', 'database', 'redis', 'ok'}
    assert_check_payload_contract(payload['database'], True)
    assert_check_payload_contract(payload['redis'], True)


def test_ops_deps_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('ops', 'deps', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode in {SUCCESS, DEPENDENCY_ERROR}
    assert set(payload) == {'ok', 'message', 'missingRequired', 'includeDev', 'packages'}
    assert isinstance(payload['ok'], bool)
    assert isinstance(payload['message'], str)
    assert isinstance(payload['missingRequired'], list)
    assert payload['includeDev'] is False
    assert isinstance(payload['packages'], dict)
    assert 'python' in payload['packages']
    assert 'fastapi' in payload['packages']
    assert 'typer' in payload['packages']
    for package_payload in payload['packages'].values():
        assert isinstance(package_payload, dict)
        assert isinstance(package_payload.get('installed'), bool)
        assert isinstance(package_payload.get('version'), str)
        assert isinstance(package_payload.get('required'), bool)


def test_ops_server_info_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('ops', 'server-info', '--env=dev', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == 0
    assert payload['ok'] is True
    assert isinstance(payload['server'], dict)

    server = payload['server']
    assert set(server) == {'cpu', 'mem', 'sys', 'py', 'sysFiles'}

    cpu = server['cpu']
    assert set(cpu) == {'cpuNum', 'used', 'sys', 'free'}
    assert isinstance(cpu['cpuNum'], int)
    assert isinstance(cpu['used'], float | int | str)
    assert isinstance(cpu['sys'], float | int | str)
    assert isinstance(cpu['free'], float | int | str)

    memory = server['mem']
    assert set(memory) == {'total', 'used', 'free', 'usage'}
    assert isinstance(memory['total'], str)
    assert isinstance(memory['used'], str)
    assert isinstance(memory['free'], str)
    assert isinstance(memory['usage'], float | int)

    sys_info = server['sys']
    assert set(sys_info) == {'computerIp', 'computerName', 'osArch', 'osName', 'userDir'}
    assert all(isinstance(value, str) for value in sys_info.values())

    py_info = server['py']
    assert set(py_info) == {
        'name',
        'version',
        'startTime',
        'runTime',
        'home',
        'total',
        'used',
        'free',
        'usage',
    }
    assert isinstance(py_info['name'], str)
    assert isinstance(py_info['version'], str)
    assert isinstance(py_info['startTime'], str)
    assert isinstance(py_info['runTime'], str)
    assert isinstance(py_info['home'], str)
    assert isinstance(py_info['total'], str)
    assert isinstance(py_info['used'], str)
    assert isinstance(py_info['free'], str)
    assert isinstance(py_info['usage'], float | int)

    assert isinstance(server['sysFiles'], list)
    assert server['sysFiles']
    first_disk = server['sysFiles'][0]
    assert set(first_disk) == {'dirName', 'sysTypeName', 'typeName', 'total', 'used', 'free', 'usage'}
    assert all(isinstance(value, str) for value in first_disk.values())
