from pathlib import Path

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.management.entity.vo.schemas import PluginModel
from plugins.core.manifest.schema import PluginManifest
from plugins.core.validation.plugin_deps import (
    PluginDependencyChecker,
    PluginDependencyPlanBuilder,
)


def build_discovered_plugin(
    tmp_path: Path,
    plugin_id: str,
    version: str = '1.0.0',
    dependencies: list[object] | None = None,
) -> DiscoveredPlugin:
    """构造测试用已发现插件。"""
    backend_path = tmp_path / 'plugins' / plugin_id
    manifest_path = backend_path / 'plugin.yaml'
    backend_path.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('', encoding='utf-8')
    manifest = PluginManifest.model_validate(
        {
            'id': plugin_id,
            'name': plugin_id,
            'version': version,
            'backend': {'module': f'plugins.{plugin_id}'},
            'dependencies': {'plugins': dependencies or []},
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def build_database_plugin(
    plugin_id: str, version: str, *, enabled: str = '0', status: str = 'installed'
) -> PluginModel:
    """构造测试用数据库插件状态。"""
    return PluginModel(
        pluginId=plugin_id,
        pluginName=plugin_id,
        version=version,
        installedVersion=version,
        enabled=enabled,
        status=status,
    )


def test_plugin_dependency_checker_accepts_satisfied_dependency(tmp_path: Path) -> None:
    """校验插件间依赖满足时检查通过。"""
    target = build_discovered_plugin(tmp_path, 'target', dependencies=['base>=1.0.0'])
    base = build_discovered_plugin(tmp_path, 'base', version='1.2.0')

    result = PluginDependencyChecker(
        [target, base],
        [build_database_plugin('base', '1.2.0')],
    ).check_manifest(target.manifest)

    assert result.ok is True
    assert result.items[0].status == 'satisfied'


def test_plugin_dependency_checker_reports_missing_and_not_installed(tmp_path: Path) -> None:
    """校验插件间依赖能报告缺失和未安装。"""
    target = build_discovered_plugin(
        tmp_path,
        'target',
        dependencies=['missing', {'id': 'base'}],
    )
    base = build_discovered_plugin(tmp_path, 'base')

    result = PluginDependencyChecker([target, base], []).check_manifest(target.manifest)

    assert result.ok is False
    assert [item.status for item in result.failed_items] == ['missing', 'not_installed']


def test_plugin_dependency_checker_reports_disabled_and_version_unsatisfied(tmp_path: Path) -> None:
    """校验插件间依赖能报告未启用和版本不满足。"""
    target = build_discovered_plugin(
        tmp_path,
        'target',
        dependencies=[{'id': 'base', 'version': '>=2.0.0'}, 'helper'],
    )
    base = build_discovered_plugin(tmp_path, 'base', version='1.0.0')
    helper = build_discovered_plugin(tmp_path, 'helper')

    result = PluginDependencyChecker(
        [target, base, helper],
        [
            build_database_plugin('base', '1.0.0'),
            build_database_plugin('helper', '1.0.0', enabled='1', status='installed'),
        ],
    ).check_manifest(target.manifest)

    assert result.ok is False
    assert [item.status for item in result.failed_items] == ['version_unsatisfied', 'disabled']


def test_plugin_dependency_checker_treats_bare_version_as_exact_constraint(tmp_path: Path) -> None:
    """校验插件依赖裸版本约束按精确版本匹配。"""
    target = build_discovered_plugin(
        tmp_path,
        'target',
        dependencies=[{'id': 'base', 'version': '1.0.0'}],
    )
    base = build_discovered_plugin(tmp_path, 'base', version='2.0.0')

    result = PluginDependencyChecker(
        [target, base],
        [build_database_plugin('base', '2.0.0')],
    ).check_manifest(target.manifest)

    assert result.ok is False
    assert result.failed_items[0].status == 'version_unsatisfied'


def test_plugin_dependency_checker_reports_cycle(tmp_path: Path) -> None:
    """校验插件间依赖能报告循环依赖。"""
    alpha = build_discovered_plugin(tmp_path, 'alpha', dependencies=['beta'])
    beta = build_discovered_plugin(tmp_path, 'beta', dependencies=['alpha'])

    result = PluginDependencyChecker(
        [alpha, beta],
        [
            build_database_plugin('alpha', '1.0.0'),
            build_database_plugin('beta', '1.0.0'),
        ],
    ).check_manifest(alpha.manifest)

    assert result.ok is False
    assert result.failed_items[-1].status == 'cycle'


def test_plugin_dependency_checker_reports_enabled_dependents(tmp_path: Path) -> None:
    """校验停用被依赖方前会报告仍启用的依赖方。"""
    base = build_discovered_plugin(tmp_path, 'base')
    app = build_discovered_plugin(tmp_path, 'app', dependencies=['base>=1.0.0'])
    disabled_app = build_discovered_plugin(tmp_path, 'disabled_app', dependencies=['base'])

    result = PluginDependencyChecker(
        [base, app, disabled_app],
        [
            build_database_plugin('base', '1.0.0'),
            build_database_plugin('app', '1.0.0'),
            build_database_plugin('disabled_app', '1.0.0', enabled='1', status='installed'),
        ],
    ).check_enabled_dependents('base')

    assert result.ok is False
    assert len(result.failed_items) == 1
    assert result.failed_items[0].plugin_id == 'app'
    assert result.failed_items[0].dependency_id == 'base'
    assert result.failed_items[0].status == 'dependent'


def test_plugin_dependency_plan_builder_sorts_dependencies_first_for_install(tmp_path: Path) -> None:
    """校验插件批量安装计划按依赖优先排序。"""
    app = build_discovered_plugin(tmp_path, 'app', dependencies=['base'])
    base = build_discovered_plugin(tmp_path, 'base')

    plan = PluginDependencyPlanBuilder([app, base], []).build_plan('install', ['app'])

    assert plan.ok is True
    assert plan.ordered_plugin_ids == ['base', 'app']
    assert [item.plugin_id for item in plan.items] == ['base', 'app']
    assert plan.items[0].requested is False
    assert plan.items[1].requested is True


def test_plugin_dependency_plan_builder_blocks_install_when_database_dependency_disabled(tmp_path: Path) -> None:
    """校验批量安装计划会阻止依赖插件已停用的场景。"""
    app = build_discovered_plugin(tmp_path, 'app', dependencies=['base'])
    base = build_discovered_plugin(tmp_path, 'base')
    database_base = build_database_plugin('base', '1.0.0', enabled='1', status='installed')

    plan = PluginDependencyPlanBuilder([app, base], [database_base]).build_plan('install', ['app'])

    assert plan.ok is False
    assert plan.blockers[0].status == 'disabled'


def test_plugin_dependency_plan_builder_reports_missing_dependency(tmp_path: Path) -> None:
    """校验插件批量操作计划会报告缺失依赖。"""
    app = build_discovered_plugin(tmp_path, 'app', dependencies=['missing'])

    plan = PluginDependencyPlanBuilder([app], []).build_plan('install', ['app'])

    assert plan.ok is False
    assert plan.blockers[0].plugin_id == 'app'
    assert plan.blockers[0].dependency_id == 'missing'
    assert plan.blockers[0].status == 'missing'


def test_plugin_dependency_plan_builder_blocks_enable_when_dependency_not_installed(tmp_path: Path) -> None:
    """校验批量启用计划会阻止未安装依赖。"""
    app = build_discovered_plugin(tmp_path, 'app', dependencies=['base'])
    base = build_discovered_plugin(tmp_path, 'base')

    plan = PluginDependencyPlanBuilder([app, base], []).build_plan('enable', ['app'])

    assert plan.ok is False
    assert plan.items[1].plugin_id == 'app'
    assert plan.items[1].blockers[0].status == 'not_installed'


def test_plugin_dependency_plan_builder_allows_enable_with_disabled_installed_dependency(tmp_path: Path) -> None:
    """校验批量启用计划允许依赖插件在同一批次中从停用变为启用。"""
    app = build_discovered_plugin(tmp_path, 'app', dependencies=['base'])
    base = build_discovered_plugin(tmp_path, 'base')

    plan = PluginDependencyPlanBuilder(
        [app, base],
        [
            build_database_plugin('app', '1.0.0', enabled='1', status='installed'),
            build_database_plugin('base', '1.0.0', enabled='1', status='installed'),
        ],
    ).build_plan('enable', ['app'])

    assert plan.ok is True
    assert plan.ordered_plugin_ids == ['base', 'app']


def test_plugin_dependency_plan_builder_blocks_upgrade_when_dependency_disabled(tmp_path: Path) -> None:
    """校验批量升级计划会阻止依赖插件处于停用状态。"""
    app = build_discovered_plugin(tmp_path, 'app', dependencies=['base'])
    base = build_discovered_plugin(tmp_path, 'base')

    plan = PluginDependencyPlanBuilder(
        [app, base],
        [
            build_database_plugin('app', '1.0.0'),
            build_database_plugin('base', '1.0.0', enabled='1', status='installed'),
        ],
    ).build_plan('upgrade', ['app'])

    assert plan.ok is False
    assert plan.items[1].plugin_id == 'app'
    assert plan.items[1].blockers[0].status == 'disabled'


def test_plugin_dependency_plan_builder_reports_cycle(tmp_path: Path) -> None:
    """校验插件批量操作计划能报告循环依赖。"""
    alpha = build_discovered_plugin(tmp_path, 'alpha', dependencies=['beta'])
    beta = build_discovered_plugin(tmp_path, 'beta', dependencies=['alpha'])

    plan = PluginDependencyPlanBuilder([alpha, beta], []).build_plan('install', ['alpha'])

    assert plan.ok is False
    assert any(blocker.status == 'cycle' for blocker in plan.blockers)
