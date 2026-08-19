import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import plugins.core.runtime.service.audit as audit_module
from plugins.core.runtime.service.audit import PluginAuditUseCase
from plugins.core.runtime.service.dependencies import PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS
from plugins.core.validation.dependency_policy import DependencyInstallPolicyConfig
from tests.plugins.core.runtime.fakes import (
    EXPECTED_DEPENDENCY_COUNT,
    FakePluginRuntimeGateway,
    FakePluginService,
    build_runtime,
    build_runtime_with_gateway,
    create_controller_dir,
    create_frontend_view,
    write_manifest,
)


def test_plugin_runtime_check_deps_reports_dependency_items(tmp_path: Path) -> None:
    """校验插件依赖专项检查返回稳定负载。"""
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
    """校验插件运行时可以生成批量操作拓扑计划。"""
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

    payload = build_runtime(backend_root).plan_plugins('install', ['app'])

    assert payload['ok'] is True
    assert payload['operation'] == 'install'
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['plan']['items'][0]['requested'] is False
    assert payload['plan']['items'][1]['requested'] is True


def test_plugin_runtime_plan_plugins_reports_blockers(tmp_path: Path) -> None:
    """校验插件运行时计划会输出阻塞项。"""
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


def test_plugin_runtime_plan_plugins_reports_database_state_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验批量计划会显式输出数据库状态读取错误。"""
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

    payload = runtime.plan_plugins('install', ['app'])

    assert payload['databaseAvailable'] is False
    assert payload['databaseError'] == 'db unavailable'


def test_record_plugin_failure_state_logs_and_swallows_persistence_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验失败状态辅助写入异常会记录日志且不影响主流程。"""
    logged_messages = []

    class BrokenAuditGateway:
        """
        测试用异常审计网关。
        """

        @staticmethod
        async def mark_plugin_error(plugin_id: str, error_message: str) -> None:
            """模拟标记插件异常失败。"""
            raise RuntimeError('db unavailable')

    def fake_exception(message: str, *args: object) -> None:
        """构造测试用批量操作异常。"""
        logged_messages.append(message % args)

    monkeypatch.setattr(audit_module.logger, 'exception', fake_exception)
    use_case = PluginAuditUseCase(SimpleNamespace(audit_gateway=BrokenAuditGateway()))

    asyncio.run(use_case.record_plugin_failure_state({'ok': False, 'pluginId': 'demo'}, '失败'))

    assert logged_messages == ['记录插件失败状态失败：plugin_id=demo']


def test_plugin_runtime_batch_plugins_dry_run_returns_plan(tmp_path: Path) -> None:
    """校验插件批量执行 dry-run 只返回拓扑计划，执行汇总只统计显式选择插件。"""
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

    payload = asyncio.run(build_runtime(backend_root).batch_plugins('install', ['app'], dry_run=True))

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['continueOnError'] is False
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['executed'] == []
    assert payload['failed'] is None
    assert payload['summary'] == {'total': 1, 'succeeded': 0, 'failed': 0, 'skipped': 1}


def test_plugin_runtime_batch_plugins_stops_when_plan_has_blockers(tmp_path: Path) -> None:
    """校验插件批量执行遇到计划阻塞时不会执行写操作。"""
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
    gateway = FakePluginRuntimeGateway()

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
    """校验插件批量执行只执行显式选择插件，依赖插件只参与计划校验和排序展示。"""
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
backend:
  module: plugins.base
frontend:
  menus: []
""",
    )
    create_controller_dir(backend_root / 'plugins' / 'app')
    create_controller_dir(backend_root / 'plugins' / 'base')
    gateway = FakePluginRuntimeGateway()
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
    assert payload['summary'] == {'total': 1, 'succeeded': 1, 'failed': 0, 'skipped': 0}
    assert payload['failed'] is None
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['summary']['succeeded'] == 1


def test_plugin_runtime_batch_plugins_continue_on_error_runs_remaining_items(tmp_path: Path) -> None:
    """校验插件批量执行开启 continue-on-error 后会继续执行后续插件。"""
    backend_root = tmp_path / 'backend'
    for plugin_id in ['alpha', 'beta', 'gamma']:
        write_manifest(
            backend_root / 'plugins' / plugin_id,
            f"""
id: {plugin_id}
name: {plugin_id.title()}
version: 1.0.0
backend:
  module: plugins.{plugin_id}
frontend:
  menus: []
""",
        )

    gateway = FakePluginRuntimeGateway()
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
        """测试用单插件执行函数。"""
        executed_plugin_ids.append(plugin_id)
        return {
            'ok': plugin_id != 'beta',
            'message': '失败' if plugin_id == 'beta' else '成功',
            'pluginId': plugin_id,
        }

    runtime.execute_batch_plugin_item = fake_execute

    payload = asyncio.run(runtime.batch_plugins('install', ['alpha', 'beta', 'gamma'], continue_on_error=True))

    assert payload['ok'] is False
    assert payload['continueOnError'] is True
    assert executed_plugin_ids == ['alpha', 'beta', 'gamma']
    assert [item['pluginId'] for item in payload['executed']] == ['alpha', 'beta', 'gamma']
    assert payload['failed']['pluginId'] == 'beta'
    assert payload['summary'] == {'total': 3, 'succeeded': 2, 'failed': 1, 'skipped': 0}


def test_plugin_runtime_batch_plugins_dry_run_does_not_record_operation_log(tmp_path: Path) -> None:
    """校验插件批量执行 dry-run 不写入审计日志。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.demo
frontend:
  menus: []
""",
    )
    gateway = FakePluginRuntimeGateway()

    payload = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).batch_plugins('install', ['demo'], dry_run=True)
    )

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert FakePluginService.operation_logs == []


def test_plugin_runtime_install_deps_dry_run_returns_plan(tmp_path: Path) -> None:
    """校验插件依赖安装 dry-run 返回安装计划且不执行安装。"""
    backend_root = tmp_path / 'backend'
    expected_plan_count = 3
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


def test_plugin_runtime_dependency_install_uses_default_command_timeout(tmp_path: Path) -> None:
    """校验插件依赖安装命令使用默认超时时间。"""
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
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    payload = runtime.install_plugin_dependencies(
        'demo',
        policy_config=DependencyInstallPolicyConfig(mode='explicit', env='dev'),
        confirmed=True,
    )

    assert payload['ok'] is True
    assert len(gateway.commands) == 1
    assert gateway.commands[0][2] == PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS


def test_plugin_runtime_dependency_install_reports_live_progress(tmp_path: Path) -> None:
    """校验插件依赖安装会转发命令输出并报告单项开始、完成状态。"""
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
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)
    progress: list[tuple[str, str]] = []

    payload = runtime.install_plugin_dependencies(
        'demo',
        policy_config=DependencyInstallPolicyConfig(mode='explicit', env='dev'),
        confirmed=True,
        output_callback=lambda kind, text: progress.append((kind, text)),
    )

    assert payload['ok'] is True
    assert progress == [
        ('status', '[1/1] 开始安装：missing-python\n'),
        ('stdout', '1 passed\n'),
        ('status', '[1/1] 安装完成：missing-python\n'),
    ]


def test_plugin_runtime_dependency_install_plan_only_policy_blocks_command_execution(tmp_path: Path) -> None:
    """校验 plan_only 策略会阻断真实依赖安装并返回策略 payload。"""
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
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    payload = runtime.install_plugin_dependencies(
        'demo',
        policy_config=DependencyInstallPolicyConfig(mode='plan_only', env='dev'),
        confirmed=True,
    )

    assert payload['ok'] is False
    assert payload['dryRun'] is False
    assert payload['policy']['mode'] == 'plan_only'
    assert payload['policy']['allowed'] is False
    assert '当前策略仅允许生成依赖安装计划' in payload['policy']['reasons']
    assert gateway.commands == []


def test_plugin_runtime_dependency_install_policy_block_records_operation_log(tmp_path: Path) -> None:
    """校验 standalone 依赖安装被策略阻断时仍记录审计日志。"""
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
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    payload = runtime.install_plugin_dependencies(
        'demo',
        policy_config=DependencyInstallPolicyConfig(mode='plan_only', env='dev'),
        confirmed=True,
    )

    assert payload['ok'] is False
    assert gateway.commands == []
    assert len(FakePluginService.operation_logs) == 1
    log_payload = FakePluginService.operation_logs[0].payload
    assert log_payload['operation'] == 'dependency_install'
    assert log_payload['pluginId'] == 'demo'
    assert log_payload['confirmed'] is True
    assert log_payload['policy']['allowed'] is False


def test_plugin_runtime_dependency_install_explicit_policy_requires_confirmation(tmp_path: Path) -> None:
    """校验 explicit 策略未确认时不执行真实依赖安装。"""
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
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    payload = runtime.install_plugin_dependencies(
        'demo',
        policy_config=DependencyInstallPolicyConfig(mode='explicit', env='dev'),
        confirmed=False,
    )

    assert payload['ok'] is False
    assert payload['policy']['mode'] == 'explicit'
    assert payload['policy']['requirements'] == ['需要显式确认 --yes']
    assert gateway.commands == []


def test_plugin_runtime_dependency_install_success_records_operation_log(tmp_path: Path) -> None:
    """校验 standalone 依赖安装成功时记录策略、确认和结果审计。"""
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
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    payload = runtime.install_plugin_dependencies(
        'demo',
        policy_config=DependencyInstallPolicyConfig(mode='explicit', env='dev'),
        confirmed=True,
    )

    assert payload['ok'] is True
    assert len(gateway.commands) == 1
    assert len(FakePluginService.operation_logs) == 1
    log_payload = FakePluginService.operation_logs[0].payload
    assert log_payload['operation'] == 'dependency_install'
    assert log_payload['pluginId'] == 'demo'
    assert log_payload['confirmed'] is True
    assert log_payload['policy']['mode'] == 'explicit'
    assert log_payload['policy']['allowed'] is True
    assert log_payload['results'][0]['returnCode'] == 0


def test_plugin_runtime_dependency_install_async_uses_default_command_timeout(tmp_path: Path) -> None:
    """校验插件依赖异步安装命令使用默认超时时间。"""
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
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)
    discovered_plugin = runtime.context.get_discovered_plugin('demo')
    assert discovered_plugin is not None
    dependency_result = runtime.dependencies.dependency_checker.check_manifest(discovered_plugin.manifest)

    payload = asyncio.run(
        runtime.install_plugin_dependencies_from_result_async(
            'demo',
            dependency_result,
            discovered_plugin=discovered_plugin,
            policy_config=DependencyInstallPolicyConfig(mode='explicit', env='dev'),
            confirmed=True,
        )
    )

    assert payload['ok'] is True
    assert len(gateway.commands) == 1
    assert gateway.commands[0][2] == PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS


def test_plugin_runtime_blocks_state_changes_in_service_mode(tmp_path: Path) -> None:
    """校验服务运行模式下阻断插件状态变更。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.demo
""",
    )
    runtime = build_runtime(backend_root)
    runtime.dependencies.runtime_environment.backend_runtime_mode = 'service'

    payload = asyncio.run(runtime.install_plugin('demo', dry_run=True))

    assert payload['ok'] is False
    assert payload['status'] == 'blocked'
    assert payload['capability']['backendRuntimeManageable'] is False
    assert 'install' in payload['capability']['blockedOperations']


def test_plugin_runtime_allows_only_cli_dependency_install_in_built_service_mode(tmp_path: Path) -> None:
    """校验生产服务模式拦截 Web 入口，仅 CLI 可安装后端依赖。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
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
  - demo:list
dependencies:
  python:
    - missing-python
  npm:
    - missing-npm
""",
    )
    create_frontend_view(backend_root, 'demo')
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)
    runtime.dependencies.runtime_environment.frontend_mode = 'built'
    runtime.dependencies.runtime_environment.backend_runtime_mode = 'service'
    runtime.refresh_dependency_checker()

    web_payload = runtime.install_plugin_dependencies(
        'demo',
        policy_config=DependencyInstallPolicyConfig(
            mode='explicit',
            env='prod',
            allow_prod=True,
            allow_prod_install=True,
            require_lockfile=False,
            require_allowlist=False,
        ),
        confirmed=True,
    )
    cli_policy_blocked_payload = runtime.install_plugin_dependencies_from_cli(
        'demo',
        policy_config=DependencyInstallPolicyConfig(mode='plan_only', env='prod'),
        confirmed=True,
    )
    assert gateway.commands == []

    cli_payload = runtime.install_plugin_dependencies_from_cli(
        'demo',
        policy_config=DependencyInstallPolicyConfig.from_cli_environment(
            env='prod',
            allow_prod=True,
            allow_unlisted=True,
            require_lockfile=False,
        ),
        confirmed=True,
    )

    assert web_payload['ok'] is False
    assert web_payload['status'] == 'blocked'
    assert 'dependency_install' in web_payload['capability']['blockedOperations']
    assert cli_policy_blocked_payload['ok'] is False
    assert cli_policy_blocked_payload['policy']['allowed'] is False
    assert 'capability' not in cli_policy_blocked_payload
    assert cli_payload['ok'] is True
    assert 'capability' not in cli_payload
    assert [item['kind'] for item in cli_payload['dependencies']] == ['python', 'npm']
    assert cli_payload['dependencies'][1]['status'] == 'skipped'
    assert len(gateway.commands) == 1
    assert gateway.commands[0][0][1:4] == ['-m', 'pip', 'install']
