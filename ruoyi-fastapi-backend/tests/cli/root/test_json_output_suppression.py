import subprocess
from collections.abc import Callable


def test_config_doctor_json_stdout_is_not_polluted_by_sqlalchemy_logs(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> None:
    """
    校验 JSON 输出模式下不会混入 SQLAlchemy engine 日志。

    :param run_cli_command: CLI 子进程执行器
    :return: None
    """
    completed = run_cli_command('config', 'doctor', '--env=dev', '--output=json')

    assert 'sqlalchemy.engine.Engine' not in completed.stdout
    assert 'SELECT DATABASE()' not in completed.stdout
    assert completed.stdout.lstrip().startswith('{')
