# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_runtime_check_reports_structure_errors(tmp_path: Path) -> None:
    """
    校验插件运行时检查会报告结构错误。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
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


def test_plugin_runtime_check_reports_migration_structure_errors(tmp_path: Path) -> None:
    """
    校验插件运行时检查会报告 migration 结构错误。

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
    """
    校验插件运行时检查会报告 hook 结构错误。

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
    """
    校验插件运行时检查接受 SQL seed。

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

    payload = build_runtime(backend_root).check_plugin('demo')

    assert payload['ok'] is True
    assert payload['checks'][0]['structureErrors'] == []


def test_plugin_runtime_check_reports_menu_conflicts(tmp_path: Path) -> None:
    """
    校验插件运行时检查会报告菜单冲突。

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
    write_manifest(
        backend_root / 'plugins' / 'sample',
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

    payload = build_runtime(backend_root).check_plugin('sample')

    assert payload['ok'] is False
    assert payload['checks'][0]['menuConflicts'][0]['kind'] == 'duplicate_permission'
    assert payload['checks'][0]['menuConflicts'][0]['level'] == 'error'
    assert payload['checks'][0]['menuConflicts'][0]['value'] == 'shared:list'
