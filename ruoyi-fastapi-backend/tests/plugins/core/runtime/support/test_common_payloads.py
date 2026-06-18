# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_not_found_payload_builder_builds_minimal_payload() -> None:
    """
    校验插件不存在 payload builder 生成最小负载契约。

    :return: None
    """
    payload = PluginPayloadBuilder.build_plugin_not_found_payload('demo')

    assert payload == {
        'ok': False,
        'message': '插件不存在：demo',
        'pluginId': 'demo',
    }


def test_plugin_not_found_payload_builder_builds_operation_context() -> None:
    """
    校验插件不存在 payload builder 生成操作上下文负载契约。

    :return: None
    """
    payload = PluginPayloadBuilder.build_plugin_not_found_payload(
        'demo',
        operation='enable',
        dry_run=True,
        enabled=True,
    )

    assert payload['ok'] is False
    assert payload['message'] == '插件不存在：demo'
    assert payload['operation'] == 'enable'
    assert payload['dryRun'] is True
    assert payload['enabled'] is True
