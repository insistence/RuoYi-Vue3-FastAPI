import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.discovery.registry import PluginRegistry  # noqa: E402
from plugins.core.discovery.scanner import DiscoveredPlugin  # noqa: E402
from plugins.core.management.entity.vo.schemas import PluginModel  # noqa: E402
from plugins.core.manifest.schema import PluginManifest  # noqa: E402


def build_discovered_plugin(
    tmp_path: Path,
    plugin_id: str = 'demo',
    enabled: bool = True,
    auto_scan: bool = True,
    version: str = '1.0.0',
) -> DiscoveredPlugin:
    """
    构造测试用已发现插件。

    :param tmp_path: pytest 临时目录
    :param plugin_id: 插件 ID
    :param enabled: manifest 默认启用状态
    :param auto_scan: 是否自动扫描 controller
    :param version: 插件版本
    :return: 已发现插件对象
    """
    backend_path = tmp_path / plugin_id
    backend_path.mkdir(parents=True)
    manifest_path = backend_path / 'plugin.yaml'
    manifest_path.write_text('', encoding='utf-8')
    manifest = PluginManifest.model_validate(
        {
            'id': plugin_id,
            'name': '演示插件',
            'version': version,
            'enabled': enabled,
            'backend': {'module': f'plugins.{plugin_id}', 'routers': {'autoScan': auto_scan}},
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def test_registry_uses_manifest_enabled_when_database_state_missing(tmp_path: Path) -> None:
    discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)

    registry = PluginRegistry.build([discovered_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.enabled is True
    assert plugin.status == 'discovered'
    assert registry.list_enabled_plugins() == [plugin]


def test_registry_prefers_database_enabled_state(tmp_path: Path) -> None:
    discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
    database_plugin = PluginModel(
        pluginId='demo',
        pluginName='演示插件',
        version='1.0.0',
        installedVersion='1.0.0',
        enabled='1',
        status='disabled',
    )

    registry = PluginRegistry.build([discovered_plugin], [database_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.enabled is False
    assert plugin.status == 'disabled'
    assert registry.list_enabled_plugins() == []


def test_registry_marks_pending_upgrade_when_versions_differ(tmp_path: Path) -> None:
    discovered_plugin = build_discovered_plugin(tmp_path, version='1.1.0')
    database_plugin = PluginModel(
        pluginId='demo',
        pluginName='演示插件',
        version='1.1.0',
        installedVersion='1.0.0',
        enabled='0',
        status='installed',
    )

    registry = PluginRegistry.build([discovered_plugin], [database_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.enabled is True
    assert plugin.status == 'pending_upgrade'


def test_registry_keeps_installed_when_source_version_is_older(tmp_path: Path) -> None:
    """
    校验源码版本低于已安装版本时不会误标记待升级。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    discovered_plugin = build_discovered_plugin(tmp_path, version='1.2.0')
    database_plugin = PluginModel(
        pluginId='demo',
        pluginName='演示插件',
        version='1.2.0',
        installedVersion='1.10.0',
        enabled='0',
        status='installed',
    )

    registry = PluginRegistry.build([discovered_plugin], [database_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.status == 'installed'


def test_registry_keeps_error_status(tmp_path: Path) -> None:
    """
    校验异常状态插件不会继续进入启用运行时列表。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    discovered_plugin = build_discovered_plugin(tmp_path)
    database_plugin = PluginModel(
        pluginId='demo',
        pluginName='演示插件',
        version='1.0.0',
        installedVersion='1.0.0',
        enabled='0',
        status='error',
    )

    registry = PluginRegistry.build([discovered_plugin], [database_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.enabled is False
    assert plugin.status == 'error'
    assert registry.list_enabled_plugins() == []


def test_registry_returns_existing_controller_and_entity_dirs(tmp_path: Path) -> None:
    discovered_plugin = build_discovered_plugin(tmp_path)
    controller_dir = discovered_plugin.backend_path / 'controller'
    entity_do_dir = discovered_plugin.backend_path / 'entity' / 'do'
    controller_dir.mkdir()
    entity_do_dir.mkdir(parents=True)

    registry = PluginRegistry.build([discovered_plugin])

    assert registry.get_enabled_controller_dirs() == [controller_dir]
    assert registry.get_enabled_entity_do_dirs() == [entity_do_dir]


def test_registry_skips_controller_dir_when_auto_scan_disabled(tmp_path: Path) -> None:
    discovered_plugin = build_discovered_plugin(tmp_path, auto_scan=False)
    controller_dir = discovered_plugin.backend_path / 'controller'
    controller_dir.mkdir()

    registry = PluginRegistry.build([discovered_plugin])

    assert registry.get_enabled_controller_dirs() == []
