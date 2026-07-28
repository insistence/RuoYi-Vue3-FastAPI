from pathlib import Path

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.management.entity.vo.schemas import PluginModel
from plugins.core.manifest.schema import PluginManifest


def build_discovered_plugin(
    tmp_path: Path,
    plugin_id: str = 'demo',
    auto_scan: bool = True,
    version: str = '1.0.0',
) -> DiscoveredPlugin:
    """构造测试用已发现插件。"""
    backend_path = tmp_path / plugin_id
    backend_path.mkdir(parents=True)
    manifest_path = backend_path / 'plugin.yaml'
    manifest_path.write_text('', encoding='utf-8')
    manifest = PluginManifest.model_validate(
        {
            'id': plugin_id,
            'name': '演示插件',
            'version': version,
            'backend': {'module': f'plugins.{plugin_id}', 'routers': {'autoScan': auto_scan}},
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def build_database_plugin(plugin_id: str = 'demo', *, enabled: str = '0', status: str = 'installed') -> PluginModel:
    """构造测试用数据库插件状态。"""
    return PluginModel(
        pluginId=plugin_id,
        pluginName='演示插件',
        version='1.0.0',
        installedVersion='1.0.0',
        enabled=enabled,
        status=status,
    )


def test_registry_keeps_discovered_plugin_disabled_when_database_state_missing(tmp_path: Path) -> None:
    """校验缺少数据库状态时，已发现插件保持禁用。"""
    discovered_plugin = build_discovered_plugin(tmp_path)

    registry = PluginRegistry.build([discovered_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.enabled is False
    assert plugin.status == 'discovered'
    assert registry.list_enabled_plugins() == []


def test_registry_prefers_database_enabled_state(tmp_path: Path) -> None:
    """校验插件注册表优先采用数据库启用状态。"""
    discovered_plugin = build_discovered_plugin(tmp_path)
    database_plugin = build_database_plugin(enabled='1', status='installed')

    registry = PluginRegistry.build([discovered_plugin], [database_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.enabled is False
    assert plugin.status == 'installed'
    assert registry.list_enabled_plugins() == []


def test_registry_marks_pending_upgrade_when_versions_differ(tmp_path: Path) -> None:
    """校验源码版本高于已安装版本时标记待升级。"""
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
    """校验源码版本低于已安装版本时不会误标记待升级。"""
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
    """校验异常状态插件不会继续进入启用运行时列表。"""
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
    """校验注册表只返回实际存在的控制器与实体目录。"""
    discovered_plugin = build_discovered_plugin(tmp_path)
    database_plugin = build_database_plugin()
    controller_dir = discovered_plugin.backend_path / 'controller'
    entity_do_dir = discovered_plugin.backend_path / 'entity' / 'do'
    controller_dir.mkdir()
    entity_do_dir.mkdir(parents=True)

    registry = PluginRegistry.build([discovered_plugin], [database_plugin])

    assert registry.get_enabled_controller_dirs() == [controller_dir]
    assert registry.get_enabled_entity_do_dirs() == [entity_do_dir]


def test_registry_skips_controller_dir_when_auto_scan_disabled(tmp_path: Path) -> None:
    """校验关闭自动扫描后不返回控制器目录。"""
    discovered_plugin = build_discovered_plugin(tmp_path, auto_scan=False)
    database_plugin = build_database_plugin()
    controller_dir = discovered_plugin.backend_path / 'controller'
    controller_dir.mkdir()

    registry = PluginRegistry.build([discovered_plugin], [database_plugin])

    assert registry.get_enabled_controller_dirs() == []
