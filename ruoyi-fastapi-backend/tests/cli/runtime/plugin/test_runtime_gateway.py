from pathlib import Path

from cli.runtime.plugin.service import CliPluginRuntimeService
from plugins.core.validation.dependencies import PluginDependencyChecker
from tests.cli.runtime.plugin.conftest import (
    FakePluginRuntimeGateway,
    FakeRuntimeEnvironment,
    build_runtime,
    build_runtime_with_gateway,
)

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
    """校验 CLI 插件运行时延迟初始化 core runtime 时不会触发 __getattr__ 递归。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()

    runtime = build_runtime(backend_root)
    core_runtime = runtime.core_runtime

    assert core_runtime is runtime.core_runtime
    assert core_runtime is not runtime


def test_plugin_runtime_exposes_only_cli_workflow_surface(tmp_path: Path) -> None:
    """校验 CLI 运行时只暴露命令工作流所需接口。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    runtime = build_runtime(backend_root)
    runtime.core_runtime.dynamic_core_only = 'hidden'

    assert not hasattr(runtime, '_missing_internal')
    assert not hasattr(runtime, 'dynamic_core_only')
    assert [method for method in SHARED_CORE_RUNTIME_METHODS if hasattr(runtime, method)] == []
    assert all(
        hasattr(runtime, method)
        for method in (
            'create_plugin',
            'test_plugin',
            'lock_plugin_dependencies',
            'generate_plugin_dependency_allowlist_example',
        )
    )


def test_plugin_runtime_uses_core_environment_by_default() -> None:
    """校验 CLI 插件运行时默认使用 core 插件运行时环境。"""
    runtime = CliPluginRuntimeService()

    core_runtime = runtime.core_runtime

    assert core_runtime.dependencies.runtime_environment is runtime.dependencies.runtime_environment
    assert hasattr(core_runtime.dependencies.runtime_environment, 'get_frontend_mode')


def test_plugin_runtime_dependencies_are_exposed_through_container(tmp_path: Path) -> None:
    """校验 CLI 插件运行时通过集中依赖容器暴露运行时依赖。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    runtime_gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, runtime_gateway)

    assert runtime.dependencies.runtime_environment.get_backend_dir() == str(backend_root)
    assert runtime.dependencies.management_gateway is runtime_gateway
    assert runtime.dependencies.model_gateway is runtime_gateway
    assert runtime.dependencies.command_gateway is runtime_gateway


def test_plugin_runtime_passes_lifecycle_lock_to_core_runtime(tmp_path: Path) -> None:
    """校验 CLI 创建核心插件运行时时会显式注入生命周期锁。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    backend_root.mkdir()
    lifecycle_lock = object()
    runtime = CliPluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(),
        lifecycle_lock=lifecycle_lock,
    )

    assert runtime.core_runtime.lifecycle_lock is lifecycle_lock
