# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_runtime_install_plugin_runs_install_hook(tmp_path: Path) -> None:
    """
    校验插件安装会执行 manifest 声明的 on_install 钩子。

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
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['hooks'][0]['hook_name'] == 'on_install'
    assert gateway.session_local.sessions[0].install_hook_ran == 'demo'


def test_plugin_runtime_install_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """
    校验插件安装执行失败时返回失败生命周期步骤。

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
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['operation'] == 'install'
    assert result['failedStep'] == 'run_install_hook'
    assert 'install hook failed' in result['error']
    assert FakePluginService.marked_errors == [('demo', '插件安装失败：install hook failed')]


def test_plugin_runtime_install_plugin_delegates_to_install_use_case(tmp_path: Path) -> None:
    """
    校验插件安装入口委托给组合式安装 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeInstallUseCase:
        """
        测试用插件安装 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件安装 use case。
            """
            self.plugin_id: str | None = None
            self.dry_run: bool | None = None
            self.record_operation_log: bool | None = None

        async def install_plugin(
            self,
            plugin_id: str,
            *,
            dry_run: bool = False,
            record_operation_log: bool = True,
        ) -> dict:
            """
            记录插件安装调用。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :param record_operation_log: 是否记录审计日志
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.dry_run = dry_run
            self.record_operation_log = record_operation_log
            return {'ok': True, 'pluginId': plugin_id, 'operation': 'install'}

    install = FakeInstallUseCase()
    runtime.install = install

    payload = asyncio.run(runtime.install_plugin('demo', dry_run=True, record_operation_log=False))

    assert install.plugin_id == 'demo'
    assert install.dry_run is True
    assert install.record_operation_log is False
    assert payload == {'ok': True, 'pluginId': 'demo', 'operation': 'install'}


def test_plugin_runtime_install_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验安装 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    assert runtime.install.context is runtime.context

    class FakeInstallContextService:
        """
        测试用安装上下文服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用安装上下文服务。
            """
            self.discovered_plugins: list[object] | None = None
            self.plugin_id: str | None = None
            self.blocked_operation: str | None = None
            self.capability_plugin: object | None = None

        def get_discovered_plugin_from_list(self, discovered_plugins: list[object], plugin_id: str) -> object:
            """
            记录插件列表查找调用。

            :param discovered_plugins: 已发现插件列表
            :param plugin_id: 插件ID
            :return: 测试插件对象
            """
            self.discovered_plugins = discovered_plugins
            self.plugin_id = plugin_id
            return sentinel

        def build_operation_blocked_payload(
            self,
            discovered_plugin: object,
            operation: str,
            *,
            dry_run: bool | None = None,
        ) -> dict | None:
            """
            记录运行模式阻断检查调用。

            :param discovered_plugin: 已发现插件
            :param operation: 操作类型
            :param dry_run: 是否预演
            :return: 阻断负载
            """
            self.blocked_operation = operation
            return None

        def with_plugin_capability(self, payload: dict, discovered_plugin: object | None) -> dict:
            """
            记录 capability 附加调用。

            :param payload: 响应负载
            :param discovered_plugin: 已发现插件
            :return: 附加后的响应负载
            """
            self.capability_plugin = discovered_plugin
            payload['contextPlugin'] = discovered_plugin
            return payload

    context = FakeInstallContextService()
    runtime.install.context = context
    discovered_plugins = [object()]

    listed_plugin = runtime.install._get_discovered_plugin_from_list(discovered_plugins, 'demo')
    blocked_payload = runtime.install._build_operation_blocked_payload(sentinel, 'install', dry_run=True)
    payload = runtime.install._with_plugin_capability({'ok': True}, sentinel)

    assert listed_plugin is sentinel
    assert context.discovered_plugins is discovered_plugins
    assert context.plugin_id == 'demo'
    assert context.blocked_operation == 'install'
    assert blocked_payload is None
    assert context.capability_plugin is sentinel
    assert payload == {'ok': True, 'contextPlugin': sentinel}


def test_plugin_runtime_upgrade_plugin_dry_run_reports_version_state(tmp_path: Path) -> None:
    """
    校验插件升级 dry-run 会返回版本状态和动作计划。

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
version: 1.1.0
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
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
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
    """
    校验插件升级 dry-run 会提前报告已执行 migration 内容变更。

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
    FakePluginService.reset()
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
    """
    校验插件升级会被 manifest error 阻断。

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
version: 1.1.0
enabled: true
backend:
  module: plugins.demo
compatibility:
  pythonVersion: '>=99.0.0'
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
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
    """
    校验未安装插件执行升级会被拒绝。

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
version: 1.1.0
enabled: true
backend:
  module: plugins.demo
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).upgrade_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件尚未安装，升级已中止'
    assert result['installed'] is False
    assert gateway.session_local.sessions[0].committed is False
    assert FakePluginService.marked_errors == [('demo', '插件尚未安装，升级已中止')]


def test_plugin_runtime_upgrade_plugin_skips_latest_version(tmp_path: Path) -> None:
    """
    校验已是最新版本时升级命令不会写数据库。

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
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
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
    """
    校验源码版本低于已安装版本时升级命令不会写数据库。

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
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
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
    """
    校验插件升级会执行幂等写入、seed、on_upgrade 钩子并提交事务。

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
version: 1.1.0
enabled: true
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
    FakePluginService.reset()
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
    assert FakePluginService.install_enabled_menu_called is True
    assert FakePluginService.mark_installed_called is True
    assert any(getattr(session, 'upgrade_migration_ran', False) is True for session in gateway.session_local.sessions)
    assert any(getattr(session, 'upgrade_seed_ran', False) is True for session in gateway.session_local.sessions)
    assert any(getattr(session, 'upgrade_hook_ran', None) == 'demo' for session in gateway.session_local.sessions)
    assert gateway.session_local.committed_session is not None
    assert result['migrations'][0]['migration_path'] == 'migrations/001_upgrade.py'
    assert result['hooks'][0]['hook_name'] == 'on_upgrade'


def test_plugin_runtime_upgrade_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """
    校验插件升级执行失败时返回失败生命周期步骤。

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
version: 1.1.0
backend:
  module: plugins.demo
  hooks:
    onUpgrade: hooks:on_upgrade
""",
    )
    create_controller_dir(plugin_root)
    (plugin_root / 'hooks.py').write_text(
        "async def on_upgrade(context):\n    raise RuntimeError('upgrade hook failed')\n",
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
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


def test_plugin_runtime_upgrade_plugin_uses_injected_dependencies(tmp_path: Path) -> None:
    """
    校验插件升级使用构造期注入的集中依赖对象。

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
version: 1.1.0
enabled: true
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
    FakePluginService.reset()
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
    assert FakePluginService.migration_records[0].migration_path == 'migrations/001_upgrade.sql'
    assert gateway.session_local.executed_session.executed_statements == ['select 3']
    assert gateway.session_local.committed_session is not None


def test_plugin_runtime_upgrade_plugin_delegates_to_upgrade_use_case(tmp_path: Path) -> None:
    """
    校验插件升级入口委托给组合式升级 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeUpgradeUseCase:
        """
        测试用插件升级 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件升级 use case。
            """
            self.plugin_id: str | None = None
            self.dry_run: bool | None = None
            self.record_operation_log: bool | None = None

        async def upgrade_plugin(
            self,
            plugin_id: str,
            *,
            dry_run: bool = False,
            record_operation_log: bool = True,
        ) -> dict:
            """
            记录插件升级调用。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :param record_operation_log: 是否记录审计日志
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.dry_run = dry_run
            self.record_operation_log = record_operation_log
            return {'ok': True, 'pluginId': plugin_id, 'operation': 'upgrade'}

    upgrade = FakeUpgradeUseCase()
    runtime.upgrade = upgrade

    payload = asyncio.run(runtime.upgrade_plugin('demo', dry_run=True, record_operation_log=False))

    assert upgrade.plugin_id == 'demo'
    assert upgrade.dry_run is True
    assert upgrade.record_operation_log is False
    assert payload == {'ok': True, 'pluginId': 'demo', 'operation': 'upgrade'}


def test_plugin_runtime_upgrade_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验升级 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()
    database_state = object()

    assert runtime.upgrade.context is runtime.context

    class FakeUpgradeContextService:
        """
        测试用升级上下文服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用升级上下文服务。
            """
            self.discovered_plugins: list[object] | None = None
            self.plugin_id: str | None = None
            self.blocked_operation: str | None = None
            self.capability_plugin: object | None = None

        def get_discovered_plugin_from_list(self, discovered_plugins: list[object], plugin_id: str) -> object:
            """
            记录插件列表查找调用。

            :param discovered_plugins: 已发现插件列表
            :param plugin_id: 插件ID
            :return: 测试插件对象
            """
            self.discovered_plugins = discovered_plugins
            self.plugin_id = plugin_id
            return sentinel

        def build_operation_blocked_payload(
            self,
            discovered_plugin: object,
            operation: str,
            *,
            dry_run: bool | None = None,
        ) -> dict | None:
            """
            记录运行模式阻断检查调用。

            :param discovered_plugin: 已发现插件
            :param operation: 操作类型
            :param dry_run: 是否预演
            :return: 阻断负载
            """
            self.blocked_operation = operation
            return None

        async def load_database_plugin_state(self, plugin_id: str) -> tuple[object, None]:
            """
            记录数据库状态读取调用。

            :param plugin_id: 插件ID
            :return: 测试数据库状态
            """
            self.plugin_id = plugin_id
            return database_state, None

        def with_plugin_capability(self, payload: dict, discovered_plugin: object | None) -> dict:
            """
            记录 capability 附加调用。

            :param payload: 响应负载
            :param discovered_plugin: 已发现插件
            :return: 附加后的响应负载
            """
            self.capability_plugin = discovered_plugin
            payload['contextPlugin'] = discovered_plugin
            return payload

    context = FakeUpgradeContextService()
    runtime.upgrade.context = context
    discovered_plugins = [object()]

    listed_plugin = runtime.upgrade._get_discovered_plugin_from_list(discovered_plugins, 'demo')
    blocked_payload = runtime.upgrade._build_operation_blocked_payload(sentinel, 'upgrade', dry_run=True)
    loaded_state, database_error = asyncio.run(runtime.upgrade._load_database_plugin_state('demo'))
    payload = runtime.upgrade._with_plugin_capability({'ok': True}, sentinel)

    assert listed_plugin is sentinel
    assert context.discovered_plugins is discovered_plugins
    assert context.plugin_id == 'demo'
    assert context.blocked_operation == 'upgrade'
    assert blocked_payload is None
    assert loaded_state is database_state
    assert database_error is None
    assert context.capability_plugin is sentinel
    assert payload == {'ok': True, 'contextPlugin': sentinel}


def test_plugin_runtime_set_plugin_enabled_dry_run_returns_actions(tmp_path: Path) -> None:
    """
    校验插件启停 dry-run 返回动作计划。

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
enabled: false
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


def test_plugin_runtime_set_plugin_enabled_delegates_to_enable_use_case(tmp_path: Path) -> None:
    """
    校验插件启停入口委托给组合式启停 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeEnableUseCase:
        """
        测试用插件启停 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件启停 use case。
            """
            self.plugin_id: str | None = None
            self.enabled: bool | None = None
            self.dry_run: bool | None = None
            self.record_operation_log: bool | None = None

        async def set_plugin_enabled(
            self,
            plugin_id: str,
            *,
            enabled: bool,
            dry_run: bool = False,
            record_operation_log: bool = True,
        ) -> dict:
            """
            记录插件启停调用。

            :param plugin_id: 插件ID
            :param enabled: 是否启用
            :param dry_run: 是否仅预演
            :param record_operation_log: 是否记录审计日志
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.enabled = enabled
            self.dry_run = dry_run
            self.record_operation_log = record_operation_log
            return {'ok': True, 'pluginId': plugin_id, 'enabled': enabled}

    enable = FakeEnableUseCase()
    runtime.enable = enable

    payload = asyncio.run(
        runtime.set_plugin_enabled(
            'demo',
            enabled=True,
            dry_run=True,
            record_operation_log=False,
        )
    )

    assert enable.plugin_id == 'demo'
    assert enable.enabled is True
    assert enable.dry_run is True
    assert enable.record_operation_log is False
    assert payload == {'ok': True, 'pluginId': 'demo', 'enabled': True}


def test_plugin_runtime_enable_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验启停 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    assert runtime.enable.context is runtime.context

    class FakeEnableContextService:
        """
        测试用启停上下文服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用启停上下文服务。
            """
            self.plugin_id: str | None = None
            self.discovered_plugins: list[object] | None = None
            self.blocked_operation: str | None = None
            self.capability_plugin: object | None = None

        def get_discovered_plugin(self, plugin_id: str) -> object:
            """
            记录插件发现调用。

            :param plugin_id: 插件ID
            :return: 测试插件对象
            """
            self.plugin_id = plugin_id
            return sentinel

        def get_discovered_plugin_from_list(self, discovered_plugins: list[object], plugin_id: str) -> object:
            """
            记录插件列表查找调用。

            :param discovered_plugins: 已发现插件列表
            :param plugin_id: 插件ID
            :return: 测试插件对象
            """
            self.discovered_plugins = discovered_plugins
            self.plugin_id = plugin_id
            return sentinel

        def build_operation_blocked_payload(
            self,
            discovered_plugin: object,
            operation: str,
            *,
            dry_run: bool | None = None,
        ) -> dict | None:
            """
            记录运行模式阻断检查调用。

            :param discovered_plugin: 已发现插件
            :param operation: 操作类型
            :param dry_run: 是否预演
            :return: 阻断负载
            """
            self.blocked_operation = operation
            return None

        def with_plugin_capability(self, payload: dict, discovered_plugin: object | None) -> dict:
            """
            记录 capability 附加调用。

            :param payload: 响应负载
            :param discovered_plugin: 已发现插件
            :return: 附加后的响应负载
            """
            self.capability_plugin = discovered_plugin
            payload['contextPlugin'] = discovered_plugin
            return payload

    context = FakeEnableContextService()
    runtime.enable.context = context
    discovered_plugins = [object()]

    discovered_plugin = runtime.enable._get_discovered_plugin('demo')
    listed_plugin = runtime.enable._get_discovered_plugin_from_list(discovered_plugins, 'demo')
    blocked_payload = runtime.enable._build_operation_blocked_payload(sentinel, 'enable', dry_run=True)
    payload = runtime.enable._with_plugin_capability({'ok': True}, sentinel)

    assert context.plugin_id == 'demo'
    assert discovered_plugin is sentinel
    assert listed_plugin is sentinel
    assert context.discovered_plugins is discovered_plugins
    assert context.blocked_operation == 'enable'
    assert blocked_payload is None
    assert context.capability_plugin is sentinel
    assert payload == {'ok': True, 'contextPlugin': sentinel}


def test_plugin_runtime_set_plugin_enabled_persists_state(tmp_path: Path) -> None:
    """
    校验插件启停会调用插件服务并提交事务。

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
enabled: false
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
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('demo', enabled=True))

    assert result['ok'] is True
    assert FakePluginService.install_plugin_menu_called_with == ('demo', True)
    assert FakePluginService.update_enabled_called_with == ('demo', True)
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'enable'


def test_plugin_runtime_set_plugin_enabled_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """
    校验插件启用执行失败时返回失败生命周期步骤。

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
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    async def raise_enable_failure(query_db: object, plugin_id: str, enabled: bool) -> object:
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
    """
    校验停用被启用插件依赖的插件时会阻断写库。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    FakePluginService.reset()
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
    """
    校验停用预演会暴露被依赖方检查结果但不失败。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    FakePluginService.reset()
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
    """
    校验插件启用使用构造期注入的集中依赖对象。

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
enabled: false
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
    FakePluginService.reset()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.set_plugin_enabled('demo', enabled=True, record_operation_log=False))

    assert result['ok'] is True
    assert FakePluginService.install_plugin_menu_called_with == ('demo', True)
    assert FakePluginService.update_enabled_called_with == ('demo', True)
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_check_reports_plugin_dependency_errors(tmp_path: Path) -> None:
    """
    校验插件检查会报告插件间依赖错误。

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
    """
    校验插件安装会阻止未满足的插件间依赖。

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
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件间依赖检查失败，安装已中止'
    assert result['pluginDependencyErrors'][0]['status'] == 'missing'
    assert FakePluginService.upsert_called is False
    assert FakePluginService.marked_errors == [('demo', '插件间依赖检查失败，安装已中止')]


def test_plugin_runtime_enable_blocks_unsatisfied_plugin_dependency(tmp_path: Path) -> None:
    """
    校验插件启用会阻止未满足的插件间依赖。

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
enabled: false
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
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).set_plugin_enabled('demo', enabled=True))

    assert result['ok'] is False
    assert result['message'] == '插件间依赖检查失败，启用已中止'
    assert result['pluginDependencyErrors'][0]['status'] == 'missing'
    assert FakePluginService.update_enabled_called_with is None
    assert FakePluginService.marked_errors == [('demo', '插件间依赖检查失败，启用已中止')]


def test_plugin_runtime_disable_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """
    校验插件停用执行失败时返回失败生命周期步骤。

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
    create_controller_dir(plugin_root)
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    async def raise_disable_failure(query_db: object, plugin_id: str, enabled: bool) -> object:
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
    """
    校验插件安全卸载 dry-run 返回安全卸载语义。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    backend_root.mkdir()

    result = asyncio.run(build_runtime(backend_root).uninstall_plugin('demo', dry_run=True))

    assert result['ok'] is True
    assert result['operation'] == 'uninstall'
    assert result['enabled'] is False
    assert result['safeMode'] is True
    assert result['removesSource'] is False
    assert result['removesMenus'] is True


def test_plugin_runtime_uninstall_plugin_delegates_to_enable_use_case(tmp_path: Path) -> None:
    """
    校验插件卸载入口委托给组合式启停 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeEnableUseCase:
        """
        测试用插件启停 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件启停 use case。
            """
            self.plugin_id: str | None = None
            self.dry_run: bool | None = None
            self.record_operation_log: bool | None = None

        async def uninstall_plugin(
            self,
            plugin_id: str,
            *,
            dry_run: bool = False,
            record_operation_log: bool = True,
        ) -> dict:
            """
            记录插件卸载调用。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :param record_operation_log: 是否记录审计日志
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.dry_run = dry_run
            self.record_operation_log = record_operation_log
            return {'ok': True, 'pluginId': plugin_id, 'operation': 'uninstall'}

    enable = FakeEnableUseCase()
    runtime.enable = enable

    payload = asyncio.run(runtime.uninstall_plugin('demo', dry_run=True, record_operation_log=False))

    assert enable.plugin_id == 'demo'
    assert enable.dry_run is True
    assert enable.record_operation_log is False
    assert payload == {'ok': True, 'pluginId': 'demo', 'operation': 'uninstall'}


def test_plugin_runtime_uninstall_plugin_dry_run_includes_precheck_when_source_exists(tmp_path: Path) -> None:
    """
    校验插件安全卸载 dry-run 在源码存在时返回统一预检负载。

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
    """
    校验卸载被启用插件依赖的插件时会阻断写库。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    FakePluginService.reset()
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
    """
    校验插件安全卸载会标记卸载并提交事务。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    backend_root.mkdir()
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).uninstall_plugin('demo'))

    assert result['ok'] is True
    assert result['operation'] == 'uninstall'
    assert FakePluginService.mark_uninstalled_called_with == 'demo'
    assert FakePluginService.update_enabled_called_with is None
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'uninstall'


def test_plugin_runtime_uninstall_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """
    校验插件卸载执行失败时返回失败生命周期步骤。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    backend_root.mkdir()
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    async def raise_uninstall_failure(query_db: object, plugin_id: str) -> object:
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
    """
    校验插件物理清理 dry-run 返回清理计划且不提交事务。

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
    FakePluginService.reset()

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


def test_plugin_runtime_purge_plugin_delegates_to_purge_use_case(tmp_path: Path) -> None:
    """
    校验插件物理清理入口委托给组合式清理 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakePurgeUseCase:
        """
        测试用插件清理 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件清理 use case。
            """
            self.plugin_id: str | None = None
            self.dry_run: bool | None = None
            self.record_operation_log: bool | None = None

        async def purge_plugin(
            self,
            plugin_id: str,
            *,
            dry_run: bool = False,
            record_operation_log: bool = True,
        ) -> dict:
            """
            记录插件物理清理调用。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :param record_operation_log: 是否记录审计日志
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.dry_run = dry_run
            self.record_operation_log = record_operation_log
            return {'ok': True, 'pluginId': plugin_id, 'operation': 'purge'}

    purge = FakePurgeUseCase()
    runtime.purge = purge

    payload = asyncio.run(runtime.purge_plugin('demo', dry_run=True, record_operation_log=False))

    assert purge.plugin_id == 'demo'
    assert purge.dry_run is True
    assert purge.record_operation_log is False
    assert payload == {'ok': True, 'pluginId': 'demo', 'operation': 'purge'}


def test_plugin_runtime_purge_plugin_blocks_enabled_dependents(tmp_path: Path) -> None:
    """
    校验物理清理被启用插件依赖的插件时会阻断写库。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    FakePluginService.reset()
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
    """
    校验物理清理 dry-run 会暴露被依赖方检查结果但不执行清理。

    :param tmp_path: pytest 临时目录
    :return: None
    """
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
    FakePluginService.reset()
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


def test_plugin_runtime_purge_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验物理清理 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    assert runtime.purge.context is runtime.context

    class FakePurgeContextService:
        """
        测试用物理清理上下文服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用物理清理上下文服务。
            """
            self.plugin_id: str | None = None
            self.capability_plugin: object | None = None

        def get_discovered_plugin(self, plugin_id: str) -> object:
            """
            记录插件发现调用。

            :param plugin_id: 插件ID
            :return: 测试插件对象
            """
            self.plugin_id = plugin_id
            return sentinel

        def with_plugin_capability(self, payload: dict, discovered_plugin: object | None) -> dict:
            """
            记录 capability 附加调用。

            :param payload: 响应负载
            :param discovered_plugin: 已发现插件
            :return: 附加后的响应负载
            """
            self.capability_plugin = discovered_plugin
            payload['contextPlugin'] = discovered_plugin
            return payload

    context = FakePurgeContextService()
    runtime.purge.context = context

    discovered_plugin = runtime.purge._get_discovered_plugin('demo')
    payload = runtime.purge._with_plugin_capability({'ok': True}, sentinel)

    assert context.plugin_id == 'demo'
    assert discovered_plugin is sentinel
    assert context.capability_plugin is sentinel
    assert payload == {'ok': True, 'contextPlugin': sentinel}


def test_plugin_runtime_purge_plugin_runs_hook_and_cleans_metadata(tmp_path: Path) -> None:
    """
    校验插件物理清理会执行 on_purge 钩子、清理平台元数据并提交事务。

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
  hooks:
    onPurge: hooks:on_purge
""",
    )
    (plugin_root / 'hooks.py').write_text(
        'async def on_purge(context):\n    context.query_db.purge_hook_ran = context.plugin_id\n',
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).purge_plugin('demo'))

    assert result['ok'] is True
    assert result['operation'] == 'purge'
    assert result['hooks'][0]['hook_name'] == 'on_purge'
    assert FakePluginService.purge_called is True
    assert gateway.session_local.sessions[0].purge_hook_ran == 'demo'
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'purge'


def test_plugin_runtime_purge_plugin_reports_failed_lifecycle_step(tmp_path: Path) -> None:
    """
    校验插件物理清理执行失败时返回失败生命周期步骤。

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
  hooks:
    onPurge: hooks:on_purge
""",
    )
    (plugin_root / 'hooks.py').write_text(
        "async def on_purge(context):\n    raise RuntimeError('purge hook failed')\n",
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).purge_plugin('demo'))

    assert result['ok'] is False
    assert result['pluginId'] == 'demo'
    assert result['operation'] == 'purge'
    assert result['failedStep'] == 'run_purge_hook'
    assert 'purge hook failed' in result['error']
    assert FakePluginService.purge_called is False


def test_plugin_runtime_purge_plugin_uses_injected_dependencies(tmp_path: Path) -> None:
    """
    校验插件物理清理使用构造期注入的集中依赖网关。

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
  hooks:
    onPurge: hooks:on_purge
""",
    )
    (plugin_root / 'hooks.py').write_text(
        'async def on_purge(context):\n    context.query_db.purge_hook_ran = context.plugin_id\n',
        encoding='utf-8',
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    result = asyncio.run(runtime.purge_plugin('demo', record_operation_log=False))

    assert result['ok'] is True
    assert FakePluginService.purge_called is True
    assert gateway.session_local.sessions[0].purge_hook_ran == 'demo'
    assert gateway.session_local.sessions[0].committed is True
