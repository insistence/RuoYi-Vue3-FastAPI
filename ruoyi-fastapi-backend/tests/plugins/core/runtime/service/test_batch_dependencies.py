# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_runtime_check_deps_reports_dependency_items(tmp_path: Path) -> None:
    """
    校验插件依赖专项检查返回稳定负载。

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
  npm:
    - vue>=3.5.0
""",
    )

    payload = build_runtime(backend_root).check_plugin_dependencies('demo')

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['missingDependencies'] == ['missing-python']
    assert len(payload['dependencies']) == EXPECTED_DEPENDENCY_COUNT


def test_plugin_runtime_plan_plugins_returns_dependency_order(tmp_path: Path) -> None:
    """
    校验插件运行时可以生成批量操作拓扑计划。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
enabled: true
backend:
  module: plugins.base
""",
    )

    payload = build_runtime(backend_root).plan_plugins('install', ['app'])

    assert payload['ok'] is True
    assert payload['operation'] == 'install'
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['plan']['items'][0]['requested'] is False
    assert payload['plan']['items'][1]['requested'] is True


def test_plugin_runtime_plan_plugins_reports_blockers(tmp_path: Path) -> None:
    """
    校验插件运行时计划会输出阻塞项。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    - missing
""",
    )

    payload = build_runtime(backend_root).plan_plugins('install', ['app'])

    assert payload['ok'] is False
    assert payload['plan']['blockerCount'] == 1
    assert payload['plan']['blockers'][0]['status'] == 'missing'


def test_plugin_runtime_batch_plugins_dry_run_returns_plan(tmp_path: Path) -> None:
    """
    校验插件批量执行 dry-run 只返回拓扑计划，执行汇总只统计显式选择插件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
enabled: true
backend:
  module: plugins.base
""",
    )

    payload = asyncio.run(build_runtime(backend_root).batch_plugins('install', ['app'], dry_run=True))

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['continueOnError'] is False
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['executed'] == []
    assert payload['failed'] is None
    assert payload['summary'] == {'total': 1, 'succeeded': 0, 'failed': 0, 'skipped': 1}


def test_plugin_runtime_batch_plugins_stops_when_plan_has_blockers(tmp_path: Path) -> None:
    """
    校验插件批量执行遇到计划阻塞时不会执行写操作。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    - missing
""",
    )
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    payload = asyncio.run(build_runtime_with_gateway(backend_root, gateway).batch_plugins('install', ['app']))

    assert payload['ok'] is False
    assert payload['continueOnError'] is False
    assert payload['plan']['blockerCount'] == 1
    assert payload['executed'] == []
    assert payload['failed'] is None
    assert payload['summary'] == {'total': 1, 'succeeded': 0, 'failed': 0, 'skipped': 1}
    assert FakePluginService.upsert_called is False
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['message'] == '插件批量操作计划存在阻塞项，未执行任何写操作'


def test_plugin_runtime_batch_plugins_executes_requested_plugins_only(tmp_path: Path) -> None:
    """
    校验插件批量执行只执行显式选择插件，依赖插件只参与计划校验和排序展示。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
frontend:
  menus: []
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
enabled: true
backend:
  module: plugins.base
frontend:
  menus: []
""",
    )
    create_controller_dir(backend_root / 'plugins' / 'app')
    create_controller_dir(backend_root / 'plugins' / 'base')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='base', installed_version='1.0.0', enabled='0', status='installed')
    ]

    payload = asyncio.run(build_runtime_with_gateway(backend_root, gateway).batch_plugins('install', ['app']))

    assert payload['ok'] is True
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['plan']['requestedPluginIds'] == ['app']
    assert [item['pluginId'] for item in payload['executed']] == ['app']
    assert all(item['status'] == 'success' for item in payload['executed'])
    assert all(isinstance(item['durationMs'], int) for item in payload['executed'])
    assert all(item['exitCode'] == 0 for item in payload['executed'])
    assert payload['summary'] == {'total': 1, 'succeeded': 1, 'failed': 0, 'skipped': 0}
    assert payload['failed'] is None
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['summary']['succeeded'] == 1


def test_plugin_runtime_batch_plugins_continue_on_error_runs_remaining_items(tmp_path: Path) -> None:
    """
    校验插件批量执行开启 continue-on-error 后会继续执行后续插件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    for plugin_id in ['alpha', 'beta', 'gamma']:
        write_manifest(
            backend_root / 'plugins' / plugin_id,
            f"""
id: {plugin_id}
name: {plugin_id.title()}
version: 1.0.0
enabled: true
backend:
  module: plugins.{plugin_id}
frontend:
  menus: []
""",
        )

    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()
    FakePluginService.operation_logs = [
        SimpleNamespace(
            payload={'ok': True, 'operation': 'install', 'pluginId': 'demo', 'message': 'installed'},
            dry_run=False,
            continue_on_error=False,
        ),
        SimpleNamespace(
            payload={'ok': True, 'operation': 'install', 'pluginId': 'other', 'message': 'other installed'},
            dry_run=False,
            continue_on_error=False,
        ),
    ]
    runtime = build_runtime_with_gateway(backend_root, gateway)
    executed_plugin_ids = []

    async def fake_execute(operation: str, plugin_id: str) -> dict[str, object]:
        """
        测试用单插件执行函数。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 单插件执行负载
        """
        executed_plugin_ids.append(plugin_id)
        return {
            'ok': plugin_id != 'beta',
            'message': '失败' if plugin_id == 'beta' else '成功',
            'pluginId': plugin_id,
        }

    runtime._execute_batch_plugin_item = fake_execute

    payload = asyncio.run(runtime.batch_plugins('install', ['alpha', 'beta', 'gamma'], continue_on_error=True))

    assert payload['ok'] is False
    assert payload['continueOnError'] is True
    assert executed_plugin_ids == ['alpha', 'beta', 'gamma']
    assert [item['pluginId'] for item in payload['executed']] == ['alpha', 'beta', 'gamma']
    assert payload['failed']['pluginId'] == 'beta'
    assert payload['summary'] == {'total': 3, 'succeeded': 2, 'failed': 1, 'skipped': 0}


def test_plugin_runtime_batch_plugins_dry_run_does_not_record_operation_log(tmp_path: Path) -> None:
    """
    校验插件批量执行 dry-run 不写入审计日志。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
frontend:
  menus: []
""",
    )
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    payload = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).batch_plugins('install', ['demo'], dry_run=True)
    )

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert FakePluginService.operation_logs == []


def test_plugin_runtime_install_deps_dry_run_returns_plan(tmp_path: Path) -> None:
    """
    校验插件依赖安装 dry-run 返回安装计划且不执行安装。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    expected_plan_count = 3
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
  npm:
    - missing-npm
  npmDev:
    - missing-dev-npm
""",
    )

    payload = build_runtime(backend_root).install_plugin_dependencies('demo', dry_run=True)

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['planCount'] == expected_plan_count
    assert payload['plan'][0]['kind'] == 'python'
    assert payload['plan'][0]['command'][1:4] == ['-m', 'pip', 'install']
    assert payload['plan'][1]['kind'] == 'npm'
    assert payload['plan'][1]['command'] == ['npm', 'install', 'missing-npm']
    assert payload['plan'][2]['kind'] == 'npmDev'
    assert payload['plan'][2]['command'] == ['npm', 'install', '--save-dev', 'missing-dev-npm']


def test_plugin_runtime_blocks_state_changes_in_service_mode(tmp_path: Path) -> None:
    """
    校验服务运行模式下阻断插件状态变更。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
""",
    )
    runtime = build_runtime(backend_root)
    runtime.runtime_environment.backend_runtime_mode = 'service'

    payload = asyncio.run(runtime.install_plugin('demo', dry_run=True))

    assert payload['ok'] is False
    assert payload['status'] == 'blocked'
    assert payload['capability']['backendRuntimeManageable'] is False
    assert 'install' in payload['capability']['blockedOperations']


def test_plugin_runtime_blocks_frontend_plugin_dependency_install_in_built_mode(tmp_path: Path) -> None:
    """
    校验已构建前端模式下阻断前端源码插件依赖安装。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
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
  - demo:list
dependencies:
  npm:
    - missing-npm
""",
    )
    create_frontend_view(backend_root, 'demo')
    runtime = build_runtime(backend_root)
    runtime.runtime_environment.frontend_mode = 'built'

    payload = runtime.install_plugin_dependencies('demo', dry_run=True)

    assert payload['ok'] is False
    assert payload['status'] == 'blocked'
    assert payload['capability']['frontendRuntimeManageable'] is False
    assert 'dependency_install' in payload['capability']['blockedOperations']
