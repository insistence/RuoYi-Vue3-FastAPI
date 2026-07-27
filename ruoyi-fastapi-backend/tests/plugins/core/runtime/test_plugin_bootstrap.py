import sys
from pathlib import Path

from plugins.core.management.entity.vo.schemas import PluginModel
from plugins.core.runtime.bootstrap import PluginRuntimeBuilder

BACKEND_ROOT = Path(__file__).resolve().parents[4]


def test_plugin_runtime_builder_defaults_to_backend_root() -> None:
    """校验运行时构建器默认使用后端项目根目录。"""
    builder = PluginRuntimeBuilder()

    assert builder.backend_root == BACKEND_ROOT
    assert builder.plugins_root == BACKEND_ROOT / 'plugins'
    assert builder.frontend_plugins_root == BACKEND_ROOT.parent / 'ruoyi-fastapi-frontend' / 'plugins'


def test_plugin_runtime_builder_resolves_frontend_plugins_root_from_backend_root(tmp_path: Path) -> None:
    """校验运行时构建器根据后端根目录解析前端插件目录。"""
    backend_root = tmp_path / 'api-server'

    builder = PluginRuntimeBuilder(backend_root)

    assert builder.frontend_plugins_root == tmp_path / 'frontend' / 'plugins'


def write_manifest(plugin_dir: Path, content: str) -> None:
    """写入测试插件清单。"""
    plugin_dir.mkdir(parents=True)
    (plugin_dir / 'plugin.yaml').write_text(content, encoding='utf-8')


def test_plugin_runtime_builder_builds_registry_from_backend_plugins(tmp_path: Path) -> None:
    """校验运行时构建器从后端插件目录创建注册表。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )

    registry = PluginRuntimeBuilder(backend_root).build_registry()

    plugin = registry.get_plugin('demo')
    assert plugin is not None
    assert plugin.enabled is False
    assert plugin.status == 'discovered'


def test_plugin_runtime_builder_returns_empty_registry_when_plugins_root_missing(tmp_path: Path) -> None:
    """校验插件目录不存在时运行时构建器返回空注册表。"""
    registry = PluginRuntimeBuilder(tmp_path / 'backend').build_registry()

    assert registry.list_plugins() == []


def test_plugin_runtime_builder_merges_database_plugin_state(tmp_path: Path) -> None:
    """校验运行时构建器会合并数据库插件状态。"""
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )
    database_plugin = PluginModel(
        pluginId='demo',
        pluginName='演示插件',
        version='1.0.0',
        installedVersion='1.0.0',
        enabled='1',
        status='installed',
    )

    registry = PluginRuntimeBuilder(backend_root).build_registry([database_plugin])
    plugin = registry.get_plugin('demo')

    assert plugin is not None
    assert plugin.enabled is False
    assert plugin.status == 'installed'


def test_plugin_runtime_builder_imports_enabled_plugin_entities(tmp_path: Path) -> None:
    """校验运行时构建器可以导入启用插件实体。"""
    backend_root = tmp_path / 'backend'
    plugin_dir = backend_root / 'plugins' / 'sample_entity'
    write_manifest(
        plugin_dir,
        """
id: sample_entity
name: 演示插件
version: 1.0.0
backend:
  module: plugins.sample_entity
""",
    )
    entity_do_dir = plugin_dir / 'entity' / 'do'
    entity_do_dir.mkdir(parents=True)
    (entity_do_dir / 'demo_do.py').write_text('DEMO_PLUGIN_ENTITY_IMPORTED = True\n', encoding='utf-8')
    builder = PluginRuntimeBuilder(backend_root)
    registry = builder.build_registry(
        [
            PluginModel(
                pluginId='sample_entity',
                pluginName='演示插件',
                version='1.0.0',
                installedVersion='1.0.0',
                enabled='0',
                status='installed',
            )
        ]
    )

    import_result = builder.import_plugin_entities(registry)

    assert import_result.imported_count == 1
    assert import_result.failures == []
    assert sys.modules['plugins.sample_entity.entity.do.demo_do'].DEMO_PLUGIN_ENTITY_IMPORTED is True


def test_plugin_runtime_builder_reports_failed_plugin_entity_import(tmp_path: Path) -> None:
    """校验运行时构建器会按插件返回实体导入失败结果。"""
    backend_root = tmp_path / 'backend'
    plugin_dir = backend_root / 'plugins' / 'broken_entity'
    write_manifest(
        plugin_dir,
        """
id: broken_entity
name: 异常插件
version: 1.0.0
backend:
  module: plugins.broken_entity
""",
    )
    entity_do_dir = plugin_dir / 'entity' / 'do'
    entity_do_dir.mkdir(parents=True)
    (entity_do_dir / 'broken_do.py').write_text("raise RuntimeError('broken entity')\n", encoding='utf-8')
    builder = PluginRuntimeBuilder(backend_root)
    registry = builder.build_registry(
        [
            PluginModel(
                pluginId='broken_entity',
                pluginName='异常插件',
                version='1.0.0',
                installedVersion='1.0.0',
                enabled='0',
                status='installed',
            )
        ]
    )

    import_result = builder.import_plugin_entities(registry)

    assert import_result.imported_count == 0
    assert len(import_result.failures) == 1
    assert import_result.failures[0].plugin_id == 'broken_entity'
    assert 'broken entity' in import_result.failures[0].error_message
