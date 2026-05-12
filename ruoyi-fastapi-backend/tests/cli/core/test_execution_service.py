import importlib
import sys
from pathlib import Path

from cli.exit_codes import RUNTIME_ERROR

BACKEND_DIR = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(BACKEND_DIR))
sys.modules.pop('cli.core.execution', None)
sys.modules.pop('cli', None)

cli_execution = importlib.import_module('cli.core.execution')
EXPLICIT_EXIT_CODE = 23
DEFAULT_EXIT_CODE = 7


def test_build_result_does_not_mutate_payload_and_removes_exit_code_from_result_data() -> None:
    """
    校验结果翻译不会修改调用方 payload，且会从结果数据中移除 exit_code 字段。

    :return: None
    """
    payload = {'ok': True, 'message': 'done', 'exit_code': EXPLICIT_EXIT_CODE}

    result = cli_execution.CliExecutionService.build_result(payload)

    assert result.exit_code == EXPLICIT_EXIT_CODE
    assert result.data == {'ok': True, 'message': 'done'}
    assert payload == {'ok': True, 'message': 'done', 'exit_code': EXPLICIT_EXIT_CODE}


def test_build_result_uses_runtime_error_when_failed_payload_has_no_explicit_exit_code() -> None:
    """
    校验失败 payload 未显式提供退出码时，会回退到统一运行时错误码。

    :return: None
    """
    payload = {'ok': False, 'message': 'failed'}

    result = cli_execution.CliExecutionService.build_result(payload)

    assert result.exit_code == RUNTIME_ERROR
    assert result.data == {'ok': False, 'message': 'failed'}
    assert payload == {'ok': False, 'message': 'failed'}


def test_build_result_uses_default_exit_code_without_mutating_payload() -> None:
    """
    校验显式默认退出码会参与结果翻译，且不会修改原始 payload。

    :return: None
    """
    payload = {'ok': True, 'message': 'warn'}

    result = cli_execution.CliExecutionService.build_result(payload, default_exit_code=DEFAULT_EXIT_CODE)

    assert result.exit_code == DEFAULT_EXIT_CODE
    assert result.data == {'ok': True, 'message': 'warn'}
    assert payload == {'ok': True, 'message': 'warn'}


def test_build_result_uses_runtime_error_when_failed_payload_keeps_default_zero() -> None:
    """
    校验失败 payload 在未显式提供退出码且默认退出码为 0 时，会回退到统一运行时错误码。

    :return: None
    """
    payload = {'ok': False, 'message': 'failed'}

    result = cli_execution.CliExecutionService.build_result(payload, default_exit_code=0)

    assert result.exit_code == RUNTIME_ERROR
    assert result.data == {'ok': False, 'message': 'failed'}
