import subprocess
from typing import Any

from cli.exit_codes import RUNTIME_ERROR
from cli.runtime.base import RuntimeEnvironmentService


class DevelopmentProcessGateway:
    """
    开发子进程执行网关。

    该对象负责统一执行开发工具子进程命令，
    避免支持对象直接依赖 `subprocess` 细节。

    :param runtime_environment: 运行时环境服务
    """

    def __init__(self, runtime_environment: RuntimeEnvironmentService) -> None:
        """
        初始化开发子进程执行网关。

        :param runtime_environment: 运行时环境服务
        :return: None
        """
        self.runtime_environment = runtime_environment

    def run_command(self, command: list[str]) -> dict[str, Any]:
        """
        执行子进程命令并返回统一结果。

        :param command: 待执行命令
        :return: 命令执行结果
        """
        try:
            completed = subprocess.run(
                command,
                cwd=self.runtime_environment.get_backend_dir(),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            return {
                'ok': False,
                'message': '开发命令执行失败',
                'error': str(exc),
                'command': command,
                'exit_code': RUNTIME_ERROR,
            }

        payload: dict[str, Any] = {
            'ok': completed.returncode == 0,
            'command': command,
            'returnCode': completed.returncode,
        }
        if completed.stdout.strip():
            payload['stdout'] = completed.stdout.strip()
        if completed.stderr.strip():
            payload['stderr'] = completed.stderr.strip()
        return payload
