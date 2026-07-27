from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.plugins.core.runtime.fakes import build_runtime


@pytest.mark.asyncio
async def test_facade_routes_lifecycle_operations_with_public_arguments(tmp_path: Path) -> None:
    """校验运行时门面使用公开参数路由生命周期操作。"""
    runtime = build_runtime(tmp_path / 'backend')
    expected = {'ok': True}
    cases = (
        (
            'install',
            'install_plugin',
            {'dry_run': True, 'record_operation_log': False, 'operated_by': 'alice'},
        ),
        (
            'upgrade',
            'upgrade_plugin',
            {'dry_run': True, 'record_operation_log': False, 'operated_by': 'alice'},
        ),
        (
            'enable',
            'set_plugin_enabled',
            {'enabled': True, 'dry_run': True, 'record_operation_log': False},
        ),
        (
            'enable',
            'uninstall_plugin',
            {'dry_run': True, 'record_operation_log': False, 'operated_by': 'alice'},
        ),
        (
            'purge',
            'purge_plugin',
            {'dry_run': True, 'record_operation_log': False, 'operated_by': 'alice'},
        ),
    )

    for use_case_name, method_name, kwargs in cases:
        routed_method = AsyncMock(return_value=expected)
        setattr(runtime, use_case_name, SimpleNamespace(**{method_name: routed_method}))

        result = await getattr(runtime, method_name)('demo', **kwargs)

        assert result is expected
        routed_method.assert_awaited_once_with('demo', **kwargs)


@pytest.mark.asyncio
async def test_facade_routes_config_and_diagnose_operations(tmp_path: Path) -> None:
    """校验运行时门面正确路由配置与诊断操作。"""
    runtime = build_runtime(tmp_path / 'backend')
    expected = {'ok': True}
    cases = (
        ('config', 'get_plugin_config', ('demo',), {'reveal_secret': True}),
        ('config', 'export_plugin_config', ('demo',), {'reveal_secret': True}),
        (
            'config',
            'set_plugin_config',
            ('demo', {'provider': 'mistral'}),
            {'audit_operation': 'custom_set', 'success_message': '已保存'},
        ),
        ('config', 'import_plugin_config', ('demo', {'provider': 'mistral'}), {}),
        ('query', 'diagnose_plugin', ('demo',), {}),
    )

    for use_case_name, method_name, args, kwargs in cases:
        routed_method = AsyncMock(return_value=expected)
        setattr(runtime, use_case_name, SimpleNamespace(**{method_name: routed_method}))

        result = await getattr(runtime, method_name)(*args, **kwargs)

        assert result is expected
        routed_method.assert_awaited_once_with(*args, **kwargs)


@pytest.mark.asyncio
async def test_facade_routes_batch_dependency_and_audit_operations(tmp_path: Path) -> None:
    """校验运行时门面正确路由批量、依赖与审计操作。"""
    runtime = build_runtime(tmp_path / 'backend')
    expected = {'ok': True}
    dependency_result = object()
    payload = {'ok': False, 'pluginId': 'demo'}
    cases = (
        (
            'batch',
            'plan_plugins',
            False,
            ('install', ['demo']),
            {},
            ('install', ['demo']),
            {},
        ),
        (
            'batch',
            'batch_plugins',
            True,
            ('install', ['demo']),
            {'dry_run': True, 'continue_on_error': True},
            ('install', ['demo']),
            {'dry_run': True, 'continue_on_error': True},
        ),
        (
            'batch',
            'execute_batch_plugin_item',
            True,
            ('install', 'demo'),
            {},
            ('install', 'demo'),
            {},
        ),
        (
            'dependency',
            'install_plugin_dependencies',
            False,
            ('demo',),
            {'dry_run': True, 'confirmed': True, 'record_operation_log': False},
            ('demo',),
            {'dry_run': True, 'policy_config': None, 'confirmed': True},
        ),
        (
            'dependency',
            'install_plugin_dependencies_from_result',
            False,
            ('demo', dependency_result),
            {'dry_run': True},
            ('demo', dependency_result),
            {
                'dry_run': True,
                'discovered_plugin': None,
                'policy_config': None,
                'confirmed': False,
            },
        ),
        (
            'dependency',
            'install_plugin_dependencies_from_result_async',
            True,
            ('demo', dependency_result),
            {'dry_run': True},
            ('demo', dependency_result),
            {
                'dry_run': True,
                'discovered_plugin': None,
                'policy_config': None,
                'confirmed': False,
            },
        ),
        (
            'audit',
            'record_plugin_operation_log',
            True,
            (payload,),
            {'dry_run': False, 'continue_on_error': False},
            (payload,),
            {'dry_run': False, 'continue_on_error': False},
        ),
        (
            'audit',
            'record_plugin_failure_state',
            True,
            (payload, '插件操作失败'),
            {},
            (payload, '插件操作失败'),
            {},
        ),
    )

    for use_case_name, method_name, is_async, args, kwargs, routed_args, routed_kwargs in cases:
        routed_method = AsyncMock(return_value=expected) if is_async else MagicMock(return_value=expected)
        setattr(runtime, use_case_name, SimpleNamespace(**{method_name: routed_method}))

        result = getattr(runtime, method_name)(*args, **kwargs)
        if is_async:
            result = await result

        if use_case_name == 'audit':
            assert result is None
        else:
            assert result is expected
        if is_async:
            routed_method.assert_awaited_once_with(*routed_args, **routed_kwargs)
        else:
            routed_method.assert_called_once_with(*routed_args, **routed_kwargs)
