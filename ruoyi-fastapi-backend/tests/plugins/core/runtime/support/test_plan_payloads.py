# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_plan_payload_model_serializes_success_payload() -> None:
    """
    校验插件批量计划结构化模型可序列化为现有成功负载契约。

    :return: None
    """
    plan = PluginDependencyPlan(
        operation='install',
        requested_plugin_ids=['app'],
        ordered_plugin_ids=['base', 'app'],
        items=[
            PluginDependencyPlanItem(
                plugin_id='base',
                name='Base',
                version='1.0.0',
                operation='install',
                order=0,
                requested=False,
                dependencies=[],
                installed_version=None,
                enabled=None,
                status=None,
                blockers=[],
            )
        ],
        blockers=[],
    )

    payload = PluginPayloadBuilder.build_plan_payload(plan)

    assert payload['ok'] is True
    assert payload['message'] == '插件批量操作计划生成完成'
    assert payload['operation'] == 'install'
    assert payload['databaseAvailable'] is True
    assert payload['databaseError'] is None
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['plan']['items'][0]['ready'] is True


def test_plugin_plan_payload_model_serializes_blocked_payload() -> None:
    """
    校验插件批量计划结构化模型可序列化为现有阻断负载契约。

    :return: None
    """
    blocker = PluginDependencyPlanBlocker(
        plugin_id='app',
        dependency_id='base',
        status='not_installed',
        message='依赖插件未安装：base',
    )
    plan = PluginDependencyPlan(
        operation='enable',
        requested_plugin_ids=['app'],
        ordered_plugin_ids=['app'],
        items=[
            PluginDependencyPlanItem(
                plugin_id='app',
                name='App',
                version='1.0.0',
                operation='enable',
                order=0,
                requested=True,
                dependencies=['base'],
                installed_version='1.0.0',
                enabled='0',
                status='installed',
                blockers=[blocker],
            )
        ],
        blockers=[blocker],
    )

    payload = PluginPayloadBuilder.build_plan_payload(plan)

    assert payload['ok'] is False
    assert payload['message'] == '插件批量操作计划存在阻塞项'
    assert payload['plan']['blockerCount'] == 1
    assert payload['plan']['items'][0]['ready'] is False
    assert payload['plan']['blockers'][0]['dependencyId'] == 'base'


def test_plugin_upgrade_dry_run_payload_model_serializes_payload() -> None:
    """
    校验插件升级预演结构化模型可序列化为现有负载契约。

    :return: None
    """
    dependency_result = DependencyCheckResult(plugin_id='demo', items=[])
    plugin_dependency_result = PluginDependencyCheckResult(plugin_id='demo', items=[])
    payload_context = {
        'versionState': {
            'installed': True,
            'installedVersion': '1.0.0',
            'currentVersion': '1.1.0',
            'needsUpgrade': True,
        },
        'dependencyResult': dependency_result,
        'pluginDependencyResult': plugin_dependency_result,
        'structureResult': SimpleNamespace(ok=True),
        'menuConflictResult': SimpleNamespace(ok=True),
        'manifestOk': True,
        'actions': [{'name': 'upsert_plugin'}],
        'manifestIssues': [],
        'manifestWarnings': [],
        'pluginDependencyErrors': [],
        'structureErrors': [],
        'menuConflicts': [],
    }

    payload = PluginPayloadBuilder.build_upgrade_dry_run_payload('demo', payload_context)

    assert payload['ok'] is True
    assert payload['message'] == '插件升级演练完成，未执行实际写入'
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is True
    assert payload['needsUpgrade'] is True
    assert payload['databaseAvailable'] is True
    assert payload['dependencyOk'] is True
    assert payload['pluginDependencyOk'] is True
    assert payload['actions'][0]['name'] == 'upsert_plugin'
