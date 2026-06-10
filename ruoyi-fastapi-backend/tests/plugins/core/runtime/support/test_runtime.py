# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_runtime_exception_payload_model_serializes_payload() -> None:
    """
    校验插件运行时异常结构化模型可序列化为现有异常负载契约。

    :return: None
    """
    payload = PluginRuntimeExceptionPayload('插件安装失败', RuntimeError('boom')).to_payload()

    assert payload == {
        'ok': False,
        'message': '插件安装失败',
        'error': 'boom',
        'exit_code': RUNTIME_ERROR,
    }


def test_plugin_runtime_payload_builder_builds_health_payload() -> None:
    """
    校验插件运行时负载构建器生成健康检查负载。

    :return: None
    """
    health_result = SimpleNamespace(
        plugin_id='demo',
        ok=True,
        status='healthy',
        message='ok',
        checker='health:check',
        duration_ms=12,
        details={'ready': True},
        error=None,
    )

    payload = PluginRuntimePayloadBuilder.build_health_payload(health_result)

    assert payload == {
        'pluginId': 'demo',
        'ok': True,
        'status': 'healthy',
        'message': 'ok',
        'checker': 'health:check',
        'durationMs': 12,
        'details': {'ready': True},
        'error': None,
    }


def test_plugin_runtime_health_payload_model_serializes_payload() -> None:
    """
    校验插件健康检查结构化模型可序列化为现有健康负载契约。

    :return: None
    """
    health_result = SimpleNamespace(
        plugin_id='demo',
        ok=True,
        status='healthy',
        message='ok',
        checker='health:check',
        duration_ms=12,
        details={'ready': True},
        error=None,
    )

    payload = PluginRuntimeHealthPayload(health_result).to_payload()

    assert payload == {
        'pluginId': 'demo',
        'ok': True,
        'status': 'healthy',
        'message': 'ok',
        'checker': 'health:check',
        'durationMs': 12,
        'details': {'ready': True},
        'error': None,
    }


def test_plugin_runtime_payload_builder_builds_health_response_payload() -> None:
    """
    校验插件运行时负载构建器生成健康检查响应负载。

    :return: None
    """
    health_result = SimpleNamespace(
        plugin_id='demo',
        ok=False,
        status='unhealthy',
        message='failed',
        checker='health:check',
        duration_ms=12,
        details={},
        error='boom',
    )

    payload = PluginRuntimePayloadBuilder.build_health_response_payload('demo', health_result)

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['health']['status'] == 'unhealthy'
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_runtime_health_response_payload_model_serializes_payload() -> None:
    """
    校验插件健康检查响应结构化模型可序列化为现有响应负载契约。

    :return: None
    """
    health_result = SimpleNamespace(
        plugin_id='demo',
        ok=False,
        status='unhealthy',
        message='failed',
        checker='health:check',
        duration_ms=12,
        details={},
        error='boom',
    )

    payload = PluginRuntimeHealthResponsePayload('demo', health_result).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == 'failed'
    assert payload['pluginId'] == 'demo'
    assert payload['health']['status'] == 'unhealthy'
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_operation_result_treats_missing_ok_as_failure() -> None:
    """
    校验插件操作结果模型将缺失 ok 的 payload 视为失败。

    :return: None
    """
    payload = {'message': '未知结果'}

    result = PluginOperationResult.from_payload(payload)

    assert result.ok is False
    assert result.message == '未知结果'
    assert result.payload is payload


def test_plugin_operation_result_uses_default_message_when_payload_message_missing() -> None:
    """
    校验插件操作结果模型支持默认消息。

    :return: None
    """
    result = PluginOperationResult.from_payload({'ok': True}, default_message='操作完成')

    assert result.ok is True
    assert result.message == '操作完成'


def test_plugin_runtime_payload_builder_builds_invalid_operation_payload() -> None:
    """
    校验插件运行时负载构建器生成非法操作负载。

    :return: None
    """
    payload = PluginRuntimePayloadBuilder.build_invalid_operation_payload(
        None,
        'purge',
        message='插件计划操作不支持：purge',
    )

    assert payload['ok'] is False
    assert payload['operation'] == 'purge'
    assert 'pluginId' not in payload


def test_plugin_runtime_invalid_operation_payload_model_serializes_payload() -> None:
    """
    校验插件非法操作结构化模型可序列化为现有负载契约。

    :return: None
    """
    payload = PluginRuntimeInvalidOperationPayload(
        None,
        'purge',
        message='插件计划操作不支持：purge',
    ).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件计划操作不支持：purge'
    assert payload['operation'] == 'purge'
    assert payload['exit_code'] == RUNTIME_ERROR
    assert 'pluginId' not in payload


def test_plugin_runtime_payload_builder_builds_batch_item_unsupported_payload() -> None:
    """
    校验插件运行时负载构建器生成批量单项不支持负载。

    :return: None
    """
    payload = PluginRuntimePayloadBuilder.build_batch_item_unsupported_payload('purge', 'demo')

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['message'] == '插件批量操作不支持：purge'


def test_plugin_runtime_batch_item_unsupported_payload_model_serializes_payload() -> None:
    """
    校验插件批量单项不支持结构化模型可序列化为现有负载契约。

    :return: None
    """
    payload = PluginRuntimeBatchItemUnsupportedPayload('purge', 'demo').to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件批量操作不支持：purge'
    assert payload['pluginId'] == 'demo'
    assert payload['exit_code'] == RUNTIME_ERROR


def test_plugin_runtime_payload_builder_builds_failure_state_message() -> None:
    """
    校验插件运行时负载构建器生成失败状态消息。

    :return: None
    """
    payload = {'message': '安装失败', 'error': 'boom'}

    message = PluginRuntimePayloadBuilder.build_failure_state_message(payload, '插件操作失败')

    assert message == '安装失败：boom'


def test_plugin_runtime_payload_builder_builds_precheck_actions(tmp_path: Path) -> None:
    """
    校验插件运行时负载构建器生成预检动作。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    plugin_root = backend_root / 'plugins' / 'demo'
    write_manifest(
        plugin_root,
        """
id: demo
name: Demo
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
frontend:
  menus:
    - name: Demo
      path: demo
      component: plugin/demo/index
      perms: demo:list
permissions:
  - demo:list
""",
    )
    create_controller_dir(plugin_root)
    create_frontend_view(backend_root, 'demo')
    precheck_result = asyncio.run(build_runtime(backend_root).precheck_plugin_operation('demo', 'install'))
    runtime = build_runtime(backend_root)
    discovered_plugin = runtime.context.get_discovered_plugin('demo')
    assert discovered_plugin is not None
    precheck = SimpleNamespace(
        dependency_result=SimpleNamespace(ok=precheck_result['dependencyOk']),
        plugin_dependency_result=SimpleNamespace(ok=precheck_result['pluginDependencyOk']),
        structure_result=SimpleNamespace(ok=precheck_result['structureOk']),
        menu_conflict_result=SimpleNamespace(ok=precheck_result['menuConflictOk']),
    )

    actions = PluginRuntimePayloadBuilder.build_precheck_actions('install', discovered_plugin, precheck)

    action_names = [action['name'] for action in actions]
    assert 'upsert_plugin' in action_names
    assert 'install_menus' in action_names
    assert 'check_dependencies' in action_names


def test_plugin_runtime_payload_builder_builds_upgrade_blocker() -> None:
    """
    校验插件运行时负载构建器生成升级前置阻断负载。

    :return: None
    """
    precheck = SimpleNamespace(
        manifest_result=SimpleNamespace(ok=True),
        operation_payload={'manifestOk': True, 'dependencyOk': True},
    )
    version_state = {
        'installed': False,
        'installedVersion': None,
        'currentVersion': '1.0.0',
        'needsUpgrade': True,
    }

    blocker = PluginRuntimePayloadBuilder.build_upgrade_pre_execution_blocker(
        'demo',
        version_state,
        [{'name': 'check_installed_version'}],
        precheck,
    )

    assert blocker is not None
    assert blocker['ok'] is False
    assert blocker['message'] == '插件尚未安装，升级已中止'
    assert blocker['pluginId'] == 'demo'
    assert blocker['manifestOk'] is True


def test_plugin_runtime_upgrade_blocker_payload_model_serializes_not_installed_payload() -> None:
    """
    校验插件升级阻断结构化模型可序列化为未安装阻断负载契约。

    :return: None
    """
    precheck = SimpleNamespace(
        manifest_result=SimpleNamespace(ok=True),
        operation_payload={'manifestOk': True, 'dependencyOk': True},
    )
    version_state = {
        'installed': False,
        'installedVersion': None,
        'currentVersion': '1.0.0',
        'needsUpgrade': True,
    }

    payload = PluginRuntimeUpgradeBlockerPayload(
        plugin_id='demo',
        message='插件尚未安装，升级已中止',
        version_state=version_state,
        actions=[{'name': 'check_installed_version'}],
        precheck=precheck,
        exit_code=RUNTIME_ERROR,
    ).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件尚未安装，升级已中止'
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is False
    assert payload['installed'] is False
    assert payload['manifestOk'] is True
    assert payload['exit_code'] == RUNTIME_ERROR


def test_plugin_runtime_payload_builder_builds_diagnose_payload() -> None:
    """
    校验插件运行时负载构建器生成诊断包负载。

    :return: None
    """
    info_payload = {'ok': True, 'plugin': {'pluginId': 'demo'}}
    check_payload = {'ok': True, 'checks': []}
    config_payload = {'ok': True, 'configs': []}
    audit_payload = {'available': True, 'items': []}
    menu_plan = PluginRuntimePayloadBuilder.build_empty_menu_plan()

    payload = PluginRuntimePayloadBuilder.build_diagnose_payload(
        'demo',
        info_payload=info_payload,
        check_payload=check_payload,
        menu_plan=menu_plan,
        config_payload=config_payload,
        audit_payload=audit_payload,
    )

    assert payload['ok'] is True
    assert payload['pluginId'] == 'demo'
    assert payload['info'] == {'pluginId': 'demo'}
    assert payload['menuPlan'] == menu_plan


def test_plugin_runtime_diagnose_payload_model_serializes_payload() -> None:
    """
    校验插件诊断结构化模型可序列化为现有负载契约。

    :return: None
    """
    info_payload = {'ok': True, 'plugin': {'pluginId': 'demo'}}
    check_payload = {'ok': True, 'checks': []}
    config_payload = {'ok': True, 'configs': []}
    audit_payload = {'available': True, 'items': []}
    menu_plan = PluginRuntimePayloadBuilder.build_empty_menu_plan()

    payload = PluginRuntimeDiagnosePayload(
        plugin_id='demo',
        info_payload=info_payload,
        check_payload=check_payload,
        menu_plan=menu_plan,
        config_payload=config_payload,
        audit_payload=audit_payload,
    ).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件诊断包生成完成'
    assert payload['pluginId'] == 'demo'
    assert payload['info'] == {'pluginId': 'demo'}
    assert payload['check'] == check_payload
    assert payload['menuPlan'] == menu_plan
    assert payload['config'] == config_payload
    assert payload['audit'] == audit_payload
    assert payload['exit_code'] == SUCCESS


def test_plugin_runtime_payload_builder_builds_diagnose_failure_payload() -> None:
    """
    校验插件运行时负载构建器生成诊断包失败负载。

    :return: None
    """
    info_payload = {'ok': False, 'message': '插件不存在：demo', 'exit_code': RUNTIME_ERROR}

    payload = PluginRuntimePayloadBuilder.build_diagnose_failure_payload('demo', info_payload)

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['info'] == info_payload
    assert payload['exit_code'] == RUNTIME_ERROR


def test_plugin_runtime_diagnose_failure_payload_model_serializes_payload() -> None:
    """
    校验插件诊断失败结构化模型可序列化为现有失败负载契约。

    :return: None
    """
    info_payload = {'ok': False, 'message': '插件不存在：demo', 'exit_code': RUNTIME_ERROR}

    payload = PluginRuntimeDiagnoseFailurePayload('demo', info_payload).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件诊断包生成失败'
    assert payload['pluginId'] == 'demo'
    assert payload['info'] == info_payload
    assert payload['exit_code'] == RUNTIME_ERROR


def test_plugin_runtime_payload_builder_builds_precheck_payload() -> None:
    """
    校验插件运行时负载构建器生成预检负载。

    :return: None
    """
    precheck = SimpleNamespace(
        ok=False,
        operation_payload={'manifestOk': True, 'dependencyOk': False},
        check_payload={'missingDependencies': ['missing-python']},
    )
    purge_plan = PluginPurgePlan(
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

    payload = PluginRuntimePayloadBuilder.build_precheck_payload(
        'demo',
        'purge',
        precheck=precheck,
        version_state={'installed': True, 'needsUpgrade': False},
        actions=[{'name': 'build_purge_plan'}],
        database_error='db unavailable',
        purge_plan=purge_plan,
    )

    assert payload['ok'] is False
    assert payload['databaseAvailable'] is False
    assert payload['databaseError'] == 'db unavailable'
    assert payload['dependencyOk'] is False
    assert payload['precheck'] == {'missingDependencies': ['missing-python']}
    assert payload['plan']['pluginId'] == 'demo'


def test_plugin_runtime_precheck_payload_model_serializes_payload() -> None:
    """
    校验插件预检结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = SimpleNamespace(
        ok=False,
        operation_payload={'manifestOk': True, 'dependencyOk': False},
        check_payload={'missingDependencies': ['missing-python']},
    )
    purge_plan = PluginPurgePlan(
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

    payload = PluginRuntimePrecheckPayload(
        plugin_id='demo',
        operation='purge',
        precheck=precheck,
        version_state={'installed': True, 'needsUpgrade': False},
        actions=[{'name': 'build_purge_plan'}],
        database_error='db unavailable',
        purge_plan=purge_plan,
    ).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件操作预检存在问题'
    assert payload['pluginId'] == 'demo'
    assert payload['operation'] == 'purge'
    assert payload['databaseAvailable'] is False
    assert payload['databaseError'] == 'db unavailable'
    assert payload['dependencyOk'] is False
    assert payload['precheck'] == {'missingDependencies': ['missing-python']}
    assert payload['plan']['pluginId'] == 'demo'
    assert payload['exit_code'] == DEPENDENCY_ERROR
