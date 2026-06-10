# ruff: noqa: F403, F405

import pytest

import plugins.core.runtime.service.context as runtime_context_module
from tests.plugin_runtime_helpers import *


def test_plugin_runtime_environment_defaults_to_backend_project_root() -> None:
    """
    校验插件运行时默认后端根目录指向 backend 项目根。

    :return: None
    """
    backend_root = Path(PluginRuntimeEnvironmentService().get_backend_dir())

    assert backend_root.name == 'ruoyi-fastapi-backend'
    assert (backend_root / 'plugins').is_dir()


def test_plugin_runtime_exposes_grouped_dependencies(tmp_path: Path) -> None:
    """
    校验插件运行时集中暴露基础依赖对象。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    environment = PluginRuntimeEnvironmentService(backend_root=tmp_path)
    dependency_checker = PluginDependencyChecker()
    gateway = FakePluginRuntimeGateway()

    runtime = PluginRuntimeService(
        runtime_environment=environment,
        dependency_checker=dependency_checker,
        state_gateway=gateway,
        model_gateway=gateway,
        command_gateway=gateway,
    )

    assert runtime.dependencies.runtime_environment is environment
    assert runtime.dependencies.dependency_checker is dependency_checker
    assert runtime.dependencies.state_gateway is gateway
    assert runtime.dependencies.model_gateway is gateway
    assert runtime.dependencies.command_gateway is gateway
    assert not hasattr(runtime.dependencies, 'infrastructure_gateway')
    assert runtime.batch.dependencies is runtime.dependencies
    assert runtime.batch.context is runtime.context
    assert runtime.config.dependencies is runtime.dependencies
    assert runtime.config.context is runtime.context
    assert runtime.dependency.dependencies is runtime.dependencies
    assert runtime.dependency.context is runtime.context
    assert runtime.query.dependencies is runtime.dependencies
    assert runtime.query.context is runtime.context
    assert runtime.tools.dependencies is runtime.dependencies
    assert runtime.tools.context is runtime.context
    assert runtime.context.dependencies is runtime.dependencies


def test_plugin_runtime_legacy_dependency_aliases_are_removed(tmp_path: Path) -> None:
    """
    校验插件运行时旧依赖别名已移除，避免保留重复入口。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    assert not hasattr(runtime, 'runtime_environment')
    assert not hasattr(runtime, 'dependency_checker')
    assert not hasattr(runtime, 'infrastructure_gateway')


def test_plugin_runtime_rejects_legacy_infrastructure_gateway_argument(tmp_path: Path) -> None:
    """
    校验插件运行时构造期不再接受旧聚合网关参数。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    with pytest.raises(TypeError):
        PluginRuntimeService(
            runtime_environment=FakeRuntimeEnvironment(tmp_path / 'backend'),
            dependency_checker=PluginDependencyChecker(),
            infrastructure_gateway=FakePluginRuntimeGateway(),
        )


def test_plugin_runtime_context_mixin_is_removed_from_facade(tmp_path: Path) -> None:
    """
    校验 runtime facade 不再继承 context 兼容 mixin。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    assert not hasattr(runtime_context_module, 'PluginRuntimeContextMixin')
    assert not hasattr(runtime, '_get_context_service')


def test_plugin_runtime_config_uses_dependency_gateway(tmp_path: Path) -> None:
    """
    校验插件运行时配置读取使用集中依赖网关。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
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
        state_gateway=gateway,
        model_gateway=gateway,
        command_gateway=gateway,
    )

    payload = asyncio.run(runtime.get_plugin_config('demo'))

    assert payload['ok'] is True
    assert payload['configs'][0]['key'] == 'provider'
    assert gateway.session_local.last_session is not None


def test_plugin_runtime_updates_dependency_checker_in_container(tmp_path: Path) -> None:
    """
    校验插件运行时刷新依赖检查器时更新集中依赖容器。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    original_environment = runtime.dependencies.runtime_environment
    original_state_gateway = runtime.dependencies.state_gateway
    original_model_gateway = runtime.dependencies.model_gateway
    original_command_gateway = runtime.dependencies.command_gateway
    refreshed_checker = PluginDependencyChecker(
        python_inspector=PythonDependencyInspector(installed_packages={'missing-python': '1.0.0'}),
        npm_inspector=NpmDependencyInspector(installed_packages={'missing-npm': '2.0.0'}),
    )

    runtime._set_dependency_checker(refreshed_checker)

    assert runtime.dependencies.dependency_checker is refreshed_checker
    assert runtime.dependencies.runtime_environment is original_environment
    assert runtime.dependencies.state_gateway is original_state_gateway
    assert runtime.dependencies.model_gateway is original_model_gateway
    assert runtime.dependencies.command_gateway is original_command_gateway
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


def test_plugin_runtime_query_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验查询 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    class FakeQueryContextService:
        """
        测试用查询上下文服务。
        """

        def get_discovered_plugin(self, plugin_id: str) -> object:
            """
            返回测试插件对象。

            :param plugin_id: 插件ID
            :return: 测试对象
            """
            return sentinel

        def with_plugin_capability(self, payload: dict, discovered_plugin: object | None) -> dict:
            """
            记录 capability 附加调用。

            :param payload: 响应负载
            :param discovered_plugin: 已发现插件
            :return: 附加后的响应负载
            """
            payload['contextPlugin'] = discovered_plugin
            return payload

    context = FakeQueryContextService()
    runtime.query.context = context

    payload = runtime.query._with_plugin_capability({'ok': True}, sentinel)

    assert payload == {'ok': True, 'contextPlugin': sentinel}


def test_plugin_runtime_context_service_exposes_plugin_discovery(tmp_path: Path) -> None:
    """
    校验插件运行时上下文服务承接插件发现能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    class FakeContextService:
        """
        测试用上下文服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用上下文服务。
            """
            self.plugin_id: str | None = None

        def get_discovered_plugin(self, plugin_id: str) -> object:
            """
            记录插件发现调用。

            :param plugin_id: 插件ID
            :return: 测试对象
            """
            self.plugin_id = plugin_id
            return sentinel

    context = FakeContextService()
    runtime.context = context

    discovered_plugin = runtime.context.get_discovered_plugin('demo')

    assert context.plugin_id == 'demo'
    assert discovered_plugin is sentinel


def test_plugin_runtime_tool_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验工具 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    class FakeToolContextService:
        """
        测试用工具上下文服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用工具上下文服务。
            """
            self.plugin_id: str | None = None

        def get_discovered_plugin(self, plugin_id: str) -> object:
            """
            记录插件发现调用。

            :param plugin_id: 插件ID
            :return: 测试插件对象
            """
            self.plugin_id = plugin_id
            return sentinel

    context = FakeToolContextService()
    runtime.tools.context = context

    discovered_plugin = runtime.tools._get_discovered_plugin('demo')

    assert context.plugin_id == 'demo'
    assert discovered_plugin is sentinel


def test_plugin_runtime_config_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验配置 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    class FakeConfigContextService:
        """
        测试用配置上下文服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用配置上下文服务。
            """
            self.plugin_id: str | None = None

        def get_discovered_plugin(self, plugin_id: str) -> object:
            """
            记录插件发现调用。

            :param plugin_id: 插件ID
            :return: 测试插件对象
            """
            self.plugin_id = plugin_id
            return sentinel

    context = FakeConfigContextService()
    runtime.config.context = context

    discovered_plugin = runtime.config._get_discovered_plugin('demo')

    assert context.plugin_id == 'demo'
    assert discovered_plugin is sentinel


def test_plugin_runtime_environment_uses_dev_modes_in_dev_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    校验开发环境自动使用插件开发态模式。

    :param monkeypatch: pytest monkeypatch 夹具
    :param tmp_path: pytest 临时目录
    :return: None
    """
    monkeypatch.setattr('plugins.core.runtime.service.environment.AppConfig.app_env', 'dev')

    environment = PluginRuntimeEnvironmentService(backend_root=tmp_path)

    assert environment.get_frontend_mode() == 'dev'
    assert environment.get_backend_runtime_mode() == 'dev'


def test_plugin_runtime_environment_uses_service_modes_outside_dev(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    校验非开发环境自动使用已构建前端和服务运行态模式。

    :param monkeypatch: pytest monkeypatch 夹具
    :param tmp_path: pytest 临时目录
    :return: None
    """
    monkeypatch.setattr('plugins.core.runtime.service.environment.AppConfig.app_env', 'prod')

    environment = PluginRuntimeEnvironmentService(backend_root=tmp_path)

    assert environment.get_frontend_mode() == 'built'
    assert environment.get_backend_runtime_mode() == 'service'


def test_plugin_runtime_lists_discovered_plugins(tmp_path: Path) -> None:
    """
    校验插件运行时可以列出已发现插件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
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


def test_plugin_runtime_list_plugins_delegates_to_query_use_case(tmp_path: Path) -> None:
    """
    校验插件运行时列表入口委托给组合式查询 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeQueryUseCase:
        """
        测试用插件查询 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件查询 use case。
            """
            self.called = False

        def list_plugins(self) -> dict:
            """
            记录插件列表查询调用。

            :return: 测试负载
            """
            self.called = True
            return {'ok': True, 'plugins': [{'pluginId': 'delegated'}]}

    query = FakeQueryUseCase()
    runtime.query = query

    payload = runtime.list_plugins()

    assert query.called is True
    assert payload == {'ok': True, 'plugins': [{'pluginId': 'delegated'}]}


def test_plugin_payload_builder_builds_not_found_payload() -> None:
    """
    校验插件基础负载构建器生成插件不存在负载。

    :return: None
    """
    payload = PluginPayloadBuilder.build_plugin_not_found_payload(
        'demo',
        operation='enable',
        dry_run=True,
        enabled=True,
    )

    assert payload['ok'] is False
    assert payload['message'] == '插件不存在：demo'
    assert payload['operation'] == 'enable'
    assert payload['dryRun'] is True
    assert payload['enabled'] is True


def test_plugin_payload_builder_builds_check_payload() -> None:
    """
    校验插件基础负载构建器生成检查聚合负载。

    :return: None
    """
    success_payload = PluginPayloadBuilder.build_check_payload([{'pluginId': 'demo', 'ok': True}])
    failed_payload = PluginPayloadBuilder.build_check_payload([{'pluginId': 'demo', 'ok': False}])

    assert success_payload['ok'] is True
    assert success_payload['message'] == '插件检查通过'
    assert failed_payload['ok'] is False
    assert failed_payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_payload_builder_builds_plan_payload() -> None:
    """
    校验插件基础负载构建器生成批量计划负载。

    :return: None
    """
    plan = PluginDependencyPlan(
        operation='install',
        requested_plugin_ids=['app'],
        ordered_plugin_ids=['base', 'app'],
        items=[
            PluginDependencyPlanItem(
                plugin_id='base',
                name='Base',
                version='1.0.0',
                operation='install',
                order=0,
                requested=False,
                dependencies=[],
                installed_version=None,
                enabled=None,
                status=None,
                blockers=[],
            )
        ],
        blockers=[],
    )

    payload = PluginPayloadBuilder.build_plan_payload(plan)

    assert payload['ok'] is True
    assert payload['operation'] == 'install'
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']


def test_plugin_runtime_gets_plugin_info_with_dependencies(tmp_path: Path) -> None:
    """
    校验插件运行时可以读取插件详情和依赖检查结果。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
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


def test_plugin_runtime_get_plugin_info_delegates_to_query_use_case(tmp_path: Path) -> None:
    """
    校验插件运行时详情入口委托给组合式查询 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeQueryUseCase:
        """
        测试用插件查询 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件查询 use case。
            """
            self.plugin_id: str | None = None

        def get_plugin_info(self, plugin_id: str) -> dict:
            """
            记录插件详情查询调用。

            :param plugin_id: 插件ID
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            return {'ok': True, 'plugin': {'pluginId': plugin_id}}

    query = FakeQueryUseCase()
    runtime.query = query

    payload = runtime.get_plugin_info('demo')

    assert query.plugin_id == 'demo'
    assert payload == {'ok': True, 'plugin': {'pluginId': 'demo'}}


def test_plugin_runtime_gets_plugin_info_with_config_schema(tmp_path: Path) -> None:
    """
    校验插件详情会返回 manifest 配置声明。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
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
    """
    校验插件运行时详情会合并数据库安装状态。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: false
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
    FakePluginService.reset()
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


def test_plugin_runtime_get_plugin_info_with_state_delegates_to_query_use_case(tmp_path: Path) -> None:
    """
    校验插件运行时带状态详情入口委托给组合式查询 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeQueryUseCase:
        """
        测试用插件查询 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件查询 use case。
            """
            self.plugin_id: str | None = None

        async def get_plugin_info_with_state(self, plugin_id: str) -> dict:
            """
            记录带状态插件详情查询调用。

            :param plugin_id: 插件ID
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            return {'ok': True, 'plugin': {'pluginId': plugin_id, 'database': {'available': True}}}

    query = FakeQueryUseCase()
    runtime.query = query

    payload = asyncio.run(runtime.get_plugin_info_with_state('demo'))

    assert query.plugin_id == 'demo'
    assert payload == {'ok': True, 'plugin': {'pluginId': 'demo', 'database': {'available': True}}}


def test_plugin_runtime_gets_plugin_info_when_database_unavailable(tmp_path: Path) -> None:
    """
    校验数据库不可用时插件详情仍返回 manifest 信息和数据库错误。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
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
