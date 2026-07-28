import json
from pathlib import Path

from plugins.core.runtime.support import PluginBatchReportBuilder, PluginNpmPackageJsonSynchronizer
from plugins.core.validation.dependencies import DependencyInstallPlanItem


def build_npm_plan_item(
    workdir: Path,
    *,
    kind: str,
    requirement: str,
    name: str,
) -> DependencyInstallPlanItem:
    """构造测试用 npm 依赖安装计划项。"""
    command = ['npm', 'install']
    if kind == 'npmDev':
        command.append('--save-dev')
    command.append(requirement)
    return DependencyInstallPlanItem(
        kind=kind,
        requirement=requirement,
        name=name,
        command=command,
        workdir=str(workdir),
        reason='缺失依赖',
    )


def test_batch_report_builder_prefers_explicit_requested_plugin_ids() -> None:
    """校验批量报告优先使用显式请求的插件 ID。"""
    payload = {
        'plan': {
            'requestedPluginIds': ['app', 'worker'],
            'orderedPluginIds': ['base', 'app', 'shared', 'worker'],
        }
    }

    assert PluginBatchReportBuilder.resolve_executable_plugin_ids(payload) == ['app', 'worker']


def test_batch_report_builder_falls_back_to_ordered_plugin_ids() -> None:
    """校验批量报告在未显式指定时采用排序后的插件 ID。"""
    payload = {'plan': {'orderedPluginIds': ['base', 'app']}}

    assert PluginBatchReportBuilder.resolve_executable_plugin_ids(payload) == ['base', 'app']


def test_npm_package_json_synchronizer_preserves_manifest_versions(tmp_path: Path) -> None:
    """校验 package.json 同步保留清单中的 npm 版本约束。"""
    package_json_path = tmp_path / 'package.json'
    package_json_path.write_text('{"dependencies": {}, "devDependencies": {}}\n', encoding='utf-8')
    plan_items = [
        build_npm_plan_item(
            tmp_path,
            kind='npm',
            requirement='markstream-vue>=0.0.7-beta.6',
            name='markstream-vue',
        ),
        build_npm_plan_item(
            tmp_path,
            kind='npmDev',
            requirement='vite-plugin-demo==1.0.0',
            name='vite-plugin-demo',
        ),
    ]

    PluginNpmPackageJsonSynchronizer.sync_successful_items(
        plan_items,
        [{'returnCode': 0}, {'returnCode': 0}],
    )

    package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
    assert package_json['dependencies']['markstream-vue'] == '>=0.0.7-beta.6'
    assert package_json['devDependencies']['vite-plugin-demo'] == '1.0.0'


def test_npm_package_json_synchronizer_skips_failed_and_non_npm_items(tmp_path: Path) -> None:
    """校验 package.json 同步跳过失败项与非 npm 依赖。"""
    package_json_path = tmp_path / 'package.json'
    package_json_path.write_text('{"dependencies": {}, "devDependencies": {}}\n', encoding='utf-8')
    failed_npm = build_npm_plan_item(
        tmp_path,
        kind='npm',
        requirement='failed-npm>=1.0.0',
        name='failed-npm',
    )
    python_item = DependencyInstallPlanItem(
        kind='python',
        requirement='requests>=2.0.0',
        name='requests',
        command=['python', '-m', 'pip', 'install', 'requests>=2.0.0'],
        workdir=str(tmp_path),
        reason='缺失依赖',
    )

    PluginNpmPackageJsonSynchronizer.sync_successful_items(
        [failed_npm, python_item],
        [{'returnCode': 1}, {'returnCode': 0}],
    )

    package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
    assert package_json['dependencies'] == {}
    assert package_json['devDependencies'] == {}


def test_npm_package_json_synchronizer_uses_star_without_version(tmp_path: Path) -> None:
    """校验未声明版本的 npm 依赖使用星号约束。"""
    package_json_path = tmp_path / 'package.json'
    package_json_path.write_text('{}\n', encoding='utf-8')
    plan_item = build_npm_plan_item(
        tmp_path,
        kind='npm',
        requirement='plain-npm',
        name='plain-npm',
    )

    PluginNpmPackageJsonSynchronizer.sync_item(plan_item)

    package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
    assert package_json['dependencies']['plain-npm'] == '*'
