import subprocess
from pathlib import Path
from typing import runtime_checkable

from plugins.core.runtime.service.gateway import (
    DefaultPluginInfrastructureGateway,
    PluginCommandRunnerGateway,
    PluginManagementModelGateway,
    PluginStateGateway,
)


def test_default_plugin_gateway_is_command_runner_port() -> None:
    """
    校验默认插件网关提供命令执行窄接口。

    :return: None
    """
    assert isinstance(DefaultPluginInfrastructureGateway(), PluginCommandRunnerGateway)


def test_plugin_gateway_ports_are_runtime_checkable_protocols() -> None:
    """
    校验插件窄接口协议可用于运行时能力判断。

    :return: None
    """
    assert getattr(PluginCommandRunnerGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginStateGateway, '_is_runtime_protocol', False) is True
    assert getattr(PluginManagementModelGateway, '_is_runtime_protocol', False) is True
    assert runtime_checkable is not None


def test_default_plugin_gateway_state_methods_remain_explicitly_unavailable() -> None:
    """
    校验默认插件网关不隐式提供管理状态能力。

    :return: None
    """
    gateway = DefaultPluginInfrastructureGateway()

    try:
        gateway.get_async_session_local()
    except RuntimeError as exc:
        assert '数据库会话适配器' in str(exc)
    else:
        raise AssertionError('默认插件网关不应提供数据库会话')


def test_default_plugin_gateway_run_command_returns_completed_process(tmp_path: Path) -> None:
    """
    校验默认插件网关命令执行窄接口保持可用。

    :param tmp_path: pytest临时目录
    :return: None
    """
    completed = DefaultPluginInfrastructureGateway.run_command(
        ['python', '-c', "print('ok')"],
        str(tmp_path),
    )

    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode == 0
    assert completed.stdout.strip() == 'ok'
