from pathlib import Path
from types import SimpleNamespace

import pytest

import plugins.core.validation.manifest as manifest_module
from plugins.core.manifest.schema import FrontendManifest, PluginDependencyManifest, PluginManifest
from plugins.core.validation.manifest import PluginManifestChecker


def write_project_versions(backend_root: Path, frontend_root: Path) -> None:
    """写入测试项目版本文件。"""
    backend_root.mkdir(parents=True)
    frontend_root.mkdir(parents=True)
    (backend_root / 'pyproject.toml').write_text('[project]\nversion = "1.10.0"\n', encoding='utf-8')
    (frontend_root / 'package.json').write_text('{"version": "1.10.0"}\n', encoding='utf-8')


def test_manifest_rejects_hyphenated_plugin_ids() -> None:
    """校验插件 manifest 短期全局拒绝带短横线的插件 ID。"""
    with pytest.raises(ValueError, match='只能包含小写字母、数字和下划线'):
        PluginManifest.model_validate(
            {
                'id': 'demo-plugin',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo-plugin'},
            }
        )
    with pytest.raises(ValueError, match='只能包含小写字母、数字和下划线'):
        FrontendManifest.model_validate({'pluginId': 'demo-plugin'})
    with pytest.raises(ValueError, match='只能包含小写字母、数字和下划线'):
        PluginDependencyManifest.model_validate({'id': 'base-plugin'})


def test_manifest_checker_warns_secret_config_default() -> None:
    """校验敏感配置非空默认值会产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'api_key',
                        'type': 'password',
                        'default': 'sk-test',
                        'secret': True,
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].level == 'warning'
    assert result.warning_issues[0].kind == 'secret_config_default'


def test_manifest_checker_accepts_empty_secret_config_default() -> None:
    """校验敏感配置空默认值不会产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'api_key',
                        'type': 'password',
                        'default': '',
                        'secret': True,
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_rejects_boolean_default_for_number_config() -> None:
    """校验 number 类型配置不会把 bool 默认值当作数字。"""
    with pytest.raises(ValueError, match='必须是数字'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'config': {'items': [{'key': 'enabled_ratio', 'type': 'number', 'default': True}]},
            }
        )


def test_manifest_checker_warns_password_config_without_secret_flag() -> None:
    """校验 password 类型配置缺少 secret 标记时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'api_key',
                        'type': 'password',
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'password_config_without_secret'
    assert result.warning_issues[0].path == 'config.items.api_key.secret'


def test_manifest_checker_warns_secret_config_with_non_password_type() -> None:
    """校验 secret 配置使用非 password 类型时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'api_key',
                        'type': 'string',
                        'secret': True,
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'secret_config_non_password_type'
    assert result.warning_issues[0].path == 'config.items.api_key.type'


def test_manifest_checker_accepts_secret_password_config() -> None:
    """校验 password 类型配置声明 secret 标记时不产生类型一致性 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'api_key',
                        'type': 'password',
                        'secret': True,
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_accepts_satisfied_compatibility(tmp_path: Path) -> None:
    """校验兼容性声明满足当前版本时不产生问题。"""
    backend_root = tmp_path / 'backend'
    frontend_root = tmp_path / 'frontend'
    write_project_versions(backend_root, frontend_root)
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'compatibility': {
                'backendVersion': '>=1.0.0',
                'frontendVersion': '>=1.0.0',
                'pythonVersion': '>=3.10',
                'nodeVersion': '>=18.0.0',
            },
        }
    )

    result = PluginManifestChecker(
        backend_root=backend_root,
        frontend_root=frontend_root,
        python_version='3.10.19',
        node_version='20.0.0',
    ).check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_accepts_supported_database(monkeypatch: object) -> None:
    """校验当前数据库在插件支持列表内时不产生问题。"""
    monkeypatch.setattr(manifest_module.DataBaseConfig.default_source, 'db_type', 'postgresql')
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'compatibility': {'databases': ['mysql', 'postgresql']},
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_caches_resolved_node_version(tmp_path: Path, monkeypatch: object) -> None:
    """校验 Node.js 版本解析会缓存 subprocess 结果。"""
    backend_root = tmp_path / 'backend'
    frontend_root = tmp_path / 'frontend'
    write_project_versions(backend_root, frontend_root)
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'compatibility': {
                'nodeVersion': '>=18.0.0',
            },
        }
    )
    calls = []

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        """记录 node 版本命令调用。"""
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='v20.0.0\n')

    monkeypatch.setattr(manifest_module.subprocess, 'run', fake_run)
    monkeypatch.setattr(
        PluginManifestChecker,
        '_node_version_cache',
        manifest_module.UNRESOLVED_NODE_VERSION,
    )

    first_result = PluginManifestChecker(backend_root=backend_root, frontend_root=frontend_root).check(manifest)
    second_result = PluginManifestChecker(backend_root=backend_root, frontend_root=frontend_root).check(manifest)

    assert first_result.ok is True
    assert second_result.ok is True
    assert len(calls) == 1


def test_manifest_checker_reports_unsatisfied_compatibility(tmp_path: Path) -> None:
    """校验兼容性声明不满足当前版本时产生 error。"""
    backend_root = tmp_path / 'backend'
    frontend_root = tmp_path / 'frontend'
    write_project_versions(backend_root, frontend_root)
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'compatibility': {'pythonVersion': '>=99.0.0'},
        }
    )

    result = PluginManifestChecker(
        backend_root=backend_root,
        frontend_root=frontend_root,
        python_version='3.10.19',
        node_version='20.0.0',
    ).check(manifest)

    assert result.ok is False
    assert len(result.error_issues) == 1
    assert result.error_issues[0].kind == 'compatibility_unsatisfied'
    assert result.error_issues[0].path == 'compatibility.pythonVersion'


def test_manifest_checker_reports_unsupported_database(monkeypatch: object) -> None:
    """校验当前数据库不在插件支持列表内时产生 error。"""
    monkeypatch.setattr(manifest_module.DataBaseConfig.default_source, 'db_type', 'postgresql')
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'compatibility': {'databases': ['mysql']},
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is False
    assert len(result.error_issues) == 1
    assert result.error_issues[0].kind == 'compatibility_unsatisfied'
    assert result.error_issues[0].path == 'compatibility.databases'


def test_manifest_checker_warns_unknown_compatibility_version(tmp_path: Path) -> None:
    """校验无法读取平台版本时产生 warning 且不阻断。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'compatibility': {'backendVersion': '>=1.0.0'},
        }
    )

    result = PluginManifestChecker(
        backend_root=tmp_path / 'missing-backend',
        frontend_root=tmp_path / 'missing-frontend',
        python_version='3.10.19',
        node_version='20.0.0',
    ).check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'compatibility_unknown'
    assert result.warning_issues[0].path == 'compatibility.backendVersion'


def test_manifest_checker_warns_unpinned_dependencies() -> None:
    """校验未声明版本约束的依赖会产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'dependencies': {
                'python': ['openai'],
                'npm': ['axios'],
                'npmDev': ['vite'],
                'plugins': ['base'],
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert [issue.kind for issue in result.warning_issues] == [
        'dependency_unpinned',
        'dependency_unpinned',
        'dependency_unpinned',
        'plugin_dependency_unpinned',
    ]
    assert result.warning_issues[0].path == 'dependencies.python.0'
    assert result.warning_issues[1].path == 'dependencies.npm.0'
    assert result.warning_issues[2].path == 'dependencies.npmDev.0'
    assert result.warning_issues[3].path == 'dependencies.plugins.base.version'


def test_manifest_checker_accepts_pinned_dependencies() -> None:
    """校验声明版本约束的依赖不会产生未锁定 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'dependencies': {
                'python': ['openai>=2.0.0'],
                'npm': ['axios^1.0.0'],
                'plugins': ['base>=1.0.0'],
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_resources_without_purge_hook() -> None:
    """校验声明资源清单但未声明 onPurge 时会产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'resources': {'uploads': ['uploads/demo']},
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'resources_without_purge_hook'
    assert result.warning_issues[0].path == 'resources'


def test_manifest_checker_accepts_resources_with_purge_hook() -> None:
    """校验资源清单声明了 onPurge 时不会产生资源清理 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'hooks': {'onPurge': 'hooks:on_purge'},
            },
            'resources': {'uploads': ['uploads/demo']},
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_required_config_without_default() -> None:
    """校验必填配置缺少默认值时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'endpoint',
                        'type': 'string',
                        'required': True,
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'required_config_without_default'
    assert result.warning_issues[0].path == 'config.items.endpoint.default'


def test_manifest_checker_accepts_required_config_with_default() -> None:
    """校验必填配置声明默认值时不产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'endpoint',
                        'type': 'string',
                        'required': True,
                        'default': 'http://127.0.0.1',
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_ineffective_config_constraints() -> None:
    """校验配置项声明不会生效的增强约束时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'title',
                        'type': 'string',
                        'min': 1,
                        'max': 10,
                    },
                    {
                        'key': 'enabled',
                        'type': 'boolean',
                        'pattern': '^true$',
                    },
                    {
                        'key': 'mode',
                        'type': 'string',
                        'options': [{'label': 'A', 'value': 'a'}],
                    },
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert [issue.kind for issue in result.warning_issues] == [
        'ineffective_config_constraint',
        'ineffective_config_constraint',
        'ineffective_config_constraint',
    ]
    assert [issue.path for issue in result.warning_issues] == [
        'config.items.title.min/max',
        'config.items.enabled.pattern',
        'config.items.mode.options',
    ]


def test_manifest_checker_accepts_effective_config_constraints() -> None:
    """校验配置项增强约束用于正确类型时不产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'temperature',
                        'type': 'number',
                        'min': 0,
                        'max': 2,
                    },
                    {
                        'key': 'endpoint',
                        'type': 'string',
                        'pattern': '^https?://.+$',
                    },
                    {
                        'key': 'mode',
                        'type': 'select',
                        'options': [{'label': 'A', 'value': 'a'}],
                    },
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_rejects_permission_without_plugin_prefix() -> None:
    """校验权限标识未使用插件 ID 前缀时阻断 manifest 加载。"""
    with pytest.raises(ValueError, match='插件权限必须使用 demo: 前缀'):
        PluginManifest.model_validate(
            {
                'id': 'demo',
                'name': '演示插件',
                'version': '1.0.0',
                'backend': {'module': 'plugins.demo'},
                'permissions': ['demo:list', 'system:user:list'],
                'frontend': {
                    'menus': [
                        {
                            'name': '用户',
                            'path': 'user',
                            'component': 'plugin/demo/user/index',
                            'perms': 'system:user:list',
                        }
                    ]
                },
            }
        )


def test_manifest_checker_accepts_permissions_with_plugin_prefix() -> None:
    """校验权限标识使用插件 ID 前缀时不产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'permissions': ['demo:user:list'],
            'frontend': {
                'menus': [
                    {
                        'name': '用户',
                        'path': 'user',
                        'component': 'plugin/demo/user/index',
                        'perms': 'demo:user:list',
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_frontend_menus_without_permissions() -> None:
    """校验声明前端菜单但完全缺少权限标识时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'frontend': {
                'menus': [
                    {
                        'name': '用户',
                        'path': 'user',
                        'component': 'plugin/demo/user/index',
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'frontend_menus_without_permissions'
    assert result.warning_issues[0].path == 'frontend.menus'


def test_manifest_checker_accepts_frontend_menus_with_child_permissions() -> None:
    """校验子菜单存在权限标识时不产生前端菜单无权限 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'permissions': ['demo:user:list'],
            'frontend': {
                'menus': [
                    {
                        'name': '演示',
                        'path': 'demo',
                        'component': 'Layout',
                        'type': 'M',
                        'children': [
                            {
                                'name': '用户',
                                'path': 'user',
                                'component': 'plugin/demo/user/index',
                                'perms': 'demo:user:list',
                            }
                        ],
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_button_menu_without_permission() -> None:
    """校验按钮菜单缺少权限标识时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'frontend': {
                'menus': [
                    {
                        'name': '删除',
                        'path': 'remove',
                        'component': '',
                        'type': 'F',
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'button_menu_without_permission'
    assert result.warning_issues[0].path == 'frontend.menus.remove.perms'


def test_manifest_checker_accepts_button_menu_with_permission() -> None:
    """校验按钮菜单声明权限标识时不产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'permissions': ['demo:remove'],
            'frontend': {
                'menus': [
                    {
                        'name': '删除',
                        'path': 'remove',
                        'component': '',
                        'type': 'F',
                        'perms': 'demo:remove',
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_button_menu_with_component_and_children() -> None:
    """校验按钮菜单混入路由组件或子菜单时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'permissions': ['demo:remove', 'demo:remove:child'],
            'frontend': {
                'menus': [
                    {
                        'name': '删除',
                        'path': 'remove',
                        'component': 'plugin/demo/remove/index',
                        'type': 'F',
                        'perms': 'demo:remove',
                        'children': [
                            {
                                'name': '二级删除',
                                'path': 'child',
                                'component': '',
                                'type': 'F',
                                'perms': 'demo:remove:child',
                            }
                        ],
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert [issue.kind for issue in result.warning_issues] == [
        'button_menu_with_component',
        'button_menu_with_children',
    ]
    assert [issue.path for issue in result.warning_issues] == [
        'frontend.menus.remove.component',
        'frontend.menus.remove.children',
    ]


def test_manifest_checker_warns_permission_without_menu_parent() -> None:
    """校验顶层权限缺少可挂载按钮的父级菜单时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'permissions': ['demo:user:add'],
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'permission_without_menu_parent'
    assert result.warning_issues[0].path == 'permissions.demo:user:add'


def test_manifest_checker_accepts_auto_permission_buttons_with_parent_menu() -> None:
    """校验顶层权限存在页面父级菜单时不产生自动按钮挂载 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'permissions': ['demo:user:list', 'demo:user:add'],
            'frontend': {
                'menus': [
                    {
                        'name': '用户',
                        'path': 'user',
                        'component': 'plugin/demo/user/index',
                        'perms': 'demo:user:list',
                    }
                ]
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_unsorted_lifecycle_scripts() -> None:
    """校验 migration 和 seed 未按文件名顺序声明时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'migrations': ['migrations/002_add.sql', 'migrations/001_init.sql'],
                'seeds': ['seeds/002_extra.sql', 'seeds/001_init.sql'],
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert [issue.kind for issue in result.warning_issues] == ['script_order_unsorted', 'script_order_unsorted']
    assert [issue.path for issue in result.warning_issues] == ['backend.migrations', 'backend.seeds']


def test_manifest_checker_accepts_sorted_lifecycle_scripts() -> None:
    """校验 migration 和 seed 按文件名顺序声明时不产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'migrations': ['migrations/001_init.sql', 'migrations/002_add.sql'],
                'seeds': ['seeds/001_init.sql', 'seeds/002_extra.sql'],
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_enabled_jobs_without_health_checker() -> None:
    """校验默认启用任务缺少健康检查时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'jobs': [
                    {
                        'id': 'sync',
                        'callable': 'plugins.demo.jobs.sync',
                        'cronExpression': '0 0/5 * * * ?',
                        'enabled': True,
                    }
                ],
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'enabled_jobs_without_health_checker'
    assert result.warning_issues[0].path == 'backend.health.checker'


def test_manifest_checker_accepts_enabled_jobs_with_health_checker() -> None:
    """校验默认启用任务声明健康检查时不产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'health': {'checker': 'health:check'},
                'jobs': [
                    {
                        'id': 'sync',
                        'callable': 'plugins.demo.jobs.sync',
                        'cronExpression': '0 0/5 * * * ?',
                        'enabled': True,
                    }
                ],
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_warns_unpaired_runtime_hook() -> None:
    """校验启动和关闭钩子未成对声明时产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'hooks': {'onStartup': 'hooks:on_startup'},
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert len(result.warning_issues) == 1
    assert result.warning_issues[0].kind == 'unpaired_runtime_hook'
    assert result.warning_issues[0].path == 'backend.hooks.onShutdown'


def test_manifest_checker_accepts_paired_runtime_hooks() -> None:
    """校验启动和关闭钩子成对声明时不产生 warning。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'hooks': {
                    'onStartup': 'hooks:on_startup',
                    'onShutdown': 'hooks:on_shutdown',
                },
            },
        }
    )

    result = PluginManifestChecker().check(manifest)

    assert result.ok is True
    assert result.issues == []


def test_manifest_checker_does_not_warn_pep508_comma_range_as_unpinned() -> None:
    """校验清单检查器不会将 PEP 508 逗号范围误判为未锁定。"""
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': 'Demo',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'dependencies': {'python': ['openai>=2,<3', 'requests']},
        }
    )

    result = PluginManifestChecker().check(manifest)
    unpinned = [i for i in result.issues if i.kind == 'dependency_unpinned']

    assert len(unpinned) == 1
    assert 'openai' not in unpinned[0].message
    assert 'requests' in unpinned[0].message
