# ruff: noqa: F403, F405

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

    assert core_runtime.runtime_environment is runtime.runtime_environment
    assert hasattr(core_runtime.runtime_environment, 'get_frontend_mode')
