import asyncio
from pathlib import Path
from types import SimpleNamespace

from plugins.core.lifecycle.purge import PluginPurgePlanner
from plugins.core.runtime.service import PluginRuntimeService
from plugins.core.runtime.service.dependency_container import PluginRuntimeGatewayOverrides
from plugins.core.validation.dependencies import PluginDependencyChecker
from tests.plugins.core.runtime.fakes import (
    EXPECTED_PURGE_DESTRUCTIVE_COUNT,
    FakePluginRuntimeGateway,
    FakePluginService,
    FakeRuntimeEnvironment,
    build_runtime,
    build_runtime_with_gateway,
    create_controller_dir,
    create_frontend_view,
    write_manifest,
)


class PrecheckStateQueryGateway:
    """
    仅提供预检所需插件状态查询能力的测试网关。
    """

    async def get_plugin_state(self, plugin_id: str) -> object | None:
        """获取插件状态。"""
        return None

    async def list_plugin_states(self) -> list[object]:
        """获取插件状态列表。"""
        return []

    def get_plugin_service(self) -> object:
        """禁止预检状态读取回退到管理服务胖接口。"""
        raise AssertionError('预检状态读取不应依赖 PluginManagementServiceProtocol')


class PurgePlanOnlyGateway:
    """
    仅提供插件清理计划能力的测试网关。
    """

    def __init__(self) -> None:
        """初始化测试清理计划网关。"""
        self.calls: list[str] = []

    async def build_plugin_purge_plan(self, discovered_plugin: object) -> object:
        """构建测试清理计划。"""
        self.calls.append(discovered_plugin.manifest.id)
        return PluginPurgePlanner.build_plan(
            discovered_plugin,
            menu_count=1,
            config_count=2,
            migration_count=3,
            job_count=4,
        )

    def get_plugin_service(self) -> object:
        """禁止清理计划链路回退到管理服务胖接口。"""
        raise AssertionError('清理计划不应依赖 PluginManagementServiceProtocol')


def test_plugin_runtime_check_reports_missing_dependencies(tmp_path: Path) -> None:
    """校验插件运行时检查会报告缺失依赖。"""
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
    - missing-python
""",
    )

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is False
    assert payload['checks'][0]['missingDependencies'] == ['missing-python']
    assert payload['checks'][0]['dependencies'][0]['level'] == 'error'


def test_plugin_runtime_check_reports_manifest_warnings(tmp_path: Path) -> None:
    """校验插件运行时检查会报告 manifest warning 且不阻断通过状态。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
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
    create_controller_dir(plugin_root)

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is True
    assert payload['checks'][0]['manifestOk'] is True
    assert payload['checks'][0]['manifestWarnings'][0]['level'] == 'warning'
    assert payload['checks'][0]['manifestWarnings'][0]['kind'] == 'secret_config_default'


def test_plugin_runtime_check_reports_compatibility_errors(tmp_path: Path) -> None:
    """校验插件运行时检查会报告兼容性错误并阻断通过状态。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
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


def test_plugin_runtime_install_dry_run_reports_manifest_warnings(tmp_path: Path) -> None:
    """校验插件安装 dry-run 会报告 manifest warning。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
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
    create_controller_dir(plugin_root)

    result = asyncio.run(build_runtime(backend_root).install_plugin('demo', dry_run=True))

    assert result['ok'] is True, result
    assert result['manifestWarnings'][0]['level'] == 'warning'
    assert result['manifestWarnings'][0]['kind'] == 'secret_config_default'


def test_plugin_runtime_install_dry_run_reports_compatibility_errors(tmp_path: Path) -> None:
    """校验插件安装 dry-run 会报告兼容性错误但不执行写入。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
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
    """校验插件操作预检会返回统一的依赖、结构和菜单冲突负载。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
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


def test_plugin_runtime_precheck_purge_uses_purge_plan_port(tmp_path: Path) -> None:
    """校验 purge 预检只依赖清理计划窄端口。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )
    create_controller_dir(plugin_root)
    purge_plan_gateway = PurgePlanOnlyGateway()
    runtime = PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(),
        gateways=PluginRuntimeGatewayOverrides(
            state_query_gateway=PrecheckStateQueryGateway(),
            purge_plan_gateway=purge_plan_gateway,
        ),
    )

    result = asyncio.run(runtime.precheck_plugin_operation('demo', 'purge'))

    assert result['ok'] is True
    assert result['operation'] == 'purge'
    assert result['plan']['pluginId'] == 'demo'
    assert result['plan']['destructiveCount'] == EXPECTED_PURGE_DESTRUCTIVE_COUNT
    assert purge_plan_gateway.calls == ['demo']


def test_plugin_runtime_precheck_upgrade_includes_version_state(tmp_path: Path) -> None:
    """校验插件升级预检会返回版本和数据库状态。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.2.0
backend:
  module: plugins.demo
""",
    )
    create_controller_dir(plugin_root)
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
    """校验插件运行时可根据 manifest 生成 Markdown 文档片段。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
description: 文档生成示例
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
