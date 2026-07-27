from pathlib import Path

from tests.plugins.core.runtime.fakes import build_runtime, create_controller_dir, create_frontend_view, write_manifest


def test_plugin_runtime_check_reports_structure_errors(tmp_path: Path) -> None:
    """校验插件运行时检查会报告结构错误。"""
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
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
    - seeds/missing_seed.py
frontend:
  menus:
    - name: 演示菜单
      path: demo
      component: plugin/demo/missing
""",
    )
    (plugin_root / 'controller').mkdir()
    (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo' / 'views').mkdir(parents=True)

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is False
    assert payload['checks'][0]['missingDependencies'] == []
    assert [item['kind'] for item in payload['checks'][0]['structureErrors']] == [
        'seed_file',
        'frontend_api_path',
        'frontend_view',
    ]
    assert [item['level'] for item in payload['checks'][0]['structureErrors']] == ['error', 'error', 'error']


def test_plugin_runtime_check_uses_runtime_frontend_plugin_root(tmp_path: Path) -> None:
    """校验插件检查使用运行时环境提供的前端插件目录。"""
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
frontend:
  menus:
    - name: 演示菜单
      path: demo
      component: plugin/demo/index
""",
    )
    create_controller_dir(plugin_root)
    create_frontend_view(backend_root, 'demo', frontend_root=frontend_root)

    payload = build_runtime(backend_root, frontend_root=frontend_root).check_plugin('demo')

    assert payload['ok'] is True
    assert payload['checks'][0]['structureErrors'] == []


def test_plugin_runtime_check_reports_migration_structure_errors(tmp_path: Path) -> None:
    """校验插件运行时检查会报告 migration 结构错误。"""
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
    - migrations/missing.txt
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is False
    assert [item['kind'] for item in payload['checks'][0]['structureErrors']] == [
        'migration_file',
        'migration_type',
    ]


def test_plugin_runtime_check_reports_hook_structure_errors(tmp_path: Path) -> None:
    """校验插件运行时检查会报告 hook 结构错误。"""
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
    onInstall: plugins.other.hooks:on_install
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is False
    assert [item['kind'] for item in payload['checks'][0]['structureErrors']] == [
        'hook_boundary',
        'hook_callable',
    ]


def test_plugin_runtime_check_accepts_sql_seed(tmp_path: Path) -> None:
    """校验插件运行时检查接受 SQL seed。"""
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

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is True
    assert payload['checks'][0]['structureErrors'] == []


def test_plugin_runtime_check_accepts_namespaced_permissions(tmp_path: Path) -> None:
    """校验插件运行时检查接受不同插件使用各自权限命名空间。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
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
    create_controller_dir(backend_root / 'plugins' / 'demo')
    create_frontend_view(backend_root, 'demo')
    write_manifest(
        backend_root / 'plugins' / 'sample',
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
    create_controller_dir(backend_root / 'plugins' / 'sample')
    create_frontend_view(backend_root, 'sample')

    payload = build_runtime(backend_root).check_plugin('sample')

    assert payload['ok'] is True
    assert payload['checks'][0]['menuConflicts'] == []
