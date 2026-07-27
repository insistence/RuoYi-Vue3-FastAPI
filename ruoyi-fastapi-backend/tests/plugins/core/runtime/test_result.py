from plugins.core.runtime.result import PluginOperationResult


def test_plugin_operation_result_reads_ok_payload() -> None:
    """校验插件操作结果可读取成功 payload。"""
    payload = {'ok': True, 'message': 'ok'}
    result = PluginOperationResult.from_payload(payload)

    assert result.ok is True
    assert result.message == 'ok'
    assert result.payload is payload


def test_plugin_operation_result_treats_missing_ok_as_failure() -> None:
    """校验插件操作结果将缺失 ok 的 payload 视为失败。"""
    result = PluginOperationResult.from_payload({'message': 'unknown'})

    assert result.ok is False
    assert result.message == 'unknown'
