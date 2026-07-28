import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import plugins.core.runtime.service.context as runtime_context_module
from plugins.core.discovery.scanner import PluginDiscoveryResult
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.runtime.service import PluginRuntimeService
from plugins.core.runtime.service.dependency_container import PluginRuntimeGatewayOverrides
from plugins.core.validation.dependencies import (
    NpmDependencyInspector,
    PluginDependencyChecker,
    PythonDependencyInspector,
)
from tests.plugins.core.runtime.fakes import (
    EXPECTED_DEPENDENCY_COUNT,
    FakePluginRuntimeGateway,
    FakePluginService,
    FakeRuntimeEnvironment,
    build_gateway_overrides,
    build_runtime,
    build_runtime_with_gateway,
    write_manifest,
)


class QueryOnlyStateGateway:
    """
    仅提供插件状态查询能力的测试网关。
    """

    def __init__(self, plugin_state: object | None = None) -> None:
        """初始化查询网关。"""
        self.plugin_state = plugin_state
        self.detail_calls: list[str] = []
        self.list_called = False

    async def get_plugin_state(self, plugin_id: str) -> object | None:
        """获取插件状态。"""
        self.detail_calls.append(plugin_id)
        return self.plugin_state

    async def list_plugin_states(self) -> list[object]:
        """获取插件状态列表。"""
        self.list_called = True
        return [self.plugin_state] if self.plugin_state is not None else []

    def get_plugin_service(self) -> object:
        """禁止查询链路回退到管理服务胖接口。"""
        raise AssertionError('状态查询不应依赖 PluginManagementServiceProtocol')


def test_plugin_runtime_environment_defaults_to_backend_project_root() -> None:
    """校验插件运行时默认后端根目录指向 backend 项目根。"""
    backend_root = Path(PluginRuntimeEnvironmentService().get_backend_dir())

    assert backend_root.name == 'ruoyi-fastapi-backend'
    assert (backend_root / 'plugins').is_dir()


def test_plugin_runtime_config_uses_dependency_gateway(tmp_path: Path) -> None:
    """校验插件运行时配置读取使用集中依赖网关。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
config:
  items:
    - key: provider
      default: openai
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(),
        gateways=build_gateway_overrides(gateway),
        model_gateway=gateway,
        command_gateway=gateway,
    )

    payload = asyncio.run(runtime.get_plugin_config('demo'))

    assert payload['ok'] is True
    assert payload['configs'][0]['key'] == 'provider'
    assert gateway.session_local.last_session is not None
    assert gateway.session_local.last_session.committed is False


def test_plugin_runtime_updates_dependency_checker_in_container(tmp_path: Path) -> None:
    """校验插件运行时刷新依赖检查器时更新集中依赖容器。"""
    runtime = build_runtime(tmp_path / 'backend')
    original_dependencies = runtime.dependencies
    original_environment = runtime.dependencies.runtime_environment
    original_model_gateway = runtime.dependencies.model_gateway
    original_command_gateway = runtime.dependencies.command_gateway
    original_use_cases = {
        'audit': runtime.audit,
        'batch': runtime.batch,
        'config': runtime.config,
        'dependency': runtime.dependency,
        'enable': runtime.enable,
        'install': runtime.install,
        'precheck': runtime.precheck,
        'purge': runtime.purge,
        'query': runtime.query,
        'tools': runtime.tools,
        'upgrade': runtime.upgrade,
    }
    refreshed_checker = PluginDependencyChecker(
        python_inspector=PythonDependencyInspector(installed_packages={'missing-python': '1.0.0'}),
        npm_inspector=NpmDependencyInspector(installed_packages={'missing-npm': '2.0.0'}),
    )

    runtime.set_dependency_checker(refreshed_checker)

    assert runtime.dependencies is original_dependencies
    assert runtime.dependencies.dependency_checker is refreshed_checker
    assert runtime.dependencies.runtime_environment is original_environment
    assert runtime.dependencies.model_gateway is original_model_gateway
    assert runtime.dependencies.command_gateway is original_command_gateway
    assert runtime.audit is original_use_cases['audit']
    assert runtime.batch is original_use_cases['batch']
    assert runtime.config is original_use_cases['config']
    assert runtime.dependency is original_use_cases['dependency']
    assert runtime.enable is original_use_cases['enable']
    assert runtime.install is original_use_cases['install']
    assert runtime.precheck is original_use_cases['precheck']
    assert runtime.purge is original_use_cases['purge']
    assert runtime.query is original_use_cases['query']
    assert runtime.tools is original_use_cases['tools']
    assert runtime.upgrade is original_use_cases['upgrade']
    assert runtime.batch.dependencies.dependency_checker is refreshed_checker
    assert runtime.batch.context.dependencies.dependency_checker is refreshed_checker
    assert runtime.config.dependencies.dependency_checker is refreshed_checker
    assert runtime.config.context.dependencies.dependency_checker is refreshed_checker
    assert runtime.dependency.dependencies.dependency_checker is refreshed_checker
    assert runtime.dependency.context.dependencies.dependency_checker is refreshed_checker
    assert runtime.query.dependencies.dependency_checker is refreshed_checker
    assert runtime.query.context.dependencies.dependency_checker is refreshed_checker
    assert runtime.tools.dependencies.dependency_checker is refreshed_checker
    assert runtime.tools.context.dependencies.dependency_checker is refreshed_checker
    assert runtime.context.dependencies.dependency_checker is refreshed_checker


def test_plugin_runtime_context_sync_state_loader_warns_inside_running_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验事件循环内同步读取数据库插件状态会输出可观测 warning。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.demo
dependencies:
  plugins:
    - base
""",
    )
    runtime = build_runtime(backend_root)
    warnings = []

    def fake_warning(message: str) -> None:
        """记录 warning 日志。"""
        warnings.append(message)

    monkeypatch.setattr(runtime_context_module.logger, 'warning', fake_warning)

    async def load_states_sync_in_loop() -> tuple[list[object], str | None]:
        """在事件循环内调用同步状态读取。"""
        return runtime.context.load_database_plugin_states_sync_with_error()

    result, database_error = asyncio.run(load_states_sync_in_loop())

    assert result == []
    assert database_error == '当前事件循环内不能同步读取数据库插件状态，已返回空列表'
    assert warnings == ['当前事件循环内不能同步读取数据库插件状态，已返回空列表']


def test_plugin_runtime_context_caches_discovered_plugins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验插件发现结果在上下文实例内短暂复用。"""
    backend_root = tmp_path / 'backend'
    scanner_roots = []

    class FakePluginScanner:
        """
        测试用插件扫描器。
        """

        def __init__(self, plugins_root: Path) -> None:
            """记录插件扫描根目录。"""
            scanner_roots.append(plugins_root)

        @staticmethod
        def discover() -> list:
            """返回测试插件列表。"""
            return []

        @staticmethod
        def discover_with_errors() -> 'PluginDiscoveryResult':
            """返回包含发现错误的测试结果。"""
            return PluginDiscoveryResult()

    monkeypatch.setattr(runtime_context_module, 'PluginScanner', FakePluginScanner)
    runtime = build_runtime(backend_root)

    first_result = runtime.context.discover_plugins(backend_root)
    second_result = runtime.context.discover_plugins(backend_root)

    assert first_result == []
    assert second_result == []
    assert scanner_roots == [backend_root.resolve() / 'plugins']


def test_plugin_runtime_environment_uses_dev_modes_in_dev_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """校验开发环境自动使用插件开发态模式。"""
    monkeypatch.setattr('plugins.core.environment.AppConfig.app_env', 'dev')

    environment = PluginRuntimeEnvironmentService(backend_root=tmp_path)

    assert environment.get_frontend_mode() == 'dev'
    assert environment.get_backend_runtime_mode() == 'dev'


def test_plugin_runtime_environment_uses_service_modes_outside_dev(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """校验非开发环境自动使用已构建前端和服务运行态模式。"""
    monkeypatch.setattr('plugins.core.environment.AppConfig.app_env', 'prod')

    environment = PluginRuntimeEnvironmentService(backend_root=tmp_path)

    assert environment.get_frontend_mode() == 'built'
    assert environment.get_backend_runtime_mode() == 'service'


def test_plugin_runtime_environment_exposes_configured_project_roots(tmp_path: Path) -> None:
    """校验插件运行时环境服务暴露显式配置的前后端目录。"""
    backend_root = tmp_path / 'api-server'
    frontend_root = tmp_path / 'web-client'

    environment = PluginRuntimeEnvironmentService(backend_root=backend_root, frontend_root=frontend_root)

    assert environment.get_backend_dir() == str(backend_root.resolve())
    assert environment.get_frontend_dir() == str(frontend_root.resolve())
    assert environment.get_backend_plugins_dir() == str(backend_root.resolve() / 'plugins')
    assert environment.get_frontend_plugins_dir() == str(frontend_root.resolve() / 'plugins')


def test_plugin_runtime_lists_discovered_plugins(tmp_path: Path) -> None:
    """校验插件运行时可以列出已发现插件。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
config:
  items:
    - key: api_key
      type: password
      secret: true
      default: sk-test
""",
    )

    payload = build_runtime(backend_root).list_plugins()

    assert payload['ok'] is True
    assert payload['count'] == 1
    assert payload['plugins'][0]['pluginId'] == 'demo'


def test_plugin_runtime_lists_plugins_with_database_state(tmp_path: Path) -> None:
    """校验状态感知列表会合并数据库启停与安装状态。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )
    query_gateway = QueryOnlyStateGateway(
        SimpleNamespace(
            plugin_id='demo',
            installed_version='1.0.0',
            enabled='0',
            status='installed',
            source='local',
            frontend_path='demo',
            last_error=None,
        )
    )
    runtime = build_runtime(backend_root)
    runtime.dependencies.state_query_gateway = query_gateway

    payload = asyncio.run(runtime.list_plugins_with_state())

    assert query_gateway.list_called is True
    assert payload['ok'] is True
    assert payload['databaseAvailable'] is True
    assert payload['databaseError'] is None
    assert payload['plugins'][0]['enabled'] is True
    assert payload['plugins'][0]['status'] == 'installed'


@pytest.mark.parametrize(
    ('entrypoint', 'expected_payload'),
    [
        ('list_plugins', {'ok': True, 'plugins': [{'pluginId': 'delegated'}]}),
        ('get_plugin_info', {'ok': True, 'plugin': {'pluginId': 'demo'}}),
        (
            'get_plugin_info_with_state',
            {'ok': True, 'plugin': {'pluginId': 'demo', 'database': {'available': True}}},
        ),
    ],
)
def test_plugin_runtime_query_entrypoints_delegate_to_query_use_case(
    tmp_path: Path,
    entrypoint: str,
    expected_payload: dict,
) -> None:
    """校验插件查询入口委托给组合式查询 use case。"""
    runtime = build_runtime(tmp_path / 'backend')

    class FakeQueryUseCase:
        """
        测试用插件查询 use case。
        """

        def __init__(self) -> None:
            """初始化测试用插件查询 use case。"""
            self.called_entrypoint: str | None = None
            self.plugin_id: str | None = None

        def list_plugins(self) -> dict:
            """记录插件列表查询调用。"""
            self.called_entrypoint = 'list_plugins'
            return {'ok': True, 'plugins': [{'pluginId': 'delegated'}]}

        def get_plugin_info(self, plugin_id: str) -> dict:
            """记录插件详情查询调用。"""
            self.called_entrypoint = 'get_plugin_info'
            self.plugin_id = plugin_id
            return {'ok': True, 'plugin': {'pluginId': plugin_id}}

        async def get_plugin_info_with_state(self, plugin_id: str) -> dict:
            """记录带状态插件详情查询调用。"""
            self.called_entrypoint = 'get_plugin_info_with_state'
            self.plugin_id = plugin_id
            return {'ok': True, 'plugin': {'pluginId': plugin_id, 'database': {'available': True}}}

    query = FakeQueryUseCase()
    runtime.query = query

    if entrypoint == 'list_plugins':
        payload = runtime.list_plugins()
    elif entrypoint == 'get_plugin_info':
        payload = runtime.get_plugin_info('demo')
    else:
        payload = asyncio.run(runtime.get_plugin_info_with_state('demo'))

    assert query.called_entrypoint == entrypoint
    if entrypoint != 'list_plugins':
        assert query.plugin_id == 'demo'
    assert payload == expected_payload


def test_plugin_runtime_check_plugin_reports_database_state_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验插件检查会显式输出数据库状态读取错误。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
dependencies:
  plugins:
    - base
""",
    )
    write_manifest(
        backend_root / 'plugins' / 'base',
        """
id: base
name: Base
version: 1.0.0
backend:
  module: plugins.base
""",
    )
    runtime = build_runtime(backend_root)
    monkeypatch.setattr(
        runtime.context,
        'load_database_plugin_states_sync_with_error',
        lambda: ([], 'db unavailable'),
    )

    payload = runtime.check_plugin('app')

    assert payload['databaseAvailable'] is False
    assert payload['databaseError'] == 'db unavailable'


def test_plugin_runtime_gets_plugin_info_with_dependencies(tmp_path: Path) -> None:
    """校验插件运行时可以读取插件详情和依赖检查结果。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
dependencies:
  python:
    - openai>=2.17.0
  npm:
    - vue>=3.5.0
""",
    )

    payload = build_runtime(backend_root).get_plugin_info('demo')

    assert payload['ok'] is True
    assert payload['plugin']['pluginId'] == 'demo'
    assert len(payload['plugin']['dependencies']) == EXPECTED_DEPENDENCY_COUNT
    assert all(item['ok'] for item in payload['plugin']['dependencies'])


def test_plugin_runtime_gets_plugin_info_with_config_schema(tmp_path: Path) -> None:
    """校验插件详情会返回 manifest 配置声明。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
config:
  items:
    - key: provider
      label: 默认供应商
      type: select
      default: openai
      options:
        - label: OpenAI
          value: openai
""",
    )

    payload = build_runtime(backend_root).get_plugin_info('demo')

    assert payload['ok'] is True
    assert payload['plugin']['config'][0]['key'] == 'provider'
    assert payload['plugin']['config'][0]['default'] == 'openai'


def test_plugin_runtime_gets_plugin_info_with_database_state(tmp_path: Path) -> None:
    """校验插件运行时详情会合并数据库安装状态。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
config:
  items:
    - key: api_key
      type: password
      secret: true
      default: sk-test
""",
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='installed',
        source='local',
        frontend_path='demo',
        last_error='',
    )

    payload = asyncio.run(build_runtime_with_gateway(backend_root, gateway).get_plugin_info_with_state('demo'))

    assert payload['ok'] is True
    assert payload['plugin']['enabled'] is True
    assert payload['plugin']['status'] == 'installed'
    assert payload['plugin']['installedVersion'] == '1.0.0'
    assert payload['plugin']['database']['available'] is True
    assert payload['plugin']['database']['installed'] is True


def test_plugin_runtime_gets_plugin_info_with_state_through_query_port(tmp_path: Path) -> None:
    """校验插件详情查询只依赖状态查询窄端口，不依赖完整管理服务端口。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )
    query_gateway = QueryOnlyStateGateway(
        SimpleNamespace(
            plugin_id='demo',
            installed_version='1.0.0',
            enabled='0',
            status='installed',
            source='local',
            frontend_path='demo',
            last_error='',
        )
    )
    runtime = PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(),
        gateways=PluginRuntimeGatewayOverrides(state_query_gateway=query_gateway),
    )

    payload = asyncio.run(runtime.get_plugin_info_with_state('demo'))

    assert payload['ok'] is True
    assert payload['plugin']['pluginId'] == 'demo'
    assert payload['plugin']['status'] == 'installed'
    assert payload['plugin']['database']['available'] is True
    assert query_gateway.detail_calls == ['demo']


def test_plugin_runtime_gets_plugin_info_when_database_unavailable(tmp_path: Path) -> None:
    """校验数据库不可用时插件详情仍返回 manifest 信息和数据库错误。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )

    payload = asyncio.run(build_runtime(backend_root).get_plugin_info_with_state('demo'))

    assert payload['ok'] is True
    assert payload['plugin']['pluginId'] == 'demo'
    assert payload['plugin']['database']['available'] is False
    assert payload['plugin']['database']['installed'] is False
    assert payload['plugin']['database']['error']
