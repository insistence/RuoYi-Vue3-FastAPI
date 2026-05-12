import os

from cli.runtime import RUNTIME_ENVIRONMENT, RuntimeEnvironmentService


class AppBootstrapService:
    """
    应用引导服务。

    该服务负责解析应用原始入口路径、构建启动命令，并以 `exec`
    方式将当前 CLI 进程切换为 FastAPI 应用入口进程。
    """

    def __init__(self, *, runtime_environment: RuntimeEnvironmentService | None = None) -> None:
        """
        初始化应用引导服务。

        :param runtime_environment: 运行时环境服务
        :return: None
        """
        self.runtime_environment = runtime_environment or RUNTIME_ENVIRONMENT

    def get_app_entry_path(self) -> str:
        """
        获取应用启动入口路径。

        :return: 应用启动入口绝对路径
        """
        return os.path.join(self.runtime_environment.get_backend_dir(), 'app.py')

    def build_app_run_command(self, env: str) -> list[str]:
        """
        构建应用启动命令。

        :param env: 运行环境
        :return: 应用启动命令参数列表
        """
        return [
            self.runtime_environment.get_python_executable(),
            self.get_app_entry_path(),
            '--env',
            env,
        ]

    def exec_app_run_command(self, env: str) -> None:
        """
        以应用原始入口进程启动当前 FastAPI 应用。

        :param env: 运行环境
        :return: None
        """
        command = self.build_app_run_command(env)
        os.execvp(command[0], command)


APP_BOOTSTRAP = AppBootstrapService()
