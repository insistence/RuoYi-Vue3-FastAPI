import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.exit_codes import RUNTIME_ERROR
from cli.runtime.base import RUNTIME_ENVIRONMENT

_SNAKE_CASE_BOUNDARY_PATTERN = re.compile(r'(?<!^)(?=[A-Z])')
_ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')


@dataclass(frozen=True)
class NestedCliResult:
    """
    内部 CLI 调用结果。

    :param command: 实际执行的命令参数列表
    :param returncode: 子进程退出码
    :param stdout: 标准输出文本
    :param stderr: 标准错误文本
    :param payload: 解析后的 JSON 负载，解析失败时为 None
    """

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    payload: dict[str, Any] | list[Any] | None


class ShellTextFormatter:
    """
    Shell 与通用文本格式化服务。

    该对象集中封装 shell 命令展示、文本截断和字段名标准化逻辑，
    避免调用方继续直接依赖零散模块级工具函数。
    """

    @staticmethod
    def format_shell_command(arguments: list[str]) -> str:
        """
        将命令参数列表格式化为 shell 可读文本。

        :param arguments: 命令参数列表
        :return: shell 命令文本
        """
        return shlex.join(arguments)

    @staticmethod
    def truncate_text(value: object, max_length: int) -> str:
        """
        将文本截断到指定长度。

        :param value: 原始文本值
        :param max_length: 最大长度
        :return: 截断后的文本
        """
        text = '' if value is None else str(value).strip()
        if len(text) <= max_length:
            return text
        return f'{text[: max_length - 3]}...'

    @staticmethod
    def to_snake_case(value: object) -> str:
        """
        将字段名标准化为 `snake_case` 形式。

        :param value: 原始字段名
        :return: `snake_case` 字段名
        """
        text = '' if value is None else str(value).strip()
        if not text:
            return ''
        normalized_text = text.replace('-', '_').replace(' ', '_')
        return _SNAKE_CASE_BOUNDARY_PATTERN.sub('_', normalized_text).lower()


@dataclass(frozen=True)
class NestedCliProjectLocator:
    """
    内部 CLI 项目目录定位器。

    该对象负责识别后端根目录，并为内部 CLI 调用返回稳定的项目目录。
    """

    @staticmethod
    def is_backend_project_dir(project_dir: Path) -> bool:
        """
        判断给定目录是否为后端项目根目录。

        :param project_dir: 待检查目录
        :return: 是否为后端项目根目录
        """
        return RUNTIME_ENVIRONMENT.is_backend_project_dir(project_dir)

    def resolve_project_dir(self) -> Path:
        """
        解析内部 CLI 子进程应使用的后端项目目录。

        优先使用当前工作目录；若当前目录不是后端目录，则回退到当前
        `cli/utils.py` 所在代码树的上一层目录。

        :return: 后端项目根目录
        """
        current_dir = Path.cwd().resolve()
        if self.is_backend_project_dir(current_dir):
            return current_dir
        return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class NestedCliEnvironmentBuilder:
    """
    内部 CLI 环境构建器。

    该对象负责构建子进程环境变量以及内部 CLI 调用命令。
    """

    @staticmethod
    def build_process_env(project_dir: Path) -> dict[str, str]:
        """
        构建内部 CLI 子进程环境变量。

        :param project_dir: 后端项目根目录
        :return: 子进程环境变量字典
        """
        process_env = dict(os.environ)
        project_dir_str = str(project_dir)
        python_path = process_env.get('PYTHONPATH', '').strip()
        if python_path:
            process_env['PYTHONPATH'] = os.pathsep.join([project_dir_str, python_path])
        else:
            process_env['PYTHONPATH'] = project_dir_str
        return process_env

    @staticmethod
    def build_nested_cli_command(*arguments: str) -> list[str]:
        """
        构建内部 CLI 调用命令。

        :param arguments: CLI 参数列表
        :return: 完整子进程命令参数列表
        """
        return [sys.executable, '-m', 'cli.main', '--color=never', '--icon=none', *arguments]


@dataclass(frozen=True)
class NestedCliPayloadParser:
    """
    内部 CLI 负载解析器。

    该对象负责从标准输出/错误中提取 JSON，并为非 JSON 结果构建兜底负载。
    """

    @staticmethod
    def extract_json_payload(output_text: str) -> dict[str, Any] | list[Any] | None:
        """
        从原始输出文本中提取 JSON 负载。

        该逻辑优先尝试直接解析；若输出前后混入提示文本、ANSI 控制序列
        或其他噪声，则尝试截取最外层 JSON 对象或数组再解析。

        :param output_text: 原始输出文本
        :return: 解析成功的 JSON 负载，失败时返回 None
        """
        normalized_output = _ANSI_ESCAPE_PATTERN.sub('', output_text).strip()
        if not normalized_output:
            return None

        decoder = json.JSONDecoder()
        try:
            return decoder.decode(normalized_output)
        except Exception:
            pass

        for index, char in enumerate(normalized_output):
            if char not in '{[':
                continue
            try:
                payload, _ = decoder.raw_decode(normalized_output[index:])
                return payload
            except Exception:
                continue
        return None

    @staticmethod
    def build_non_json_payload_fallback(
        *,
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> dict[str, Any]:
        """
        为未返回 JSON 的内部 CLI 输出构建兜底负载。

        :param stdout: 标准输出文本
        :param stderr: 标准错误文本
        :param returncode: 进程退出码
        :return: 兜底结果负载
        """
        stdout_text = stdout.strip()
        stderr_text = stderr.strip()
        summary = stdout_text or stderr_text or '内部 CLI 未返回可解析的 JSON 输出'
        return {
            'ok': returncode == 0,
            'message': summary,
            'stdout': stdout_text,
            'stderr': stderr_text,
            'exit_code': returncode or RUNTIME_ERROR,
            'fallback': 'non_json_output',
        }


@dataclass
class NestedCliSupport:
    """
    内部 CLI 子进程支持服务。

    该对象统一负责编排项目目录解析、环境注入、标准输出解析以及
    实时执行/进程替换执行路径。

    :param project_locator: 项目目录定位器
    :param environment_builder: 子进程环境构建器
    :param payload_parser: 负载解析器
    """

    project_locator: NestedCliProjectLocator = field(default_factory=NestedCliProjectLocator)
    environment_builder: NestedCliEnvironmentBuilder = field(default_factory=NestedCliEnvironmentBuilder)
    payload_parser: NestedCliPayloadParser = field(default_factory=NestedCliPayloadParser)

    def resolve_project_dir(self) -> Path:
        """
        解析内部 CLI 子进程应使用的后端项目目录。

        :return: 后端项目根目录
        """
        return self.project_locator.resolve_project_dir()

    def build_process_env(self, project_dir: Path) -> dict[str, str]:
        """
        构建内部 CLI 子进程环境变量。

        :param project_dir: 后端项目根目录
        :return: 子进程环境变量字典
        """
        return self.environment_builder.build_process_env(project_dir)

    def build_nested_cli_command(self, *arguments: str) -> list[str]:
        """
        构建内部 CLI 调用命令。

        :param arguments: CLI 参数列表
        :return: 完整子进程命令参数列表
        """
        return self.environment_builder.build_nested_cli_command(*arguments)

    def extract_json_payload(self, output_text: str) -> dict[str, Any] | list[Any] | None:
        """
        从原始输出文本中提取 JSON 负载。

        :param output_text: 原始输出文本
        :return: 解析成功的 JSON 负载，失败时返回 None
        """
        return self.payload_parser.extract_json_payload(output_text)

    def build_non_json_payload_fallback(
        self,
        *,
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> dict[str, Any]:
        """
        为未返回 JSON 的内部 CLI 输出构建兜底负载。

        :param stdout: 标准输出文本
        :param stderr: 标准错误文本
        :param returncode: 进程退出码
        :return: 兜底结果负载
        """
        return self.payload_parser.build_non_json_payload_fallback(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
        )

    def run(self, *arguments: str, parse_json: bool = False) -> NestedCliResult:
        """
        在当前后端目录中执行内部 CLI 命令。

        :param arguments: CLI 参数列表
        :param parse_json: 是否尝试解析标准输出中的 JSON 负载
        :return: 内部 CLI 调用结果
        """
        project_dir = self.resolve_project_dir()
        command = self.build_nested_cli_command(*arguments)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(project_dir),
            env=self.build_process_env(project_dir),
        )
        payload: dict[str, Any] | list[Any] | None = None
        if parse_json:
            payload = self.extract_json_payload(completed.stdout)
            if payload is None:
                payload = self.extract_json_payload(completed.stderr)
            if payload is None:
                payload = self.build_non_json_payload_fallback(
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    returncode=completed.returncode,
                )
        return NestedCliResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            payload=payload,
        )

    def run_live(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        """
        在当前终端中直接执行内部 CLI 命令。

        该模式不会捕获标准输出/错误，适用于需要占用当前终端交互的 wizard
        或其他外部命令入口；调用方应自行决定是否先挂起 TUI。

        :param arguments: CLI 参数列表
        :return: 子进程执行结果
        """
        project_dir = self.resolve_project_dir()
        command = self.build_nested_cli_command(*arguments)
        return subprocess.run(
            command,
            text=True,
            check=False,
            cwd=str(project_dir),
            env=self.build_process_env(project_dir),
        )

    def exec(self, *arguments: str) -> None:
        """
        以进程替换方式执行内部 CLI 命令。

        :param arguments: CLI 参数列表
        :return: None
        """
        project_dir = self.resolve_project_dir()
        command = self.build_nested_cli_command(*arguments)
        executable = command[0]
        subprocess_arguments = [executable, *command[1:]]
        os.chdir(project_dir)
        os.execvp(executable, subprocess_arguments)


SHELL_TEXT_FORMATTER = ShellTextFormatter()
NESTED_CLI_SUPPORT = NestedCliSupport()
