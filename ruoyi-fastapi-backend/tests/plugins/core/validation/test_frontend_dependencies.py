import json
from pathlib import Path

import pytest

from cli.runtime.plugin.support import PluginDependencyLockfileTemplateBuilder
from plugins.core.capability import PluginRuntimeCapabilityResolver
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.frontend import PluginFrontendFrameworkResolver
from plugins.core.management.service.service import PluginService
from plugins.core.manifest.schema import PluginManifest, PluginManifestFactory
from plugins.core.runtime.support.payload.documentation import PluginDocumentationBuilder
from plugins.core.validation.dependencies import (
    NpmDependencyInspector,
    PluginDependencyChecker,
    PluginDependencyInstallPlanner,
    PythonDependencyInspector,
)
from plugins.core.validation.dependency_policy import (
    DependencyInstallPolicyConfig,
    DependencyInstallPolicyEvaluator,
    DependencyLockfile,
)
from plugins.core.validation.manifest import PluginManifestChecker


def build_manifest() -> PluginManifest:
    """
    构建包含 Vue 2、Vue 3 和虚构 React 宿主依赖分类的测试清单。

    :return: 测试插件清单
    """
    return PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': 'Demo',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'dependencies': {
                'frontend': {
                    'vue2': {
                        'npm': ['shared==1.0.0', 'renderer==2.0.0', 'vue2-only==1.0.0'],
                        'npmDev': ['shared-build==1.0.0'],
                    },
                    'vue3': {
                        'npm': ['shared==1.0.0', 'renderer==3.0.0'],
                        'npmDev': ['shared-build==1.0.0', 'vite-extra==1.0.0'],
                    },
                    'react': {
                        'npm': ['shared==1.0.0', 'react-renderer==1.0.0'],
                        'npmDev': ['react-build==1.0.0'],
                    },
                },
            },
        }
    )


def write_frontend(tmp_path: Path, framework: str) -> Path:
    """
    创建指定前端框架的临时测试工程并写入 package.json。

    :param tmp_path: 临时工程根目录
    :param framework: 前端框架标识
    :return: 前端 Web 工程目录
    """
    root = tmp_path / 'ruoyi-fastapi-frontend' / framework / 'web'
    root.mkdir(parents=True)
    dependencies = {'react': '^19.0.0'} if framework == 'react' else {'vue': f'^{framework[-1]}.0.0'}
    (root / 'package.json').write_text(json.dumps({'dependencies': dependencies}), encoding='utf-8')
    return root


@pytest.mark.parametrize('framework', ['vue2', 'vue3', 'react'])
def test_profiles_select_dependencies_and_install_only_in_target(tmp_path: Path, framework: str) -> None:
    """校验依赖检查和安装计划仅使用目标框架分类及工程目录。"""
    root = write_frontend(tmp_path, framework)
    manifest = build_manifest()
    result = PluginDependencyChecker(
        python_inspector=PythonDependencyInspector(installed_packages={}),
        npm_inspector=NpmDependencyInspector(frontend_root=root),
    ).check_manifest(manifest)
    requirements = {item.requirement for item in result.items}
    assert 'shared==1.0.0' in requirements
    assert ('renderer==2.0.0' in requirements) == (framework == 'vue2')
    assert ('renderer==3.0.0' in requirements) == (framework == 'vue3')
    assert ('react-renderer==1.0.0' in requirements) == (framework == 'react')
    assert ('vue2-only==1.0.0' in requirements) == (framework == 'vue2')
    assert ('vite-extra==1.0.0' in requirements) == (framework == 'vue3')
    assert ('react-build==1.0.0' in requirements) == (framework == 'react')
    plan = PluginDependencyInstallPlanner(frontend_root=root).build_plan(result)
    assert {item.workdir for item in plan.items} == {str(root)}
    assert {item.requirement for item in plan.items} == requirements
    assert set(manifest.dependencies.model_dump(by_alias=True)) == {'python', 'frontend', 'plugins'}


def test_backend_only_dependencies_do_not_require_frontend_framework(tmp_path: Path) -> None:
    """校验未声明前端依赖时无需识别宿主前端框架。"""
    (tmp_path / 'package.json').write_text('{"dependencies": {}}', encoding='utf-8')
    manifest = build_manifest()
    manifest.dependencies.frontend = {}
    result = PluginDependencyChecker(npm_inspector=NpmDependencyInspector(frontend_root=tmp_path)).check_manifest(
        manifest
    )
    assert result.items == []


def test_missing_profile_returns_empty_dependencies() -> None:
    """校验未声明目标框架分类时返回空的前端依赖列表。"""
    manifest = build_manifest()
    del manifest.dependencies.frontend['vue2']
    assert manifest.dependencies.resolve_frontend('vue2').model_dump(by_alias=True) == {'npm': [], 'npmDev': []}


def test_selected_profile_is_an_independent_copy() -> None:
    """校验返回的依赖分类是独立副本，不会修改原始清单。"""
    manifest = build_manifest()
    profile = manifest.dependencies.resolve_frontend('vue2')
    profile.npm.append('mutation==1.0.0')
    profile.npm_dev.clear()
    assert 'mutation==1.0.0' not in manifest.dependencies.frontend['vue2'].npm
    assert manifest.dependencies.frontend['vue2'].npm_dev == ['shared-build==1.0.0']


@pytest.mark.parametrize('legacy_key', ['npm', 'npmDev', 'npm_dev'])
@pytest.mark.parametrize('manifest_version', [1, 2])
def test_legacy_top_level_frontend_dependencies_are_rejected(legacy_key: str, manifest_version: int) -> None:
    """校验两个清单版本都拒绝旧顶层前端依赖字段。"""
    payload = build_manifest().model_dump(by_alias=True)
    payload['manifestVersion'] = manifest_version
    if manifest_version != 1:
        payload['backend'].update(entrypoint='plugins.demo.entry:create_plugin', routers={'autoScan': False})
    payload['dependencies'][legacy_key] = ['legacy-package==1.0.0']
    with pytest.raises(ValueError, match='Extra inputs are not permitted'):
        PluginManifestFactory.create(payload)


def test_documentation_lists_dependencies_by_frontend_profile(tmp_path: Path) -> None:
    """校验生成的插件文档按框架分类展示完整前端依赖。"""
    plugin = DiscoveredPlugin(manifest=build_manifest(), backend_path=tmp_path, manifest_path=tmp_path / 'plugin.yaml')
    markdown = '\n'.join(PluginDocumentationBuilder._build_dependency_section(plugin))
    assert '### vue2 宿主依赖' in markdown
    assert '### vue3 宿主依赖' in markdown
    assert '### react 宿主依赖' in markdown
    assert 'renderer==2.0.0' in markdown
    assert 'renderer==3.0.0' in markdown
    assert '公共' not in markdown


@pytest.mark.parametrize('framework', ['vue2', 'vue3', 'react'])
def test_built_host_without_source_preserves_workspace_profile(tmp_path: Path, framework: str) -> None:
    """校验无前端源码的构建模式仍按工程路径识别并跳过对应分类依赖。"""
    root = tmp_path / 'ruoyi-fastapi-frontend' / framework / 'web'
    checker = PluginDependencyChecker(npm_inspector=NpmDependencyInspector(frontend_root=root), frontend_mode='built')
    result = checker.check_manifest(build_manifest())
    assert all(item.status == 'skipped' for item in result.items)
    assert {item.requirement for item in result.items if item.kind == 'npm'} == set(
        build_manifest().dependencies.resolve_frontend(framework).npm
    )
    assert PluginDependencyInstallPlanner(frontend_root=root).build_plan(result).items == []
    assert PluginFrontendFrameworkResolver.resolve(root) == framework


@pytest.mark.parametrize('framework', ['vue2', 'vue3', 'react'])
def test_management_detail_uses_selected_frontend_profile(tmp_path: Path, framework: str) -> None:
    """校验管理详情展示当前宿主分类的依赖及全部分类信息。"""
    root = write_frontend(tmp_path, framework)
    manifest = build_manifest()
    plugin = DiscoveredPlugin(
        manifest=manifest,
        backend_path=tmp_path / 'plugins' / 'demo',
        manifest_path=tmp_path / 'plugins' / 'demo' / 'plugin.yaml',
    )
    model = PluginService._build_plugin_model(plugin, tmp_path / 'plugins', root / 'plugins', None)
    assert model.dependencies['frontendFramework'] == framework
    assert model.dependencies['npm'] == manifest.dependencies.resolve_frontend(framework).npm
    assert set(model.dependencies['frontendProfiles']) == {'vue2', 'vue3', 'react'}
    assert 'frontendVersion' not in model.dependencies


@pytest.mark.parametrize('framework', ['', 'React', 'auto', '../vue3', 'react/web', 'react.next', '9react'])
def test_unsafe_framework_profile_is_rejected(framework: str) -> None:
    """校验清单拒绝不安全或非小写的框架分类标识。"""
    payload = build_manifest().model_dump(by_alias=True)
    payload['dependencies']['frontend'][framework] = {'npm': ['wrong-host==1.0.0']}
    with pytest.raises(ValueError):
        PluginManifest.model_validate(payload)


def test_new_framework_profile_requires_no_schema_change() -> None:
    """校验新增安全框架标识可直接声明完整依赖，无需修改模型白名单。"""
    payload = build_manifest().model_dump(by_alias=True)
    payload['dependencies']['frontend']['custom_ui-1'] = {'npm': ['custom-renderer==1.0.0']}
    manifest = PluginManifest.model_validate(payload)
    assert manifest.dependencies.resolve_frontend('custom_ui-1').npm == ['custom-renderer==1.0.0']


@pytest.mark.parametrize('framework', ['vue2', 'vue3', 'react'])
def test_lock_template_contains_only_selected_host_dependencies(tmp_path: Path, framework: str) -> None:
    """校验锁文件模板只包含当前宿主分类的前端依赖。"""
    root = write_frontend(tmp_path, framework)
    template = PluginDependencyLockfileTemplateBuilder.build(build_manifest(), frontend_root=root)
    payload = template.to_dict()
    assert payload['frontendFramework'] == framework
    assert 'frontendVersion' not in payload
    assert {item['requirement'] for item in payload['npm']} == set(
        build_manifest().dependencies.resolve_frontend(framework).npm
    )


@pytest.mark.parametrize('selection_source', ['constructor', 'environment'])
def test_independent_host_preserves_explicit_framework_through_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selection_source: str
) -> None:
    """校验独立工程保留自定义框架身份，且不会将当前身份套用到其他工程。"""
    for name in (
        'RUOYI_PLUGIN_FRONTEND_ROOT',
        'RUOYI_FRONTEND_ROOT',
        'RUOYI_PLUGIN_FRONTEND_FRAMEWORK',
        'RUOYI_FRONTEND_FRAMEWORK',
    ):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / 'external-react-app'
    root.mkdir()
    (root / 'package.json').write_text('{"dependencies": {"react": "^18.3.1"}}', encoding='utf-8')
    if selection_source == 'environment':
        monkeypatch.setenv('RUOYI_PLUGIN_FRONTEND_FRAMEWORK', 'react18')
    environment = PluginRuntimeEnvironmentService(
        backend_root=tmp_path / 'backend',
        frontend_root=root,
        frontend_framework='react18' if selection_source == 'constructor' else 'auto',
    )
    for module in (
        'plugins.core.environment',
        'plugins.core.management.service.service',
    ):
        monkeypatch.setattr(f'{module}.PLUGIN_RUNTIME_ENVIRONMENT', environment)
    if selection_source == 'environment':
        for module in ('plugins.core.validation.dependencies', 'plugins.core.validation.dependency_policy'):
            monkeypatch.setattr(f'{module}.PLUGIN_RUNTIME_ENVIRONMENT', environment)
    payload = build_manifest().model_dump(by_alias=True)
    payload['dependencies']['frontend']['react18'] = {'npm': ['react18-renderer==1.0.0']}
    manifest = PluginManifest.model_validate(payload)
    checker = PluginDependencyChecker(
        npm_inspector=NpmDependencyInspector(frontend_root=root),
        runtime_environment=environment if selection_source == 'constructor' else None,
    )
    result = checker.check_manifest(manifest)
    assert {item.requirement for item in result.items} == {'react18-renderer==1.0.0'}
    plan = PluginDependencyInstallPlanner(frontend_root=root).build_plan(result)
    assert {item.workdir for item in plan.items} == {str(root)}
    plugin = DiscoveredPlugin(
        manifest=manifest,
        backend_path=tmp_path / 'plugins' / 'demo',
        manifest_path=tmp_path / 'plugins' / 'demo' / 'plugin.yaml',
    )
    model = PluginService._build_plugin_model(plugin, tmp_path / 'plugins', root / 'plugins', None)
    assert model.dependencies['frontendFramework'] == 'react18'
    assert model.dependencies['npm'] == ['react18-renderer==1.0.0']
    for framework in ('auto', environment.get_frontend_framework()):
        template = PluginDependencyLockfileTemplateBuilder.build(
            manifest, frontend_root=root, frontend_framework=framework
        ).to_dict()
        assert template['frontendFramework'] == 'react18'
        assert {item['requirement'] for item in template['npm']} == {'react18-renderer==1.0.0'}
    lock_path = tmp_path / 'react18.lock.yaml'
    lock_path.write_text('frontendFramework: react18\n', encoding='utf-8')
    evaluator = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(mode='explicit', lockfile_path=lock_path, allow_unlisted=True),
        runtime_environment=environment if selection_source == 'constructor' else None,
    )
    assert evaluator.evaluate(plan, confirmed=True).allowed
    other_root = tmp_path / 'other-react-app'
    other_root.mkdir()
    (other_root / 'package.json').write_text('{"dependencies": {"react": "^18.3.1"}}', encoding='utf-8')
    other_plan = PluginDependencyInstallPlanner(frontend_root=other_root).build_plan(result)
    other_decision = evaluator.evaluate(other_plan, confirmed=True)
    assert other_decision.allowed is False
    assert any('lock=react18 host=react' in reason for reason in other_decision.reasons)


@pytest.mark.parametrize(('framework', 'locked_framework'), [('vue2', 'vue3'), ('react', 'vue3'), ('vue3', 'react')])
def test_lockfile_rejects_another_frontend_framework(tmp_path: Path, framework: str, locked_framework: str) -> None:
    """校验安装策略拒绝与宿主前端框架不匹配的锁文件。"""
    root = write_frontend(tmp_path, framework)
    manifest = build_manifest()
    result = PluginDependencyChecker(npm_inspector=NpmDependencyInspector(frontend_root=root)).check_manifest(manifest)
    plan = PluginDependencyInstallPlanner(frontend_root=root).build_plan(result)
    lock_path = tmp_path / f'{locked_framework}.lock.yaml'
    lock_path.write_text(f'frontendFramework: {locked_framework}\n', encoding='utf-8')
    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(mode='explicit', lockfile_path=lock_path)
    ).evaluate(plan, confirmed=True)
    assert decision.allowed is False
    assert any(f'lock={locked_framework} host={framework}' in reason for reason in decision.reasons)


@pytest.mark.parametrize('legacy_field', ['frontendVersion: vue3', 'frontendVersion: null'])
def test_lockfile_rejects_legacy_framework_metadata(tmp_path: Path, legacy_field: str) -> None:
    """校验旧框架元数据不会被静默忽略，必须先迁移锁文件。"""
    lock_path = tmp_path / 'legacy.lock.yaml'
    lock_path.write_text(legacy_field + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match=r'frontendVersion 已移除.*frontendFramework'):
        DependencyLockfile.load(lock_path)


@pytest.mark.parametrize('framework', ['null', '23', '""', 'auto', 'React', '../vue3'])
def test_lockfile_rejects_invalid_framework_metadata(tmp_path: Path, framework: str) -> None:
    """校验锁文件框架元数据必须是安全的小写框架标识。"""
    lock_path = tmp_path / 'invalid.lock.yaml'
    lock_path.write_text(f'frontendFramework: {framework}\n', encoding='utf-8')
    with pytest.raises(ValueError):
        DependencyLockfile.load(lock_path)


def test_lockfile_without_framework_metadata_preserves_general_lock_format(tmp_path: Path) -> None:
    """校验未绑定框架的通用依赖锁文件仍可加载。"""
    lock_path = tmp_path / 'general.lock.yaml'
    lock_path.write_text('npm: []\npython: []\n', encoding='utf-8')
    lockfile = DependencyLockfile.load(lock_path)
    assert lockfile is not None
    assert lockfile.frontend_framework is None
    assert lockfile.entries == {}


def test_profile_dependencies_trigger_frontend_build_and_lint(tmp_path: Path) -> None:
    """校验分类依赖参与前端构建判定、清单检查和运行能力限制。"""
    payload = build_manifest().model_dump(by_alias=True)
    payload.pop('frontend')
    payload['dependencies'] = {'frontend': {'vue2': {'npm': ['unpinned-package']}}}
    manifest = PluginManifest.model_validate(payload)
    assert manifest.frontend.delivery.build_required is True
    issues = PluginManifestChecker._check_unpinned_dependencies(None, manifest)
    assert issues[0].path == 'dependencies.frontend.vue2.npm.0'
    plugin = DiscoveredPlugin(manifest=manifest, backend_path=tmp_path, manifest_path=tmp_path / 'plugin.yaml')
    capability = PluginRuntimeCapabilityResolver(frontend_mode='built', backend_runtime_mode='service').resolve(plugin)
    assert capability.has_frontend_resources is True
    assert capability.frontend_runtime_manageable is False


def test_bundle_rejects_host_profile_dependencies() -> None:
    """校验独立 bundle 插件不能声明宿主前端分类依赖。"""
    payload = build_manifest().model_dump(by_alias=True)
    payload['manifestVersion'] = 2
    payload['backend'].update(integration='asgi', entrypoint='plugins.demo.entry:create_plugin')
    payload['backend']['routers'] = {'autoScan': False}
    payload['frontend'] = {'delivery': {'type': 'bundle'}, 'bundle': {}}
    payload['dependencies'] = {'frontend': {'vue2': {'npm': ['renderer==2.0.0']}}}
    with pytest.raises(ValueError, match='不能安装到宿主'):
        PluginManifestFactory.create(payload)
