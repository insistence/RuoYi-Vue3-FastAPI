# ruff: noqa: F403, F405

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
