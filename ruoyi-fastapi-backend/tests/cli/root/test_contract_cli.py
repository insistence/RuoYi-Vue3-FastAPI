import subprocess
from collections.abc import Callable
from pathlib import Path

from cli.exit_codes import SUCCESS


def test_root_help_shows_commands_without_completion_options(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_cli_command('--help')

    assert completed.returncode == 0
    assert 'Usage: ruoyi [OPTIONS] COMMAND [ARGS]...' in completed.stdout
    assert 'app' in completed.stdout
    assert 'db' in completed.stdout
    assert 'completion' in completed.stdout
    assert 'wizard' in completed.stdout
    assert 'tui' in completed.stdout
    assert completed.stdout.index('wizard') < completed.stdout.index('tui')
    assert '--install-completion' not in completed.stdout
    assert '--show-completion' not in completed.stdout


def test_completion_show_bash_outputs_completion_script(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_cli_command('completion', 'show', 'bash')

    assert completed.returncode == SUCCESS
    assert completed.stderr == ''
    assert '_RUOYI_COMPLETE=bash_complete' in completed.stdout
    assert '_ruoyi_completion()' in completed.stdout
    assert 'if command -v compopt >/dev/null 2>&1; then' in completed.stdout
    assert 'if complete -o nosort -F _ruoyi_completion ruoyi 2>/dev/null; then' in completed.stdout
    assert 'complete -F _ruoyi_completion ruoyi' in completed.stdout


def test_completion_show_powershell_outputs_completion_script(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_cli_command('completion', 'show', 'powershell')

    assert completed.returncode == SUCCESS
    assert completed.stderr == ''
    assert 'Register-ArgumentCompleter -Native -CommandName ruoyi' in completed.stdout
    assert '$env:_RUOYI_COMPLETE = "powershell_complete"' in completed.stdout


def test_bash_completion_protocol_returns_candidates_without_not_supported_error(
    run_cli_completion_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_cli_completion_command(comp_words='ruoyi comp', comp_cword=1)

    assert completed.returncode == SUCCESS
    assert 'plain,completion' in completed.stdout
    assert 'not supported' not in completed.stdout.lower()
    assert completed.stderr == ''


def test_powershell_completion_protocol_returns_candidates_without_not_supported_error(
    run_cli_completion_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_cli_completion_command(
        comp_words='ruoyi comp',
        comp_cword='comp',
        instruction='powershell_complete',
    )

    assert completed.returncode == SUCCESS
    assert 'completion' in completed.stdout
    assert 'not supported' not in completed.stdout.lower()
    assert completed.stderr == ''


def test_completion_doctor_json_output_has_stable_contract(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    completed = run_cli_command('completion', 'doctor', '--output=json')
    payload = parse_json_stdout(completed)

    assert completed.returncode == SUCCESS
    assert payload['ok'] is True
    assert payload['message'] == 'completion 诊断信息已生成'
    assert set(payload) == {
        'ok',
        'message',
        'activeShell',
        'projectDir',
        'envChoices',
        'completeEnvVar',
        'recommendedInstallCommand',
        'shells',
    }
    assert isinstance(payload['envChoices'], list)
    assert payload['completeEnvVar'] == '_RUOYI_COMPLETE'
    assert isinstance(payload['shells'], dict)
    assert set(payload['shells']) == {'bash', 'zsh', 'fish', 'powershell'}
    assert payload['shells']['bash']['supported'] is True
    assert payload['shells']['fish']['autoDiscovery'] is True
    assert payload['shells']['powershell']['supported'] is True
    assert isinstance(payload['shells']['bash']['sourceCommand'], str)
    assert isinstance(payload['shells']['bash']['recommendedInstallCommand'], str)
    assert isinstance(payload['shells']['powershell']['sourceCommand'], str)
    assert isinstance(payload['shells']['powershell']['recommendedInstallCommand'], str)


def test_completion_install_json_output_has_stable_contract(
    tmp_path: Path,
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    target_file = tmp_path / 'ruoyi.bash'
    rc_file = tmp_path / '.bashrc'
    completed = run_cli_command(
        'completion',
        'install',
        '--shell=bash',
        '--target-file',
        str(target_file),
        '--activate',
        '--rc-file',
        str(rc_file),
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == SUCCESS
    assert payload['ok'] is True
    assert set(payload) == {
        'ok',
        'message',
        'shell',
        'detectedShell',
        'targetFile',
        'activated',
        'activateRequested',
        'rcFile',
        'rcFileUpdated',
        'sourceCommand',
        'autoDiscovery',
        'activationRequired',
        'nextStep',
        'completeEnvVar',
    }
    assert payload['shell'] == 'bash'
    assert payload['targetFile'] == str(target_file.resolve())
    assert payload['activated'] is True
    assert payload['activateRequested'] is True
    assert payload['rcFile'] == str(rc_file.resolve())
    assert payload['rcFileUpdated'] is True
    assert payload['autoDiscovery'] is False
    assert payload['activationRequired'] is True
    assert isinstance(payload['nextStep'], str)
    assert target_file.exists()
    assert rc_file.exists()
    assert '_RUOYI_COMPLETE=bash_complete' in target_file.read_text(encoding='utf-8')
    assert payload['sourceCommand'] in rc_file.read_text(encoding='utf-8')


def test_completion_install_powershell_json_output_has_stable_contract(
    tmp_path: Path,
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    parse_json_stdout: Callable[[subprocess.CompletedProcess[str]], dict],
) -> None:
    target_file = tmp_path / 'ruoyi.ps1'
    rc_file = tmp_path / 'Microsoft.PowerShell_profile.ps1'
    completed = run_cli_command(
        'completion',
        'install',
        '--shell=powershell',
        '--target-file',
        str(target_file),
        '--activate',
        '--rc-file',
        str(rc_file),
        '--output=json',
    )
    payload = parse_json_stdout(completed)

    assert completed.returncode == SUCCESS
    assert payload['ok'] is True
    assert payload['shell'] == 'powershell'
    assert payload['targetFile'] == str(target_file.resolve())
    assert payload['activated'] is True
    assert payload['activateRequested'] is True
    assert payload['rcFile'] == str(rc_file.resolve())
    assert payload['rcFileUpdated'] is True
    assert payload['autoDiscovery'] is False
    assert payload['activationRequired'] is True
    assert payload['sourceCommand'] == f'. "{target_file.resolve()}"'
    assert target_file.exists()
    assert rc_file.exists()
    assert 'Register-ArgumentCompleter -Native -CommandName ruoyi' in target_file.read_text(encoding='utf-8')
    assert payload['sourceCommand'] in rc_file.read_text(encoding='utf-8')


def test_app_run_help_only_exposes_env_option(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    completed = run_cli_command('app', 'run', '--help')

    assert completed.returncode == 0
    assert 'Usage: ruoyi app run [OPTIONS]' in completed.stdout
    assert '--env' in completed.stdout
    assert '--output' not in completed.stdout
