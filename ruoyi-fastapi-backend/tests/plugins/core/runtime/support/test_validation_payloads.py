# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_dependency_check_payload_model_serializes_success_payload() -> None:
    """
    校验插件依赖检查结构化模型可序列化为现有成功负载契约。

    :return: None
    """
    dependency_result = DependencyCheckResult(
        plugin_id='demo',
        items=[
            DependencyCheckItem(
                kind='python',
                requirement='openai>=2.17.0',
                name='openai',
                installed=True,
                version_satisfied=True,
                installed_version='2.17.0',
                required_version='>=2.17.0',
                message='依赖已满足',
            )
        ],
    )

    payload = PluginDependencyCheckPayload('demo', dependency_result).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件依赖已满足'
    assert payload['pluginId'] == 'demo'
    assert payload['dependencyOk'] is True
    assert payload['dependencies'][0]['name'] == 'openai'
    assert payload['missingDependencies'] == []
    assert payload['unsatisfiedDependencies'] == []
    assert payload['exit_code'] == SUCCESS


def test_plugin_dependency_check_payload_model_serializes_failure_payload() -> None:
    """
    校验插件依赖检查结构化模型可序列化为现有失败负载契约。

    :return: None
    """
    dependency_result = DependencyCheckResult(
        plugin_id='demo',
        items=[
            DependencyCheckItem(
                kind='python',
                requirement='missing-python>=1.0.0',
                name='missing-python',
                installed=False,
                version_satisfied=False,
                installed_version=None,
                required_version='>=1.0.0',
                message='依赖缺失',
            )
        ],
    )

    payload = PluginDependencyCheckPayload('demo', dependency_result).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件依赖存在问题'
    assert payload['dependencyOk'] is False
    assert payload['dependencies'][0]['level'] == 'error'
    assert payload['missingDependencies'] == ['missing-python']
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_check_item_payload_model_serializes_payload() -> None:
    """
    校验插件检查单项结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck(ok=False)

    payload = PluginCheckItemPayload('demo', precheck).to_payload()

    assert payload['pluginId'] == 'demo'
    assert payload['ok'] is False
    assert payload['manifestOk'] is False
    assert payload['dependencyOk'] is False


def test_plugin_check_payload_model_serializes_payload() -> None:
    """
    校验插件检查聚合结构化模型可序列化为现有负载契约。

    :return: None
    """
    success_payload = PluginCheckPayload([{'pluginId': 'demo', 'ok': True}]).to_payload()
    failed_payload = PluginCheckPayload([{'pluginId': 'demo', 'ok': False}]).to_payload()

    assert success_payload['ok'] is True
    assert success_payload['message'] == '插件检查通过'
    assert success_payload['count'] == 1
    assert success_payload['exit_code'] == SUCCESS
    assert failed_payload['ok'] is False
    assert failed_payload['message'] == '插件检查存在问题'
    assert failed_payload['exit_code'] == DEPENDENCY_ERROR
