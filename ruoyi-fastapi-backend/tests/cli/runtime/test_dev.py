from cli.exit_codes import DEPENDENCY_ERROR
from cli.runtime.base import RuntimeEnvironmentService
from cli.runtime.dev import DevelopmentRuntimeService
from cli.runtime.dev.gateway import DevelopmentProcessGateway
from cli.runtime.dev.support import DevelopmentCommandSupport, DevelopmentToolingSupport


class FakeRuntimeEnvironment(RuntimeEnvironmentService):
    """
    模拟运行时环境服务。
    """

    @staticmethod
    def get_backend_dir() -> str:
        """
        返回固定后端目录。

        :return: 固定目录
        """
        return '/tmp/ruoyi-backend'

    @staticmethod
    def get_python_executable() -> str:
        """
        返回固定 Python 可执行文件。

        :return: Python 可执行文件路径
        """
        return '/usr/bin/python3'


def test_development_runtime_service_returns_dependency_error_when_pytest_missing() -> None:
    """
    校验开发运行时在 pytest 缺失时会返回依赖错误结果。

    :return: None
    """

    class FakeToolingSupport(DevelopmentToolingSupport):
        """
        模拟开发工具支持对象。
        """

        @staticmethod
        def is_pytest_available() -> bool:
            """
            返回 pytest 不可用状态。

            :return: False
            """
            return False

    service = DevelopmentRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(),
        tooling_support=FakeToolingSupport(),
    )

    payload = service.run_tests(['tests/cli'])

    assert payload == {
        'ok': False,
        'message': 'pytest 未安装，无法执行 dev test',
        'hint': '请在当前环境安装 pytest 后重试',
        'exit_code': DEPENDENCY_ERROR,
    }


def test_development_runtime_service_run_lint_uses_command_support() -> None:
    """
    校验开发运行时会通过命令支持对象串联 format/check 执行流程。

    :return: None
    """

    class FakeCommandSupport(DevelopmentCommandSupport):
        """
        模拟开发命令支持对象。
        """

        def __init__(self) -> None:
            self.recorded_commands: list[list[str]] = []

        def build_format_command(self, normalized_targets: list[str], *, check_only: bool) -> list[str]:
            assert normalized_targets == ['tests/cli']
            assert check_only is True
            return ['format-command']

        def build_check_command(
            self,
            normalized_targets: list[str],
            *,
            check_only: bool,
            fix: bool,
            unsafe_fixes: bool,
        ) -> list[str]:
            assert normalized_targets == ['tests/cli']
            assert check_only is True
            assert fix is False
            assert unsafe_fixes is False
            return ['check-command']

    class FakeProcessGateway(DevelopmentProcessGateway):
        """
        模拟开发子进程执行网关。
        """

        def __init__(self) -> None:
            self.recorded_commands: list[list[str]] = []

        def run_command(self, command: list[str]) -> dict[str, object]:
            self.recorded_commands.append(command)
            return {'ok': True, 'command': command, 'returnCode': 0}

    command_support = FakeCommandSupport()
    process_gateway = FakeProcessGateway()
    service = DevelopmentRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(),
        command_support=command_support,
        process_gateway=process_gateway,
    )

    payload = service.run_lint(['tests/cli'], check_only=True)

    assert payload['ok'] is True
    assert payload['targets'] == ['tests/cli']
    assert process_gateway.recorded_commands == [['format-command'], ['check-command']]
