import subprocess
from pathlib import Path
from typing import runtime_checkable

import plugins.core.runtime.service.gateway as gateway_module
from plugins.core.runtime.service.gateway import (
    DefaultPluginCommandRunnerGateway,
    PluginCommandRunnerGateway,
    PluginManagementModelGateway,
    PluginStateGateway,
    UnavailablePluginManagementModelGateway,
    UnavailablePluginStateGateway,
)


def test_old_plugin_infrastructure_gateway_exports_are_removed() -> None:
    """
    校验旧聚合基础设施网关不再作为 runtime 公开端口。

    :return: None
    """
    assert not hasattr(gateway_module, 'PluginInfrastructureGateway')
    assert not hasattr(gateway_module, 'DefaultPluginInfrastructureGateway')


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
    assert getattr(PluginCommandRunnerGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginStateGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginManagementModelGateway, '_is_runtime_protocol', False) is True
    assert runtime_checkable is not None


def test_unavailable_state_gateway_remains_explicitly_unavailable() -> None:
    """
    校验默认插件网关不隐式提供管理状态能力。

    :return: None
    """
    gateway = UnavailablePluginStateGateway()

    try:
        gateway.get_async_session_local()
    except RuntimeError as exc:
        assert '数据库会话适配器' in str(exc)
    else:
        raise AssertionError('默认插件网关不应提供数据库会话')


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
