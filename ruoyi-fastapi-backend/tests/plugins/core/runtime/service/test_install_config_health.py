import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from pytest import MonkeyPatch

from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.runtime.service import PluginRuntimeService
from plugins.core.runtime.service.dependency_container import PluginRuntimeGatewayOverrides
from plugins.core.runtime.service.migration_store import PluginDatabaseMigrationHistoryStore
from plugins.core.runtime.support import PluginConfigPayloadBuilder
from plugins.core.validation.dependencies import PluginDependencyChecker
from tests.plugins.core.runtime.fakes import (
    EXPECTED_CONFIG_ORDER,
    FakePluginRuntimeGateway,
    FakePluginService,
    FakeRuntimeEnvironment,
    FakeSession,
    build_runtime,
    build_runtime_with_gateway,
    create_controller_dir,
    create_frontend_view,
    write_manifest,
)


class ConfigOnlyGateway:
    """
    仅提供插件配置读写能力的测试网关。
    """

    def __init__(self) -> None:
        """初始化测试配置网关。"""
        self.get_calls: list[tuple[str, bool]] = []
        self.update_calls: list[tuple[str, dict[str, object]]] = []
        self.audit_payloads: list[dict[str, object]] = []

    async def get_plugin_config(self, discovered_plugin: object, *, reveal_secret: bool = False) -> list[object]:
        """获取插件配置。"""
        plugin_id = discovered_plugin.manifest.id
        self.get_calls.append((plugin_id, reveal_secret))
        value = 'openai-key' if reveal_secret else '******'
        return [
            SimpleNamespace(
                model_dump=lambda by_alias=True: {
                    'key': 'provider',
                    'value': value,
                    'default': value,
                    'secret': True,
                }
            )
        ]

    async def update_plugin_config(self, discovered_plugin: object, values: dict[str, object]) -> list[object]:
        """更新插件配置。"""
        plugin_id = discovered_plugin.manifest.id
        self.update_calls.append((plugin_id, values))
        return [
            SimpleNamespace(
                model_dump=lambda by_alias=True, key=key, value=value: {
                    'key': key,
                    'value': value,
                    'secret': False,
                }
            )
            for key, value in values.items()
        ]

    async def set_plugin_config(
        self,
        discovered_plugin: object,
        values: dict[str, object],
        *,
        audit_operation: str,
        success_message: str,
    ) -> list[object]:
        """在同一事务语义中更新插件配置并记录审计负载。"""
        before_configs = await self.get_plugin_config(discovered_plugin, reveal_secret=True)
        configs = await self.update_plugin_config(discovered_plugin, values)
        self.audit_payloads.append(
            PluginConfigPayloadBuilder.build_audit_payload(
                discovered_plugin.manifest.id,
                operation=audit_operation,
                values=values,
                before_configs=before_configs,
                after_configs=configs,
                message=success_message,
            )
        )
        return configs

    def get_plugin_service(self) -> object:
        """禁止配置链路回退到管理服务胖接口。"""
        raise AssertionError('配置读写不应依赖 PluginManagementServiceProtocol')


def test_plugin_runtime_install_plugin_dry_run_returns_actions(tmp_path: Path) -> None:
    """校验插件安装 dry-run 返回动作计划且不写数据库。"""
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

    result = asyncio.run(build_runtime(backend_root).install_plugin('demo', dry_run=True))

    assert result['ok'] is True, result
    assert result['dryRun'] is True
    assert result['actions'][0]['name'] == 'upsert_plugin'
    assert any(action['name'] == 'check_structure' for action in result['actions'])
    assert any(action['name'] == 'check_menu_conflicts' for action in result['actions'])
    assert result['manifestOk'] is True
    assert result['structureOk'] is True
    assert result['structureErrors'] == []
    assert result['menuConflictOk'] is True
    assert result['menuConflicts'] == []


def test_plugin_runtime_install_plugin_uses_injected_dependencies(tmp_path: Path) -> None:
    """校验插件安装使用构造期注入的集中依赖对象。"""
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
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.install_plugin('demo', record_operation_log=False))

    assert result['ok'] is True
    assert FakePluginService.upsert_called is True
    assert FakePluginService.install_plugin_job_called_with == ('demo', True)
    assert FakePluginService.mark_installed_called is True
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_install_plugin_uses_lifecycle_uow_and_migration_gateway_without_fat_service(
    tmp_path: Path,
) -> None:
    """校验插件安装通过生命周期 UoW 和 migration 执行端口完成，不回退到 fat state gateway。"""
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
  migrations:
    - migrations/001_demo.sql
  seeds:
    - seeds/demo_seed.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_demo.sql').write_text('select 2;\n', encoding='utf-8')
    (plugin_root / 'seeds').mkdir()
    (plugin_root / 'seeds' / 'demo_seed.sql').write_text('select 3;\n', encoding='utf-8')

    class InstallLifecycleUnitOfWork:
        """
        测试用插件安装生命周期 UoW。
        """

        def __init__(self, gateway: 'NoFatInstallGateway') -> None:
            """初始化测试 UoW。"""
            self.gateway = gateway
            self.session: FakeSession | None = None
            self.session_context: FakeSession | None = None

        async def __aenter__(self) -> 'InstallLifecycleUnitOfWork':
            """打开测试 UoW 会话。"""
            self.session_context = self.gateway.session_local()
            self.session = await self.session_context.__aenter__()
            return self

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
            """关闭测试 UoW 会话。"""
            await self.session_context.__aexit__(exc_type, exc, traceback)

        async def check_installed_menu_conflicts(self, discovered_plugin: object) -> list[object]:
            """检查已安装菜单冲突。"""
            return await FakePluginService.check_installed_menu_conflict_services(self.session, discovered_plugin)

        async def upsert_discovered_plugin(
            self,
            discovered_plugin: object,
            backend_root: Path,
            frontend_root: Path,
        ) -> object:
            """写入插件基础状态。"""
            return await FakePluginService.upsert_discovered_plugin_services(
                self.session,
                discovered_plugin,
                backend_root,
                frontend_root,
            )

        async def install_plugin_menu(self, discovered_plugin: object, *, enabled: bool) -> None:
            """安装插件菜单。"""
            await FakePluginService.install_plugin_menu_services(self.session, discovered_plugin, enabled=enabled)

        async def install_plugin_default_config(self, discovered_plugin: object) -> list[object]:
            """安装插件默认配置。"""
            return await FakePluginService.install_plugin_default_config_services(self.session, discovered_plugin)

        async def install_plugin_jobs(self, discovered_plugin: object, *, enabled: bool) -> None:
            """同步插件任务。"""
            await FakePluginService.install_plugin_job_services(self.session, discovered_plugin, enabled=enabled)

        async def mark_plugin_installed(self, discovered_plugin: object) -> object:
            """标记插件已安装。"""
            return await FakePluginService.mark_plugin_installed_services(self.session, discovered_plugin)

        async def commit(self) -> None:
            """提交测试 UoW。"""
            await self.session.commit()

    class NoFatInstallGateway(FakePluginRuntimeGateway):
        """
        禁止安装流程读取 fat state gateway 的测试适配器。
        """

        def get_async_session_local(self) -> object:
            """禁止通过 state gateway 打开数据库会话。"""
            raise AssertionError('安装流程不应通过 state gateway 打开数据库会话')

        def get_plugin_service(self) -> object:
            """禁止通过 state gateway 获取管理服务。"""
            raise AssertionError('安装流程不应通过 state gateway 获取管理服务')

        def open_lifecycle_unit_of_work(self) -> InstallLifecycleUnitOfWork:
            """打开测试生命周期 UoW。"""
            return InstallLifecycleUnitOfWork(self)

        async def run_plugin_migrations(self, discovered_plugin: object) -> list[object]:
            """通过独立 migration session 执行插件 migration。"""
            async with self.session_local() as migration_session:
                return await PluginMigrationRunner(
                    discovered_plugin,
                    PluginDatabaseMigrationHistoryStore.with_model_gateway(
                        FakePluginService,
                        self,
                        self.session_local,
                    ),
                    manage_execution_transaction=True,
                ).run(migration_session)

    gateway = NoFatInstallGateway()

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).install_plugin('demo', record_operation_log=False)
    )

    assert result['ok'] is True
    assert FakePluginService.upsert_called is True
    assert FakePluginService.mark_installed_called is True
    assert [record.status for record in FakePluginService.migration_records] == ['running', 'success']
    executed_statements = [session.executed_statements for session in gateway.session_local.sessions]
    assert ['select 2'] in executed_statements
    assert ['select 3'] in executed_statements
    seed_session = next(
        session for session in gateway.session_local.sessions if session.executed_statements == ['select 3']
    )
    assert seed_session.committed is True


def test_plugin_runtime_install_plugin_uses_runtime_plugin_roots(tmp_path: Path) -> None:
    """校验插件安装写入状态时使用运行时环境提供的插件根目录。"""
    project_root = tmp_path / 'project'
    backend_root = project_root / 'api-server'
    frontend_root = project_root / 'web-client'
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

    result = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway, frontend_root=frontend_root).install_plugin('demo')
    )

    assert result['ok'] is True
    assert FakePluginService.upsert_backend_root == backend_root / 'plugins'
    assert FakePluginService.upsert_frontend_root == frontend_root / 'plugins'


def test_plugin_runtime_install_plugin_rejects_manifest_errors(tmp_path: Path) -> None:
    """校验插件安装会被 manifest error 阻断。"""
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
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件 manifest 检查失败，安装已中止'
    assert result['manifestOk'] is False
    assert result['manifestIssues'][0]['kind'] == 'compatibility_unsatisfied'
    assert FakePluginService.upsert_called is False
    assert FakePluginService.marked_errors == [('demo', '插件 manifest 检查失败，安装已中止')]


def test_plugin_runtime_install_plugin_runs_sql_seed(tmp_path: Path) -> None:
    """校验插件安装可以执行 SQL seed。"""
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
  seeds:
    - seeds/demo_seed.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'seeds').mkdir()
    (plugin_root / 'seeds' / 'demo_seed.sql').write_text('select 1;\n', encoding='utf-8')
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['structureOk'] is True
    assert result['structureErrors'] == []
    assert result['seeds'][0]['seed_path'] == 'seeds/demo_seed.sql'
    assert result['seeds'][0]['statement_count'] == 1
    assert gateway.session_local.executed_session.executed_statements == ['select 1']
    assert gateway.session_local.committed_session is not None


def test_plugin_runtime_install_plugin_runs_sql_migration(tmp_path: Path) -> None:
    """校验插件安装可以执行 SQL migration。"""
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
  migrations:
    - migrations/001_demo.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_demo.sql').write_text('select 2;\n', encoding='utf-8')
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['migrations'][0]['migration_path'] == 'migrations/001_demo.sql'
    assert result['migrations'][0]['statement_count'] == 1
    assert result['migrations'][0]['checksum']
    assert result['migrations'][0]['skipped'] is False
    assert [record.status for record in FakePluginService.migration_records] == ['running', 'success']
    assert FakePluginService.migration_records[-1].migration_path == 'migrations/001_demo.sql'
    migration_session = gateway.session_local.executed_session
    assert migration_session is not None
    assert migration_session.executed_statements == ['select 2']
    assert migration_session is not gateway.session_local.sessions[0]
    assert migration_session.committed is True
    assert gateway.session_local.committed_session is not None


def test_plugin_runtime_install_plugin_skips_recorded_migration(tmp_path: Path) -> None:
    """校验插件安装会跳过已记录且未变化的 migration。"""
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
  migrations:
    - migrations/001_demo.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    migration_file = plugin_root / 'migrations' / '001_demo.sql'
    migration_file.write_text('select 2;\n', encoding='utf-8')
    gateway = FakePluginRuntimeGateway()

    FakePluginService.migration_checksums = {
        ('demo', 'migrations/001_demo.sql'): PluginMigrationRunner._calculate_checksum(migration_file)
    }

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['migrations'][0]['skipped'] is True
    assert FakePluginService.migration_records == []
    assert all(not session.executed_statements for session in gateway.session_local.sessions)
    assert gateway.session_local.committed_session is not None


def test_plugin_runtime_install_dry_run_reports_changed_recorded_migration(tmp_path: Path) -> None:
    """校验插件安装 dry-run 会提前报告已执行 migration 内容变更。"""
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
  migrations:
    - migrations/001_demo.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    migration_file = plugin_root / 'migrations' / '001_demo.sql'
    migration_file.write_text('select 1;\n', encoding='utf-8')
    old_checksum = PluginMigrationRunner._calculate_checksum(migration_file)
    migration_file.write_text('select 2;\n', encoding='utf-8')
    gateway = FakePluginRuntimeGateway()
    FakePluginService.migration_checksums = {('demo', 'migrations/001_demo.sql'): old_checksum}

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo', dry_run=True))

    assert result['ok'] is True
    assert result['manifestOk'] is False
    assert result['manifestIssues'][0]['kind'] == 'migration_checksum_changed'
    assert result['manifestIssues'][0]['path'] == 'backend.migrations.migrations/001_demo.sql'
    assert result['message'] == '插件安装演练完成，未执行实际写入'


def test_plugin_runtime_lifecycle_precheck_uses_migration_history_gateway(tmp_path: Path) -> None:
    """校验生命周期脚本预检通过 migration 历史窄端口读取历史，不再回退到 fat state gateway。"""
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
  migrations:
    - migrations/001_demo.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_demo.sql').write_text('select 1;\n', encoding='utf-8')

    class NoFatStateGateway(FakePluginRuntimeGateway):
        """
        禁止生命周期预检读取 fat state gateway 的测试适配器。
        """

        def get_async_session_local(self) -> object:
            """禁止通过 state gateway 打开数据库会话。"""
            raise AssertionError('生命周期脚本预检不应通过 state gateway 打开数据库会话')

        def get_plugin_service(self) -> object:
            """禁止通过 state gateway 获取管理服务。"""
            raise AssertionError('生命周期脚本预检不应通过 state gateway 获取管理服务')

    gateway = NoFatStateGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).precheck_plugin_operation('demo', 'install'))

    assert result['ok'] is True
    assert result['manifestOk'] is True
    assert [issue['kind'] for issue in result['manifestWarnings']] == ['migration_pending']


def test_plugin_runtime_install_plugin_accepts_namespaced_permissions_across_plugins(tmp_path: Path) -> None:
    """校验插件安装接受不同插件使用各自权限命名空间。"""
    backend_root = tmp_path / 'backend'
    demo_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        demo_root,
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
frontend:
  menus:
    - name: 演示菜单
      path: demo
      component: plugin/demo/index
      perms: demo:list
permissions:
  - demo:list
""",
    )
    sample_root = backend_root / 'plugins' / 'sample'
    write_manifest(
        sample_root,
        """
id: sample
name: 样例插件
version: 1.0.0
backend:
  module: plugins.sample
frontend:
  menus:
    - name: 样例菜单
      path: sample
      component: plugin/sample/index
      perms: sample:list
permissions:
  - sample:list
""",
    )
    create_controller_dir(demo_root)
    create_controller_dir(sample_root)
    create_frontend_view(backend_root, 'demo')
    create_frontend_view(backend_root, 'sample')
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('sample'))

    assert result['ok'] is True
    assert result['message'] == '插件安装完成'
    assert result['menuConflictOk'] is True
    assert result['menuConflicts'] == []
    assert FakePluginService.upsert_called is True
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'install'
    assert FakePluginService.operation_logs[0].payload['pluginId'] == 'sample'
    assert FakePluginService.operation_logs[0].payload['ok'] is True


def test_plugin_runtime_install_plugin_stops_when_database_menu_conflict_exists(tmp_path: Path) -> None:
    """校验插件安装遇到数据库已安装菜单冲突时中止且不写插件状态。"""
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
    - name: 演示菜单
      path: demo
      component: plugin/demo/index
      perms: demo:page:list
permissions:
  - demo:page:list
""",
    )
    create_controller_dir(plugin_root)
    create_frontend_view(backend_root, 'demo')
    gateway = FakePluginRuntimeGateway()
    FakePluginService.installed_menu_conflicts = [
        SimpleNamespace(
            kind='installed_permission',
            plugin_id='demo',
            conflict_plugin_id=None,
            value='demo:page:list',
            message='插件 demo 权限 demo:page:list 与已存在菜单 900（core）冲突',
        )
    ]

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件菜单与已安装菜单存在冲突，安装已中止'
    assert result['menuConflictOk'] is False
    assert result['menuConflicts'][0]['kind'] == 'installed_permission'
    assert FakePluginService.upsert_called is False
    assert gateway.session_local.sessions[0] is not None
    assert gateway.session_local.sessions[0].committed is False
    assert FakePluginService.marked_errors == [('demo', '插件菜单与已安装菜单存在冲突，安装已中止')]


def test_plugin_runtime_install_plugin_persists_plugin_and_menus(tmp_path: Path) -> None:
    """校验插件安装会写入插件状态和菜单。"""
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
    create_frontend_view(backend_root, 'demo')
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert FakePluginService.upsert_called is True
    assert FakePluginService.install_plugin_menu_called_with == ('demo', True)
    assert FakePluginService.install_config_called is True
    assert FakePluginService.mark_installed_called is True
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'install'
    assert FakePluginService.operation_logs[0].payload['pluginId'] == 'demo'


def test_plugin_runtime_install_plugin_blocks_when_dependencies_are_missing(tmp_path: Path) -> None:
    """校验插件安装只生成缺失依赖安装计划，不自动执行依赖安装。"""
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
dependencies:
  python:
    - missing-python
  npm:
    - missing-npm>=1.2.3
  npmDev:
    - missing-dev-npm==4.5.6
""",
    )
    create_controller_dir(plugin_root)
    frontend_root = Path(PluginRuntimeEnvironmentService(backend_root=backend_root).get_frontend_dir())
    frontend_root.mkdir()
    (frontend_root / 'package.json').write_text('{"dependencies": {}, "devDependencies": {}}\n', encoding='utf-8')
    gateway = FakePluginRuntimeGateway()
    expected_plan_count = 3
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件依赖缺失，安装已中止，请先显式安装依赖'
    assert result['dependencyInstall']['ok'] is True
    assert result['dependencyInstall']['dryRun'] is True
    assert result['dependencyInstall']['planCount'] == expected_plan_count
    assert result['dependencyInstall']['dependencyOk'] is False
    assert result['dependencyInstall']['plan'][0]['command'][1:4] == ['-m', 'pip', 'install']
    assert result['dependencyInstall']['plan'][0]['command'][-1] == 'missing-python'
    assert result['dependencyInstall']['plan'][1]['command'] == ['npm', 'install', 'missing-npm@>=1.2.3']
    assert result['dependencyInstall']['plan'][2]['command'] == [
        'npm',
        'install',
        '--save-dev',
        'missing-dev-npm@4.5.6',
    ]
    assert gateway.commands == []
    package_json = json.loads((frontend_root / 'package.json').read_text(encoding='utf-8'))
    assert package_json['dependencies'] == {}
    assert package_json['devDependencies'] == {}
    assert FakePluginService.upsert_called is False
    assert FakePluginService.mark_installed_called is False


def test_plugin_runtime_install_plugin_does_not_execute_dependency_install_commands(tmp_path: Path) -> None:
    """校验插件安装依赖缺失时不会执行依赖安装命令。"""
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
dependencies:
  python:
    - missing-python
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件依赖缺失，安装已中止，请先显式安装依赖'
    assert result['dependencyInstall']['ok'] is True
    assert result['dependencyInstall']['dryRun'] is True
    assert result['dependencyInstall']['dependencyOk'] is False
    assert gateway.commands == []
    assert FakePluginService.upsert_called is False
    assert FakePluginService.mark_installed_called is False


def test_plugin_runtime_get_and_set_plugin_config(tmp_path: Path) -> None:
    """校验插件运行时可以读取和更新插件配置。"""
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
    - key: provider
      label: 默认供应商
      type: string
      default: openai
      group: model
      order: 10
      placeholder: provider name
      pattern: '^[a-z]+$'
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    get_result = asyncio.run(runtime.get_plugin_config('demo'))
    set_result = asyncio.run(runtime.set_plugin_config('demo', {'provider': 'mistral'}))

    assert get_result['ok'] is True
    assert get_result['configs'][0]['key'] == 'provider'
    assert get_result['configs'][0]['value'] == 'openai'
    assert get_result['configs'][0]['group'] == 'model'
    assert get_result['configs'][0]['order'] == EXPECTED_CONFIG_ORDER
    assert get_result['configs'][0]['placeholder'] == 'provider name'
    assert get_result['configs'][0]['pattern'] == '^[a-z]+$'
    assert set_result['ok'] is True
    assert set_result['operation'] == 'config_set'
    assert set_result['configs'][0]['value'] == 'mistral'
    assert len(FakePluginService.operation_logs) == 1
    operation_log = FakePluginService.operation_logs[0]
    assert operation_log.payload['operation'] == 'config_set'
    assert operation_log.payload['summary']['changedKeys'] == ['provider']
    assert operation_log.payload['summary']['changes'][0]['before'] == 'openai'
    assert operation_log.payload['summary']['changes'][0]['after'] == 'mistral'


def test_plugin_runtime_set_plugin_config_keeps_audit_and_update_atomic(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """校验插件配置更新和审计日志写入保持同一事务边界。"""
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
    - key: provider
      default: openai
""",
    )

    async def fail_add_plugin_operation_log_services(
        cls: type[FakePluginService],
        query_db: object,
        payload: dict[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """模拟管理服务审计日志写入失败。"""
        raise RuntimeError('audit failed')

    gateway = FakePluginRuntimeGateway()
    monkeypatch.setattr(
        FakePluginService,
        'add_plugin_operation_log_services',
        classmethod(fail_add_plugin_operation_log_services),
    )
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.set_plugin_config('demo', {'provider': 'mistral'}))

    assert result['ok'] is False
    assert result['message'] == '更新插件配置失败'
    assert FakePluginService.operation_logs == []
    assert gateway.session_local.committed_session is None


def test_plugin_runtime_config_uses_config_port_without_fat_service_fallback(tmp_path: Path) -> None:
    """校验插件配置读写只依赖配置窄端口且不回退管理服务胖接口。"""
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
      secret: true
      default: openai-key
""",
    )
    config_gateway = ConfigOnlyGateway()
    runtime = PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(),
        gateways=PluginRuntimeGatewayOverrides(config_gateway=config_gateway),
    )

    get_result = asyncio.run(runtime.get_plugin_config('demo', reveal_secret=True))
    set_result = asyncio.run(runtime.set_plugin_config('demo', {'provider': 'mistral'}))

    assert get_result['ok'] is True
    assert get_result['configs'][0]['value'] == 'openai-key'
    assert set_result['ok'] is True
    assert set_result['configs'][0]['value'] == 'mistral'
    assert config_gateway.get_calls == [('demo', True), ('demo', True)]
    assert config_gateway.update_calls == [('demo', {'provider': 'mistral'})]
    assert len(config_gateway.audit_payloads) == 1
    assert config_gateway.audit_payloads[0]['operation'] == 'config_set'


def test_plugin_runtime_export_plugin_config_masks_secret_by_default(tmp_path: Path) -> None:
    """校验插件配置导出默认脱敏敏感配置，并可显式导出明文。"""
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
      label: API Key
      type: password
      default: sk-secret
      secret: true
""",
    )
    runtime = build_runtime_with_gateway(backend_root, FakePluginRuntimeGateway())

    masked_result = asyncio.run(runtime.export_plugin_config('demo'))
    plain_result = asyncio.run(runtime.export_plugin_config('demo', reveal_secret=True))

    assert masked_result['ok'] is True
    assert masked_result['revealSecret'] is False
    assert masked_result['values']['api_key'] == '******'
    assert masked_result['configs'][0]['default'] == '******'
    assert masked_result['metadata'][0]['secret'] is True
    assert masked_result['metadata'][0]['default'] == '******'
    assert plain_result['revealSecret'] is True
    assert plain_result['values']['api_key'] == 'sk-secret'
    assert plain_result['configs'][0]['default'] == 'sk-secret'
    assert plain_result['metadata'][0]['default'] == 'sk-secret'


def test_plugin_runtime_import_plugin_config_updates_values(tmp_path: Path) -> None:
    """校验插件配置导入会复用配置更新能力。"""
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
    - key: provider
      label: 默认供应商
      type: string
      default: openai
""",
    )
    runtime = build_runtime_with_gateway(backend_root, FakePluginRuntimeGateway())

    result = asyncio.run(runtime.import_plugin_config('demo', {'provider': 'mistral'}))

    assert result['ok'] is True
    assert result['message'] == '插件配置导入完成'
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'config_import'
    assert result['importedKeys'] == ['provider']
    assert result['configs'][0]['value'] == 'mistral'
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'config_import'


def test_plugin_runtime_diagnose_plugin_returns_masked_snapshot(tmp_path: Path) -> None:
    """校验插件诊断包会聚合检查结果和脱敏配置快照。"""
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: Demo
version: 1.0.0
permissions:
  - demo:page:list
backend:
  module: plugins.demo
frontend:
  menus:
    - name: Demo
      path: demo
      component: plugin/demo/index
      perms: demo:page:list
      type: C
config:
  items:
    - key: api_key
      label: API Key
      type: password
      default: sk-test
      secret: true
""",
    )
    create_controller_dir(plugin_root)
    create_frontend_view(backend_root, 'demo')
    gateway = FakePluginRuntimeGateway()
    FakePluginService.plugin_list = [
        SimpleNamespace(
            plugin_id='demo',
            installed_version='1.0.0',
            enabled='0',
            status='installed',
            last_error=None,
            source='local',
            backend_path='plugins/demo',
            frontend_path='plugins/demo',
        )
    ]
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

    result = asyncio.run(runtime.diagnose_plugin('demo'))

    assert result['ok'] is True, result
    assert result['pluginId'] == 'demo'
    assert result['info']['pluginId'] == 'demo'
    assert result['check']['checks'][0]['pluginId'] == 'demo'
    assert result['check']['databaseAvailable'] is True
    assert result['check']['databaseError'] is None
    assert result['menuPlan']['total'] == 1
    assert result['menuPlan']['permissionCount'] == 1
    assert result['menuPlan']['items'][0]['component'] == 'plugin/demo/index'
    assert result['config']['configs'][0]['key'] == 'api_key'
    assert result['config']['configs'][0]['value'] == '******'
    assert result['config']['summary'] == {
        'total': 1,
        'secretCount': 1,
        'requiredCount': 0,
        'configuredCount': 0,
        'missingRequiredCount': 0,
        'missingRequiredKeys': [],
        'masked': True,
    }
    assert result['audit']['available'] is True
    assert result['audit']['count'] == 1
    assert result['audit']['items'][0]['operation'] == 'install'


def test_plugin_runtime_diagnose_plugin_uses_audit_gateway_for_snapshot(tmp_path: Path) -> None:
    """校验插件诊断包通过审计窄端口读取最近审计快照，不再回退到 fat state gateway。"""
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
config:
  items:
    - key: api_key
      label: API Key
      type: password
      default: sk-test
      secret: true
""",
    )
    create_controller_dir(plugin_root)
    FakePluginService.plugin_list = [
        SimpleNamespace(
            plugin_id='demo',
            installed_version='1.0.0',
            enabled='0',
            status='installed',
            last_error=None,
            source='local',
            backend_path='plugins/demo',
            frontend_path='plugins/demo',
        )
    ]
    FakePluginService.operation_logs = [
        SimpleNamespace(
            payload={'ok': True, 'operation': 'install', 'pluginId': 'demo', 'message': 'installed'},
            dry_run=False,
            continue_on_error=False,
        )
    ]

    class NoFatStateGateway(FakePluginRuntimeGateway):
        """
        禁止诊断审计快照读取 fat state gateway 的测试适配器。
        """

        def get_async_session_local(self) -> object:
            """禁止通过 state gateway 打开数据库会话。"""
            raise AssertionError('诊断审计快照不应通过 state gateway 打开数据库会话')

        def get_plugin_service(self) -> object:
            """禁止通过 state gateway 获取管理服务。"""
            raise AssertionError('诊断审计快照不应通过 state gateway 获取管理服务')

    result = asyncio.run(build_runtime_with_gateway(backend_root, NoFatStateGateway()).diagnose_plugin('demo'))

    assert result['ok'] is True
    assert result['audit']['available'] is True
    assert result['audit']['count'] == 1
    assert result['audit']['items'][0]['operation'] == 'install'


def test_plugin_runtime_health_plugin_returns_checker_result(tmp_path: Path) -> None:
    """校验插件运行时可以执行健康检查。"""
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
  health:
    checker: health:check
""",
    )
    (plugin_root / 'health.py').write_text(
        'async def check(context):\n'
        "    return {'ok': True, 'status': 'healthy', 'message': context.plugin_id, 'details': {'ready': True}}\n",
        encoding='utf-8',
    )
    runtime = build_runtime(backend_root)

    result = asyncio.run(runtime.health_plugin('demo'))

    assert result['ok'] is True
    assert result['pluginId'] == 'demo'
    assert result['health']['status'] == 'healthy'
    assert result['health']['details'] == {'ready': True}


def test_plugin_runtime_health_plugin_reports_missing_plugin(tmp_path: Path) -> None:
    """校验插件健康检查会报告不存在的插件。"""
    result = asyncio.run(build_runtime(tmp_path / 'backend').health_plugin('missing'))

    assert result['ok'] is False
    assert result['pluginId'] == 'missing'


def test_plugin_runtime_install_plugin_runs_seed_files(tmp_path: Path) -> None:
    """校验插件安装会执行 manifest 声明的 seed 文件。"""
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
  seeds:
    - seeds/demo_seed.py
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'seeds').mkdir()
    (plugin_root / 'seeds' / 'demo_seed.py').write_text(
        'async def run(query_db):\n    query_db.seed_ran = True\n',
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['seeds'][0]['seed_path'] == 'seeds/demo_seed.py'
    assert any(getattr(session, 'seed_ran', False) is True for session in gateway.session_local.sessions)
