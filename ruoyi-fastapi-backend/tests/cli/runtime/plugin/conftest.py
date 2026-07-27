import sys
from pathlib import Path
from subprocess import CompletedProcess

from cli.runtime.plugin.service import CliPluginRuntimeService
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.validation.dependencies import (
    NpmDependencyInspector,
    PluginDependencyChecker,
    PythonDependencyInspector,
)

EXPECTED_FRONTEND_BUILD_TIMEOUT = 300


class FakeRuntimeEnvironment:
    """
    测试用插件 CLI 运行时环境服务。
    """

    def __init__(self, backend_dir: Path, frontend_dir: Path | None = None) -> None:
        """初始化测试用插件 CLI 运行时环境服务。"""
        self.backend_dir = backend_dir
        self.frontend_dir = frontend_dir or Path(
            PluginRuntimeEnvironmentService(backend_root=backend_dir).get_frontend_dir()
        )

    def get_backend_dir(self) -> str:
        """获取后端项目根目录。"""
        return str(self.backend_dir)

    def get_backend_plugins_dir(self) -> str:
        """获取后端插件根目录。"""
        return str(self.backend_dir / 'plugins')

    def get_frontend_dir(self) -> str:
        """获取前端项目根目录。"""
        return str(self.frontend_dir)

    def get_frontend_plugins_dir(self) -> str:
        """获取前端插件根目录。"""
        return str(self.frontend_dir / 'plugins')

    @staticmethod
    def get_frontend_mode() -> str:
        """获取测试用前端运行模式。"""
        return 'dev'

    @staticmethod
    def get_backend_runtime_mode() -> str:
        """获取测试用后端运行模式。"""
        return 'dev'

    @staticmethod
    def get_python_executable() -> str:
        """获取测试用 Python 解释器。"""
        return sys.executable


class FakePluginRuntimeGateway:
    """
    测试用插件 CLI 运行时适配器。
    """

    def __init__(self) -> None:
        """初始化测试用插件 CLI 运行时适配器。"""
        self.completed_process = CompletedProcess(args=[], returncode=0, stdout='1 passed\n', stderr='')
        self.commands: list[tuple[list[str], str, int | None]] = []

    def run_command(
        self,
        command: list[str],
        workdir: str,
        *,
        timeout: int | None = None,
    ) -> CompletedProcess[str]:
        """记录测试用系统命令。"""
        self.commands.append((command, workdir, timeout))
        return self.completed_process


def build_runtime(backend_root: Path, frontend_root: Path | None = None) -> CliPluginRuntimeService:
    """构建测试用插件 CLI 运行时服务。"""
    return CliPluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root, frontend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
    )


def build_runtime_with_gateway(
    backend_root: Path,
    gateway: FakePluginRuntimeGateway,
    frontend_root: Path | None = None,
) -> CliPluginRuntimeService:
    """构建带测试运行时适配器的插件 CLI 运行时服务。"""
    return CliPluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root, frontend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
        management_gateway=gateway,
        model_gateway=gateway,
        command_gateway=gateway,
    )
