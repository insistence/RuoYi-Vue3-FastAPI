# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_not_found_payload_model_serializes_minimal_payload() -> None:
    """
    校验插件不存在结构化模型可序列化为现有最小负载契约。

    :return: None
    """
    payload = PluginNotFoundPayload('demo').to_payload()

    assert payload == {
        'ok': False,
        'message': '插件不存在：demo',
        'pluginId': 'demo',
        'exit_code': RUNTIME_ERROR,
    }


def test_plugin_not_found_payload_model_serializes_operation_context() -> None:
    """
    校验插件不存在结构化模型可序列化操作上下文负载契约。

    :return: None
    """
    payload = PluginNotFoundPayload(
        'demo',
        operation='enable',
        dry_run=True,
        enabled=True,
    ).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件不存在：demo'
    assert payload['operation'] == 'enable'
    assert payload['dryRun'] is True
    assert payload['enabled'] is True
    assert payload['exit_code'] == RUNTIME_ERROR
