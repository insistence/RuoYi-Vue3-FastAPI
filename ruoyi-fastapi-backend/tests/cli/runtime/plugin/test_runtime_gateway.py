# ruff: noqa: F403, F405

import pytest

from tests.cli.runtime.plugin.conftest import *

SHARED_CORE_RUNTIME_METHODS = (
    'list_plugins',
    'get_plugin_info_with_state',
    'check_plugin',
    'check_plugin_dependencies',
    'precheck_plugin_operation',
    'health_plugin',
    'diagnose_plugin',
    'generate_plugin_docs',
    'plan_plugins',
    'batch_plugins',
    'install_plugin_dependencies',
    'install_plugin',
    'upgrade_plugin',
    'set_plugin_enabled',
    'uninstall_plugin',
    'purge_plugin',
    'list_plugin_migrations',
    'mark_plugin_migration_success',
    'mark_plugin_migration_failed',
    'get_plugin_config',
    'export_plugin_config',
    'import_plugin_config',
    'set_plugin_config',
)


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


def test_plugin_runtime_does_not_proxy_unknown_public_attribute(tmp_path: Path) -> None:
    """
    校验 CLI 插件运行时不会把未显式声明的公共属性透传给核心运行时。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    runtime = build_runtime(backend_root)
    runtime.core_runtime.dynamic_core_only = 'hidden'

    assert hasattr(runtime, 'dynamic_core_only') is False


def test_plugin_runtime_does_not_expose_shared_core_methods(tmp_path: Path) -> None:
    """
    校验 CLI 插件运行时不再暴露核心运行时的薄转发方法。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    runtime = build_runtime(backend_root)

    assert [method for method in SHARED_CORE_RUNTIME_METHODS if hasattr(runtime, method)] == []
    assert hasattr(runtime, 'create_plugin') is True
    assert hasattr(runtime, 'test_plugin') is True
    assert hasattr(runtime, 'lock_plugin_dependencies') is True
    assert hasattr(runtime, 'generate_plugin_dependency_allowlist_example') is True


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
    assert runtime.dependencies.management_gateway is runtime_gateway
    assert runtime.dependencies.model_gateway is runtime_gateway
    assert runtime.dependencies.command_gateway is runtime_gateway
    assert hasattr(runtime.dependencies, 'state_gateway') is False
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


def test_plugin_runtime_rejects_legacy_state_gateway_argument(tmp_path: Path) -> None:
    """
    校验 CLI 插件运行时构造期不再接受旧 state_gateway 参数。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()

    with pytest.raises(TypeError):
        CliPluginRuntimeService(
            runtime_environment=FakeRuntimeEnvironment(backend_root),
            dependency_checker=PluginDependencyChecker(),
            state_gateway=FakePluginRuntimeGateway(),
        )


def test_plugin_runtime_passes_lifecycle_lock_to_core_runtime(tmp_path: Path) -> None:
    """
    校验 CLI 创建核心插件运行时时会显式注入生命周期锁。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    lifecycle_lock = object()
    runtime = CliPluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(),
        lifecycle_lock=lifecycle_lock,
    )

    assert runtime.core_runtime.lifecycle_lock is lifecycle_lock
