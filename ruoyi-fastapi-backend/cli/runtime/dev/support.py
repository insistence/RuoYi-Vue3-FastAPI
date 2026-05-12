import importlib.util

from cli.runtime.base import RuntimeEnvironmentService


class DevelopmentToolingSupport:
    """
    开发工具支持对象。

    该对象负责目标列表规整与开发依赖可用性检查，
    避免主运行时服务继续承载轻量工具规则。
    """

    @staticmethod
    def resolve_targets(targets: list[str] | None) -> list[str]:
        """
        规范化命令目标列表。

        :param targets: 原始目标列表
        :return: 规范化后的目标列表
        """
        normalized_targets = [target.strip() for target in (targets or []) if target.strip()]
        return normalized_targets or ['.']

    @staticmethod
    def is_pytest_available() -> bool:
        """
        检查 pytest 是否已安装。

        :return: pytest 是否可用
        """
        return importlib.util.find_spec('pytest') is not None


class DevelopmentCommandSupport:
    """
    开发命令构建支持对象。

    该对象负责开发工具命令参数拼装，
    避免主运行时服务继续承载命令行桥接细节。

    :param runtime_environment: 运行时环境服务
    """

    def __init__(self, runtime_environment: RuntimeEnvironmentService) -> None:
        """
        初始化开发命令构建支持对象。

        :param runtime_environment: 运行时环境服务
        :return: None
        """
        self.runtime_environment = runtime_environment

    def build_format_command(self, normalized_targets: list[str], *, check_only: bool) -> list[str]:
        """
        构建 Ruff format 命令。

        :param normalized_targets: 已规整目标列表
        :param check_only: 是否仅检查
        :return: 格式化命令参数列表
        """
        command = [self.runtime_environment.get_python_executable(), '-m', 'ruff', 'format']
        if check_only:
            command.append('--check')
        command.extend(normalized_targets)
        return command

    def build_check_command(
        self,
        normalized_targets: list[str],
        *,
        check_only: bool,
        fix: bool,
        unsafe_fixes: bool,
    ) -> list[str]:
        """
        构建 Ruff check 命令。

        :param normalized_targets: 已规整目标列表
        :param check_only: 是否仅检查
        :param fix: 是否允许自动修复
        :param unsafe_fixes: 是否允许不安全修复
        :return: 检查命令参数列表
        """
        command = [self.runtime_environment.get_python_executable(), '-m', 'ruff', 'check']
        if fix and not check_only:
            command.append('--fix')
            if unsafe_fixes:
                command.append('--unsafe-fixes')
        command.extend(normalized_targets)
        return command

    def build_pytest_command(
        self,
        normalized_targets: list[str],
        *,
        keyword: str,
        maxfail: int,
        quiet: bool,
    ) -> list[str]:
        """
        构建 pytest 命令。

        :param normalized_targets: 已规整目标列表
        :param keyword: pytest `-k` 表达式
        :param maxfail: 最大失败数
        :param quiet: 是否启用简洁输出
        :return: pytest 命令参数列表
        """
        command = [self.runtime_environment.get_python_executable(), '-m', 'pytest']
        if quiet:
            command.append('-q')
        if keyword:
            command.extend(['-k', keyword])
        if maxfail > 0:
            command.append(f'--maxfail={maxfail}')
        command.extend(normalized_targets)
        return command
