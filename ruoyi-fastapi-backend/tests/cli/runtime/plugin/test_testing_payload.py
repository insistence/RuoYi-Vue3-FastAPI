# ruff: noqa: F403, F405

import cli.runtime.plugin.support as plugin_test_support

from .conftest import *


def test_plugin_test_payload_builder_builds_execution_payload(tmp_path: Path) -> None:
    """
    校验插件测试负载构建器生成执行结果负载。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    target = PluginTestTarget(
        kind='backend',
        target_path=tmp_path / 'tests' / 'plugins' / 'demo',
        command=[sys.executable, '-m', 'pytest'],
        workdir=tmp_path,
        timeout=120,
    )
    result_item = PluginTestPayloadBuilder.build_result_item(
        target,
        CompletedProcess(args=[], returncode=0, stdout='1 passed\n', stderr=''),
    )

    payload = PluginTestPayloadBuilder.build_execution_payload(
        'demo',
        keyword='ping',
        maxfail=1,
        quiet=True,
        frontend_build=False,
        results=[result_item],
    )

    assert payload['ok'] is True
    assert payload['pluginId'] == 'demo'
    assert payload['targets'] == [str(target.target_path)]
    assert payload['command'] == [sys.executable, '-m', 'pytest']
    assert payload['test']['returnCode'] == 0


def test_plugin_test_command_result_payload_model_preserves_existing_contract() -> None:
    """
    校验插件测试命令结果结构化负载保持既有 JSON 契约。

    :return: None
    """
    completed = CompletedProcess(args=[], returncode=1, stdout='x' * 5000, stderr='y' * 5000)

    payload_model = getattr(plugin_test_support, 'PluginTestCommandResultPayload', None)
    assert payload_model is not None

    payload = payload_model(completed).to_payload()

    assert payload == {
        'returnCode': 1,
        'stdout': 'x' * 4000,
        'stderr': 'y' * 4000,
    }


def test_plugin_test_result_item_payload_model_preserves_existing_contract(tmp_path: Path) -> None:
    """
    校验插件测试单目标结构化负载保持既有 JSON 契约。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    target = PluginTestTarget(
        kind='backend',
        target_path=tmp_path / 'tests' / 'plugins' / 'demo',
        command=[sys.executable, '-m', 'pytest'],
        workdir=tmp_path,
        timeout=120,
    )
    completed = CompletedProcess(args=[], returncode=0, stdout='1 passed\n', stderr='')

    payload_model = getattr(plugin_test_support, 'PluginTestResultItemPayload', None)
    assert payload_model is not None

    payload = payload_model(target, completed).to_payload()

    assert payload == {
        'kind': 'backend',
        'target': str(target.target_path),
        'command': [sys.executable, '-m', 'pytest'],
        'workdir': str(tmp_path),
        'test': {'returnCode': 0, 'stdout': '1 passed\n', 'stderr': ''},
    }


def test_plugin_test_execution_payload_model_preserves_existing_contract(tmp_path: Path) -> None:
    """
    校验插件测试执行结构化负载保持既有 JSON 契约。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    result = {
        'kind': 'backend',
        'target': str(tmp_path / 'tests' / 'plugins' / 'demo'),
        'command': [sys.executable, '-m', 'pytest'],
        'workdir': str(tmp_path),
        'test': {'returnCode': 0, 'stdout': '1 passed\n', 'stderr': ''},
    }

    payload_model = getattr(plugin_test_support, 'PluginTestExecutionPayload', None)
    assert payload_model is not None

    payload = payload_model(
        plugin_id='demo',
        keyword='ping',
        maxfail=1,
        quiet=True,
        frontend_build=False,
        results=[result],
    ).to_payload()

    assert payload == {
        'ok': True,
        'message': '插件测试执行完成',
        'pluginId': 'demo',
        'targets': [result['target']],
        'keyword': 'ping',
        'maxfail': 1,
        'quiet': True,
        'frontendBuild': False,
        'results': [result],
        'test': result['test'],
        'command': result['command'],
    }


def test_plugin_test_payload_builder_adds_exit_code(tmp_path: Path) -> None:
    """
    校验插件测试负载构建器补充退出码。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    success_payload = PluginTestPayloadBuilder.with_exit_code({'ok': True})
    failed_payload = PluginTestPayloadBuilder.with_exit_code({'ok': False})

    assert success_payload['exit_code'] == 0
    assert failed_payload['exit_code'] == RUNTIME_ERROR


def test_plugin_test_payload_builder_builds_missing_payload(tmp_path: Path) -> None:
    """
    校验插件测试负载构建器生成缺失目标负载。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    expected_paths = [tmp_path / 'backend-tests', tmp_path / 'frontend-tests']

    payload = PluginTestPayloadBuilder.build_missing_payload('demo', expected_paths)

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['targets'] == [str(path) for path in expected_paths]


def test_plugin_test_missing_payload_model_preserves_existing_contract(tmp_path: Path) -> None:
    """
    校验插件测试缺失目标结构化负载保持既有 JSON 契约。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    expected_paths = [tmp_path / 'backend-tests', tmp_path / 'frontend-tests']

    payload_model = getattr(plugin_test_support, 'PluginTestMissingPayload', None)
    assert payload_model is not None

    payload = payload_model('demo', expected_paths).to_payload()

    assert payload == {
        'ok': False,
        'message': '插件测试目录不存在',
        'pluginId': 'demo',
        'targets': [str(path) for path in expected_paths],
    }


def test_cli_plugin_runtime_exception_payload_model_preserves_existing_contract() -> None:
    """
    校验 CLI 插件运行时异常结构化负载保持既有 JSON 契约。

    :return: None
    """
    payload_model = getattr(plugin_test_support, 'CliPluginRuntimeExceptionPayload', None)
    assert payload_model is not None

    payload = payload_model(
        exception_payload={'ok': False, 'message': '创建插件模板失败', 'error': 'boom'},
        failure_code=99,
    ).to_payload()

    assert payload == {
        'ok': False,
        'message': '创建插件模板失败',
        'error': 'boom',
        'exit_code': 99,
    }


def test_cli_plugin_runtime_exit_code_payload_model_preserves_existing_contract() -> None:
    """
    校验 CLI 插件运行时退出码结构化负载保持既有 JSON 契约。

    :return: None
    """
    payload_model = getattr(plugin_test_support, 'CliPluginRuntimeExitCodePayload', None)
    assert payload_model is not None

    success_payload = payload_model(
        payload={'ok': True, 'message': 'ok'},
        success_code=7,
        failure_code=99,
    ).to_payload()
    failure_payload = payload_model(
        payload={'ok': False, 'message': 'failed'},
        success_code=7,
        failure_code=99,
    ).to_payload()

    assert success_payload == {'ok': True, 'message': 'ok', 'exit_code': 7}
    assert failure_payload == {'ok': False, 'message': 'failed', 'exit_code': 99}
