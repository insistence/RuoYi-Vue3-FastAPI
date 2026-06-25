# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_runtime_check_reports_missing_dependencies(tmp_path: Path) -> None:
    """
    校验插件运行时检查会报告缺失依赖。

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
    - missing-python
""",
    )

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is False
    assert payload['checks'][0]['missingDependencies'] == ['missing-python']
    assert payload['checks'][0]['dependencies'][0]['level'] == 'error'


def test_plugin_runtime_check_reports_manifest_warnings(tmp_path: Path) -> None:
    """
    校验插件运行时检查会报告 manifest warning 且不阻断通过状态。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
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
    create_controller_dir(plugin_root)

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is True
    assert payload['checks'][0]['manifestOk'] is True
    assert payload['checks'][0]['manifestWarnings'][0]['level'] == 'warning'
    assert payload['checks'][0]['manifestWarnings'][0]['kind'] == 'secret_config_default'


def test_plugin_runtime_check_reports_compatibility_errors(tmp_path: Path) -> None:
    """
    校验插件运行时检查会报告兼容性错误并阻断通过状态。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
compatibility:
  pythonVersion: '>=99.0.0'
""",
    )
    create_controller_dir(plugin_root)

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is False
    assert payload['checks'][0]['ok'] is False
    assert payload['checks'][0]['manifestOk'] is False
    assert payload['checks'][0]['manifestIssues'][0]['level'] == 'error'
    assert payload['checks'][0]['manifestIssues'][0]['kind'] == 'compatibility_unsatisfied'
    assert payload['checks'][0]['manifestIssues'][0]['path'] == 'compatibility.pythonVersion'


def test_plugin_runtime_check_plugin_delegates_to_query_use_case(tmp_path: Path) -> None:
    """
    校验插件检查入口委托给组合式查询 use case。

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

        def check_plugin(self, plugin_id: str | None = None) -> dict:
            """
            记录插件检查调用。

            :param plugin_id: 插件ID
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            return {'ok': True, 'checks': [{'pluginId': plugin_id}]}

    query = FakeQueryUseCase()
    runtime.query = query

    payload = runtime.check_plugin('demo')

    assert query.plugin_id == 'demo'
    assert payload == {'ok': True, 'checks': [{'pluginId': 'demo'}]}


def test_plugin_runtime_check_plugin_dependencies_delegates_to_query_use_case(tmp_path: Path) -> None:
    """
    校验插件依赖检查入口委托给组合式查询 use case。

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

        def check_plugin_dependencies(self, plugin_id: str) -> dict:
            """
            记录插件依赖检查调用。

            :param plugin_id: 插件ID
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            return {'ok': True, 'pluginId': plugin_id, 'dependencyOk': True}

    query = FakeQueryUseCase()
    runtime.query = query

    payload = runtime.check_plugin_dependencies('demo')

    assert query.plugin_id == 'demo'
    assert payload == {'ok': True, 'pluginId': 'demo', 'dependencyOk': True}


def test_plugin_runtime_health_plugin_delegates_to_query_use_case(tmp_path: Path) -> None:
    """
    校验插件健康检查入口委托给组合式查询 use case。

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

        async def health_plugin(self, plugin_id: str) -> dict:
            """
            记录插件健康检查调用。

            :param plugin_id: 插件ID
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            return {'ok': True, 'pluginId': plugin_id, 'health': {'ok': True}}

    query = FakeQueryUseCase()
    runtime.query = query

    payload = asyncio.run(runtime.health_plugin('demo'))

    assert query.plugin_id == 'demo'
    assert payload == {'ok': True, 'pluginId': 'demo', 'health': {'ok': True}}


def test_plugin_runtime_install_dry_run_reports_manifest_warnings(tmp_path: Path) -> None:
    """
    校验插件安装 dry-run 会报告 manifest warning。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
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
    create_controller_dir(plugin_root)

    result = asyncio.run(build_runtime(backend_root).install_plugin('demo', dry_run=True))

    assert result['ok'] is True, result
    assert result['manifestWarnings'][0]['level'] == 'warning'
    assert result['manifestWarnings'][0]['kind'] == 'secret_config_default'


def test_plugin_runtime_install_dry_run_reports_compatibility_errors(tmp_path: Path) -> None:
    """
    校验插件安装 dry-run 会报告兼容性错误但不执行写入。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
compatibility:
  pythonVersion: '>=99.0.0'
""",
    )
    create_controller_dir(plugin_root)

    result = asyncio.run(build_runtime(backend_root).install_plugin('demo', dry_run=True))

    assert result['ok'] is True, result
    assert result['dryRun'] is True
    assert result['manifestOk'] is False
    assert result['manifestIssues'][0]['level'] == 'error'
    assert result['manifestIssues'][0]['kind'] == 'compatibility_unsatisfied'


def test_plugin_runtime_precheck_plugin_operation_returns_unified_payload(tmp_path: Path) -> None:
    """
    校验插件操作预检会返回统一的依赖、结构和菜单冲突负载。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
frontend:
  menus:
    - name: Demo
      path: demo
      component: plugin/demo/index
      perms: demo:list
permissions:
  - code: demo:list
    name: 演示列表
""",
    )
    create_controller_dir(plugin_root)
    create_frontend_view(backend_root, 'demo')

    result = asyncio.run(build_runtime(backend_root).precheck_plugin_operation('demo', 'install'))

    assert result['ok'] is True
    assert result['message'] == '插件操作预检通过'
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'install'
    assert result['manifestOk'] is True
    assert result['dependencyOk'] is True
    assert result['pluginDependencyOk'] is True
    assert result['structureOk'] is True
    assert result['menuConflictOk'] is True
    assert result['precheck']['menuConflicts'] == []
    assert any(action['name'] == 'install_menus' for action in result['actions'])


def test_plugin_runtime_precheck_plugin_operation_delegates_to_precheck_use_case(tmp_path: Path) -> None:
    """
    校验插件预检入口委托给组合式预检 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakePrecheckUseCase:
        """
        测试用插件预检 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件预检 use case。
            """
            self.plugin_id: str | None = None
            self.operation: str | None = None

        async def precheck_plugin_operation(self, plugin_id: str, operation: str) -> dict:
            """
            记录插件预检调用。

            :param plugin_id: 插件ID
            :param operation: 操作类型
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.operation = operation
            return {'ok': True, 'pluginId': plugin_id, 'operation': operation}

    precheck = FakePrecheckUseCase()
    runtime.precheck = precheck

    payload = asyncio.run(runtime.precheck_plugin_operation('demo', 'install'))

    assert precheck.plugin_id == 'demo'
    assert precheck.operation == 'install'
    assert payload == {'ok': True, 'pluginId': 'demo', 'operation': 'install'}


def test_plugin_runtime_precheck_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验预检 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    class FakePrecheckContextService:
        """
        测试用预检上下文服务。
        """

        @staticmethod
        def discover_plugins(backend_root: Path) -> list:
            """
            返回空插件列表。

            :param backend_root: 后端项目根目录
            :return: 空插件列表
            """
            return []

        @staticmethod
        def get_discovered_plugin_from_list(discovered_plugins: list, plugin_id: str) -> object:
            """
            返回测试插件对象。

            :param discovered_plugins: 已发现插件列表
            :param plugin_id: 插件ID
            :return: 测试对象
            """
            return sentinel

    context = FakePrecheckContextService()
    assert runtime.precheck.context is runtime.context

    runtime.precheck.context = context

    discovered_plugin = runtime.precheck._get_discovered_plugin_from_list([], 'demo')

    assert discovered_plugin is sentinel


def test_plugin_runtime_precheck_upgrade_includes_version_state(tmp_path: Path) -> None:
    """
    校验插件升级预检会返回版本和数据库状态。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.2.0
enabled: true
backend:
  module: plugins.demo
""",
    )
    create_controller_dir(plugin_root)
    FakePluginService.reset()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='installed',
    )

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, FakePluginRuntimeGateway()).precheck_plugin_operation(
            'demo',
            'upgrade',
        )
    )

    assert result['ok'] is True
    assert result['operation'] == 'upgrade'
    assert result['databaseAvailable'] is True
    assert result['installed'] is True
    assert result['installedVersion'] == '1.0.0'
    assert result['currentVersion'] == '1.2.0'
    assert result['needsUpgrade'] is True


def test_plugin_runtime_generate_plugin_docs_from_manifest(tmp_path: Path) -> None:
    """
    校验插件运行时可根据 manifest 生成 Markdown 文档片段。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
description: 文档生成示例
enabled: true
backend:
  module: plugins.demo
  migrations:
    - migrations/001_init.sql
  seeds:
    - seeds/001_seed.sql
  hooks:
    onInstall: hooks:on_install
  jobs:
    - id: heartbeat
      name: 心跳
      callable: plugins.demo.jobs.heartbeat
      trigger: cron
      cronExpression: '0 0/30 * * * ?'
frontend:
  menus:
    - name: Demo
      path: demo
      component: plugin/demo/index
      perms: demo:list
permissions:
  - code: demo:list
    name: 演示列表
dependencies:
  python:
    - requests>=2.0.0
  npm:
    - lodash@^4.17.0
  plugins:
    - base>=1.0.0
config:
  items:
    - key: api_key
      label: API Key
      type: password
      default: sk-demo
      secret: true
""",
    )

    result = build_runtime(backend_root).generate_plugin_docs('demo')

    assert result['ok'] is True
    assert result['format'] == 'markdown'
    assert '# 演示插件' in result['markdown']
    assert '| Demo | `demo` | `plugin/demo/index` | `demo:list` | `C` |' in result['markdown']
    assert '| `demo:list` | 演示列表 | - |' in result['markdown']
    assert '`******`' in result['markdown']
    assert '- `requests>=2.0.0`' in result['markdown']
    assert '- `onInstall`：`hooks:on_install`' in result['markdown']


def test_plugin_runtime_generate_plugin_docs_delegates_to_tool_use_case(tmp_path: Path) -> None:
    """
    校验插件文档生成入口委托给组合式工具 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeToolUseCase:
        """
        测试用插件工具 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件工具 use case。
            """
            self.plugin_id: str | None = None

        def generate_plugin_docs(self, plugin_id: str) -> dict:
            """
            记录文档生成调用。

            :param plugin_id: 插件ID
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            return {'ok': True, 'pluginId': plugin_id, 'markdown': '# Demo\n'}

    fake_tools = FakeToolUseCase()
    runtime.tools = fake_tools

    payload = runtime.generate_plugin_docs('demo')

    assert fake_tools.plugin_id == 'demo'
    assert payload['markdown'] == '# Demo\n'


def test_plugin_documentation_builder_builds_payload(tmp_path: Path) -> None:
    """
    校验插件文档构建器生成响应负载。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.demo
""",
    )
    discovered_plugin = build_runtime(backend_root).context.get_discovered_plugin('demo')
    assert discovered_plugin is not None

    payload = PluginDocumentationBuilder.build_payload('demo', discovered_plugin)

    assert payload['ok'] is True
    assert payload['pluginId'] == 'demo'
    assert payload['format'] == 'markdown'
    assert payload['length'] == len(payload['markdown'])


def test_plugin_documentation_payload_model_serializes_payload() -> None:
    """
    校验插件文档结构化模型可序列化为现有负载契约。

    :return: None
    """
    payload = PluginDocumentationBuilder.build_payload_from_markdown('demo', '# Demo\n')

    assert payload['ok'] is True
    assert payload['message'] == '插件文档生成完成'
    assert payload['pluginId'] == 'demo'
    assert payload['format'] == 'markdown'
    assert payload['markdown'] == '# Demo\n'
    assert payload['length'] == len('# Demo\n')
