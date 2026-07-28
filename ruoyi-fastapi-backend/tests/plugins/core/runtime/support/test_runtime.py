import pytest
from pydantic import ValidationError

from plugins.core.runtime.result import PluginOperationResult
from plugins.core.runtime.support import PluginRuntimePayloadBuilder
from plugins.core.runtime.support.payload.runtime import PluginRuntimeExceptionPayload


def test_runtime_exception_payload_serializes_recovery_context() -> None:
    """校验运行时异常负载可以序列化恢复上下文。"""
    payload = PluginRuntimePayloadBuilder.build_exception_payload(
        '插件安装失败',
        RuntimeError('migration failed'),
        plugin_id='demo',
        failed_step='run_migrations',
        extra_payload={
            'migrationRecovery': {
                'migrationPath': 'migrations/001_init.sql',
                'status': 'running',
                'suggestion': '请人工确认后标记',
            }
        },
    )

    assert payload == {
        'ok': False,
        'message': '插件安装失败',
        'error': 'migration failed',
        'pluginId': 'demo',
        'failedStep': 'run_migrations',
        'migrationRecovery': {
            'migrationPath': 'migrations/001_init.sql',
            'status': 'running',
            'suggestion': '请人工确认后标记',
        },
    }


def test_runtime_exception_payload_rejects_unknown_fields() -> None:
    """校验运行时异常负载拒绝未知字段。"""
    with pytest.raises(ValidationError):
        PluginRuntimeExceptionPayload.model_validate(
            {
                'ok': False,
                'message': '插件安装失败',
                'error': 'boom',
                'unexpected': True,
            }
        )


def test_runtime_exception_builder_rejects_unknown_extra_payload() -> None:
    """校验运行时异常构建器拒绝未知扩展负载。"""
    with pytest.raises(ValidationError):
        PluginRuntimePayloadBuilder.build_exception_payload(
            '插件安装失败',
            RuntimeError('boom'),
            extra_payload={'unexpected': True},
        )


def test_plugin_operation_result_uses_default_message_when_missing() -> None:
    """校验插件操作结果在缺少消息时使用默认值。"""
    result = PluginOperationResult.from_payload({'ok': True}, default_message='操作完成')

    assert result.ok is True
    assert result.message == '操作完成'


def test_runtime_payload_builder_combines_failure_message_and_error() -> None:
    """校验运行时负载构建器合并失败消息与错误详情。"""
    message = PluginRuntimePayloadBuilder.build_failure_state_message(
        {'message': '安装失败', 'error': 'boom'},
        '插件操作失败',
    )

    assert message == '安装失败：boom'
