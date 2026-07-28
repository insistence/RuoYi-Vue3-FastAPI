import asyncio
from pathlib import Path
from types import SimpleNamespace

from plugins.core.lifecycle.migration import PluginMigrationRunner
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
    write_manifest,
)


class MigrationOnlyGateway:
    """
    仅提供插件 migration 历史能力的测试网关。
    """

    def __init__(self) -> None:
        """初始化测试 migration 历史网关。"""
        self.records = [
            SimpleNamespace(
                plugin_id='demo',
                migration_path='migrations/001.sql',
                migration_checksum='checksum-1',
                version='1.0.0',
                statement_count=1,
                status='running',
                error_message='interrupted',
                attempt_count=1,
                started_time=None,
                finished_time=None,
                create_time=None,
                update_time=None,
            ),
            SimpleNamespace(
                plugin_id='demo',
                migration_path='migrations/002.sql',
                migration_checksum='checksum-2',
                version='1.0.0',
                statement_count=1,
                status='success',
                error_message=None,
                attempt_count=1,
                started_time=None,
                finished_time=None,
                create_time=None,
                update_time=None,
            ),
        ]
        self.list_calls: list[tuple[str, str | None]] = []
        self.mark_calls: list[tuple[str, str, str, str | None]] = []

    async def list_plugin_migrations(self, plugin_id: str, status: str | None = None) -> list[object]:
        """查询测试 migration 历史。"""
        self.list_calls.append((plugin_id, status))
        return [
            record
            for record in self.records
            if record.plugin_id == plugin_id and (status is None or record.status == status)
        ]

    async def get_plugin_migration(self, plugin_id: str, migration_path: str) -> object | None:
        """获取测试 migration 历史。"""
        for record in reversed(self.records):
            if record.plugin_id == plugin_id and record.migration_path == migration_path:
                return record
        return None

    async def mark_plugin_migration_status(
        self,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> object | None:
        """标记测试 migration 历史状态。"""
        self.mark_calls.append((plugin_id, migration_path, status, error_message))
        record = await self.get_plugin_migration(plugin_id, migration_path)
        if record:
            record.status = status
            record.error_message = error_message
        return record

    def get_plugin_service(self) -> object:
        """禁止 migration 链路回退到管理服务胖接口。"""
        raise AssertionError('migration 历史不应依赖 PluginManagementServiceProtocol')


def test_plugin_runtime_lists_plugin_migration_history(tmp_path: Path) -> None:
    """校验运行时可以查询插件 migration 历史。"""
    backend_root = tmp_path / 'backend'
    gateway = FakePluginRuntimeGateway()
    FakePluginService.migration_records = [
        gateway.build_migration_record('demo', 'migrations/001.sql', 'checksum-1', '1.0.0', 1, 'success'),
        gateway.build_migration_record('demo', 'migrations/002.sql', 'checksum-2', '1.0.0', 1, 'running'),
        gateway.build_migration_record('other', 'migrations/001.sql', 'checksum-3', '1.0.0', 1, 'running'),
    ]

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).list_plugin_migrations('demo', 'running'))

    assert result['ok'] is True
    assert result['pluginId'] == 'demo'
    assert result['status'] == 'running'
    assert result['count'] == 1
    assert result['migrations'][0]['migrationPath'] == 'migrations/002.sql'


def test_plugin_runtime_migration_uses_migration_history_port(tmp_path: Path) -> None:
    """校验 migration 查询和人工标记只依赖 migration 历史窄端口。"""
    gateway = MigrationOnlyGateway()
    runtime = PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(tmp_path / 'backend'),
        dependency_checker=PluginDependencyChecker(),
        gateways=PluginRuntimeGatewayOverrides(migration_history_gateway=gateway),
    )

    list_result = asyncio.run(runtime.list_plugin_migrations('demo', 'running'))
    mark_result = asyncio.run(
        runtime.mark_plugin_migration_failed(
            'demo',
            'migrations/001.sql',
            note='retry later',
            record_operation_log=False,
        )
    )

    assert list_result['ok'] is True
    assert list_result['count'] == 1
    assert list_result['migrations'][0]['migrationPath'] == 'migrations/001.sql'
    assert mark_result['ok'] is True
    assert mark_result['operation'] == 'migration_mark_failed'
    assert gateway.records[0].status == 'failed'
    assert gateway.records[0].error_message == 'retry later'
    assert gateway.list_calls == [('demo', 'running')]
    assert gateway.mark_calls == [('demo', 'migrations/001.sql', 'failed', 'retry later')]


def test_plugin_runtime_marks_plugin_migration_success_and_records_audit(tmp_path: Path) -> None:
    """校验运行时可以人工标记 migration 成功并记录审计日志。"""
    backend_root = tmp_path / 'backend'
    gateway = FakePluginRuntimeGateway()
    migration = gateway.build_migration_record(
        'demo',
        'migrations/001.sql',
        'checksum-1',
        '1.0.0',
        1,
        'running',
        'interrupted',
    )
    FakePluginService.migration_records = [migration]

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).mark_plugin_migration_success(
            'demo',
            'migrations/001.sql',
            note='confirmed',
        )
    )

    assert result['ok'] is True
    assert result['operation'] == 'migration_mark_success'
    assert migration.status == 'success'
    assert migration.error_message is None
    assert FakePluginService.operation_logs[0].payload['operation'] == 'migration_mark_success'


def test_plugin_runtime_marks_plugin_migration_failed(tmp_path: Path) -> None:
    """校验运行时可以人工标记 migration 失败以允许后续重试。"""
    backend_root = tmp_path / 'backend'
    gateway = FakePluginRuntimeGateway()
    migration = gateway.build_migration_record('demo', 'migrations/001.sql', 'checksum-1', '1.0.0', 1, 'running')
    FakePluginService.migration_records = [migration]

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).mark_plugin_migration_failed(
            'demo',
            'migrations/001.sql',
            note='not applied',
        )
    )

    assert result['ok'] is True
    assert result['operation'] == 'migration_mark_failed'
    assert migration.status == 'failed'
    assert migration.error_message == 'not applied'


def test_plugin_runtime_rejects_invalid_plugin_migration_manual_transition(tmp_path: Path) -> None:
    """校验人工恢复不能把已成功 migration 标记为失败以触发重跑。"""
    backend_root = tmp_path / 'backend'
    gateway = FakePluginRuntimeGateway()
    migration = gateway.build_migration_record('demo', 'migrations/001.sql', 'checksum-1', '1.0.0', 1, 'success')
    FakePluginService.migration_records = [migration]

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).mark_plugin_migration_failed(
            'demo',
            'migrations/001.sql',
            note='should not happen',
        )
    )

    assert result['ok'] is False
    assert result['operation'] == 'migration_mark_failed'
    assert '不能人工标记为失败' in result['message']
    assert migration.status == 'success'
    assert migration.error_message is None
    assert FakePluginService.operation_logs == []


def test_plugin_runtime_install_plugin_runs_install_hook(tmp_path: Path) -> None:
    """校验插件安装会执行 manifest 声明的 on_install 钩子。"""
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
  hooks:
    onInstall: hooks:on_install
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'hooks.py').write_text(
        'async def on_install(context):\n    context.query_db.install_hook_ran = context.plugin_id\n',
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['hooks'][0]['hook_name'] == 'on_install'
    assert gateway.session_local.sessions[0].install_hook_ran == 'demo'


def test_plugin_runtime_install_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """校验插件安装执行失败时返回失败生命周期步骤。"""
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
  hooks:
    onInstall: hooks:on_install
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'hooks.py').write_text(
        "async def on_install(context):\n    raise RuntimeError('install hook failed')\n",
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['operation'] == 'install'
    assert result['failedStep'] == 'run_install_hook'
    assert 'install hook failed' in result['error']
    assert FakePluginService.marked_errors == [('demo', '插件安装失败：install hook failed')]


def test_plugin_runtime_upgrade_plugin_dry_run_reports_version_state(tmp_path: Path) -> None:
    """校验插件升级 dry-run 会返回版本状态和动作计划。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.1.0
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
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='pending_upgrade',
    )

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo', dry_run=True))

    assert result['ok'] is True
    assert result['dryRun'] is True
    assert result['installed'] is True
    assert result['installedVersion'] == '1.0.0'
    assert result['currentVersion'] == '1.1.0'
    assert result['needsUpgrade'] is True
    assert result['databaseAvailable'] is True
    assert result['databaseError'] is None
    assert result['actions'][0]['name'] == 'check_installed_version'
    assert result['manifestOk'] is True
    assert result['manifestWarnings'][0]['level'] == 'warning'
    assert result['manifestWarnings'][0]['kind'] == 'secret_config_default'
    assert FakePluginService.upsert_called is False


def test_plugin_runtime_upgrade_dry_run_reports_changed_recorded_migration(tmp_path: Path) -> None:
    """校验插件升级 dry-run 会提前报告已执行 migration 内容变更。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.1.0
backend:
  module: plugins.demo
  migrations:
    - migrations/001_demo.sql
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'migrations').mkdir()
    migration_file = plugin_root / 'migrations' / '001_demo.sql'
    migration_file.write_text('select 1;\n', encoding='utf-8')
    old_checksum = PluginMigrationRunner._calculate_checksum(migration_file)
    migration_file.write_text('select 2;\n', encoding='utf-8')
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='pending_upgrade',
    )
    FakePluginService.migration_checksums = {('demo', 'migrations/001_demo.sql'): old_checksum}

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo', dry_run=True))

    assert result['ok'] is True
    assert result['message'] == '插件升级演练完成，未执行实际写入'
    assert result['manifestOk'] is False
    assert result['manifestIssues'][0]['kind'] == 'migration_checksum_changed'
    assert result['needsUpgrade'] is True
    assert FakePluginService.upsert_called is False


def test_plugin_runtime_upgrade_plugin_rejects_manifest_errors(tmp_path: Path) -> None:
    """校验插件升级会被 manifest error 阻断。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.1.0
backend:
  module: plugins.demo
compatibility:
  pythonVersion: '>=99.0.0'
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='pending_upgrade',
    )

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件 manifest 检查失败，升级已中止'
    assert result['installed'] is True
    assert result['needsUpgrade'] is True
    assert result['manifestOk'] is False
    assert result['manifestIssues'][0]['kind'] == 'compatibility_unsatisfied'
    assert FakePluginService.upsert_called is False
    assert gateway.session_local.sessions[0].committed is False


def test_plugin_runtime_upgrade_plugin_rejects_uninstalled_plugin(tmp_path: Path) -> None:
    """校验未安装插件执行升级会被拒绝。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.1.0
backend:
  module: plugins.demo
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件尚未安装，升级已中止'
    assert result['installed'] is False
    assert gateway.session_local.sessions[0].committed is False
    assert FakePluginService.marked_errors == [('demo', '插件尚未安装，升级已中止')]


def test_plugin_runtime_upgrade_plugin_skips_latest_version(tmp_path: Path) -> None:
    """校验已是最新版本时升级命令不会写数据库。"""
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
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='installed',
    )

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo'))

    assert result['ok'] is True
    assert result['needsUpgrade'] is False
    assert result['actions'] == []
    assert FakePluginService.upsert_called is False
    assert gateway.session_local.sessions[0].committed is False


def test_plugin_runtime_upgrade_plugin_skips_older_source_version(tmp_path: Path) -> None:
    """校验源码版本低于已安装版本时升级命令不会写数据库。"""
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
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.10.0',
        enabled='0',
        status='installed',
    )

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo'))

    assert result['ok'] is True
    assert result['needsUpgrade'] is False
    assert result['installedVersion'] == '1.10.0'
    assert result['currentVersion'] == '1.2.0'
    assert FakePluginService.upsert_called is False
    assert gateway.session_local.sessions[0].committed is False


def test_plugin_runtime_upgrade_plugin_persists_upgrade(tmp_path: Path) -> None:
    """校验插件升级会执行幂等写入、seed、on_upgrade 钩子并提交事务。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.1.0
backend:
  module: plugins.demo
  migrations:
    - migrations/001_upgrade.py
  seeds:
    - seeds/demo_seed.py
  hooks:
    onUpgrade: hooks:on_upgrade
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_upgrade.py').write_text(
        'async def run(query_db):\n    query_db.upgrade_migration_ran = True\n',
        encoding='utf-8',
    )
    (plugin_root / 'seeds').mkdir()
    (plugin_root / 'seeds' / 'demo_seed.py').write_text(
        'async def run(query_db):\n    query_db.upgrade_seed_ran = True\n',
        encoding='utf-8',
    )
    (plugin_root / 'hooks.py').write_text(
        'async def on_upgrade(context):\n    context.query_db.upgrade_hook_ran = context.plugin_id\n',
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='pending_upgrade',
    )

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo'))

    assert result['ok'] is True
    assert result['message'] == '插件升级完成'
    assert result['installedVersion'] == '1.0.0'
    assert result['currentVersion'] == '1.1.0'
    assert FakePluginService.upsert_called is True
    assert FakePluginService.install_plugin_menu_called_with == ('demo', True)
    assert FakePluginService.install_plugin_job_called_with == ('demo', True)
    assert FakePluginService.mark_installed_called is True
    assert any(getattr(session, 'upgrade_migration_ran', False) is True for session in gateway.session_local.sessions)
    assert any(getattr(session, 'upgrade_seed_ran', False) is True for session in gateway.session_local.sessions)
    assert any(getattr(session, 'upgrade_hook_ran', None) == 'demo' for session in gateway.session_local.sessions)
    assert gateway.session_local.committed_session is not None
    assert result['migrations'][0]['migration_path'] == 'migrations/001_upgrade.py'
    assert result['hooks'][0]['hook_name'] == 'on_upgrade'


def test_plugin_runtime_upgrade_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """校验插件升级执行失败时返回失败生命周期步骤。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.1.0
backend:
  module: plugins.demo
  migrations:
    - migrations/001_upgrade.sql
  hooks:
    onUpgrade: hooks:on_upgrade
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_upgrade.sql').write_text('select 4;\n', encoding='utf-8')
    (plugin_root / 'hooks.py').write_text(
        "async def on_upgrade(context):\n    raise RuntimeError('upgrade hook failed')\n",
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='pending_upgrade',
    )

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo'))

    assert result['ok'] is False
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'upgrade'
    assert result['failedStep'] == 'run_upgrade_hook'
    assert 'upgrade hook failed' in result['error']
    assert FakePluginService.marked_errors == [('demo', '插件升级失败：upgrade hook failed')]
    assert [record.status for record in FakePluginService.migration_records] == ['running', 'success']
    migration_session = gateway.session_local.executed_session
    assert migration_session is not None
    assert migration_session.executed_statements == ['select 4']
    assert migration_session is not gateway.session_local.sessions[0]
    assert migration_session.committed is True


def test_plugin_runtime_upgrade_plugin_uses_injected_dependencies(tmp_path: Path) -> None:
    """校验插件升级使用构造期注入的集中依赖对象。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.1.0
backend:
  module: plugins.demo
  migrations:
    - migrations/001_upgrade.sql
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_upgrade.sql').write_text('select 3;\n', encoding='utf-8')
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(
        plugin_id='demo',
        installed_version='1.0.0',
        enabled='0',
        status='pending_upgrade',
    )
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.upgrade_plugin('demo', record_operation_log=False))

    assert result['ok'] is True
    assert FakePluginService.upsert_called is True
    assert FakePluginService.mark_installed_called is True
    assert [record.status for record in FakePluginService.migration_records] == ['running', 'success']
    assert FakePluginService.migration_records[-1].migration_path == 'migrations/001_upgrade.sql'
    migration_session = gateway.session_local.executed_session
    assert migration_session is not None
    assert migration_session.executed_statements == ['select 3']
    assert migration_session is not gateway.session_local.sessions[0]
    assert migration_session.committed is True
    assert gateway.session_local.committed_session is not None


def test_plugin_runtime_set_plugin_enabled_dry_run_returns_actions(tmp_path: Path) -> None:
    """校验插件启停 dry-run 返回动作计划。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    create_controller_dir(plugin_root)

    result = asyncio.run(build_runtime(backend_root).set_plugin_enabled('demo', enabled=True, dry_run=True))

    assert result['ok'] is True
    assert result['dryRun'] is True
    assert result['operation'] == 'enable'
    assert [action['name'] for action in result['actions']] == [
        'check_plugin_dependencies',
        'update_plugin_enabled',
        'update_plugin_menu_status',
    ]
    assert result['manifestOk'] is True
    assert result['precheck']['structureErrors'] == []


def test_plugin_runtime_set_plugin_enabled_persists_state(tmp_path: Path) -> None:
    """校验插件启停会调用插件服务并提交事务。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('demo', enabled=True))

    assert result['ok'] is True
    assert FakePluginService.install_plugin_menu_called_with == ('demo', True)
    assert FakePluginService.update_enabled_called_with is not None
    assert FakePluginService.update_enabled_called_with[:2] == ('demo', True)
    assert FakePluginService.update_enabled_called_with[2].manifest.id == 'demo'
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'enable'


def test_plugin_runtime_set_plugin_enabled_uses_lifecycle_state_gateway_without_fat_service(
    tmp_path: Path,
) -> None:
    """校验插件启用通过生命周期状态窄端口写入，不回退到 fat state gateway。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    create_controller_dir(plugin_root)

    class NoFatLifecycleStateGateway(FakePluginRuntimeGateway):
        """
        禁止启用流程读取 fat state gateway 的测试适配器。
        """

        def __init__(self) -> None:
            """初始化测试生命周期状态网关。"""
            super().__init__()
            self.enabled_state_calls: list[tuple[str, bool, object | None]] = []

        def get_async_session_local(self) -> object:
            """禁止通过 state gateway 打开数据库会话。"""
            raise AssertionError('启用流程不应通过 state gateway 打开数据库会话')

        def get_plugin_service(self) -> object:
            """禁止通过 state gateway 获取管理服务。"""
            raise AssertionError('启用流程不应通过 state gateway 获取管理服务')

        async def set_plugin_enabled_state(
            self,
            plugin_id: str,
            enabled: bool,
            discovered_plugin: object | None = None,
        ) -> object:
            """通过窄端口更新插件启停状态。"""
            self.enabled_state_calls.append((plugin_id, enabled, discovered_plugin))
            async with self.session_local() as session:
                response = await FakePluginService.update_plugin_enabled_services(
                    session,
                    plugin_id,
                    enabled,
                    discovered_plugin,
                )
                if response.is_success and enabled and discovered_plugin:
                    await FakePluginService.install_plugin_menu_services(session, discovered_plugin, enabled=True)
                await session.commit()
                return response

    gateway = NoFatLifecycleStateGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('demo', enabled=True))

    assert result['ok'] is True
    assert gateway.enabled_state_calls[0][0:2] == ('demo', True)
    assert gateway.enabled_state_calls[0][2].manifest.id == 'demo'
    assert FakePluginService.install_plugin_menu_called_with == ('demo', True)
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_set_plugin_enabled_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """校验插件启用执行失败时返回失败生命周期步骤。"""
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
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()

    async def raise_enable_failure(
        query_db: object,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: object | None = None,
    ) -> object:
        """模拟启用插件失败。"""
        raise RuntimeError('enable update failed')

    original_update_enabled = FakePluginService.update_plugin_enabled_services
    FakePluginService.update_plugin_enabled_services = raise_enable_failure

    try:
        result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('demo', enabled=True))
    finally:
        FakePluginService.update_plugin_enabled_services = original_update_enabled

    assert result['ok'] is False
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'enable'
    assert result['failedStep'] == 'update_enabled_state'
    assert 'enable update failed' in result['error']
    assert FakePluginService.marked_errors == [('demo', '更新插件启停状态失败：enable update failed')]


def test_plugin_runtime_disable_blocks_enabled_dependents(tmp_path: Path) -> None:
    """校验停用被启用插件依赖的插件时会阻断写库。"""
    backend_root = tmp_path / 'backend'
    base_root = backend_root / 'plugins' / 'base'
    app_root = backend_root / 'plugins' / 'app'
    write_manifest(
        base_root,
        """
id: base
name: Base
version: 1.0.0
backend:
  module: plugins.base
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    write_manifest(
        app_root,
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
frontend:
  menus: []
dependencies:
  python: []
  npm: []
  plugins:
    - base
""",
    )
    create_controller_dir(base_root)
    create_controller_dir(app_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='base', installed_version='1.0.0', enabled='0', status='installed'),
        SimpleNamespace(plugin_id='app', installed_version='1.0.0', enabled='0', status='installed'),
    ]

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('base', enabled=False))

    assert result['ok'] is False
    assert result['message'] == '插件仍被已启用插件依赖，操作已中止'
    assert result['operation'] == 'disable'
    assert result['pluginDependencyErrors'][0]['status'] == 'dependent'
    assert result['pluginDependencyErrors'][0]['pluginId'] == 'app'
    assert FakePluginService.update_enabled_called_with is None


def test_plugin_runtime_disable_dry_run_reports_enabled_dependents(tmp_path: Path) -> None:
    """校验停用预演会暴露被依赖方检查结果但不失败。"""
    backend_root = tmp_path / 'backend'
    base_root = backend_root / 'plugins' / 'base'
    app_root = backend_root / 'plugins' / 'app'
    write_manifest(
        base_root,
        """
id: base
name: Base
version: 1.0.0
backend:
  module: plugins.base
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    write_manifest(
        app_root,
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
frontend:
  menus: []
dependencies:
  python: []
  npm: []
  plugins:
    - base
""",
    )
    create_controller_dir(base_root)
    create_controller_dir(app_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='base', installed_version='1.0.0', enabled='0', status='installed'),
        SimpleNamespace(plugin_id='app', installed_version='1.0.0', enabled='0', status='installed'),
    ]

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('base', enabled=False, dry_run=True)
    )

    assert result['ok'] is True
    assert result['dryRun'] is True
    assert result['pluginDependencyOk'] is False
    assert result['actions'][0]['name'] == 'check_plugin_dependents'
    assert FakePluginService.update_enabled_called_with is None


def test_plugin_runtime_set_plugin_enabled_uses_injected_dependencies(tmp_path: Path) -> None:
    """校验插件启用使用构造期注入的集中依赖对象。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.set_plugin_enabled('demo', enabled=True, record_operation_log=False))

    assert result['ok'] is True
    assert FakePluginService.install_plugin_menu_called_with == ('demo', True)
    assert FakePluginService.update_enabled_called_with is not None
    assert FakePluginService.update_enabled_called_with[:2] == ('demo', True)
    assert FakePluginService.update_enabled_called_with[2].manifest.id == 'demo'
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_check_reports_plugin_dependency_errors(tmp_path: Path) -> None:
    """校验插件检查会报告插件间依赖错误。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
  plugins:
    - missing
""",
    )
    create_controller_dir(plugin_root)

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is False
    assert payload['checks'][0]['pluginDependencyErrors'][0]['status'] == 'missing'
    assert payload['checks'][0]['pluginDependencyErrors'][0]['level'] == 'error'


def test_plugin_runtime_install_blocks_unsatisfied_plugin_dependency(tmp_path: Path) -> None:
    """校验插件安装会阻止未满足的插件间依赖。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
  plugins:
    - base
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件间依赖检查失败，安装已中止'
    assert result['pluginDependencyErrors'][0]['status'] == 'missing'
    assert FakePluginService.upsert_called is False
    assert FakePluginService.marked_errors == [('demo', '插件间依赖检查失败，安装已中止')]


def test_plugin_runtime_enable_blocks_unsatisfied_plugin_dependency(tmp_path: Path) -> None:
    """校验插件启用会阻止未满足的插件间依赖。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
  plugins:
    - base
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('demo', enabled=True))

    assert result['ok'] is False
    assert result['message'] == '插件间依赖检查失败，启用已中止'
    assert result['pluginDependencyErrors'][0]['status'] == 'missing'
    assert FakePluginService.update_enabled_called_with is None
    assert FakePluginService.marked_errors == [('demo', '插件间依赖检查失败，启用已中止')]


def test_plugin_runtime_disable_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """校验插件停用执行失败时返回失败生命周期步骤。"""
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
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()

    async def raise_disable_failure(
        query_db: object,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: object | None = None,
    ) -> object:
        """模拟禁用插件失败。"""
        raise RuntimeError('disable update failed')

    original_update_enabled = FakePluginService.update_plugin_enabled_services
    FakePluginService.update_plugin_enabled_services = raise_disable_failure

    try:
        result = asyncio.run(
            build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('demo', enabled=False)
        )
    finally:
        FakePluginService.update_plugin_enabled_services = original_update_enabled

    assert result['ok'] is False
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'disable'
    assert result['failedStep'] == 'update_enabled_state'
    assert 'disable update failed' in result['error']


def test_plugin_runtime_uninstall_plugin_dry_run_returns_safe_payload(tmp_path: Path) -> None:
    """校验插件安全卸载 dry-run 返回安全卸载语义。"""
    backend_root = tmp_path / 'backend'
    backend_root.mkdir()

    result = asyncio.run(build_runtime(backend_root).uninstall_plugin('demo', dry_run=True))

    assert result['ok'] is True
    assert result['operation'] == 'uninstall'
    assert result['enabled'] is False
    assert result['safeMode'] is True
    assert result['removesSource'] is False
    assert result['removesMenus'] is True


def test_plugin_runtime_uninstall_plugin_dry_run_includes_precheck_when_source_exists(tmp_path: Path) -> None:
    """校验插件安全卸载 dry-run 在源码存在时返回统一预检负载。"""
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
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    create_controller_dir(plugin_root)

    result = asyncio.run(build_runtime(backend_root).uninstall_plugin('demo', dry_run=True))

    assert result['ok'] is True
    assert result['operation'] == 'uninstall'
    assert result['manifestOk'] is True
    assert result['precheck']['structureErrors'] == []
    assert result['safeMode'] is True


def test_plugin_runtime_uninstall_plugin_blocks_enabled_dependents(tmp_path: Path) -> None:
    """校验卸载被启用插件依赖的插件时会阻断写库。"""
    backend_root = tmp_path / 'backend'
    base_root = backend_root / 'plugins' / 'base'
    app_root = backend_root / 'plugins' / 'app'
    write_manifest(
        base_root,
        """
id: base
name: Base
version: 1.0.0
backend:
  module: plugins.base
frontend:
  menus: []
dependencies:
  python: []
  npm: []
""",
    )
    write_manifest(
        app_root,
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
frontend:
  menus: []
dependencies:
  python: []
  npm: []
  plugins:
    - base
""",
    )
    create_controller_dir(base_root)
    create_controller_dir(app_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='base', installed_version='1.0.0', enabled='0', status='installed'),
        SimpleNamespace(plugin_id='app', installed_version='1.0.0', enabled='0', status='installed'),
    ]

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).uninstall_plugin('base'))

    assert result['ok'] is False
    assert result['operation'] == 'uninstall'
    assert result['safeMode'] is True
    assert result['pluginDependencyErrors'][0]['status'] == 'dependent'
    assert result['pluginDependencyErrors'][0]['pluginId'] == 'app'
    assert FakePluginService.mark_uninstalled_called_with is None


def test_plugin_runtime_uninstall_plugin_marks_plugin_uninstalled(tmp_path: Path) -> None:
    """校验插件安全卸载会标记卸载并提交事务。"""
    backend_root = tmp_path / 'backend'
    backend_root.mkdir()
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).uninstall_plugin('demo'))

    assert result['ok'] is True
    assert result['operation'] == 'uninstall'
    assert FakePluginService.mark_uninstalled_called_with == 'demo'
    assert FakePluginService.update_enabled_called_with is None
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'uninstall'


def test_plugin_runtime_uninstall_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """校验插件卸载执行失败时返回失败生命周期步骤。"""
    backend_root = tmp_path / 'backend'
    backend_root.mkdir()
    gateway = FakePluginRuntimeGateway()

    async def raise_uninstall_failure(query_db: object, plugin_id: str) -> object:
        """模拟卸载插件失败。"""
        raise RuntimeError('uninstall update failed')

    original_mark_uninstalled = FakePluginService.mark_plugin_uninstalled_services
    FakePluginService.mark_plugin_uninstalled_services = raise_uninstall_failure

    try:
        result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).uninstall_plugin('demo'))
    finally:
        FakePluginService.mark_plugin_uninstalled_services = original_mark_uninstalled

    assert result['ok'] is False
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'uninstall'
    assert result['failedStep'] == 'mark_uninstalled'
    assert 'uninstall update failed' in result['error']


def test_plugin_runtime_purge_plugin_dry_run_returns_plan(tmp_path: Path) -> None:
    """校验插件物理清理 dry-run 返回清理计划且不提交事务。"""
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
resources:
  static:
    - assets/demo
  uploads:
    - uploads/demo
  temp:
    - tmp/demo-cache
""",
    )
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).purge_plugin('demo', dry_run=True))

    assert result['ok'] is True
    assert result['operation'] == 'purge'
    assert result['dryRun'] is True
    assert 'precheck' in result
    assert result['safeMode'] is False
    assert result['removesSource'] is False
    assert result['plan']['destructiveCount'] == EXPECTED_PURGE_DESTRUCTIVE_COUNT
    resource_items = [item for item in result['plan']['items'] if item['name'].startswith('resource_')]
    assert resource_items == [
        {
            'name': 'resource_static',
            'label': '插件静态资源需显式处理',
            'enabled': True,
            'destructive': False,
            'count': 1,
            'target': 'assets/demo',
        },
        {
            'name': 'resource_uploads',
            'label': '插件上传资源需显式处理',
            'enabled': True,
            'destructive': False,
            'count': 1,
            'target': 'uploads/demo',
        },
        {
            'name': 'resource_temp',
            'label': '插件临时资源需显式处理',
            'enabled': True,
            'destructive': False,
            'count': 1,
            'target': 'tmp/demo-cache',
        },
    ]
    assert FakePluginService.purge_called is False
    assert gateway.session_local.sessions[0].committed is False


def test_plugin_runtime_purge_plugin_blocks_enabled_dependents(tmp_path: Path) -> None:
    """校验物理清理被启用插件依赖的插件时会阻断写库。"""
    backend_root = tmp_path / 'backend'
    base_root = backend_root / 'plugins' / 'base'
    app_root = backend_root / 'plugins' / 'app'
    write_manifest(
        base_root,
        """
id: base
name: Base
version: 1.0.0
backend:
  module: plugins.base
""",
    )
    write_manifest(
        app_root,
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
    create_controller_dir(base_root)
    create_controller_dir(app_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='base', installed_version='1.0.0', enabled='0', status='installed'),
        SimpleNamespace(plugin_id='app', installed_version='1.0.0', enabled='0', status='installed'),
    ]

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).purge_plugin('base'))

    assert result['ok'] is False
    assert result['operation'] == 'purge'
    assert result['message'] == '插件仍被已启用插件依赖，物理清理已中止'
    assert result['pluginDependencyErrors'][0]['status'] == 'dependent'
    assert result['pluginDependencyErrors'][0]['pluginId'] == 'app'
    assert FakePluginService.purge_called is False


def test_plugin_runtime_purge_dry_run_reports_enabled_dependents(tmp_path: Path) -> None:
    """校验物理清理 dry-run 会暴露被依赖方检查结果但不执行清理。"""
    backend_root = tmp_path / 'backend'
    base_root = backend_root / 'plugins' / 'base'
    app_root = backend_root / 'plugins' / 'app'
    write_manifest(
        base_root,
        """
id: base
name: Base
version: 1.0.0
backend:
  module: plugins.base
""",
    )
    write_manifest(
        app_root,
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
    create_controller_dir(base_root)
    create_controller_dir(app_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='base', installed_version='1.0.0', enabled='0', status='installed'),
        SimpleNamespace(plugin_id='app', installed_version='1.0.0', enabled='0', status='installed'),
    ]

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).purge_plugin('base', dry_run=True))

    assert result['ok'] is True
    assert result['dryRun'] is True
    assert result['operation'] == 'purge'
    assert result['pluginDependencyOk'] is False
    assert result['pluginDependencyErrors'][0]['pluginId'] == 'app'
    assert result['plan']['destructiveCount'] == EXPECTED_PURGE_DESTRUCTIVE_COUNT
    assert FakePluginService.purge_called is False


def test_plugin_runtime_purge_plugin_runs_hook_and_cleans_metadata(tmp_path: Path) -> None:
    """校验插件物理清理会执行 on_purge 钩子、清理平台元数据并提交事务。"""
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
  hooks:
    onPurge: hooks:on_purge
""",
    )
    (plugin_root / 'hooks.py').write_text(
        'async def on_purge(context):\n    context.query_db.purge_hook_ran = context.plugin_id\n',
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).purge_plugin('demo'))

    assert result['ok'] is True
    assert result['operation'] == 'purge'
    assert result['hooks'][0]['hook_name'] == 'on_purge'
    assert FakePluginService.purge_called is True
    assert gateway.session_local.sessions[0].purge_hook_ran == 'demo'
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'purge'


def test_plugin_runtime_purge_orphan_metadata_without_source(tmp_path: Path) -> None:
    """校验插件源码缺失后仍可按 ID 清理平台孤儿元数据。"""
    backend_root = tmp_path / 'backend'
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).purge_plugin('orphan', record_operation_log=False)
    )

    assert result['ok'] is True
    assert result['metadataOnly'] is True
    assert result['hooks'] == []
    assert '已跳过 onPurge' in result['warnings'][0]
    assert FakePluginService.purge_by_id_called_with == 'orphan'
    assert FakePluginService.purge_called is False
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_purge_orphan_metadata_dry_run(tmp_path: Path) -> None:
    """校验孤儿元数据清理支持不写库的 dry-run。"""
    backend_root = tmp_path / 'backend'
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).purge_plugin(
            'orphan',
            dry_run=True,
            record_operation_log=False,
        )
    )

    assert result['ok'] is True
    assert result['dryRun'] is True
    assert result['metadataOnly'] is True
    assert result['plan']['requiresHook'] is False
    assert FakePluginService.purge_by_id_called_with is None
    assert gateway.session_local.sessions[0].committed is False


def test_plugin_runtime_purge_orphan_metadata_blocks_enabled_dependents(tmp_path: Path) -> None:
    """校验孤儿元数据仍被已启用插件依赖时禁止清理。"""
    backend_root = tmp_path / 'backend'
    app_root = backend_root / 'plugins' / 'app'
    write_manifest(
        app_root,
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
dependencies:
  plugins:
    - orphan
""",
    )
    create_controller_dir(app_root)
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='app', installed_version='1.0.0', enabled='0', status='installed')
    ]
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).purge_plugin('orphan', record_operation_log=False)
    )

    assert result['ok'] is False
    assert result['pluginDependencyErrors'][0]['pluginId'] == 'app'
    assert FakePluginService.purge_by_id_called_with is None
    assert gateway.session_local.sessions[0].committed is False


def test_plugin_runtime_purge_plugin_uses_lifecycle_uow_without_fat_service(tmp_path: Path) -> None:
    """校验插件物理清理通过生命周期 UoW 完成，不回退到 fat state gateway。"""
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
  hooks:
    onPurge: hooks:on_purge
""",
    )
    (plugin_root / 'hooks.py').write_text(
        'async def on_purge(context):\n    context.query_db.purge_hook_ran = context.plugin_id\n',
        encoding='utf-8',
    )

    class NoFatPurgeGateway(FakePluginRuntimeGateway):
        """
        禁止物理清理流程读取 fat state gateway 的测试适配器。
        """

        def get_async_session_local(self) -> object:
            """禁止通过 state gateway 打开数据库会话。"""
            raise AssertionError('物理清理流程不应通过 state gateway 打开数据库会话')

        def get_plugin_service(self) -> object:
            """禁止通过 state gateway 获取管理服务。"""
            raise AssertionError('物理清理流程不应通过 state gateway 获取管理服务')

    gateway = NoFatPurgeGateway()

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).purge_plugin('demo', record_operation_log=False)
    )

    assert result['ok'] is True
    assert result['operation'] == 'purge'
    assert FakePluginService.purge_called is True
    assert gateway.session_local.sessions[0].purge_hook_ran == 'demo'
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_purge_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """校验插件物理清理执行失败时返回失败生命周期步骤。"""
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
  hooks:
    onPurge: hooks:on_purge
""",
    )
    (plugin_root / 'hooks.py').write_text(
        "async def on_purge(context):\n    raise RuntimeError('purge hook failed')\n",
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).purge_plugin('demo'))

    assert result['ok'] is False
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'purge'
    assert result['failedStep'] == 'run_purge_hook'
    assert 'purge hook failed' in result['error']
    assert FakePluginService.purge_called is False


def test_plugin_runtime_purge_plugin_uses_injected_dependencies(tmp_path: Path) -> None:
    """校验插件物理清理使用构造期注入的集中依赖网关。"""
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
  hooks:
    onPurge: hooks:on_purge
""",
    )
    (plugin_root / 'hooks.py').write_text(
        'async def on_purge(context):\n    context.query_db.purge_hook_ran = context.plugin_id\n',
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.purge_plugin('demo', record_operation_log=False))

    assert result['ok'] is True
    assert FakePluginService.purge_called is True
    assert gateway.session_local.sessions[0].purge_hook_ran == 'demo'
    assert gateway.session_local.sessions[0].committed is True
