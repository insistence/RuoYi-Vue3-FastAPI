from pathlib import Path

from plugins.core.capability import PluginRuntimeCapabilityResolver
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.schema import PluginManifest


def build_discovered_plugin(*, with_frontend: bool = True) -> DiscoveredPlugin:
    """
    构建能力测试使用的已发现插件。

    :param with_frontend: 是否包含前端资源
    :return: 已发现插件
    """
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


def test_capability_allows_cleanup_operations_when_runtime_is_not_manageable() -> None:
    """
    校验非运行时可管理环境下仍允许停用、卸载和清理等收敛操作。

    :return: None
    """
    capability = PluginRuntimeCapabilityResolver(frontend_mode='built', backend_runtime_mode='service').resolve(
        build_discovered_plugin()
    )

    assert capability.runtime_manageable is False
    assert capability.allows('install') is False
    assert capability.allows('enable') is False
    assert capability.allows('upgrade') is False
    assert capability.allows('dependency_install') is False
    assert capability.allows('disable') is True
    assert capability.allows('uninstall') is True
    assert capability.allows('purge') is True
