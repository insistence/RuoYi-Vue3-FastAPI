# ruff: noqa: F403, F405

import pytest

from tests.cli.runtime.plugin.conftest import *


def test_plugin_runtime_core_runtime_initializes_without_getattr_recursion(tmp_path: Path) -> None:
    """
    校验 CLI 插件运行时延迟初始化 core runtime 时不会触发 __getattr__ 递归。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()

    runtime = build_runtime(backend_root)
    core_runtime = runtime.core_runtime

    assert core_runtime is runtime.core_runtime
    assert core_runtime is not runtime


def test_plugin_runtime_getattr_rejects_internal_missing_attribute(tmp_path: Path) -> None:
    """
    校验 CLI 插件运行时内部缺失属性不会被代理到 core runtime。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    runtime = build_runtime(backend_root)

    assert hasattr(runtime, '_missing_internal') is False


def test_plugin_runtime_uses_core_environment_by_default() -> None:
    """
    校验 CLI 插件运行时默认使用 core 插件运行时环境。

    :return: None
    """
    runtime = CliPluginRuntimeService()

    core_runtime = runtime.core_runtime

    assert core_runtime.dependencies.runtime_environment is runtime.dependencies.runtime_environment
    assert hasattr(core_runtime.dependencies.runtime_environment, 'get_frontend_mode')


def test_plugin_runtime_dependencies_are_exposed_through_container(tmp_path: Path) -> None:
    """
    校验 CLI 插件运行时通过集中依赖容器暴露运行时依赖。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    runtime_gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, runtime_gateway)

    assert runtime.dependencies.runtime_environment.get_backend_dir() == str(backend_root)
    assert runtime.dependencies.state_gateway is runtime_gateway
    assert runtime.dependencies.model_gateway is runtime_gateway
    assert runtime.dependencies.command_gateway is runtime_gateway
    assert hasattr(runtime.dependencies, 'infrastructure_gateway') is False
    assert hasattr(runtime, 'runtime_environment') is False
    assert hasattr(runtime, 'dependency_checker') is False
    assert hasattr(runtime, 'infrastructure_gateway') is False


def test_plugin_runtime_rejects_legacy_infrastructure_gateway_argument(tmp_path: Path) -> None:
    """
    校验 CLI 插件运行时构造期不再接受旧聚合网关参数。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()

    with pytest.raises(TypeError):
        CliPluginRuntimeService(
            runtime_environment=FakeRuntimeEnvironment(backend_root),
            dependency_checker=PluginDependencyChecker(),
            infrastructure_gateway=FakePluginRuntimeGateway(),
        )
