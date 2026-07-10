import asyncio
import subprocess
from pathlib import Path
from typing import runtime_checkable

import plugins.core.runtime.service.gateway as gateway_module
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


def test_old_plugin_infrastructure_gateway_exports_are_removed() -> None:
    """
    校验旧聚合基础设施网关不再作为 runtime 公开端口。

    :return: None
    """
    assert not hasattr(gateway_module, 'PluginInfrastructureGateway')
    assert not hasattr(gateway_module, 'DefaultPluginInfrastructureGateway')
    assert not hasattr(gateway_module, 'PluginStateGateway')
    assert not hasattr(gateway_module, 'UnavailablePluginStateGateway')


def test_default_plugin_command_gateway_is_command_runner_port() -> None:
    """
    校验默认插件网关提供命令执行窄接口。

    :return: None
    """
    assert isinstance(DefaultPluginCommandRunnerGateway(), PluginCommandRunnerGateway)


def test_plugin_gateway_ports_are_runtime_checkable_protocols() -> None:
    """
    校验插件窄接口协议可用于运行时能力判断。

    :return: None
    """
    assert getattr(PluginAuditGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginCommandRunnerGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginConfigGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginLifecycleStateGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginLifecycleUnitOfWorkGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginMigrationExecutionGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginMigrationHistoryGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginPurgePlanGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginStateQueryGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginManagementModelGateway, '_is_runtime_protocol', False) is True
    assert runtime_checkable is not None


def test_unavailable_config_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件配置网关不隐式提供配置读写能力。

    :return: None
    """
    gateway = UnavailablePluginConfigGateway()

    try:
        asyncio.run(gateway.get_plugin_config(object()))
    except RuntimeError as exc:
        assert '配置适配器' in str(exc)
    else:
        raise AssertionError('默认插件配置网关不应提供配置读取')


def test_unavailable_audit_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件审计网关不隐式提供审计写入能力。

    :return: None
    """
    gateway = UnavailablePluginAuditGateway()

    try:
        asyncio.run(gateway.list_plugin_operation_logs(export_limit=5))
    except RuntimeError as exc:
        assert '审计适配器' in str(exc)
    else:
        raise AssertionError('默认插件审计网关不应提供审计查询')

    try:
        asyncio.run(gateway.add_plugin_operation_log({}, dry_run=False, continue_on_error=False))
    except RuntimeError as exc:
        assert '审计适配器' in str(exc)
    else:
        raise AssertionError('默认插件审计网关不应提供审计写入')


def test_unavailable_migration_history_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件 migration 历史网关不隐式提供历史读写能力。

    :return: None
    """
    gateway = UnavailablePluginMigrationHistoryGateway()

    try:
        asyncio.run(gateway.list_plugin_migrations('demo'))
    except RuntimeError as exc:
        assert 'migration 历史适配器' in str(exc)
    else:
        raise AssertionError('默认插件 migration 历史网关不应提供历史查询')


def test_unavailable_purge_plan_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件清理计划网关不隐式提供清理计划能力。

    :return: None
    """
    gateway = UnavailablePluginPurgePlanGateway()

    try:
        asyncio.run(gateway.build_plugin_purge_plan(object()))
    except RuntimeError as exc:
        assert '清理计划适配器' in str(exc)
    else:
        raise AssertionError('默认插件清理计划网关不应提供清理计划构建')


def test_unavailable_lifecycle_state_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件生命周期状态网关不隐式提供写入能力。

    :return: None
    """
    gateway = UnavailablePluginLifecycleStateGateway()

    try:
        asyncio.run(gateway.set_plugin_enabled_state('demo', True))
    except RuntimeError as exc:
        assert '生命周期状态适配器' in str(exc)
    else:
        raise AssertionError('默认插件生命周期状态网关不应提供启停写入')

    try:
        asyncio.run(gateway.mark_plugin_uninstalled_state('demo'))
    except RuntimeError as exc:
        assert '生命周期状态适配器' in str(exc)
    else:
        raise AssertionError('默认插件生命周期状态网关不应提供卸载写入')


def test_unavailable_lifecycle_uow_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件生命周期主事务网关不隐式提供 UoW 能力。

    :return: None
    """
    gateway = UnavailablePluginLifecycleUnitOfWorkGateway()

    try:
        gateway.open_lifecycle_unit_of_work()
    except RuntimeError as exc:
        assert '生命周期主事务适配器' in str(exc)
    else:
        raise AssertionError('默认插件生命周期主事务网关不应提供 UoW')


def test_unavailable_migration_execution_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件 migration 执行网关不隐式提供执行能力。

    :return: None
    """
    gateway = UnavailablePluginMigrationExecutionGateway()

    try:
        asyncio.run(gateway.run_plugin_migrations(object()))
    except RuntimeError as exc:
        assert 'migration 执行适配器' in str(exc)
    else:
        raise AssertionError('默认插件 migration 执行网关不应提供执行能力')


def test_unavailable_state_query_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件状态查询网关不隐式提供管理状态读取能力。

    :return: None
    """
    gateway = UnavailablePluginStateQueryGateway()

    try:
        asyncio.run(gateway.list_plugin_states())
    except RuntimeError as exc:
        assert '状态查询适配器' in str(exc)
    else:
        raise AssertionError('默认插件状态查询网关不应提供状态读取')


def test_unavailable_model_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件模型网关不隐式提供管理模型能力。

    :return: None
    """
    gateway = UnavailablePluginManagementModelGateway()

    try:
        gateway.build_config_update({'provider': 'openai'})
    except RuntimeError as exc:
        assert '配置更新适配器' in str(exc)
    else:
        raise AssertionError('默认插件模型网关不应提供配置更新模型')


def test_default_plugin_command_gateway_run_command_returns_completed_process(tmp_path: Path) -> None:
    """
    校验默认插件网关命令执行窄接口保持可用。

    :param tmp_path: pytest临时目录
    :return: None
    """
    completed = DefaultPluginCommandRunnerGateway.run_command(
        ['python', '-c', "print('ok')"],
        str(tmp_path),
    )

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0
    assert completed.stdout.strip() == 'ok'
