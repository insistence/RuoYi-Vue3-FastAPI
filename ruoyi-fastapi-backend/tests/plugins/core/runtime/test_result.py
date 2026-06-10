from cli.exit_codes import DEPENDENCY_ERROR, SUCCESS
from plugins.core.runtime.result import PluginOperationResult


def test_plugin_operation_result_maps_ok_payload_to_success_exit_code() -> None:
    """
    校验插件操作结果可将成功 payload 映射为成功退出码。

    :return: None
    """
    result = PluginOperationResult.from_payload({'ok': True, 'message': 'ok'})

    assert result.exit_code(success_exit_code=SUCCESS, failure_exit_code=DEPENDENCY_ERROR) == SUCCESS


def test_plugin_operation_result_maps_missing_ok_payload_to_failure_exit_code() -> None:
    """
    校验插件操作结果将缺失 ok 的 payload 映射为失败退出码。

    :return: None
    """
    result = PluginOperationResult.from_payload({'message': 'unknown'})

    assert result.exit_code(success_exit_code=SUCCESS, failure_exit_code=DEPENDENCY_ERROR) == DEPENDENCY_ERROR
