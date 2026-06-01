# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_audit_payload_builder_builds_plain_object_payload() -> None:
    """
    校验插件审计负载构建器可适配普通对象。

    :return: None
    """
    operation_log = SimpleNamespace(
        operation_id=1,
        operation='install',
        plugin_ids=['demo'],
        dry_run=False,
        continue_on_error=True,
        status='success',
        summary={'succeeded': 1},
        create_time='2026-01-01 00:00:00',
        remark='ok',
    )

    payload = PluginAuditPayloadBuilder.build_item_payload(operation_log)

    assert payload['operationId'] == 1
    assert payload['operation'] == 'install'
    assert payload['pluginIds'] == ['demo']
    assert payload['continueOnError'] is True
    assert payload['summary'] == {'succeeded': 1}


def test_plugin_audit_payload_builder_builds_recent_snapshot_payload() -> None:
    """
    校验插件审计负载构建器生成最近审计快照。

    :return: None
    """
    operation_logs = [
        SimpleNamespace(operation_id=1, operation='install', plugin_ids=['demo'], summary={'ok': True}),
        SimpleNamespace(operation_id=2, operation='install', plugin_ids=['other'], summary={'ok': True}),
    ]

    payload = PluginAuditPayloadBuilder.build_recent_snapshot_payload('demo', operation_logs, audit_limit=5)
    failure_payload = PluginAuditPayloadBuilder.build_recent_snapshot_failure(RuntimeError('db unavailable'))

    assert payload['available'] is True
    assert payload['count'] == 1
    assert payload['items'][0]['operation'] == 'install'
    assert failure_payload['available'] is False
    assert 'db unavailable' in failure_payload['message']
