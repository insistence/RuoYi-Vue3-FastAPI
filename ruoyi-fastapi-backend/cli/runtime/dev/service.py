from typing import Any

from cli.exit_codes import DEPENDENCY_ERROR, RUNTIME_ERROR
from cli.runtime.base import RUNTIME_ENVIRONMENT, RuntimeEnvironmentService

from .gateway import DevelopmentProcessGateway
from .support import DevelopmentCommandSupport, DevelopmentToolingSupport


class DevelopmentRuntimeService:
    """
    开发运行时服务。

    该服务作为开发运行时 facade，对外统一暴露 lint/format 和 pytest
    执行入口。

    :param runtime_environment: 运行时环境服务
    :param tooling_support: 开发工具支持对象
    :param command_support: 开发命令构建支持对象
    :param process_gateway: 开发子进程执行网关
    """

    def __init__(
        self,
        *,
        runtime_environment: RuntimeEnvironmentService | None = None,
        tooling_support: DevelopmentToolingSupport | None = None,
        command_support: DevelopmentCommandSupport | None = None,
        process_gateway: DevelopmentProcessGateway | None = None,
    ) -> None:
        """
        初始化开发运行时服务。

        :param runtime_environment: 运行时环境服务
        :param tooling_support: 开发工具支持对象
        :param command_support: 开发命令构建支持对象
        :param process_gateway: 开发子进程执行网关
        :return: None
        """
        self.runtime_environment = runtime_environment or RUNTIME_ENVIRONMENT
        self.tooling_support = tooling_support or DevelopmentToolingSupport()
        self.command_support = command_support or DevelopmentCommandSupport(self.runtime_environment)
        self.process_gateway = process_gateway or DevelopmentProcessGateway(self.runtime_environment)

    def run_lint(
        self,
        targets: list[str] | None,
        *,
        check_only: bool = False,
        fix: bool = False,
        unsafe_fixes: bool = False,
    ) -> dict[str, Any]:
        """
        执行仓库 lint/format 检查。

        :param targets: 目标路径列表
        :param check_only: 是否仅检查不写回
        :param fix: 是否允许 `ruff check --fix`
        :param unsafe_fixes: 是否允许不安全修复
        :return: lint 执行结果
        """
        normalized_targets = self.tooling_support.resolve_targets(targets)
        format_command = self.command_support.build_format_command(normalized_targets, check_only=check_only)
        format_result = self.process_gateway.run_command(format_command)
        if not format_result.get('ok', False):
            return {
                'ok': False,
                'message': 'Ruff format 阶段失败',
                'targets': normalized_targets,
                'format': format_result,
                'exit_code': RUNTIME_ERROR,
            }

        check_command = self.command_support.build_check_command(
            normalized_targets,
            check_only=check_only,
            fix=fix,
            unsafe_fixes=unsafe_fixes,
        )
        check_result = self.process_gateway.run_command(check_command)
        if not check_result.get('ok', False):
            return {
                'ok': False,
                'message': 'Ruff check 阶段失败',
                'targets': normalized_targets,
                'format': format_result,
                'check': check_result,
                'exit_code': RUNTIME_ERROR,
            }

        return {
            'ok': True,
            'message': '开发检查已完成',
            'targets': normalized_targets,
            'checkOnly': check_only,
            'fix': fix and not check_only,
            'unsafeFixes': unsafe_fixes and fix and not check_only,
            'format': format_result,
            'check': check_result,
        }

    def run_tests(
        self,
        targets: list[str] | None,
        *,
        keyword: str = '',
        maxfail: int = 0,
        quiet: bool = False,
    ) -> dict[str, Any]:
        """
        执行项目测试。

        :param targets: 目标测试路径列表
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: 最大失败数，0 表示不限制
        :param quiet: 是否启用简洁输出
        :return: 测试执行结果
        """
        if not self.tooling_support.is_pytest_available():
            return {
                'ok': False,
                'message': 'pytest 未安装，无法执行 dev test',
                'hint': '请在当前环境安装 pytest 后重试',
                'exit_code': DEPENDENCY_ERROR,
            }

        normalized_targets = self.tooling_support.resolve_targets(targets)
        command = self.command_support.build_pytest_command(
            normalized_targets,
            keyword=keyword,
            maxfail=maxfail,
            quiet=quiet,
        )
        test_result = self.process_gateway.run_command(command)
        if not test_result.get('ok', False):
            return {
                'ok': False,
                'message': '测试执行失败',
                'targets': normalized_targets,
                'keyword': keyword,
                'maxfail': maxfail,
                'quiet': quiet,
                'test': test_result,
                'exit_code': RUNTIME_ERROR,
            }

        return {
            'ok': True,
            'message': '测试执行完成',
            'targets': normalized_targets,
            'keyword': keyword,
            'maxfail': maxfail,
            'quiet': quiet,
            'test': test_result,
        }


DEVELOPMENT_RUNTIME = DevelopmentRuntimeService()
