# ruff: noqa: F403, F405

from .conftest import *


def test_plugin_runtime_test_plugin_runs_pytest_target(tmp_path: Path) -> None:
    """
    校验插件测试命令会执行插件 pytest 目录。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    test_root = backend_root / 'tests' / 'plugins' / 'demo'
    test_root.mkdir(parents=True)
    gateway = FakePluginInfrastructureGateway()

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
    """
    校验插件测试命令会聚合执行后端 pytest 和前端 node 测试。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    frontend_root = project_root / 'ruoyi-fastapi-frontend'
    backend_test_root = backend_root / 'tests' / 'plugins' / 'demo'
    frontend_test_file = frontend_root / 'tests' / 'plugins' / 'demo' / 'pluginView.test.js'
    backend_test_root.mkdir(parents=True)
    frontend_test_file.parent.mkdir(parents=True)
    frontend_test_file.write_text("console.log('ok')\n", encoding='utf-8')
    gateway = FakePluginInfrastructureGateway()

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


def test_plugin_runtime_test_plugin_can_run_frontend_build_acceptance(tmp_path: Path) -> None:
    """
    校验插件测试命令可按需追加前端构建验收。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    frontend_root = project_root / 'ruoyi-fastapi-frontend'
    backend_test_root = backend_root / 'tests' / 'plugins' / 'demo'
    backend_test_root.mkdir(parents=True)
    frontend_root.mkdir(parents=True)
    gateway = FakePluginInfrastructureGateway()

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
    """
    校验插件测试目录不存在时返回清晰错误。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'

    result = build_runtime(backend_root).test_plugin('demo')

    assert result['ok'] is False
    assert result['message'].startswith('插件测试目录不存在')
    assert result['targets'] == [
        str(backend_root / 'tests' / 'plugins' / 'demo'),
        str(backend_root.parent / 'ruoyi-fastapi-frontend' / 'tests' / 'plugins' / 'demo'),
    ]


def test_plugin_runtime_test_plugin_reports_pytest_failure(tmp_path: Path) -> None:
    """
    校验 pytest 返回失败时插件测试命令返回失败负载。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    (backend_root / 'tests' / 'plugins' / 'demo').mkdir(parents=True)
    gateway = FakePluginInfrastructureGateway()
    gateway.completed_process = CompletedProcess(args=[], returncode=1, stdout='', stderr='failed\n')

    result = build_runtime_with_gateway(backend_root, gateway).test_plugin('demo')

    assert result['ok'] is False
    assert result['message'] == '插件测试执行失败'
    assert result['test']['returnCode'] == 1
    assert result['test']['stderr'] == 'failed\n'
