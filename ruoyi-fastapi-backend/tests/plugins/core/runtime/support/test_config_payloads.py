# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_config_payload_builder_builds_diagnostic_summary() -> None:
    """
    校验插件配置负载构建器生成稳定诊断摘要。

    :return: None
    """
    summary = PluginConfigPayloadBuilder.build_diagnostic_summary(
        [
            {'key': 'api_key', 'required': True, 'secret': True, 'value': '******'},
            {'key': 'endpoint', 'required': True, 'secret': False, 'value': ''},
            {'key': 'enabled', 'required': False, 'secret': False, 'value': True},
        ]
    )

    assert summary['total'] == EXPECTED_CONFIG_TOTAL
    assert summary['secretCount'] == 1
    assert summary['requiredCount'] == EXPECTED_REQUIRED_CONFIG_COUNT
    assert summary['configuredCount'] == 1
    assert summary['missingRequiredKeys'] == ['endpoint']
    assert summary['masked'] is True


def test_plugin_config_payload_builder_builds_export_payload() -> None:
    """
    校验插件配置负载构建器生成配置导出负载。

    :return: None
    """
    payload = PluginConfigPayloadBuilder.build_export_payload(
        'demo',
        [
            {
                'key': 'endpoint',
                'label': 'Endpoint',
                'type': 'string',
                'value': 'http://127.0.0.1',
                'required': True,
                'secret': False,
            }
        ],
    )

    assert payload['ok'] is True
    assert payload['pluginId'] == 'demo'
    assert payload['values'] == {'endpoint': 'http://127.0.0.1'}
    assert payload['metadata'][0]['key'] == 'endpoint'
    assert 'value' not in payload['metadata'][0]


def test_plugin_config_payload_builder_builds_read_and_update_payload() -> None:
    """
    校验插件配置负载构建器生成读取和更新负载。

    :return: None
    """
    config = SimpleNamespace(model_dump=lambda by_alias=True: {'key': 'provider', 'value': 'openai'})

    read_payload = PluginConfigPayloadBuilder.build_read_payload('demo', [config])
    update_payload = PluginConfigPayloadBuilder.build_update_payload(
        'demo',
        operation='config_set',
        message='插件配置已更新',
        configs=[config],
    )

    assert read_payload['ok'] is True
    assert read_payload['configs'][0]['key'] == 'provider'
    assert update_payload['operation'] == 'config_set'
    assert update_payload['configs'][0]['value'] == 'openai'


def test_plugin_config_payload_builder_builds_export_failure_payload() -> None:
    """
    校验插件配置负载构建器生成导出失败负载。

    :return: None
    """
    payload = PluginConfigPayloadBuilder.build_export_failure_payload(
        'demo',
        {'ok': False, 'message': '插件不存在：demo'},
        reveal_secret=True,
    )

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['revealSecret'] is True
    assert payload['values'] == {}
    assert payload['metadata'] == []


def test_plugin_config_payload_builder_builds_import_payload() -> None:
    """
    校验插件配置负载构建器生成导入负载。

    :return: None
    """
    success_payload = PluginConfigPayloadBuilder.build_import_payload(
        'demo',
        {'ok': True, 'pluginId': 'demo'},
        {'provider': 'mistral'},
    )
    failed_payload = PluginConfigPayloadBuilder.build_import_payload(
        'demo',
        {'ok': False, 'message': '失败'},
        {'provider': 'mistral'},
    )

    assert success_payload['importedKeys'] == ['provider']
    assert failed_payload['pluginId'] == 'demo'
    assert failed_payload['importedKeys'] == []


def test_plugin_config_payload_builder_builds_masked_audit_payload() -> None:
    """
    校验插件配置负载构建器生成脱敏审计摘要。

    :return: None
    """
    before_config = SimpleNamespace(
        model_dump=lambda by_alias=True: {
            'key': 'api_key',
            'label': 'API Key',
            'secret': True,
            'value': 'old-secret',
        }
    )
    after_config = SimpleNamespace(
        model_dump=lambda by_alias=True: {
            'key': 'api_key',
            'label': 'API Key',
            'secret': True,
            'value': 'new-secret',
        }
    )

    payload = PluginConfigPayloadBuilder.build_audit_payload(
        'demo',
        operation='config_set',
        values={'api_key': 'new-secret'},
        before_configs=[before_config],
        after_configs=[after_config],
        message='插件配置已更新',
    )

    assert payload['summary']['changedKeys'] == ['api_key']
    assert payload['summary']['changes'][0]['secret'] is True
    assert payload['summary']['changes'][0]['before'] == '******'
    assert payload['summary']['changes'][0]['after'] == '******'
