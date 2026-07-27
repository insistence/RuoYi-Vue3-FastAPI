from pathlib import Path

from plugins.core.capability import PluginRuntimeCapabilityResolver
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.schema import PluginManifest


def build_discovered_plugin(*, with_frontend: bool = True) -> DiscoveredPlugin:
    """构建能力测试使用的已发现插件。"""
    manifest_data: dict[str, object] = {
        'id': 'demo',
        'name': 'Demo',
        'version': '1.0.0',
        'backend': {'module': 'plugins.demo'},
    }
    if with_frontend:
        manifest_data['frontend'] = {'menus': [{'name': 'Demo', 'path': 'demo', 'component': 'plugin/demo/index'}]}

    return DiscoveredPlugin(
        manifest=PluginManifest.model_validate(manifest_data),
        backend_path=Path('/tmp/plugins/demo'),
        manifest_path=Path('/tmp/plugins/demo/plugin.yaml'),
    )


def test_capability_blocks_all_state_change_operations_when_runtime_is_not_manageable() -> None:
    """校验运行时不可管理时阻止全部状态变更操作。"""
    capability = PluginRuntimeCapabilityResolver(frontend_mode='built', backend_runtime_mode='service').resolve(
        build_discovered_plugin()
    )

    assert capability.runtime_manageable is False
    assert capability.allows('install') is False
    assert capability.allows('enable') is False
    assert capability.allows('upgrade') is False
    assert capability.allows('dependency_install') is False
    assert capability.allows('disable') is False
    assert capability.allows('uninstall') is False
    assert capability.allows('purge') is False


def test_capability_allows_state_change_operations_in_dev_mode() -> None:
    """校验开发模式允许运行插件状态变更操作。"""
    capability = PluginRuntimeCapabilityResolver(frontend_mode='dev', backend_runtime_mode='dev').resolve(
        build_discovered_plugin()
    )

    assert capability.runtime_manageable is True
    assert capability.allows('install') is True
    assert capability.allows('disable') is True
    assert capability.allows('uninstall') is True
    assert capability.allows('purge') is True
