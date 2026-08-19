from pathlib import Path

from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.validation.structure import PluginStructureChecker


def write_manifest(plugin_dir: Path, content: str) -> Path:
    """写入测试插件清单。"""
    plugin_dir.mkdir(parents=True)
    manifest_path = plugin_dir / 'plugin.yaml'
    manifest_path.write_text(content, encoding='utf-8')
    return manifest_path


def load_discovered_plugin(backend_root: Path, plugin_id: str) -> DiscoveredPlugin:
    """加载测试插件。"""
    return PluginScanner(backend_root / 'plugins').load_manifest(backend_root / 'plugins' / plugin_id / 'plugin.yaml')


def test_structure_checker_accepts_valid_backend_and_frontend_plugin(tmp_path: Path) -> None:
    """校验结构检查器接受完整插件结构。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    frontend_root = tmp_path / 'ruoyi-fastapi-frontend'
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
frontend:
  menus:
    - name: 演示菜单
      path: demo
      component: plugin/demo/index
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'seeds').mkdir()
    (plugin_root / 'seeds' / 'demo_seed.py').write_text('async def run(query_db):\n    return None\n', encoding='utf-8')
    (frontend_root / 'plugins' / 'demo' / 'views').mkdir(parents=True)
    (frontend_root / 'plugins' / 'demo' / 'api').mkdir()
    (frontend_root / 'plugins' / 'demo' / 'views' / 'index.vue').write_text('<template />\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root, frontend_root / 'plugins').check(
        load_discovered_plugin(backend_root, 'demo')
    )

    assert result.ok is True
    assert result.failed_items == []


def test_structure_checker_reports_missing_frontend_directories_from_manifest(tmp_path: Path) -> None:
    """校验结构检查器按主清单 frontend 字段报告前端目录缺失问题。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    frontend_root = tmp_path / 'ruoyi-fastapi-frontend'
    plugin_root = backend_root / 'plugins' / 'demo'
    frontend_plugin_root = frontend_root / 'plugins' / 'demo'
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
    (plugin_root / 'controller').mkdir()
    frontend_plugin_root.mkdir(parents=True)

    result = PluginStructureChecker(backend_root, frontend_root / 'plugins').check(
        load_discovered_plugin(backend_root, 'demo')
    )

    assert result.ok is False
    assert [item.kind for item in result.failed_items] == [
        'frontend_views_path',
        'frontend_api_path',
        'frontend_view',
    ]


def test_structure_checker_can_skip_frontend_source_checks_for_built_deployments(tmp_path: Path) -> None:
    """校验已构建前端部署可以只检查插件后端结构。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
    (plugin_root / 'controller').mkdir()

    result = PluginStructureChecker(backend_root, tmp_path / 'missing-frontend' / 'plugins').check(
        load_discovered_plugin(backend_root, 'demo'),
        include_frontend=False,
    )

    assert result.ok is True
    assert not any(item.kind.startswith('frontend_') for item in result.items)


def test_structure_checker_accepts_plugin_controller_route_prefix(tmp_path: Path) -> None:
    """校验结构检查器接受当前插件命名空间内的 controller 路由前缀。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'controller' / 'demo_controller.py').write_text(
        "from common.router import APIRouterPro\n\ndemo_controller = APIRouterPro(prefix='/demo/items')\n",
        encoding='utf-8',
    )

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    route_prefix_items = [item for item in result.items if item.kind == 'controller_route_prefix']
    assert route_prefix_items
    assert result.failed_items == []


def test_structure_checker_reports_plugin_controller_route_prefix_escape(tmp_path: Path) -> None:
    """校验结构检查器拒绝越过当前插件命名空间的 controller 路由前缀。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'controller' / 'demo_controller.py').write_text(
        "from common.router import APIRouterPro\n\ndemo_controller = APIRouterPro(prefix='/system/user')\n",
        encoding='utf-8',
    )

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is False
    assert [item.kind for item in result.failed_items] == ['controller_route_prefix']


def test_structure_checker_reports_missing_seed_and_frontend_view(tmp_path: Path) -> None:
    """校验结构检查器能报告缺失 seed 和前端视图。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    frontend_root = tmp_path / 'ruoyi-fastapi-frontend'
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
    (frontend_root / 'plugins' / 'demo' / 'views').mkdir(parents=True)

    result = PluginStructureChecker(backend_root, frontend_root / 'plugins').check(
        load_discovered_plugin(backend_root, 'demo')
    )

    assert result.ok is False
    assert [item.kind for item in result.failed_items] == [
        'seed_file',
        'frontend_api_path',
        'frontend_view',
    ]
    assert [item.level for item in result.failed_items] == ['error', 'error', 'error']
    assert result.failed_items[0].to_issue().category == 'structure'


def test_structure_checker_does_not_require_frontend_for_backend_only_plugin(tmp_path: Path) -> None:
    """校验后端插件没有插件菜单视图时，不强制要求前端目录存在。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is True
    assert all(item.kind != 'frontend_root' for item in result.items)


def test_structure_checker_accepts_sql_seed(tmp_path: Path) -> None:
    """校验结构检查器接受 SQL seed。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'seeds').mkdir()
    (plugin_root / 'seeds' / 'demo_seed.sql').write_text('select 1;\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is True
    assert result.failed_items == []


def test_structure_checker_checks_migration_files(tmp_path: Path) -> None:
    """校验结构检查器会检查 migration 文件存在性和类型。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
    - migrations/001_init.sql
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'migrations').mkdir()
    (plugin_root / 'migrations' / '001_init.sql').write_text('create table demo(id int);\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is True
    assert result.failed_items == []


def test_structure_checker_reports_missing_migration_and_unsupported_type(tmp_path: Path) -> None:
    """校验结构检查器会报告缺失 migration 和暂不支持的 migration 类型。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is False
    assert [item.kind for item in result.failed_items] == ['migration_file', 'migration_type']


def test_structure_checker_reports_migration_escape_path(tmp_path: Path) -> None:
    """校验结构检查器会报告越过插件根目录的 migration 路径。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
    - ../outside.sql
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (backend_root / 'plugins' / 'outside.sql').write_text('select 1;\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is False
    failed_item = result.failed_items[0]
    assert failed_item.kind == 'migration_file'
    assert failed_item.path == '../outside.sql'
    assert failed_item.message == '文件路径不能越过插件根目录：../outside.sql'
    assert failed_item.suggestion == '请使用插件目录内的相对路径'


def test_structure_checker_reports_seed_escape_path(tmp_path: Path) -> None:
    """校验结构检查器会报告越过插件根目录的 seed 路径。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
    - ../outside.sql
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (backend_root / 'plugins' / 'outside.sql').write_text('select 1;\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is False
    failed_item = result.failed_items[0]
    assert failed_item.kind == 'seed_file'
    assert failed_item.path == '../outside.sql'
    assert failed_item.message == '文件路径不能越过插件根目录：../outside.sql'
    assert failed_item.suggestion == '请使用插件目录内的相对路径'


def test_structure_checker_accepts_valid_plugin_job(tmp_path: Path) -> None:
    """校验结构检查器接受有效的插件定时任务声明。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
  jobs:
    - id: cleanup
      name: 清理任务
      callable: plugins.demo.jobs.cleanup
      cronExpression: '0 0/5 * * * ?'
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'jobs.py').write_text('def cleanup():\n    return None\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is True
    assert [item.kind for item in result.items if item.kind.startswith('job_')] == [
        'job_name',
        'job_callable_boundary',
        'job_callable',
        'job_cron',
    ]


def test_structure_checker_does_not_execute_job_module_top_level_code(tmp_path: Path) -> None:
    """校验结构检查验证任务 callable 时不会执行插件模块顶层代码。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    side_effect_file = tmp_path / 'job_side_effect.txt'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
  jobs:
    - id: cleanup
      name: 清理任务
      callable: plugins.demo.jobs.cleanup
      cronExpression: '0 0/5 * * * ?'
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'jobs.py').write_text(
        f"from pathlib import Path\nPath({str(side_effect_file)!r}).write_text('executed')\n"
        'def cleanup():\n    return None\n',
        encoding='utf-8',
    )

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is True
    assert side_effect_file.exists() is False


def test_structure_checker_reports_invalid_plugin_job(tmp_path: Path) -> None:
    """校验结构检查器报告越界 callable、不可导入 callable 和无效 cron。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
  jobs:
    - id: cleanup
      callable: plugins.demo.missing.cleanup
      cronExpression: invalid
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is False
    assert [item.kind for item in result.failed_items] == [
        'job_callable',
        'job_cron',
    ]


def test_structure_checker_accepts_valid_plugin_hook(tmp_path: Path) -> None:
    """校验结构检查器接受有效的插件生命周期钩子声明。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'hooks.py').write_text('async def on_install(context):\n    return None\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is True
    assert [item.kind for item in result.items if item.kind.startswith('hook_')] == [
        'hook_boundary',
        'hook_callable',
    ]


def test_structure_checker_rejects_sync_plugin_hook(tmp_path: Path) -> None:
    """校验结构预检拒绝无法安全终止的同步生命周期钩子。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'hooks.py').write_text('def on_install(context):\n    return None\n', encoding='utf-8')

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is False
    assert [item.kind for item in result.failed_items] == ['hook_callable']
    assert 'async def' in result.failed_items[0].message


def test_structure_checker_does_not_execute_hook_module_top_level_code(tmp_path: Path) -> None:
    """校验结构检查验证生命周期钩子时不会执行插件模块顶层代码。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
    side_effect_file = tmp_path / 'hook_side_effect.txt'
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
frontend:
  menus: []
""",
    )
    (plugin_root / 'controller').mkdir()
    (plugin_root / 'hooks.py').write_text(
        f"from pathlib import Path\nPath({str(side_effect_file)!r}).write_text('executed')\n"
        'async def on_install(context):\n    return None\n',
        encoding='utf-8',
    )

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is True
    assert side_effect_file.exists() is False


def test_structure_checker_reports_invalid_plugin_hook(tmp_path: Path) -> None:
    """校验结构检查器报告越界和不可导入生命周期钩子。"""
    backend_root = tmp_path / 'ruoyi-fastapi-backend'
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

    result = PluginStructureChecker(backend_root).check(load_discovered_plugin(backend_root, 'demo'))

    assert result.ok is False
    assert [item.kind for item in result.failed_items] == [
        'hook_boundary',
        'hook_callable',
    ]
