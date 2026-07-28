import asyncio
import subprocess
from pathlib import Path

import pytest

from plugins.core.runtime.service.gateway import (
    DefaultPluginCommandRunnerGateway,
    PluginAuditGateway,
    PluginCommandRunnerGateway,
    PluginConfigGateway,
    PluginLifecycleStateGateway,
    PluginLifecycleUnitOfWorkGateway,
    PluginManagementModelGateway,
    PluginMigrationExecutionGateway,
    PluginMigrationHistoryGateway,
    PluginPurgePlanGateway,
    PluginStateQueryGateway,
    UnavailablePluginAuditGateway,
    UnavailablePluginConfigGateway,
    UnavailablePluginLifecycleStateGateway,
    UnavailablePluginLifecycleUnitOfWorkGateway,
    UnavailablePluginManagementModelGateway,
    UnavailablePluginMigrationExecutionGateway,
    UnavailablePluginMigrationHistoryGateway,
    UnavailablePluginPurgePlanGateway,
    UnavailablePluginStateQueryGateway,
)


def test_gateway_protocols_are_runtime_checkable() -> None:
    """校验运行时网关协议支持运行期结构检查。"""
    protocols = (
        PluginAuditGateway,
        PluginCommandRunnerGateway,
        PluginConfigGateway,
        PluginLifecycleStateGateway,
        PluginLifecycleUnitOfWorkGateway,
        PluginManagementModelGateway,
        PluginMigrationExecutionGateway,
        PluginMigrationHistoryGateway,
        PluginPurgePlanGateway,
        PluginStateQueryGateway,
    )

    assert all(getattr(protocol, '_is_runtime_protocol', False) for protocol in protocols)
    assert isinstance(DefaultPluginCommandRunnerGateway(), PluginCommandRunnerGateway)


def test_unavailable_gateways_fail_explicitly() -> None:
    """校验不可用网关通过明确异常快速失败。"""
    cases = (
        (lambda: asyncio.run(UnavailablePluginConfigGateway().get_plugin_config(object())), '配置适配器'),
        (
            lambda: asyncio.run(UnavailablePluginAuditGateway().list_plugin_operation_logs(export_limit=5)),
            '审计适配器',
        ),
        (
            lambda: asyncio.run(
                UnavailablePluginAuditGateway().add_plugin_operation_log(
                    {},
                    dry_run=False,
                    continue_on_error=False,
                )
            ),
            '审计适配器',
        ),
        (
            lambda: asyncio.run(UnavailablePluginMigrationHistoryGateway().list_plugin_migrations('demo')),
            'migration 历史适配器',
        ),
        (
            lambda: asyncio.run(UnavailablePluginPurgePlanGateway().build_plugin_purge_plan(object())),
            '清理计划适配器',
        ),
        (
            lambda: asyncio.run(UnavailablePluginLifecycleStateGateway().set_plugin_enabled_state('demo', True)),
            '生命周期状态适配器',
        ),
        (
            lambda: asyncio.run(UnavailablePluginLifecycleStateGateway().mark_plugin_uninstalled_state('demo')),
            '生命周期状态适配器',
        ),
        (UnavailablePluginLifecycleUnitOfWorkGateway().open_lifecycle_unit_of_work, '生命周期主事务适配器'),
        (
            lambda: asyncio.run(UnavailablePluginMigrationExecutionGateway().run_plugin_migrations(object())),
            'migration 执行适配器',
        ),
        (lambda: asyncio.run(UnavailablePluginStateQueryGateway().list_plugin_states()), '状态查询适配器'),
        (
            lambda: UnavailablePluginManagementModelGateway().build_config_update({'provider': 'openai'}),
            '配置更新适配器',
        ),
    )

    for operation, expected_message in cases:
        with pytest.raises(RuntimeError, match=expected_message):
            operation()


def test_default_command_gateway_runs_command(tmp_path: Path) -> None:
    """校验默认命令网关可以执行子进程命令。"""
    completed = DefaultPluginCommandRunnerGateway.run_command(
        ['python', '-c', "print('ok')"],
        str(tmp_path),
    )

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0
    assert completed.stdout.strip() == 'ok'


def test_default_command_gateway_streams_and_captures_output(tmp_path: Path) -> None:
    """校验默认命令网关实时转发输出时仍保留完整执行结果。"""
    streamed: list[tuple[str, str]] = []

    completed = DefaultPluginCommandRunnerGateway.run_command(
        [
            'python',
            '-c',
            (
                "import sys; print('downloading', flush=True); "
                "print('warning', file=sys.stderr, flush=True); print('installed', flush=True)"
            ),
        ],
        str(tmp_path),
        output_callback=lambda kind, text: streamed.append((kind, text)),
    )

    assert completed.returncode == 0
    assert completed.stdout == 'downloading\ninstalled\n'
    assert completed.stderr == 'warning\n'
    assert ('stdout', 'downloading\n') in streamed
    assert ('stdout', 'installed\n') in streamed
    assert ('stderr', 'warning\n') in streamed
