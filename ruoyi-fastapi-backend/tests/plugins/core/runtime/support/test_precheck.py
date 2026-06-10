# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_precheck_operation_payload_model_serializes_payload() -> None:
    """
    校验插件预检操作片段结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = PluginPrecheckContext(
        dependency_result=SimpleNamespace(ok=False),
        manifest_result=SimpleNamespace(ok=True),
        plugin_dependency_result=SimpleNamespace(ok=True),
        structure_result=SimpleNamespace(ok=True),
        menu_conflict_result=SimpleNamespace(ok=True),
        manifest_issues=[],
        manifest_warnings=[],
        plugin_dependency_errors=[],
        structure_errors=[],
        menu_conflicts=[],
        dependencies=[{'name': 'missing-python'}],
        plugin_dependencies=[],
        structure=[],
        missing_dependencies=['missing-python'],
        unsatisfied_dependencies=[],
    )

    payload = PluginPrecheckOperationPayload(precheck).to_payload()

    assert payload['manifestOk'] is True
    assert payload['dependencyOk'] is False
    assert payload['pluginDependencyOk'] is True
    assert payload['structureOk'] is True
    assert payload['menuConflictOk'] is True
    assert payload['dependencies'] == [{'name': 'missing-python'}]
    assert payload['manifestIssues'] == []


def test_plugin_precheck_check_payload_model_serializes_payload() -> None:
    """
    校验插件预检检查片段结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = PluginPrecheckContext(
        dependency_result=SimpleNamespace(ok=False),
        manifest_result=SimpleNamespace(ok=True),
        plugin_dependency_result=SimpleNamespace(ok=True),
        structure_result=SimpleNamespace(ok=True),
        menu_conflict_result=SimpleNamespace(ok=True),
        manifest_issues=[],
        manifest_warnings=[],
        plugin_dependency_errors=[],
        structure_errors=[],
        menu_conflicts=[],
        dependencies=[{'name': 'missing-python'}],
        plugin_dependencies=[],
        structure=[{'name': 'manifest'}],
        missing_dependencies=['missing-python'],
        unsatisfied_dependencies=[],
    )

    payload = PluginPrecheckCheckPayload(precheck).to_payload()

    assert payload['manifestOk'] is True
    assert payload['dependencyOk'] is False
    assert payload['structure'] == [{'name': 'manifest'}]
    assert payload['missingDependencies'] == ['missing-python']
    assert payload['unsatisfiedDependencies'] == []
