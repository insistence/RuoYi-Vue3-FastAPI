import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.manifest.schema import PluginManifest  # noqa: E402
from plugins.core.validation.dependencies import (  # noqa: E402
    DependencyCheckItem,
    DependencyCheckResult,
    DependencyRequirementParser,
    NpmDependencyInspector,
    PluginDependencyChecker,
    PluginDependencyInstallPlanner,
    PythonDependencyInspector,
    VersionConstraintMatcher,
)


def test_dependency_requirement_parser_parses_name_operator_and_version() -> None:
    """
    校验依赖声明解析器可以解析名称、操作符和版本。

    :return: None
    """
    parsed_dependency = DependencyRequirementParser.parse('openai>=2.17.0')

    assert parsed_dependency.name == 'openai'
    assert parsed_dependency.operator == '>='
    assert parsed_dependency.version == '2.17.0'
    assert parsed_dependency.required_version == '>=2.17.0'


def test_dependency_requirement_parser_parses_scoped_npm_dependency() -> None:
    """
    校验依赖声明解析器可以解析 scoped npm 包版本约束。

    :return: None
    """
    parsed_dependency = DependencyRequirementParser.parse('@antv/infographic^0.2.13')

    assert parsed_dependency.name == '@antv/infographic'
    assert parsed_dependency.operator == '^'
    assert parsed_dependency.version == '0.2.13'
    assert parsed_dependency.required_version == '^0.2.13'


def test_version_constraint_matcher_checks_common_operators() -> None:
    """
    校验版本约束匹配器支持常见比较操作符。

    :return: None
    """
    assert VersionConstraintMatcher.is_satisfied(
        '2.17.1',
        DependencyRequirementParser.parse('openai>=2.17.0'),
    )
    assert not VersionConstraintMatcher.is_satisfied(
        '2.16.9',
        DependencyRequirementParser.parse('openai>=2.17.0'),
    )
    assert VersionConstraintMatcher.is_satisfied(
        '1.2.3',
        DependencyRequirementParser.parse('demo==1.2.3'),
    )
    assert VersionConstraintMatcher.is_satisfied(
        '1.10.0',
        DependencyRequirementParser.parse('demo>=1.2.0'),
    )
    assert VersionConstraintMatcher.is_satisfied(
        '1.0.0-rc1',
        DependencyRequirementParser.parse('demo<1.0.0'),
    )


def test_python_dependency_inspector_reports_missing_and_unsatisfied_dependencies() -> None:
    """
    校验 Python 依赖检查器可以报告缺失和版本不满足。

    :return: None
    """
    inspector = PythonDependencyInspector(installed_packages={'openai': '2.17.0'})

    items = inspector.check(['openai>=2.17.0', 'mistralai>=2.0.0', 'missing-package'])

    assert items[0].ok is True
    assert items[1].installed is False
    assert items[1].ok is False
    assert items[2].installed is False


def test_python_dependency_inspector_normalizes_distribution_names() -> None:
    """
    校验 Python 依赖检查按 PEP 503 规则归一化包名。

    :return: None
    """
    inspector = PythonDependencyInspector(
        installed_packages={
            'cerebras_cloud_sdk': '1.67.0',
            'demo.package_name': '1.0.0',
        }
    )

    items = inspector.check(['cerebras-cloud-sdk==1.67.0', 'demo-package-name>=1.0.0'])

    assert items[0].ok is True
    assert items[0].installed_version == '1.67.0'
    assert items[1].ok is True
    assert items[1].installed_version == '1.0.0'


def test_npm_dependency_inspector_reads_package_json(tmp_path: Path) -> None:
    """
    校验 npm 依赖检查器读取 package.json 的 dependencies 和 devDependencies。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    frontend_root = tmp_path / 'frontend'
    frontend_root.mkdir()
    (frontend_root / 'package.json').write_text(
        """
{
  "dependencies": {
    "vue": "3.5.26"
  },
  "devDependencies": {
    "vite": "6.4.1"
  }
}
""",
        encoding='utf-8',
    )

    inspector = NpmDependencyInspector(frontend_root=frontend_root)
    items = [
        *inspector.check(['vue>=3.5.0', 'missing-lib']),
        *inspector.check(['vite>=6.0.0'], dev=True),
    ]

    assert items[0].ok is True
    assert items[1].installed is False
    assert items[2].ok is True
    assert items[2].kind == 'npmDev'


def test_npm_dependency_inspector_defaults_to_frontend_sibling_project() -> None:
    """
    校验 npm 依赖检查器默认读取后端同级前端项目。

    :return: None
    """
    inspector = NpmDependencyInspector()

    assert inspector.frontend_root == BACKEND_ROOT.parent / 'ruoyi-fastapi-frontend'


def test_plugin_dependency_install_planner_builds_valid_npm_install_targets() -> None:
    """
    校验 npm 依赖安装计划会把 manifest 约束转换为 npm install 目标。

    :return: None
    """
    planner = PluginDependencyInstallPlanner(frontend_root='/tmp/frontend')
    items = [
        DependencyCheckItem(
            kind='npm',
            requirement='@antv/infographic^0.2.13',
            name='@antv/infographic',
            installed=False,
            version_satisfied=False,
            installed_version=None,
            required_version='^0.2.13',
            message='missing',
        ),
        DependencyCheckItem(
            kind='npm',
            requirement='katex>=0.16.27',
            name='katex',
            installed=False,
            version_satisfied=False,
            installed_version=None,
            required_version='>=0.16.27',
            message='missing',
        ),
        DependencyCheckItem(
            kind='npmDev',
            requirement='vite-plugin-monaco-editor-esm==2.0.2',
            name='vite-plugin-monaco-editor-esm',
            installed=False,
            version_satisfied=False,
            installed_version=None,
            required_version='==2.0.2',
            message='missing',
        ),
    ]

    plan = planner.build_plan(DependencyCheckResult(plugin_id='demo', items=items))

    assert plan.items[0].command == ['npm', 'install', '@antv/infographic@^0.2.13']
    assert plan.items[1].command == ['npm', 'install', 'katex@>=0.16.27']
    assert plan.items[2].command == ['npm', 'install', '--save-dev', 'vite-plugin-monaco-editor-esm@2.0.2']


def test_plugin_dependency_checker_checks_manifest_dependencies() -> None:
    """
    校验插件依赖检查器可以聚合 manifest 中的 Python 和 npm 依赖。

    :return: None
    """
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'dependencies': {
                'python': ['openai>=2.17.0', 'missing-python'],
                'npm': ['vue>=3.5.0', 'missing-npm'],
                'npmDev': ['vite>=6.0.0', 'missing-dev-npm'],
            },
        }
    )
    checker = PluginDependencyChecker(
        python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
        npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26', 'vite': '6.4.1'}),
    )

    result = checker.check_manifest(manifest)

    assert result.ok is False
    assert [item.name for item in result.missing_items] == ['missing-python', 'missing-npm', 'missing-dev-npm']
    assert result.unsatisfied_items == []


def test_plugin_dependency_checker_reads_npm_dependencies_from_plugin_manifest(tmp_path: Path) -> None:
    """
    校验依赖检查器只读取主插件清单中的 npm 依赖。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    frontend_root = tmp_path / 'ruoyi-fastapi-frontend'
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'dependencies': {'npm': ['vue>=3.5.0'], 'npmDev': ['markstream-vue']},
        }
    )
    checker = PluginDependencyChecker(
        python_inspector=PythonDependencyInspector(installed_packages={}),
        npm_inspector=NpmDependencyInspector(
            frontend_root=frontend_root,
            installed_packages={'vue': '3.5.26', 'markstream-vue': '0.1.0'},
        ),
    )

    result = checker.check_manifest(manifest)

    assert result.ok is True
    assert [item.name for item in result.items] == ['vue', 'markstream-vue']
    assert [item.kind for item in result.items] == ['npm', 'npmDev']
    assert [item.declared_version for item in result.items] == ['3.5.26', '0.1.0']


def test_plugin_dependency_checker_skips_npm_dependencies_in_built_frontend_mode() -> None:
    """
    校验已构建前端模式下 npm 依赖不参与实际检查。

    :return: None
    """
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'dependencies': {'python': ['missing-python'], 'npm': ['missing-npm'], 'npmDev': ['missing-dev-npm']},
        }
    )
    checker = PluginDependencyChecker(
        python_inspector=PythonDependencyInspector(installed_packages={}),
        npm_inspector=NpmDependencyInspector(installed_packages={}),
        frontend_mode='built',
    )

    result = checker.check_manifest(manifest)

    assert result.ok is False
    assert [item.name for item in result.missing_items] == ['missing-python']
    assert [item.status for item in result.items if item.kind in {'npm', 'npmDev'}] == ['skipped', 'skipped']
    plan = PluginDependencyInstallPlanner(frontend_root='/tmp/frontend').build_plan(result)
    assert plan.items[0].kind == 'python'
    assert len(plan.items) == 1
