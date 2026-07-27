from pathlib import Path

import pytest

from plugins.core.discovery.scanner import PluginScanner, discover_plugins
from plugins.core.manifest.schema import PluginManifest, PluginManifestError

EXPECTED_CONFIG_ORDER = 10


def write_manifest(plugin_dir: Path, content: str) -> Path:
    """写入测试插件清单。"""
    plugin_dir.mkdir(parents=True)
    manifest_path = plugin_dir / 'plugin.yaml'
    manifest_path.write_text(content, encoding='utf-8')
    return manifest_path


def test_manifest_fills_frontend_defaults() -> None:
    """校验插件清单会补齐前端配置默认值。"""
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


def test_manifest_accepts_version_metadata_databases_and_menu_system_fields() -> None:
    """校验插件清单支持版本、展示元数据、数据库兼容性和系统菜单字段。"""
    manifest = PluginManifest.model_validate(
        {
            'manifestVersion': 1,
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'description': 'demo plugin',
            'metadata': {
                'category': 'demo',
                'tags': ['demo', 'sample'],
                'author': 'RuoYi',
                'license': 'MIT',
                'homepage': 'https://example.com',
                'repository': 'https://example.com/repo',
                'documentation': 'https://example.com/docs',
            },
            'backend': {'module': 'plugins.demo'},
            'frontend': {
                'menus': [
                    {
                        'name': '演示',
                        'path': 'demo',
                        'component': 'plugin/demo/index',
                        'routeName': 'DemoIndex',
                        'query': '{"tab":"basic"}',
                        'isFrame': 1,
                        'isCache': 1,
                    }
                ]
            },
            'compatibility': {'databases': ['mysql', 'postgresql']},
        }
    )

    assert manifest.manifest_version == 1
    assert manifest.metadata.category == 'demo'
    assert manifest.metadata.tags == ['demo', 'sample']
    assert manifest.compatibility.databases == ['mysql', 'postgresql']
    assert manifest.frontend.menus[0].route_name == 'DemoIndex'
    assert manifest.frontend.menus[0].query == '{"tab":"basic"}'
    assert manifest.frontend.menus[0].is_frame == 1
    assert manifest.frontend.menus[0].is_cache == 1


def test_manifest_accepts_camel_case_fields() -> None:
    """校验插件清单接受约定的驼峰字段。"""
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


def test_manifest_rejects_unsupported_manifest_version() -> None:
    """校验插件清单版本只接受当前支持版本。"""
    with pytest.raises(ValueError):
        PluginManifest.model_validate(
            {
                'manifestVersion': 2,
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
            }
        )


def test_manifest_rejects_duplicate_metadata_tags_and_databases() -> None:
    """校验插件展示标签和数据库兼容性声明不能重复。"""
    with pytest.raises(ValueError, match=r'metadata\.tags 不能重复'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'metadata': {'tags': ['demo', 'demo']},
                'backend': {'module': 'plugins.demo'},
            }
        )
    with pytest.raises(ValueError, match=r'compatibility\.databases 不能重复'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'compatibility': {'databases': ['mysql', 'mysql']},
            }
        )


def test_manifest_rejects_invalid_metadata_url() -> None:
    """校验插件展示元数据地址必须是 http/https 地址。"""
    with pytest.raises(ValueError, match=r'metadata\.homepage 必须是 http/https 地址'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'metadata': {'homepage': 'example.com'},
                'backend': {'module': 'plugins.demo'},
            }
        )


def test_manifest_rejects_invalid_python_requirement() -> None:
    """校验插件清单拒绝无效的 Python 依赖声明。"""
    with pytest.raises(ValueError, match='Python 依赖声明无效'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'dependencies': {'python': ['openai=>999']},
            }
        )


def test_manifest_accepts_external_frame_menu() -> None:
    """校验外链菜单允许 http/https 路由地址。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'frontend': {
                'menus': [
                    {
                        'name': '外链',
                        'path': 'https://example.com/docs',
                        'component': 'InnerLink',
                        'isFrame': 0,
                    }
                ]
            },
        }
    )

    assert manifest.frontend.menus[0].path == 'https://example.com/docs'
    assert manifest.frontend.menus[0].is_frame == 0


def test_manifest_rejects_mismatched_frame_menu_path() -> None:
    """校验外链标记和菜单路径类型必须匹配。"""
    with pytest.raises(ValueError, match='外链菜单 path 必须是 http/https 地址'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'frontend': {'menus': [{'name': '外链', 'path': 'demo', 'component': 'InnerLink', 'isFrame': 0}]},
            }
        )
    with pytest.raises(ValueError, match='非外链菜单 path 不能是 http/https 地址'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'frontend': {
                    'menus': [
                        {'name': '页面', 'path': 'https://example.com/docs', 'component': 'InnerLink', 'isFrame': 1}
                    ]
                },
            }
        )


def test_manifest_normalizes_config_type_aliases() -> None:
    """校验插件配置类型别名会规范化为运行时支持的类型。"""
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
    """校验插件 manifest 支持声明资源清单。"""
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
    """校验插件资源路径必须是安全相对路径。"""
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
    """校验插件配置默认值必须与配置类型匹配。"""
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
    """校验 select 配置必须声明选项且默认值必须位于选项中。"""
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
    """校验配置项支持分组、排序、占位提示、范围和正则元数据。"""
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
    """校验配置项默认值必须满足范围和正则约束。"""
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
    """校验插件权限必须使用小写冒号分隔格式。"""
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


def test_manifest_accepts_permission_objects_and_aliases() -> None:
    """校验插件权限支持对象写法、展示名和兼容字段名。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'permissions': [
                {'code': 'demo:list', 'name': '演示列表', 'description': '查看演示页面'},
                {'perms': 'demo:add', 'name': '新增演示'},
                {'permission': 'demo:edit'},
                'demo:remove',
            ],
        }
    )

    assert manifest.permission_codes == ['demo:list', 'demo:add', 'demo:edit', 'demo:remove']
    assert manifest.permission_name_map == {'demo:list': '演示列表', 'demo:add': '新增演示'}
    assert manifest.permissions[0].description == '查看演示页面'


def test_manifest_rejects_duplicate_permission_objects() -> None:
    """校验对象权限按权限标识去重。"""
    with pytest.raises(ValueError, match='插件权限不能重复'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'permissions': [{'code': 'demo:list', 'name': '演示列表'}, {'perms': 'demo:list'}],
            }
        )


def test_manifest_rejects_undeclared_menu_permission() -> None:
    """校验菜单权限必须在顶层 permissions 中声明。"""
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
    """校验 backend.module 必须与插件 ID 对齐。"""
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
    """校验 frontend.pluginId 必须与插件 ID 对齐。"""
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
    """校验菜单组件不能引用其他插件的前端目录。"""
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
    """校验同一插件内菜单完整路径不能重复。"""
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
    """校验菜单组件必须使用核心布局组件或插件视图路径。"""
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
    """校验插件清单拒绝不符合规范的插件 ID。"""
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
    """校验插件发现流程可以加载有效清单。"""
    write_manifest(
        tmp_path / 'demo',
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
permissions:
  - demo:list
""",
    )

    plugins = discover_plugins(tmp_path)

    assert len(plugins) == 1
    assert plugins[0].manifest.id == 'demo'
    assert not hasattr(plugins[0].manifest, 'enabled')
    assert plugins[0].backend_path == tmp_path / 'demo'


def test_discover_with_errors_isolates_broken_plugin(tmp_path: Path) -> None:
    """校验插件发现流程会隔离单个损坏插件。"""
    write_manifest(
        tmp_path / 'good',
        """
id: good
name: 正常插件
version: 1.0.0
backend:
  module: plugins.good
""",
    )
    write_manifest(
        tmp_path / 'bad',
        """
id: bad
name: 损坏插件
""",
    )

    result = PluginScanner(tmp_path).discover_with_errors()

    assert len(result.plugins) == 1
    assert result.plugins[0].manifest.id == 'good'
    assert result.has_errors
    assert len(result.errors) == 1
    assert result.errors[0].plugin_dir == tmp_path / 'bad'
    assert '插件清单校验失败' in result.errors[0].error_message


def test_discover_plugins_returns_empty_for_missing_root(tmp_path: Path) -> None:
    """校验插件根目录不存在时返回空结果。"""
    assert discover_plugins(tmp_path / 'missing') == []


def test_discover_plugins_rejects_plugin_yml_manifest_name(tmp_path: Path) -> None:
    """校验插件清单必须使用 plugin.yaml 文件名，避免 plugin.yml 被静默漏扫。"""
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


def test_discover_with_errors_isolates_plugin_yml_filename(tmp_path: Path) -> None:
    """校验发现流程会隔离使用错误清单文件名的插件。"""
    write_manifest(
        tmp_path / 'good',
        """
id: good
name: 正常插件
version: 1.0.0
backend:
  module: plugins.good
""",
    )
    bad_dir = tmp_path / 'bad'
    bad_dir.mkdir()
    (bad_dir / 'plugin.yml').write_text(
        """
id: bad
name: 损坏插件
version: 1.0.0
backend:
  module: plugins.bad
""",
        encoding='utf-8',
    )

    result = PluginScanner(tmp_path).discover_with_errors()

    assert len(result.plugins) == 1
    assert result.plugins[0].manifest.id == 'good'
    assert result.has_errors
    assert len(result.errors) == 1
    assert result.errors[0].plugin_dir == bad_dir
    assert '插件清单文件名必须为 plugin.yaml' in result.errors[0].error_message


def test_discover_with_errors_isolates_directory_with_both_manifest_names(tmp_path: Path) -> None:
    """校验发现流程会隔离同时包含两种清单文件名的目录。"""
    plugin_dir = tmp_path / 'demo'
    manifest_content = """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
"""
    write_manifest(plugin_dir, manifest_content)
    (plugin_dir / 'plugin.yml').write_text(manifest_content, encoding='utf-8')

    result = PluginScanner(tmp_path).discover_with_errors()

    assert result.plugins == []
    assert len(result.errors) == 1
    assert result.errors[0].plugin_dir == plugin_dir


def test_discover_plugins_rejects_directory_name_mismatch(tmp_path: Path) -> None:
    """校验插件目录名必须与清单中的插件 ID 一致。"""
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
    """校验插件发现流程拒绝非法 YAML 数据结构。"""
    write_manifest(
        tmp_path / 'demo',
        """
- id
- demo
""",
    )

    result = PluginScanner(tmp_path).discover_with_errors()

    assert result.plugins == []
    assert result.has_errors
    assert '插件清单必须是 YAML 对象' in result.errors[0].error_message


def test_discover_plugins_rejects_invalid_manifest(tmp_path: Path) -> None:
    """校验插件发现流程拒绝未通过模型校验的清单。"""
    write_manifest(
        tmp_path / 'demo',
        """
id: demo
name: 演示插件
""",
    )

    result = PluginScanner(tmp_path).discover_with_errors()

    assert result.plugins == []
    assert result.has_errors
    assert '插件清单校验失败' in result.errors[0].error_message


def test_scanner_includes_pydantic_error_detail(tmp_path: Path) -> None:
    """校验扫描器抛出的清单校验异常包含字段级错误摘要。"""
    manifest_path = write_manifest(
        tmp_path / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.other
""",
    )

    with pytest.raises(PluginManifestError, match=r'backend\.module'):
        PluginScanner(tmp_path).load_manifest(manifest_path)
