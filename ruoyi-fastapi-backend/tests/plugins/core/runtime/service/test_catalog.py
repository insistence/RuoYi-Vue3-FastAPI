# ruff: noqa: F403, F405

import pytest

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
    gateway = FakePluginInfrastructureGateway()

    runtime = PluginRuntimeService(
        runtime_environment=environment,
        dependency_checker=dependency_checker,
        infrastructure_gateway=gateway,
    )

    assert runtime.dependencies.runtime_environment is environment
    assert runtime.dependencies.dependency_checker is dependency_checker
    assert runtime.dependencies.infrastructure_gateway is gateway
    assert runtime.runtime_environment is runtime.dependencies.runtime_environment
    assert runtime.dependency_checker is runtime.dependencies.dependency_checker
    assert runtime.infrastructure_gateway is runtime.dependencies.infrastructure_gateway


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
    gateway = FakePluginInfrastructureGateway()
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
