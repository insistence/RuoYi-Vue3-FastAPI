import sys
from pathlib import Path
from subprocess import CompletedProcess

from cli.runtime.plugin.service import CliPluginRuntimeService

from .conftest import (
    EXPECTED_FRONTEND_BUILD_TIMEOUT,
    FakePluginRuntimeGateway,
    FakeRuntimeEnvironment,
    build_runtime,
    build_runtime_with_gateway,
)


class LazyPluginGateway:
    """
    测试用 CLI 插件网关，验证测试命令可懒解析运行时依赖。
    """

    def __init__(self, backend_root: Path, runtime_gateway: FakePluginRuntimeGateway) -> None:
        """初始化测试用 CLI 插件网关。"""
        self.backend_root = backend_root
        self.runtime_gateway = runtime_gateway
        self.runtime_environment_requested = False
        self.runtime_gateway_requested = False

    def get_core_runtime_environment(self) -> FakeRuntimeEnvironment:
        """获取测试运行时环境。"""
        self.runtime_environment_requested = True
        return FakeRuntimeEnvironment(self.backend_root)

    def get_management_runtime_gateway(self) -> FakePluginRuntimeGateway:
        """获取测试运行时适配器。"""
        self.runtime_gateway_requested = True
        return self.runtime_gateway

    @staticmethod
    def build_exception_payload(message: str, exc: Exception) -> dict[str, object]:
        """构建测试异常负载。"""
        return {'ok': False, 'message': message, 'error': str(exc)}


def test_plugin_runtime_test_plugin_lazily_resolves_runtime_dependencies(tmp_path: Path) -> None:
    """校验插件测试命令会通过 CLI 网关懒解析运行时环境和运行时适配器。"""
    backend_root = tmp_path / 'backend'
    test_root = backend_root / 'tests' / 'plugins' / 'demo'
    test_root.mkdir(parents=True)
    runtime_gateway = FakePluginRuntimeGateway()
    plugin_gateway = LazyPluginGateway(backend_root, runtime_gateway)
    runtime = CliPluginRuntimeService(plugin_gateway=plugin_gateway)

    result = runtime.test_plugin('demo')

    assert result['ok'] is True
    assert plugin_gateway.runtime_environment_requested is True
    assert plugin_gateway.runtime_gateway_requested is True
    assert runtime_gateway.commands


def test_plugin_runtime_test_plugin_runs_pytest_target(tmp_path: Path) -> None:
    """校验插件测试命令会执行插件 pytest 目录。"""
    backend_root = tmp_path / 'backend'
    test_root = backend_root / 'tests' / 'plugins' / 'demo'
    test_root.mkdir(parents=True)
    gateway = FakePluginRuntimeGateway()

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin(
        'demo',
        keyword='ping',
        maxfail=1,
        quiet=True,
    )

    assert result['ok'] is True
    assert result['message'] == '插件测试执行完成'
    assert result['pluginId'] == 'demo'
    assert result['targets'] == [str(test_root)]
    assert result['test']['returnCode'] == 0
    assert gateway.commands[0][0] == [
        sys.executable,
        '-m',
        'pytest',
        '-q',
        '-k',
        'ping',
        '--maxfail=1',
        str(test_root),
    ]
    assert gateway.commands[0][1] == str(backend_root)


def test_plugin_runtime_test_plugin_runs_backend_and_frontend_targets(tmp_path: Path) -> None:
    """校验插件测试命令会聚合执行后端 pytest 和前端 node 测试。"""
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    frontend_root = project_root / 'ruoyi-fastapi-frontend'
    backend_test_root = backend_root / 'tests' / 'plugins' / 'demo'
    frontend_test_file = frontend_root / 'tests' / 'plugins' / 'demo' / 'pluginView.test.js'
    backend_test_root.mkdir(parents=True)
    frontend_test_file.parent.mkdir(parents=True)
    frontend_test_file.write_text("console.log('ok')\n", encoding='utf-8')
    gateway = FakePluginRuntimeGateway()

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin('demo')

    assert result['ok'] is True
    assert result['targets'] == [str(backend_test_root), str(frontend_test_file)]
    assert result['test'] is None
    assert result['command'] is None
    assert [item['kind'] for item in result['results']] == ['backend', 'frontend']
    assert gateway.commands[0][0] == [sys.executable, '-m', 'pytest', str(backend_test_root)]
    assert gateway.commands[0][1] == str(backend_root)
    assert gateway.commands[1][0] == ['node', str(frontend_test_file)]
    assert gateway.commands[1][1] == str(frontend_root)


def test_plugin_runtime_test_plugin_uses_runtime_frontend_dir(tmp_path: Path) -> None:
    """校验插件测试命令使用运行时环境提供的前端目录。"""
    project_root = tmp_path / 'project'
    backend_root = project_root / 'api-server'
    frontend_root = project_root / 'web-client'
    backend_test_root = backend_root / 'tests' / 'plugins' / 'demo'
    frontend_test_file = frontend_root / 'tests' / 'plugins' / 'demo' / 'pluginView.test.js'
    backend_test_root.mkdir(parents=True)
    frontend_test_file.parent.mkdir(parents=True)
    frontend_test_file.write_text("console.log('ok')\n", encoding='utf-8')
    gateway = FakePluginRuntimeGateway()

    result = build_runtime_with_gateway(backend_root, gateway, frontend_root=frontend_root).test_plugin('demo')

    assert result['ok'] is True
    assert result['targets'] == [str(backend_test_root), str(frontend_test_file)]
    assert gateway.commands[1][1] == str(frontend_root)


def test_plugin_runtime_test_plugin_can_run_frontend_build_acceptance(tmp_path: Path) -> None:
    """校验插件测试命令可按需追加前端构建验收。"""
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    frontend_root = project_root / 'ruoyi-fastapi-frontend'
    backend_test_root = backend_root / 'tests' / 'plugins' / 'demo'
    backend_test_root.mkdir(parents=True)
    frontend_root.mkdir(parents=True)
    gateway = FakePluginRuntimeGateway()

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin('demo', frontend_build=True)

    assert result['ok'] is True
    assert result['frontendBuild'] is True
    assert [item['kind'] for item in result['results']] == ['backend', 'frontend-build']
    assert result['targets'] == [str(backend_test_root), str(frontend_root)]
    assert gateway.commands[0][0] == [sys.executable, '-m', 'pytest', str(backend_test_root)]
    assert gateway.commands[1][0] == ['npm', 'run', 'build:stage']
    assert gateway.commands[1][1] == str(frontend_root)
    assert gateway.commands[1][2] == EXPECTED_FRONTEND_BUILD_TIMEOUT


def test_plugin_runtime_test_plugin_reports_missing_test_dir(tmp_path: Path) -> None:
    """校验插件测试目录不存在时返回清晰错误。"""
    backend_root = tmp_path / 'backend'

    result = build_runtime(backend_root).test_plugin('demo')

    assert result['ok'] is False
    assert result['message'].startswith('插件测试目录不存在')
    assert result['targets'] == [
        str(backend_root / 'tests' / 'plugins' / 'demo'),
        str(backend_root.parent / 'frontend' / 'tests' / 'plugins' / 'demo'),
    ]


def test_plugin_runtime_test_plugin_rejects_unsafe_plugin_id(tmp_path: Path) -> None:
    """校验插件测试命令拒绝可逃逸测试目录的插件ID。"""
    backend_root = tmp_path / 'backend'
    escaped_target = tmp_path / 'external_tests'
    escaped_target.mkdir()
    gateway = FakePluginRuntimeGateway()

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin(str(escaped_target))

    assert result['ok'] is False
    assert '插件ID必须' in str(result['error'])
    assert gateway.commands == []


def test_plugin_runtime_test_plugin_rejects_hyphenated_plugin_id(tmp_path: Path) -> None:
    """校验插件测试命令短期拒绝带短横线的插件 ID，保持与脚手架规则一致。"""
    backend_root = tmp_path / 'backend'
    gateway = FakePluginRuntimeGateway()

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin('demo-plugin')

    assert result['ok'] is False
    assert '只能包含小写字母、数字和下划线' in str(result['error'])
    assert gateway.commands == []


def test_plugin_runtime_test_plugin_reports_pytest_failure(tmp_path: Path) -> None:
    """校验 pytest 返回失败时插件测试命令返回失败负载。"""
    backend_root = tmp_path / 'backend'
    (backend_root / 'tests' / 'plugins' / 'demo').mkdir(parents=True)
    gateway = FakePluginRuntimeGateway()
    gateway.completed_process = CompletedProcess(args=[], returncode=1, stdout='', stderr='failed\n')

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin('demo')

    assert result['ok'] is False
    assert result['message'] == '插件测试执行失败'
    assert result['test']['returnCode'] == 1
    assert result['test']['stderr'] == 'failed\n'


def test_plugin_runtime_test_plugin_truncates_command_output(tmp_path: Path) -> None:
    """校验插件测试命令会截断过长的子进程输出。"""
    backend_root = tmp_path / 'backend'
    (backend_root / 'tests' / 'plugins' / 'demo').mkdir(parents=True)
    gateway = FakePluginRuntimeGateway()
    gateway.completed_process = CompletedProcess(
        args=[],
        returncode=0,
        stdout='x' * 5000,
        stderr='y' * 5000,
    )

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin('demo')

    assert result['ok'] is True
    assert result['test']['stdout'] == 'x' * 4000
    assert result['test']['stderr'] == 'y' * 4000
