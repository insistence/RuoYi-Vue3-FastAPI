import subprocess

import pytest
from pytest import MonkeyPatch

from cli import bootstrap
from cli.bootstrap import AppBootstrapService
from cli.runtime.base import RuntimeEnvironmentService

CHILD_EXIT_CODE = 7
INTERRUPT_EXIT_CODE = 130


class FakeRuntimeEnvironment(RuntimeEnvironmentService):
    @staticmethod
    def get_backend_dir() -> str:
        return 'C:\\project\\ruoyi-fastapi-backend'

    @staticmethod
    def get_python_executable() -> str:
        return 'C:\\Python\\python.exe'


def test_exec_app_run_command_waits_for_child_process_on_windows(monkeypatch: MonkeyPatch) -> None:
    service = AppBootstrapService(runtime_environment=FakeRuntimeEnvironment())
    expected_command = [
        'C:\\Python\\python.exe',
        'C:\\project\\ruoyi-fastapi-backend\\app.py',
        '--env',
        'dev',
    ]
    captured: dict[str, object] = {}

    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        captured['command'] = command
        captured['check'] = check
        return subprocess.CompletedProcess(command, CHILD_EXIT_CODE)

    monkeypatch.setattr(bootstrap, '_IS_WINDOWS', True)
    monkeypatch.setattr(bootstrap.subprocess, 'run', fake_run)

    with pytest.raises(SystemExit) as exit_info:
        service.exec_app_run_command('dev')

    assert exit_info.value.code == CHILD_EXIT_CODE
    assert captured == {'command': expected_command, 'check': False}


def test_exec_app_run_command_returns_interrupt_exit_code_on_windows(monkeypatch: MonkeyPatch) -> None:
    service = AppBootstrapService(runtime_environment=FakeRuntimeEnvironment())

    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        raise KeyboardInterrupt

    monkeypatch.setattr(bootstrap, '_IS_WINDOWS', True)
    monkeypatch.setattr(bootstrap.subprocess, 'run', fake_run)

    with pytest.raises(SystemExit) as exit_info:
        service.exec_app_run_command('dev')

    assert exit_info.value.code == INTERRUPT_EXIT_CODE


def test_exec_app_run_command_uses_exec_on_posix(monkeypatch: MonkeyPatch) -> None:
    service = AppBootstrapService(runtime_environment=FakeRuntimeEnvironment())
    captured: dict[str, object] = {}

    def fake_execvp(executable: str, command: list[str]) -> None:
        captured['executable'] = executable
        captured['command'] = command

    monkeypatch.setattr(bootstrap, '_IS_WINDOWS', False)
    monkeypatch.setattr(bootstrap.os, 'execvp', fake_execvp)

    service.exec_app_run_command('prod')

    assert captured == {
        'executable': 'C:\\Python\\python.exe',
        'command': [
            'C:\\Python\\python.exe',
            'C:\\project\\ruoyi-fastapi-backend\\app.py',
            '--env',
            'prod',
        ],
    }
