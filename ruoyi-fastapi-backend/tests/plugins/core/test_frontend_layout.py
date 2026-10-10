import json
from pathlib import Path

import pytest

from plugins.core.frontend import (
    PluginFrontendFrameworkResolver,
    resolve_frontend_framework,
    resolve_frontend_root,
    select_frontend_root,
    validate_frontend_framework,
)


@pytest.fixture(autouse=True)
def clear_frontend_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    清除前端路径与框架环境变量，避免本机配置影响测试。

    :param monkeypatch: pytest 环境变量替换工具
    :return: None
    """
    for name in (
        'RUOYI_PLUGIN_FRONTEND_ROOT',
        'RUOYI_FRONTEND_ROOT',
        'RUOYI_PLUGIN_FRONTEND_FRAMEWORK',
        'RUOYI_FRONTEND_FRAMEWORK',
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_frontend_is_vue3_web_without_existing_checkout(tmp_path: Path) -> None:
    """校验未检出前端工程时默认定位到 Vue 3 Web 目录。"""
    assert resolve_frontend_root(tmp_path / 'ruoyi-fastapi-backend') == tmp_path / 'ruoyi-fastapi-frontend/vue3/web'


def test_nested_container_never_becomes_a_project_root(tmp_path: Path) -> None:
    """校验前端聚合目录按框架定位到具体 Web 工程。"""
    root = tmp_path / 'ruoyi-fastapi-frontend'
    for version in ('vue2', 'vue3'):
        (root / version / 'web').mkdir(parents=True)
    assert resolve_frontend_root(tmp_path / 'ruoyi-fastapi-backend') == root / 'vue3/web'
    assert resolve_frontend_root(tmp_path / 'ruoyi-fastapi-backend', frontend_framework='vue2') == root / 'vue2/web'
    assert select_frontend_root(root, 'vue2') == root / 'vue2/web'


def test_framework_environment_selects_vue2_and_explicit_argument_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验框架环境变量可以选择 Vue 2，且显式参数优先。"""
    monkeypatch.setenv('RUOYI_PLUGIN_FRONTEND_FRAMEWORK', 'vue2')
    backend = tmp_path / 'ruoyi-fastapi-backend'
    assert resolve_frontend_root(backend) == tmp_path / 'ruoyi-fastapi-frontend/vue2/web'
    assert resolve_frontend_root(backend, frontend_framework='vue3') == tmp_path / 'ruoyi-fastapi-frontend/vue3/web'


def test_explicit_project_and_container_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """校验显式工程目录、聚合目录环境变量和框架选择的优先级。"""
    container = tmp_path / 'ruoyi-fastapi-frontend'
    explicit = tmp_path / 'custom-web'
    monkeypatch.setenv('RUOYI_PLUGIN_FRONTEND_ROOT', str(container))
    monkeypatch.setenv('RUOYI_PLUGIN_FRONTEND_FRAMEWORK', 'vue2')
    assert resolve_frontend_root(tmp_path / 'backend') == container / 'vue2/web'
    assert resolve_frontend_root(tmp_path / 'backend', explicit) == explicit
    assert select_frontend_root(container / 'vue3/web') == container / 'vue3/web'
    assert select_frontend_root(container / 'vue3/web', 'vue2') == container / 'vue2/web'


def test_legacy_flat_frontend_is_retained(tmp_path: Path) -> None:
    """校验原有平铺前端工程目录仍可正常解析。"""
    frontend = tmp_path / 'ruoyi-fastapi-frontend'
    frontend.mkdir()
    (frontend / 'package.json').write_text('{"dependencies":{"vue":"^2.7.16"}}', encoding='utf-8')
    assert resolve_frontend_root(tmp_path / 'ruoyi-fastapi-backend') == frontend


@pytest.mark.parametrize('framework', ['../../outside', '..', 'react/next', 'react\\next', 'react.next', '1react'])
def test_invalid_framework_cannot_be_used_as_a_path(tmp_path: Path, framework: str) -> None:
    """校验非法框架标识不能用于拼接前端工程路径。"""
    with pytest.raises(ValueError, match='frontend_framework'):
        resolve_frontend_root(tmp_path / 'backend', frontend_framework=framework)


@pytest.mark.parametrize('framework', ['react', 'react18', 'custom_ui-1'])
def test_generic_framework_can_select_a_workspace(tmp_path: Path, framework: str) -> None:
    """校验标准目录能选择合法的扩展框架而无需预先创建工程。"""
    container = tmp_path / 'ruoyi-fastapi-frontend'
    expected = container / framework / 'web'
    assert resolve_frontend_root(tmp_path / 'backend', frontend_framework=framework) == expected
    assert select_frontend_root(container, framework) == expected
    assert select_frontend_root(container / 'vue3/web', framework) == expected
    assert select_frontend_root(container / framework) == expected


def test_framework_environment_priority_and_old_names_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验新框架变量的优先级，旧版本变量不再影响框架选择。"""
    monkeypatch.setenv('RUOYI_PLUGIN_FRONTEND_VERSION', 'vue2')
    monkeypatch.setenv('RUOYI_FRONTEND_VERSION', 'vue2')
    assert resolve_frontend_framework() == 'vue3'
    monkeypatch.setenv('RUOYI_FRONTEND_FRAMEWORK', 'react')
    assert resolve_frontend_framework() == 'react'
    monkeypatch.setenv('RUOYI_PLUGIN_FRONTEND_FRAMEWORK', 'custom_ui-1')
    assert resolve_frontend_framework() == 'custom_ui-1'
    assert resolve_frontend_framework('vue2') == 'vue2'


@pytest.mark.parametrize('framework', ['auto', 'Vue3', '', 'react.next', '../react', 'react/web'])
def test_framework_identifier_validation_is_strict(framework: str) -> None:
    """校验实际框架标识不能包含自动选择值、大小写别名或路径字符。"""
    with pytest.raises(ValueError, match='frontend_framework'):
        validate_frontend_framework(framework)


@pytest.mark.parametrize('platform', ['web', 'mobile'])
@pytest.mark.parametrize('framework', ['vue2', 'react18', 'custom_ui-1'])
def test_standard_directory_identity_wins_over_package_dependencies(
    tmp_path: Path, platform: str, framework: str
) -> None:
    """校验标准工程使用目录框架身份，显式参数仍具有最高优先级。"""
    frontend = tmp_path / 'ruoyi-fastapi-frontend' / framework / platform
    frontend.mkdir(parents=True)
    (frontend / 'package.json').write_text('{"dependencies":{"vue":"^3.5.26"}}', encoding='utf-8')
    assert PluginFrontendFrameworkResolver.resolve(frontend) == framework
    assert PluginFrontendFrameworkResolver.resolve(frontend, 'react') == 'react'


@pytest.mark.parametrize(
    ('package', 'framework'),
    [
        ({'dependencies': {'vue': '^2.7.16'}}, 'vue2'),
        ({'devDependencies': {'vue': '~3.5.26'}}, 'vue3'),
        ({'dependencies': {'element-ui': '^2.15.14'}}, 'vue2'),
        ({'dependencies': {'element-plus': '^2.11.5'}}, 'vue3'),
        ({'dependencies': {'react': '^19.0.0'}}, 'react'),
    ],
)
def test_independent_project_detects_framework_from_package(
    tmp_path: Path, package: dict[str, dict[str, str]], framework: str
) -> None:
    """校验独立前端工程从已声明依赖中识别 Vue 或 React。"""
    (tmp_path / 'package.json').write_text(json.dumps(package), encoding='utf-8')
    assert PluginFrontendFrameworkResolver.resolve(tmp_path) == framework


def test_unknown_independent_project_requires_explicit_framework(tmp_path: Path) -> None:
    """校验无法识别的独立工程要求显式框架，不能默认归类为 Vue 3。"""
    (tmp_path / 'package.json').write_text('{"dependencies":{"custom-lib":"^1.0.0"}}', encoding='utf-8')
    with pytest.raises(ValueError, match='--frontend-framework'):
        PluginFrontendFrameworkResolver.resolve(tmp_path)
    assert PluginFrontendFrameworkResolver.resolve(tmp_path, 'custom_ui-1') == 'custom_ui-1'
