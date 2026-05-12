import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from pytest import MonkeyPatch

BACKEND_DIR = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(BACKEND_DIR))
sys.modules.pop('cli.utils', None)
cli_utils = importlib.import_module('cli.utils')


def test_run_nested_cli_command_extracts_json_from_noisy_stdout(monkeypatch: MonkeyPatch) -> None:
    """
    校验内部 CLI 调用可从带噪声的标准输出中提取 JSON 负载。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    def _fake_subprocess_run(*args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        return SimpleNamespace(
            stdout='debug line before json\n{"ok": true, "message": "success"}\ndebug line after json\n',
            stderr='',
            returncode=0,
        )

    monkeypatch.setattr(cli_utils.subprocess, 'run', _fake_subprocess_run)

    result = cli_utils.NESTED_CLI_SUPPORT.run('app', 'env', '--output=json', parse_json=True)

    assert result.payload == {'ok': True, 'message': 'success'}


def test_run_nested_cli_command_extracts_first_json_object_from_mixed_stdout(
    monkeypatch: MonkeyPatch,
) -> None:
    """
    校验内部 CLI 调用可从混杂文本中提取首个合法 JSON 对象。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    def _fake_subprocess_run(*args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        return SimpleNamespace(
            stdout='preface\ntrace {not-json}\n{"ok": true, "message": "job done"}\ntrailer\n',
            stderr='',
            returncode=0,
        )

    monkeypatch.setattr(cli_utils.subprocess, 'run', _fake_subprocess_run)

    result = cli_utils.NESTED_CLI_SUPPORT.run('job', 'run-once', '1', '--output=json', parse_json=True)

    assert result.payload == {'ok': True, 'message': 'job done'}


def test_run_nested_cli_command_falls_back_to_text_payload_when_json_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    """
    校验内部 CLI 未返回 JSON 时会回退为文本结果负载。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    def _fake_subprocess_run(*args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        return SimpleNamespace(
            stdout='任务已提交到调度器',
            stderr='',
            returncode=0,
        )

    monkeypatch.setattr(cli_utils.subprocess, 'run', _fake_subprocess_run)

    result = cli_utils.NESTED_CLI_SUPPORT.run('job', 'run-once', '1', '--output=json', parse_json=True)

    assert result.payload is not None
    assert result.payload.get('ok') is True
    assert result.payload.get('message') == '任务已提交到调度器'
    assert result.payload.get('fallback') == 'non_json_output'


def test_run_nested_cli_command_uses_backend_dir_and_pythonpath(monkeypatch: MonkeyPatch) -> None:
    """
    校验内部 CLI 调用会固定后端工作目录并注入项目路径。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    recorded_kwargs: dict[str, object] = {}

    def _fake_subprocess_run(*args: object, **kwargs: object) -> SimpleNamespace:
        del args
        recorded_kwargs.update(kwargs)
        return SimpleNamespace(stdout='{}', stderr='', returncode=0)

    monkeypatch.setattr(cli_utils.subprocess, 'run', _fake_subprocess_run)

    result = cli_utils.NESTED_CLI_SUPPORT.run('app', 'env', parse_json=False)

    assert result.returncode == 0
    assert recorded_kwargs['cwd'] == str(BACKEND_DIR)
    process_env = recorded_kwargs['env']
    assert isinstance(process_env, dict)
    assert str(BACKEND_DIR) in process_env.get('PYTHONPATH', '')


def test_run_nested_cli_command_live_uses_backend_dir_without_capturing_output(monkeypatch: MonkeyPatch) -> None:
    """
    校验交互式内部 CLI 调用会复用后端工作目录并直接占用当前终端。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    recorded_kwargs: dict[str, object] = {}
    recorded_args: tuple[object, ...] = ()

    def _fake_subprocess_run(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal recorded_args
        recorded_args = args
        recorded_kwargs.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli_utils.subprocess, 'run', _fake_subprocess_run)

    completed = cli_utils.NESTED_CLI_SUPPORT.run_live('wizard', 'cache-clear', '--output=text')

    assert completed.returncode == 0
    assert recorded_args
    assert recorded_kwargs['cwd'] == str(BACKEND_DIR)
    process_env = recorded_kwargs['env']
    assert isinstance(process_env, dict)
    assert str(BACKEND_DIR) in process_env.get('PYTHONPATH', '')
    assert 'capture_output' not in recorded_kwargs
