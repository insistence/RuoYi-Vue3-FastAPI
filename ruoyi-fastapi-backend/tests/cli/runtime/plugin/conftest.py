# ruff: noqa: F401

import sys
from pathlib import Path
from subprocess import CompletedProcess

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))
for module_name in list(sys.modules):
    if module_name == 'cli' or module_name.startswith('cli.'):
        sys.modules.pop(module_name)

from cli.exit_codes import RUNTIME_ERROR  # noqa: E402
from cli.runtime.plugin.scaffold import PluginScaffoldBuilder  # noqa: E402
from cli.runtime.plugin.service import CliPluginRuntimeService  # noqa: E402
from cli.runtime.plugin.support import PluginTestPayloadBuilder, PluginTestTarget  # noqa: E402
from plugins.core.environment import PluginRuntimeEnvironmentService  # noqa: E402
from plugins.core.validation.dependencies import (  # noqa: E402
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
        """
        初始化测试用插件 CLI 运行时环境服务。

        :param backend_dir: 后端项目根目录
        :param frontend_dir: 前端项目根目录
        :return: None
        """
        self.backend_dir = backend_dir
        self.frontend_dir = frontend_dir or Path(
            PluginRuntimeEnvironmentService(backend_root=backend_dir).get_frontend_dir()
        )

    def get_backend_dir(self) -> str:
        """
        获取后端项目根目录。

        :return: 后端项目根目录
        """
        return str(self.backend_dir)

    def get_backend_plugins_dir(self) -> str:
        """
        获取后端插件根目录。

        :return: 后端插件根目录
        """
        return str(self.backend_dir / 'plugins')

    def get_frontend_dir(self) -> str:
        """
        获取前端项目根目录。

        :return: 前端项目根目录
        """
        return str(self.frontend_dir)

    def get_frontend_plugins_dir(self) -> str:
        """
        获取前端插件根目录。

        :return: 前端插件根目录
        """
        return str(self.frontend_dir / 'plugins')

    @staticmethod
    def get_frontend_mode() -> str:
        """
        获取测试用前端运行模式。

        :return: 前端运行模式
        """
        return 'dev'

    @staticmethod
    def get_backend_runtime_mode() -> str:
        """
        获取测试用后端运行模式。

        :return: 后端运行模式
        """
        return 'dev'

    @staticmethod
    def get_python_executable() -> str:
        """
        获取测试用 Python 解释器。

        :return: Python 解释器路径
        """
        return sys.executable


class FakePluginRuntimeGateway:
    """
    测试用插件 CLI 运行时适配器。
    """

    def __init__(self) -> None:
        """
        初始化测试用插件 CLI 运行时适配器。

        :return: None
        """
        self.completed_process = CompletedProcess(args=[], returncode=0, stdout='1 passed\n', stderr='')
        self.commands: list[tuple[list[str], str, int | None]] = []

    def run_command(
        self,
        command: list[str],
        workdir: str,
        *,
        timeout: int | None = None,
    ) -> CompletedProcess[str]:
        """
        记录测试用系统命令。

        :param command: 命令参数列表
        :param workdir: 命令工作目录
        :param timeout: 命令超时时间
        :return: 命令执行结果
        """
        self.commands.append((command, workdir, timeout))
        return self.completed_process


def build_runtime(backend_root: Path, frontend_root: Path | None = None) -> CliPluginRuntimeService:
    """
    构建测试用插件 CLI 运行时服务。

    :param backend_root: 后端项目根目录
    :param frontend_root: 前端项目根目录
    :return: 插件 CLI 运行时服务
    """
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
    """
    构建带测试运行时适配器的插件 CLI 运行时服务。

    :param backend_root: 后端项目根目录
    :param gateway: 测试运行时适配器
    :param frontend_root: 前端项目根目录
    :return: 插件 CLI 运行时服务
    """
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
