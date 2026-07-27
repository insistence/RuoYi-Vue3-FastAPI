from pathlib import Path
from types import SimpleNamespace

from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.runtime.service import PluginRuntimeService
from plugins.core.runtime.service.dependency_container import PluginRuntimeGatewayOverrides
from plugins.core.validation.dependencies import (
    NpmDependencyInspector,
    PluginDependencyChecker,
    PythonDependencyInspector,
)

from .environment import FakeRuntimeEnvironment
from .gateway import FakePluginRuntimeGateway


def write_manifest(plugin_dir: Path, content: str) -> None:
    """写入测试插件清单。"""
    plugin_dir.mkdir(parents=True)
    (plugin_dir / 'plugin.yaml').write_text(content, encoding='utf-8')


def build_runtime(backend_root: Path, frontend_root: Path | None = None) -> PluginRuntimeService:
    """构建测试用插件运行时服务。"""
    return PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root, frontend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
    )


def build_gateway_overrides(gateway: object) -> PluginRuntimeGatewayOverrides:
    """构建测试用插件运行时窄端口覆盖项。"""
    return PluginRuntimeGatewayOverrides(
        config_gateway=gateway,
        audit_gateway=gateway,
        state_query_gateway=gateway,
        migration_history_gateway=gateway,
        purge_plan_gateway=gateway,
        lifecycle_state_gateway=gateway,
        lifecycle_uow_gateway=gateway,
        migration_execution_gateway=gateway,
    )


def build_fake_lifecycle_precheck(ok: bool = True) -> SimpleNamespace:
    """构建测试用插件生命周期预检上下文。"""
    return SimpleNamespace(
        ok=ok,
        manifest_result=SimpleNamespace(ok=ok),
        plugin_dependency_result=SimpleNamespace(ok=ok),
        structure_result=SimpleNamespace(ok=ok),
        menu_conflict_result=SimpleNamespace(ok=ok),
        operation_payload={'manifestOk': ok, 'dependencyOk': ok},
        check_payload={'manifestOk': ok, 'dependencyOk': ok},
        menu_conflicts=[],
    )


def build_runtime_with_gateway(
    backend_root: Path,
    gateway: FakePluginRuntimeGateway,
    frontend_root: Path | None = None,
) -> PluginRuntimeService:
    """构建带测试运行时适配器的插件运行时服务。"""
    return PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root, frontend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
        gateways=build_gateway_overrides(gateway),
        model_gateway=gateway,
        command_gateway=gateway,
    )


def create_controller_dir(plugin_root: Path) -> None:
    """创建测试插件 controller 目录。"""
    (plugin_root / 'controller').mkdir(parents=True)


def create_frontend_view(
    backend_root: Path,
    plugin_id: str,
    view_path: str = 'index.vue',
    frontend_root: Path | None = None,
) -> None:
    """创建测试插件前端视图文件。"""
    resolved_frontend_root = frontend_root or Path(
        PluginRuntimeEnvironmentService(backend_root=backend_root).get_frontend_dir()
    )
    frontend_api = resolved_frontend_root / 'plugins' / plugin_id / 'api'
    frontend_api.mkdir(parents=True, exist_ok=True)
    frontend_view = resolved_frontend_root / 'plugins' / plugin_id / 'views' / view_path
    frontend_view.parent.mkdir(parents=True, exist_ok=True)
    frontend_view.write_text('<template />\n', encoding='utf-8')
