from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cli.exit_codes import RUNTIME_ERROR, SUCCESS


@dataclass(frozen=True)
class PluginTestTarget:
    """
    插件测试目标。

    :param kind: 测试目标类型
    :param target_path: 测试目标路径
    :param command: 测试执行命令
    :param workdir: 命令工作目录
    :param timeout: 命令超时时间
    """

    kind: str
    target_path: Path
    command: list[str]
    workdir: Path
    timeout: int


class PluginTestPlanBuilder:
    """
    插件 CLI 测试计划构建器。

    使用 Builder 模式发现后端 pytest 与前端 node 测试目标，并生成可执行命令。
    """

    def __init__(
        self,
        *,
        backend_root: Path,
        frontend_root: Path,
        python_executable: str,
        node_executable: str = 'node',
        timeout: int = 120,
    ) -> None:
        """
        初始化插件 CLI 测试计划构建器。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端项目根目录
        :param python_executable: Python 解释器
        :param node_executable: Node.js 可执行命令
        :param timeout: 命令超时时间
        :return: None
        """
        self.backend_root = backend_root
        self.frontend_root = frontend_root
        self.python_executable = python_executable
        self.node_executable = node_executable
        self.timeout = timeout

    def build(
        self,
        plugin_id: str,
        *,
        keyword: str = '',
        maxfail: int = 0,
        quiet: bool = False,
        frontend_build: bool = False,
    ) -> list[PluginTestTarget]:
        """
        构建插件测试目标列表。

        :param plugin_id: 插件ID
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: pytest 最大失败数
        :param quiet: pytest 是否启用简洁输出
        :param frontend_build: 是否追加前端构建验收目标
        :return: 插件测试目标列表
        """
        targets = []
        backend_target = self.backend_root / 'tests' / 'plugins' / plugin_id
        if backend_target.exists():
            targets.append(
                PluginTestTarget(
                    kind='backend',
                    target_path=backend_target,
                    command=self._build_backend_command(
                        backend_target,
                        keyword=keyword,
                        maxfail=maxfail,
                        quiet=quiet,
                    ),
                    workdir=self.backend_root,
                    timeout=self.timeout,
                )
            )

        frontend_target = self.frontend_root / 'tests' / 'plugins' / plugin_id
        if frontend_target.exists():
            targets.extend(
                [
                    PluginTestTarget(
                        kind='frontend',
                        target_path=test_file,
                        command=[self.node_executable, str(test_file)],
                        workdir=self.frontend_root,
                        timeout=self.timeout,
                    )
                    for test_file in sorted(frontend_target.glob('*.test.js'))
                ]
            )
        if frontend_build and self.frontend_root.exists():
            targets.append(
                PluginTestTarget(
                    kind='frontend-build',
                    target_path=self.frontend_root,
                    command=['npm', 'run', 'build:stage'],
                    workdir=self.frontend_root,
                    timeout=max(self.timeout, 300),
                )
            )

        return targets

    def expected_paths(self, plugin_id: str) -> list[Path]:
        """
        获取插件测试约定目录列表。

        :param plugin_id: 插件ID
        :return: 插件测试约定目录列表
        """
        return [
            self.backend_root / 'tests' / 'plugins' / plugin_id,
            self.frontend_root / 'tests' / 'plugins' / plugin_id,
        ]

    def _build_backend_command(
        self,
        target_path: Path,
        *,
        keyword: str,
        maxfail: int,
        quiet: bool,
    ) -> list[str]:
        """
        构建插件 pytest 命令。

        :param target_path: 测试目标路径
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: 最大失败数
        :param quiet: 是否启用简洁输出
        :return: pytest 命令参数列表
        """
        command = [self.python_executable, '-m', 'pytest']
        if quiet:
            command.append('-q')
        if keyword:
            command.extend(['-k', keyword])
        if maxfail > 0:
            command.append(f'--maxfail={maxfail}')
        command.append(str(target_path))

        return command


class PluginTestPayloadBuilder:
    """
    插件 CLI 测试负载构建器。

    使用 Builder 模式将测试目标和命令结果转换为稳定命令负载。
    """

    @staticmethod
    def build_command_result(completed: Any) -> dict[str, Any]:
        """
        构建 CLI 系统命令执行结果负载。

        :param completed: 命令执行结果
        :return: 系统命令执行结果负载
        """
        return {
            'returnCode': completed.returncode,
            'stdout': completed.stdout[-4000:] if completed.stdout else '',
            'stderr': completed.stderr[-4000:] if completed.stderr else '',
        }

    @classmethod
    def build_result_item(cls, target: PluginTestTarget, completed: Any) -> dict[str, Any]:
        """
        构建单个插件测试结果项。

        :param target: 插件测试目标
        :param completed: 命令执行结果
        :return: 插件测试结果项
        """
        return {
            'kind': target.kind,
            'target': str(target.target_path),
            'command': target.command,
            'workdir': str(target.workdir),
            'test': cls.build_command_result(completed),
        }

    @staticmethod
    def with_exit_code(
        payload: dict[str, Any],
        *,
        success_code: int = SUCCESS,
        failure_code: int = RUNTIME_ERROR,
    ) -> dict[str, Any]:
        """
        为插件测试负载补充退出码。

        :param payload: 插件测试负载
        :param success_code: 成功退出码
        :param failure_code: 失败退出码
        :return: 带退出码的插件测试负载
        """
        return {**payload, 'exit_code': success_code if payload.get('ok') else failure_code}

    @staticmethod
    def build_missing_payload(plugin_id: str, expected_paths: list[Path]) -> dict[str, Any]:
        """
        构建插件测试目标缺失负载。

        :param plugin_id: 插件ID
        :param expected_paths: 约定测试目录列表
        :return: 插件测试目标缺失负载
        """
        return {
            'ok': False,
            'message': '插件测试目录不存在',
            'pluginId': plugin_id,
            'targets': [str(path) for path in expected_paths],
        }

    @staticmethod
    def build_execution_payload(
        plugin_id: str,
        *,
        keyword: str,
        maxfail: int,
        quiet: bool,
        frontend_build: bool,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        构建插件测试执行结果负载。

        :param plugin_id: 插件ID
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: 最大失败数
        :param quiet: 是否启用简洁输出
        :param frontend_build: 是否执行前端构建验收
        :param results: 测试结果项列表
        :return: 插件测试执行结果负载
        """
        ok = all(item['test']['returnCode'] == 0 for item in results)

        return {
            'ok': ok,
            'message': '插件测试执行完成' if ok else '插件测试执行失败',
            'pluginId': plugin_id,
            'targets': [item['target'] for item in results],
            'keyword': keyword,
            'maxfail': maxfail,
            'quiet': quiet,
            'frontendBuild': frontend_build,
            'results': results,
            'test': results[0]['test'] if len(results) == 1 else None,
            'command': results[0]['command'] if len(results) == 1 else None,
        }
