# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_purge_payload_builder_builds_dry_run_payload() -> None:
    """
    校验插件物理清理负载构建器生成预演负载。

    :return: None
    """
    plan = PluginPurgePlan(
        plugin_id='demo',
        items=[
            PluginPurgePlanItem(
                name='delete_plugin_state',
                label='删除插件状态记录',
                enabled=True,
                destructive=True,
                count=1,
            )
        ],
        removes_source=False,
        requires_hook=False,
    )

    payload = PluginPurgePayloadBuilder.build_dry_run_payload('demo', plan)

    assert payload['ok'] is True
    assert payload['operation'] == 'purge'
    assert payload['dryRun'] is True
    assert payload['plan']['destructiveCount'] == 1


def test_plugin_purge_payload_builder_builds_success_payload() -> None:
    """
    校验插件物理清理负载构建器生成成功负载。

    :return: None
    """
    plan = PluginPurgePlan(plugin_id='demo', items=[], removes_source=False, requires_hook=True)
    hook_result = SimpleNamespace(hook_name='on_purge', ok=True)

    payload = PluginPurgePayloadBuilder.build_success_payload('demo', plan, hook_result)

    assert payload['ok'] is True
    assert payload['message'] == '插件物理清理完成'
    assert payload['dryRun'] is False
    assert payload['hooks'] == [{'hook_name': 'on_purge', 'ok': True}]


def test_plugin_batch_report_builder_builds_plan_blocked_payload() -> None:
    """
    校验插件批量报告构建器生成计划阻断负载。

    :return: None
    """
    plan_payload = {
        'ok': False,
        'operation': 'install',
        'plan': {'orderedPluginIds': ['demo']},
    }

    payload = PluginBatchReportBuilder.build_plan_blocked_payload(
        plan_payload,
        dry_run=False,
        continue_on_error=True,
    )

    assert payload['ok'] is False
    assert payload['dryRun'] is False
    assert payload['continueOnError'] is True
    assert payload['executed'] == []
    assert payload['failed'] is None
    assert payload['summary'] == {'total': 1, 'succeeded': 0, 'failed': 0, 'skipped': 1}


def test_plugin_batch_report_builder_builds_dry_run_payload() -> None:
    """
    校验插件批量报告构建器生成预演负载。

    :return: None
    """
    plan_payload = {
        'ok': True,
        'operation': 'install',
        'plan': {'requestedPluginIds': ['app'], 'orderedPluginIds': ['base', 'app']},
    }

    payload = PluginBatchReportBuilder.build_dry_run_payload(plan_payload, continue_on_error=False)

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['executed'] == []
    assert payload['failed'] is None
    assert payload['summary'] == {'total': 1, 'succeeded': 0, 'failed': 0, 'skipped': 1}


def test_plugin_batch_report_builder_resolves_requested_executable_ids() -> None:
    """
    校验批量执行只解析显式请求插件，依赖闭包只用于计划展示。

    :return: None
    """
    plan_payload = {
        'plan': {
            'requestedPluginIds': ['app', 'worker'],
            'orderedPluginIds': ['base', 'app', 'shared', 'worker'],
        }
    }

    plugin_ids = PluginBatchReportBuilder.resolve_executable_plugin_ids(plan_payload)

    assert plugin_ids == ['app', 'worker']


def test_plugin_batch_report_builder_resolves_ordered_ids_without_explicit_request() -> None:
    """
    校验未传显式请求插件时按拓扑顺序执行全部计划项。

    :return: None
    """
    plan_payload = {'plan': {'orderedPluginIds': ['base', 'app']}}

    plugin_ids = PluginBatchReportBuilder.resolve_executable_plugin_ids(plan_payload)

    assert plugin_ids == ['base', 'app']


def test_plugin_batch_report_builder_builds_execution_payload() -> None:
    """
    校验插件批量报告构建器生成执行结果负载。

    :return: None
    """
    plan_payload = {
        'ok': True,
        'operation': 'install',
        'plan': {'orderedPluginIds': ['alpha', 'beta']},
    }
    reports = [
        PluginBatchItemReport(
            plugin_id='alpha',
            operation='install',
            ok=True,
            status='success',
            message='成功',
            duration_ms=1,
            exit_code=0,
            suggestion='',
        ),
        PluginBatchItemReport(
            plugin_id='beta',
            operation='install',
            ok=False,
            status='failed',
            message='失败',
            duration_ms=2,
            exit_code=1,
            suggestion='检查失败原因',
        ),
    ]
    failed = PluginBatchReportBuilder.build_failed_payload(reports[1], {'ok': False, 'message': '失败'})

    payload = PluginBatchReportBuilder.build_execution_payload(
        plan_payload,
        reports,
        failed,
        continue_on_error=True,
    )

    assert payload['ok'] is False
    assert payload['message'] == '插件批量操作完成，存在失败项'
    assert [item['pluginId'] for item in payload['executed']] == ['alpha', 'beta']
    assert payload['failed']['pluginId'] == 'beta'
    assert payload['summary'] == {'total': 2, 'succeeded': 1, 'failed': 1, 'skipped': 0}


def test_plugin_dependency_install_payload_builder_builds_dry_run_payload() -> None:
    """
    校验插件依赖安装负载构建器生成预演负载。

    :return: None
    """
    dependency_result = DependencyCheckResult(
        plugin_id='demo',
        items=[
            DependencyCheckItem(
                kind='python',
                requirement='missing-python',
                name='missing-python',
                installed=False,
                version_satisfied=False,
                installed_version=None,
                required_version=None,
                message='未安装',
            )
        ],
    )
    plan_item = DependencyInstallPlanItem(
        kind='python',
        requirement='missing-python',
        name='missing-python',
        command=[sys.executable, '-m', 'pip', 'install', 'missing-python'],
        workdir='/tmp/backend',
        reason='缺失依赖',
    )

    payload = PluginDependencyInstallPayloadBuilder.build_dry_run_payload('demo', dependency_result, [plan_item])

    assert payload['ok'] is True
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is True
    assert payload['planCount'] == 1
    assert payload['plan'][0]['commandText'].endswith('pip install missing-python')


def test_plugin_dependency_install_payload_builder_builds_execution_payload() -> None:
    """
    校验插件依赖安装负载构建器生成执行结果负载。

    :return: None
    """
    dependency_result = DependencyCheckResult(plugin_id='demo', items=[])
    plan_item = DependencyInstallPlanItem(
        kind='npm',
        requirement='missing-npm',
        name='missing-npm',
        command=['npm', 'install', 'missing-npm'],
        workdir='/tmp/frontend',
        reason='缺失依赖',
    )
    install_result = {
        'kind': 'npm',
        'requirement': 'missing-npm',
        'name': 'missing-npm',
        'command': ['npm', 'install', 'missing-npm'],
        'commandText': 'npm install missing-npm',
        'workdir': '/tmp/frontend',
        'returnCode': 1,
        'stdout': '',
        'stderr': 'failed',
    }

    payload = PluginDependencyInstallPayloadBuilder.build_execution_payload(
        'demo',
        dependency_result,
        [plan_item],
        [install_result],
    )

    assert payload['ok'] is False
    assert payload['message'] == '插件依赖安装存在失败项'
    assert payload['exit_code'] == DEPENDENCY_ERROR
    assert payload['results'] == [install_result]


def test_plugin_dependency_install_payload_builder_keeps_npm_dev_kind() -> None:
    """
    校验 npm 开发依赖安装计划保留 npmDev 类型和命令。

    :return: None
    """
    dependency_result = DependencyCheckResult(plugin_id='demo', items=[])
    plan_item = DependencyInstallPlanItem(
        kind='npmDev',
        requirement='vite-plugin-demo==1.0.0',
        name='vite-plugin-demo',
        command=['npm', 'install', '--save-dev', 'vite-plugin-demo==1.0.0'],
        workdir='/tmp/frontend',
        reason='缺失开发依赖',
    )

    payload = PluginDependencyInstallPayloadBuilder.build_dry_run_payload('demo', dependency_result, [plan_item])

    assert payload['plan'][0]['kind'] == 'npmDev'
    assert payload['plan'][0]['command'] == ['npm', 'install', '--save-dev', 'vite-plugin-demo==1.0.0']
    assert payload['plan'][0]['commandText'] == 'npm install --save-dev vite-plugin-demo==1.0.0'


def test_plugin_npm_package_json_synchronizer_keeps_manifest_versions(tmp_path: Path) -> None:
    """
    校验 npm 安装成功后按 manifest 约束同步 package.json。

    :return: None
    """
    package_json_path = tmp_path / 'package.json'
    package_json_path.write_text('{"dependencies": {}, "devDependencies": {}}\n', encoding='utf-8')
    plan_items = [
        DependencyInstallPlanItem(
            kind='npm',
            requirement='markstream-vue>=0.0.7-beta.6',
            name='markstream-vue',
            command=['npm', 'install', 'markstream-vue@>=0.0.7-beta.6'],
            workdir=str(tmp_path),
            reason='缺失依赖',
        ),
        DependencyInstallPlanItem(
            kind='npmDev',
            requirement='vite-plugin-demo==1.0.0',
            name='vite-plugin-demo',
            command=['npm', 'install', '--save-dev', 'vite-plugin-demo@1.0.0'],
            workdir=str(tmp_path),
            reason='缺失开发依赖',
        ),
    ]
    install_results = [
        {'returnCode': 0},
        {'returnCode': 0},
    ]

    PluginNpmPackageJsonSynchronizer.sync_successful_items(plan_items, install_results)

    package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
    assert package_json['dependencies']['markstream-vue'] == '>=0.0.7-beta.6'
    assert package_json['devDependencies']['vite-plugin-demo'] == '1.0.0'


def test_plugin_npm_package_json_synchronizer_skips_failed_and_python_items(tmp_path: Path) -> None:
    """
    校验同步器跳过安装失败项和非 npm 项。

    :return: None
    """
    package_json_path = tmp_path / 'package.json'
    package_json_path.write_text('{"dependencies": {}, "devDependencies": {}}\n', encoding='utf-8')
    plan_items = [
        DependencyInstallPlanItem(
            kind='npm',
            requirement='failed-npm>=1.0.0',
            name='failed-npm',
            command=['npm', 'install', 'failed-npm@>=1.0.0'],
            workdir=str(tmp_path),
            reason='缺失依赖',
        ),
        DependencyInstallPlanItem(
            kind='python',
            requirement='requests>=2.0.0',
            name='requests',
            command=[sys.executable, '-m', 'pip', 'install', 'requests>=2.0.0'],
            workdir=str(tmp_path),
            reason='缺失依赖',
        ),
    ]
    install_results = [
        {'returnCode': 1},
        {'returnCode': 0},
    ]

    PluginNpmPackageJsonSynchronizer.sync_successful_items(plan_items, install_results)

    package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
    assert package_json['dependencies'] == {}
    assert package_json['devDependencies'] == {}


def test_plugin_npm_package_json_synchronizer_uses_star_without_version(tmp_path: Path) -> None:
    """
    校验无版本约束的 npm 依赖使用星号兜底。

    :return: None
    """
    package_json_path = tmp_path / 'package.json'
    package_json_path.write_text('{}\n', encoding='utf-8')
    plan_item = DependencyInstallPlanItem(
        kind='npm',
        requirement='plain-npm',
        name='plain-npm',
        command=['npm', 'install', 'plain-npm'],
        workdir=str(tmp_path),
        reason='缺失依赖',
    )

    PluginNpmPackageJsonSynchronizer.sync_item(plan_item)

    package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
    assert package_json['dependencies']['plain-npm'] == '*'
