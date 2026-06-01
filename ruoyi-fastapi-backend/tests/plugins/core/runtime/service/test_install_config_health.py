# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_runtime_install_plugin_dry_run_returns_actions(tmp_path: Path) -> None:
    """
    校验插件安装 dry-run 返回动作计划且不写数据库。

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


def test_plugin_runtime_install_plugin_rejects_manifest_errors(tmp_path: Path) -> None:
    """
    校验插件安装会被 manifest error 阻断。

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
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件 manifest 检查失败，安装已中止'
    assert result['manifestOk'] is False
    assert result['manifestIssues'][0]['kind'] == 'compatibility_unsatisfied'
    assert FakePluginService.upsert_called is False
    assert FakePluginService.marked_errors == [('demo', '插件 manifest 检查失败，安装已中止')]


def test_plugin_runtime_install_plugin_runs_sql_seed(tmp_path: Path) -> None:
    """
    校验插件安装可以执行 SQL seed。

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
  seeds:
    - seeds/demo_seed.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'seeds').mkdir()
    (plugin_root / 'seeds' / 'demo_seed.sql').write_text('select 1;\n', encoding='utf-8')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['structureOk'] is True
    assert result['structureErrors'] == []
    assert result['seeds'][0]['seed_path'] == 'seeds/demo_seed.sql'
    assert result['seeds'][0]['statement_count'] == 1
    assert gateway.session_local.sessions[0].executed_statements == ['select 1']
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_install_plugin_runs_sql_migration(tmp_path: Path) -> None:
    """
    校验插件安装可以执行 SQL migration。

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
  migrations:
    - migrations/001_demo.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_demo.sql').write_text('select 2;\n', encoding='utf-8')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['migrations'][0]['migration_path'] == 'migrations/001_demo.sql'
    assert result['migrations'][0]['statement_count'] == 1
    assert result['migrations'][0]['checksum']
    assert result['migrations'][0]['skipped'] is False
    assert len(FakePluginService.migration_records) == 1
    assert FakePluginService.migration_records[0].migration_path == 'migrations/001_demo.sql'
    assert gateway.session_local.sessions[0].executed_statements == ['select 2']
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_install_plugin_skips_recorded_migration(tmp_path: Path) -> None:
    """
    校验插件安装会跳过已记录且未变化的 migration。

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
  migrations:
    - migrations/001_demo.sql
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    migration_file = plugin_root / 'migrations' / '001_demo.sql'
    migration_file.write_text('select 2;\n', encoding='utf-8')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    FakePluginService.migration_checksums = {
        ('demo', 'migrations/001_demo.sql'): PluginMigrationRunner._calculate_checksum(migration_file)
    }

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['migrations'][0]['skipped'] is True
    assert FakePluginService.migration_records == []
    assert gateway.session_local.sessions[0].executed_statements == []
    assert gateway.session_local.sessions[0].committed is True


def test_plugin_runtime_install_plugin_stops_when_menu_conflict_exists(tmp_path: Path) -> None:
    """
    校验插件安装遇到菜单冲突时中止且只写失败审计。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    demo_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        demo_root,
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
frontend:
  menus:
    - name: 演示菜单
      path: demo
      component: plugin/demo/index
      perms: shared:list
permissions:
  - shared:list
""",
    )
    sample_root = backend_root / 'plugins' / 'sample'
    write_manifest(
        sample_root,
        """
id: sample
name: 样例插件
version: 1.0.0
enabled: true
backend:
  module: plugins.sample
frontend:
  menus:
    - name: 样例菜单
      path: sample
      component: plugin/sample/index
      perms: shared:list
permissions:
  - shared:list
""",
    )
    create_controller_dir(demo_root)
    create_controller_dir(sample_root)
    create_frontend_view(backend_root, 'demo')
    create_frontend_view(backend_root, 'sample')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('sample'))

    assert result['ok'] is False
    assert result['message'] == '插件菜单存在冲突，安装已中止'
    assert result['menuConflictOk'] is False
    assert result['menuConflicts'][0]['kind'] == 'duplicate_permission'
    assert FakePluginService.upsert_called is False
    assert gateway.session_local.sessions[0].committed is True
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['operation'] == 'install'
    assert FakePluginService.operation_logs[0].payload['pluginId'] == 'sample'
    assert FakePluginService.operation_logs[0].payload['ok'] is False


def test_plugin_runtime_install_plugin_stops_when_database_menu_conflict_exists(tmp_path: Path) -> None:
    """
    校验插件安装遇到数据库已安装菜单冲突时中止且不写插件状态。

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
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()
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
    """
    校验插件安装会写入插件状态和菜单。

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
    create_frontend_view(backend_root, 'demo')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

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


def test_plugin_runtime_install_disabled_plugin_persists_disabled_menus(tmp_path: Path) -> None:
    """
    校验默认停用插件安装时也会写入菜单，并保持菜单停用，便于后续启用时展示菜单。

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
enabled: false
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
""",
    )
    create_controller_dir(plugin_root)
    create_frontend_view(backend_root, 'demo')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['plugin']['status'] == 'disabled'
    assert FakePluginService.install_plugin_menu_called_with == ('demo', False)
    assert FakePluginService.mark_installed_called is True


def test_plugin_runtime_install_plugin_auto_installs_missing_dependencies(tmp_path: Path) -> None:
    """
    校验插件安装会自动执行缺失依赖安装计划。

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
    frontend_root = backend_root.parent / 'ruoyi-fastapi-frontend'
    frontend_root.mkdir()
    (frontend_root / 'package.json').write_text('{"dependencies": {}, "devDependencies": {}}\n', encoding='utf-8')
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()
    expected_plan_count = 3
    runtime = build_runtime_with_gateway(backend_root, gateway)
    runtime._refresh_dependency_checker = lambda: setattr(
        runtime,
        'dependency_checker',
        PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'missing-python': '1.0.0'}),
            npm_inspector=NpmDependencyInspector(
                installed_packages={'missing-npm': '1.2.3', 'missing-dev-npm': '4.5.6'}
            ),
        ),
    )

    result = asyncio.run(runtime.install_plugin('demo'))

    assert result['ok'] is True
    assert result['dependencyInstall']['ok'] is True
    assert result['dependencyInstall']['planCount'] == expected_plan_count
    assert result['dependencyInstall']['dependencyOk'] is False
    assert result['dependencyInstall']['postCheck']['dependencyOk'] is True
    assert result['dependencyOk'] is True
    assert gateway.commands[0][0][1:4] == ['-m', 'pip', 'install']
    assert gateway.commands[0][0][-1] == 'missing-python'
    assert gateway.commands[1][0] == ['npm', 'install', 'missing-npm@>=1.2.3']
    assert gateway.commands[2][0] == ['npm', 'install', '--save-dev', 'missing-dev-npm@4.5.6']
    package_json = json.loads((frontend_root / 'package.json').read_text(encoding='utf-8'))
    assert package_json['dependencies']['missing-npm'] == '>=1.2.3'
    assert package_json['devDependencies']['missing-dev-npm'] == '4.5.6'
    assert FakePluginService.upsert_called is True
    assert FakePluginService.mark_installed_called is True


def test_plugin_runtime_install_plugin_stops_when_dependency_install_fails(tmp_path: Path) -> None:
    """
    校验插件依赖自动安装失败时中止插件安装。

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
dependencies:
  python:
    - missing-python
""",
    )
    create_controller_dir(plugin_root)
    gateway = FakePluginInfrastructureGateway()
    gateway.completed_process = CompletedProcess(args=[], returncode=1, stdout='', stderr='install failed')
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is False
    assert result['message'] == '插件依赖安装失败，安装已中止'
    assert result['dependencyInstall']['ok'] is False
    assert result['dependencyInstall']['results'][0]['stderr'] == 'install failed'
    assert FakePluginService.upsert_called is False
    assert FakePluginService.mark_installed_called is False


def test_plugin_runtime_get_and_set_plugin_config(tmp_path: Path) -> None:
    """
    校验插件运行时可以读取和更新插件配置。

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
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()
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


def test_plugin_runtime_export_plugin_config_masks_secret_by_default(tmp_path: Path) -> None:
    """
    校验插件配置导出默认脱敏敏感配置，并可显式导出明文。

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
config:
  items:
    - key: api_key
      label: API Key
      type: password
      default: sk-secret
      secret: true
""",
    )
    runtime = build_runtime_with_gateway(backend_root, FakePluginInfrastructureGateway())

    masked_result = asyncio.run(runtime.export_plugin_config('demo'))
    plain_result = asyncio.run(runtime.export_plugin_config('demo', reveal_secret=True))

    assert masked_result['ok'] is True
    assert masked_result['revealSecret'] is False
    assert masked_result['values']['api_key'] == '******'
    assert masked_result['metadata'][0]['secret'] is True
    assert plain_result['revealSecret'] is True
    assert plain_result['values']['api_key'] == 'sk-secret'


def test_plugin_runtime_import_plugin_config_updates_values(tmp_path: Path) -> None:
    """
    校验插件配置导入会复用配置更新能力。

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
config:
  items:
    - key: provider
      label: 默认供应商
      type: string
      default: openai
""",
    )
    FakePluginService.reset()
    runtime = build_runtime_with_gateway(backend_root, FakePluginInfrastructureGateway())

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
    """
    校验插件诊断包会聚合检查结果和脱敏配置快照。

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

    result = asyncio.run(runtime.diagnose_plugin('demo'))

    assert result['ok'] is True, result
    assert result['pluginId'] == 'demo'
    assert result['info']['pluginId'] == 'demo'
    assert result['check']['checks'][0]['pluginId'] == 'demo'
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


def test_plugin_runtime_health_plugin_returns_checker_result(tmp_path: Path) -> None:
    """
    校验插件运行时可以执行健康检查。

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
    """
    校验插件健康检查会报告不存在的插件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    result = asyncio.run(build_runtime(tmp_path / 'backend').health_plugin('missing'))

    assert result['ok'] is False
    assert result['pluginId'] == 'missing'
    assert result['exit_code'] == RUNTIME_ERROR


def test_plugin_runtime_install_plugin_runs_seed_files(tmp_path: Path) -> None:
    """
    校验插件安装会执行 manifest 声明的 seed 文件。

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
    gateway = FakePluginInfrastructureGateway()
    FakePluginService.reset()

    result = asyncio.run(build_runtime_with_gateway(backend_root, gateway).install_plugin('demo'))

    assert result['ok'] is True
    assert result['seeds'][0]['seed_path'] == 'seeds/demo_seed.py'
    assert gateway.session_local.sessions[0].seed_ran is True
