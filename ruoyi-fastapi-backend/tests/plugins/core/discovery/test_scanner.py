import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.discovery.scanner import PluginScanner, discover_plugins  # noqa: E402
from plugins.core.manifest.schema import PluginManifest, PluginManifestError  # noqa: E402

EXPECTED_CONFIG_ORDER = 10


def write_manifest(plugin_dir: Path, content: str) -> Path:
    """
    写入测试插件清单。

    :param plugin_dir: 插件目录
    :param content: 清单内容
    :return: 清单文件路径
    """
    plugin_dir.mkdir(parents=True)
    manifest_path = plugin_dir / 'plugin.yaml'
    manifest_path.write_text(content, encoding='utf-8')
    return manifest_path


def test_manifest_fills_frontend_defaults() -> None:
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
        }
    )

    assert manifest.frontend.plugin_id == 'demo'
    assert manifest.frontend.base_path == 'demo'
    assert manifest.frontend.views_path == 'views'
    assert manifest.backend.routers.auto_scan is True


def test_manifest_accepts_camel_case_fields() -> None:
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo', 'routers': {'autoScan': False}},
            'frontend': {
                'pluginId': 'demo',
                'basePath': 'demo',
                'viewsPath': 'custom_views',
                'apiPath': 'custom_api',
                'menus': [{'name': '演示', 'path': 'demo', 'component': 'plugin/demo/index'}],
            },
        }
    )

    assert manifest.backend.routers.auto_scan is False
    assert manifest.frontend.plugin_id == 'demo'
    assert manifest.frontend.views_path == 'custom_views'
    assert manifest.frontend.menus[0].order_num == 0


def test_manifest_normalizes_config_type_aliases() -> None:
    """
    校验插件配置类型别名会规范化为运行时支持的类型。

    :return: None
    """
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {'key': 'enabled_feature', 'type': 'switch', 'default': True},
                    {'key': 'title', 'type': 'text', 'default': 'demo'},
                ]
            },
        }
    )

    assert manifest.config.items[0].type == 'boolean'
    assert manifest.config.items[1].type == 'string'


def test_manifest_accepts_resource_declarations() -> None:
    """
    校验插件 manifest 支持声明资源清单。

    :return: None
    """
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'resources': {
                'static': ['assets/demo'],
                'uploads': ['uploads/demo'],
                'temp': ['tmp/demo-cache'],
            },
        }
    )

    assert manifest.resources.static == ['assets/demo']
    assert manifest.resources.uploads == ['uploads/demo']
    assert manifest.resources.temp == ['tmp/demo-cache']


def test_manifest_rejects_unsafe_resource_paths() -> None:
    """
    校验插件资源路径必须是安全相对路径。

    :return: None
    """
    with pytest.raises(ValueError, match='插件资源路径必须是安全相对路径'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'resources': {'uploads': ['../unsafe']},
            }
        )


def test_manifest_rejects_invalid_config_defaults() -> None:
    """
    校验插件配置默认值必须与配置类型匹配。

    :return: None
    """
    with pytest.raises(ValueError, match='default 必须是布尔值'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'config': {'items': [{'key': 'enabled_feature', 'type': 'boolean', 'default': 'yes'}]},
            }
        )


def test_manifest_rejects_invalid_select_config() -> None:
    """
    校验 select 配置必须声明选项且默认值必须位于选项中。

    :return: None
    """
    with pytest.raises(ValueError, match='必须声明 options'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'config': {'items': [{'key': 'provider', 'type': 'select', 'default': 'openai'}]},
            }
        )
    with pytest.raises(ValueError, match=r'default 必须位于 options\.value 中'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'config': {
                    'items': [
                        {
                            'key': 'provider',
                            'type': 'select',
                            'default': 'missing',
                            'options': [{'label': 'OpenAI', 'value': 'openai'}],
                        }
                    ]
                },
            }
        )


def test_manifest_accepts_config_enhanced_metadata() -> None:
    """
    校验配置项支持分组、排序、占位提示、范围和正则元数据。

    :return: None
    """
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': 'Demo',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'temperature',
                        'type': 'number',
                        'default': 0.5,
                        'group': 'model',
                        'order': 10,
                        'placeholder': '0.0 - 1.0',
                        'min': 0,
                        'max': 1,
                    },
                    {
                        'key': 'api_key',
                        'type': 'password',
                        'default': 'sk-demo',
                        'pattern': r'^sk-.+',
                    },
                ]
            },
        }
    )

    temperature = manifest.config.items[0]
    api_key = manifest.config.items[1]
    assert temperature.group == 'model'
    assert temperature.order == EXPECTED_CONFIG_ORDER
    assert temperature.placeholder == '0.0 - 1.0'
    assert temperature.min_value == 0
    assert temperature.max_value == 1
    assert api_key.pattern == r'^sk-.+'


def test_manifest_rejects_config_default_outside_enhanced_constraints() -> None:
    """
    校验配置项默认值必须满足范围和正则约束。

    :return: None
    """
    with pytest.raises(ValueError, match='default 不能大于 max'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': 'Demo',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'config': {'items': [{'key': 'temperature', 'type': 'number', 'default': 2, 'max': 1}]},
            }
        )

    with pytest.raises(ValueError, match='default 不匹配 pattern'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': 'Demo',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'config': {'items': [{'key': 'api_key', 'type': 'password', 'default': 'bad', 'pattern': r'^sk-.+'}]},
            }
        )


def test_manifest_rejects_invalid_permissions() -> None:
    """
    校验插件权限必须使用小写冒号分隔格式。

    :return: None
    """
    with pytest.raises(ValueError, match='插件权限格式无效'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'permissions': ['DemoList'],
            }
        )


def test_manifest_rejects_undeclared_menu_permission() -> None:
    """
    校验菜单权限必须在顶层 permissions 中声明。

    :return: None
    """
    with pytest.raises(ValueError, match='菜单权限必须在 permissions 中声明'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'frontend': {
                    'menus': [
                        {
                            'name': '演示',
                            'path': 'demo',
                            'component': 'plugin/demo/index',
                            'perms': 'demo:list',
                        }
                    ]
                },
                'permissions': ['demo:query'],
            }
        )


def test_manifest_rejects_backend_module_mismatch() -> None:
    """
    校验 backend.module 必须与插件 ID 对齐。

    :return: None
    """
    with pytest.raises(ValueError, match=r'backend\.module 必须为 plugins\.demo'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.other'},
            }
        )


def test_manifest_rejects_frontend_plugin_id_mismatch() -> None:
    """
    校验 frontend.pluginId 必须与插件 ID 对齐。

    :return: None
    """
    with pytest.raises(ValueError, match=r'frontend\.pluginId 必须与插件 id 一致'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'frontend': {'pluginId': 'other'},
            }
        )


def test_manifest_rejects_cross_plugin_component() -> None:
    """
    校验菜单组件不能引用其他插件的前端目录。

    :return: None
    """
    with pytest.raises(ValueError, match='插件组件路径必须引用当前插件目录'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'frontend': {
                    'menus': [
                        {
                            'name': '演示',
                            'path': 'demo',
                            'component': 'plugin/other/index',
                        }
                    ]
                },
            }
        )


def test_manifest_rejects_duplicate_menu_paths() -> None:
    """
    校验同一插件内菜单完整路径不能重复。

    :return: None
    """
    with pytest.raises(ValueError, match='菜单 path 不能重复'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'frontend': {
                    'menus': [
                        {'name': '演示一', 'path': 'demo', 'component': 'plugin/demo/one'},
                        {'name': '演示二', 'path': 'demo', 'component': 'plugin/demo/two'},
                    ]
                },
            }
        )


def test_manifest_rejects_invalid_menu_component() -> None:
    """
    校验菜单组件必须使用核心布局组件或插件视图路径。

    :return: None
    """
    with pytest.raises(ValueError, match='菜单 component 只允许核心布局组件或插件视图路径'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'frontend': {'menus': [{'name': '演示', 'path': 'demo', 'component': 'demo/index'}]},
            }
        )


@pytest.mark.parametrize('plugin_id', ['Demo', '1demo', 'a', 'system', 'demo plugin'])
def test_manifest_rejects_invalid_plugin_id(plugin_id: str) -> None:
    with pytest.raises(ValueError):
        PluginManifest.model_validate(
            {
                'id': plugin_id,
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
            }
        )


def test_discover_plugins_loads_valid_manifests(tmp_path: Path) -> None:
    write_manifest(
        tmp_path / 'demo',
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
permissions:
  - demo:list
""",
    )

    plugins = discover_plugins(tmp_path)

    assert len(plugins) == 1
    assert plugins[0].manifest.id == 'demo'
    assert plugins[0].manifest.enabled is True
    assert plugins[0].backend_path == tmp_path / 'demo'


def test_discover_plugins_returns_empty_for_missing_root(tmp_path: Path) -> None:
    assert discover_plugins(tmp_path / 'missing') == []


def test_discover_plugins_rejects_plugin_yml_manifest_name(tmp_path: Path) -> None:
    """
    校验插件清单必须使用 plugin.yaml 文件名，避免 plugin.yml 被静默漏扫。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    plugin_dir = tmp_path / 'demo'
    plugin_dir.mkdir()
    (plugin_dir / 'plugin.yml').write_text(
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
        encoding='utf-8',
    )

    with pytest.raises(PluginManifestError, match=r'插件清单文件名必须为 plugin\.yaml'):
        discover_plugins(tmp_path)


def test_discover_plugins_rejects_directory_name_mismatch(tmp_path: Path) -> None:
    manifest_path = write_manifest(
        tmp_path / 'demo_dir',
        """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
""",
    )

    with pytest.raises(PluginManifestError, match='插件目录名必须与插件 id 一致'):
        PluginScanner(tmp_path).load_manifest(manifest_path)


def test_discover_plugins_rejects_invalid_yaml_shape(tmp_path: Path) -> None:
    write_manifest(
        tmp_path / 'demo',
        """
- id
- demo
""",
    )

    with pytest.raises(PluginManifestError, match='插件清单必须是 YAML 对象'):
        discover_plugins(tmp_path)


def test_discover_plugins_rejects_invalid_manifest(tmp_path: Path) -> None:
    write_manifest(
        tmp_path / 'demo',
        """
id: demo
name: 演示插件
""",
    )

    with pytest.raises(PluginManifestError, match='插件清单校验失败'):
        discover_plugins(tmp_path)
