from pathlib import Path

from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.validation.menus import PluginMenuConflictChecker


def write_manifest(plugin_dir: Path, content: str) -> Path:
    """写入测试插件清单。"""
    plugin_dir.mkdir(parents=True)
    manifest_path = plugin_dir / 'plugin.yaml'
    manifest_path.write_text(content, encoding='utf-8')
    return manifest_path


def load_plugin(backend_root: Path, plugin_id: str) -> DiscoveredPlugin:
    """加载测试插件。"""
    return PluginScanner(backend_root / 'plugins').load_manifest(backend_root / 'plugins' / plugin_id / 'plugin.yaml')


def test_menu_conflict_checker_reports_duplicate_menu_key_in_single_plugin(tmp_path: Path) -> None:
    """校验菜单冲突检查器会报告单插件内重复菜单自然键。"""
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
    - name: Demo One
      path: demo
      component: plugin/demo/index
      perms: demo:list
    - name: Demo Two
      path: demo-copy
      component: plugin/demo/copy
      perms: demo:list
permissions:
  - demo:list
""",
    )
    plugin = load_plugin(backend_root, 'demo')

    result = PluginMenuConflictChecker().check(plugin)

    assert result.ok is False
    assert result.items[0].kind == 'duplicate_menu_key'
    assert result.items[0].value == 'perm:demo:list'


def test_menu_conflict_checker_accepts_namespaced_permissions_across_plugins(tmp_path: Path) -> None:
    """校验菜单冲突检查器接受不同插件使用各自权限命名空间。"""
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
""",
    )
    write_manifest(
        backend_root / 'plugins' / 'sample',
        """
id: sample
name: Sample
version: 1.0.0
backend:
  module: plugins.sample
frontend:
  menus:
    - name: Sample
      path: sample
      component: plugin/sample/index
      perms: sample:list
permissions:
  - sample:list
""",
    )
    plugin_list = PluginScanner(backend_root / 'plugins').discover()
    plugin_map = {plugin.manifest.id: plugin for plugin in plugin_list}

    result = PluginMenuConflictChecker().check(plugin_map['sample'], plugin_list)

    assert result.ok is True
    assert result.items == []


def test_menu_conflict_checker_accepts_unique_plugin_menus(tmp_path: Path) -> None:
    """校验菜单冲突检查器接受无冲突菜单。"""
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
""",
    )
    plugin = load_plugin(backend_root, 'demo')

    result = PluginMenuConflictChecker().check(plugin)

    assert result.ok is True
    assert result.items == []
