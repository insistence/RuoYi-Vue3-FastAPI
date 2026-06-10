# ruff: noqa: F403, F405

from tests.plugin_runtime_helpers import *


def test_plugin_lifecycle_payload_builder_builds_install_dry_run_payload() -> None:
    """
    校验插件生命周期负载构建器生成安装预演负载。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()

    payload = PluginLifecyclePayloadBuilder.build_install_dry_run_payload(
        'demo',
        [{'name': 'upsert_plugin'}],
        precheck,
    )

    assert payload['ok'] is True
    assert payload['message'] == '插件安装演练完成，未执行实际写入'
    assert payload['dryRun'] is True
    assert payload['actions'][0]['name'] == 'upsert_plugin'


def test_plugin_install_dry_run_payload_model_serializes_payload() -> None:
    """
    校验插件安装预演结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()

    payload = PluginInstallDryRunPayload(
        plugin_id='demo',
        actions=[{'name': 'upsert_plugin'}],
        precheck=precheck,
    ).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件安装演练完成，未执行实际写入'
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is True
    assert payload['actions'][0]['name'] == 'upsert_plugin'
    assert payload['dependencyOk'] is True


def test_plugin_lifecycle_payload_builder_builds_precheck_blocker_payload() -> None:
    """
    校验插件生命周期负载构建器生成预检阻断负载。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck(ok=False)

    payload = PluginLifecyclePayloadBuilder.build_precheck_blocker_payload(
        'demo',
        message='插件结构检查失败，安装已中止',
        actions=[{'name': 'check_structure'}],
        precheck=precheck,
        extra_payload={'structureOk': False},
    )

    assert payload['ok'] is False
    assert payload['structureOk'] is False
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_lifecycle_precheck_blocker_payload_model_serializes_payload() -> None:
    """
    校验插件生命周期预检阻断结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck(ok=False)

    payload = PluginLifecyclePrecheckBlockerPayload(
        plugin_id='demo',
        message='插件结构检查失败，安装已中止',
        actions=[{'name': 'check_structure'}],
        precheck=precheck,
        extra_payload={'structureOk': False},
    ).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件结构检查失败，安装已中止'
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is False
    assert payload['structureOk'] is False
    assert payload['actions'][0]['name'] == 'check_structure'
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_lifecycle_payload_builder_builds_first_precheck_blocker_payload() -> None:
    """
    校验插件生命周期负载构建器按统一优先级生成首个预检阻断负载。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck(ok=False)

    payload = PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
        'demo',
        operation='install',
        actions=[{'name': 'check_manifest'}],
        precheck=precheck,
    )

    assert payload is not None
    assert payload['ok'] is False
    assert payload['message'] == '插件 manifest 检查失败，安装已中止'
    assert payload['manifestOk'] is False
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_lifecycle_payload_builder_skips_first_precheck_blocker_when_ok() -> None:
    """
    校验插件生命周期负载构建器在预检通过时不生成阻断负载。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()

    payload = PluginLifecyclePayloadBuilder.build_first_precheck_blocker_payload(
        'demo',
        operation='enable',
        actions=[{'name': 'update_plugin_enabled'}],
        precheck=precheck,
        extra_payload={'enabled': True},
    )

    assert payload is None


def test_plugin_lifecycle_payload_builder_builds_installed_menu_conflict_payload() -> None:
    """
    校验插件生命周期负载构建器生成已安装菜单冲突负载。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()
    installed_conflict = SimpleNamespace(
        kind='perms',
        plugin_id='demo',
        conflict_plugin_id='other',
        value='demo:list',
        message='权限已存在',
    )

    payload = PluginLifecyclePayloadBuilder.build_installed_menu_conflict_payload(
        'demo',
        message='插件菜单与已安装菜单存在冲突，安装已中止',
        actions=[{'name': 'install_menus'}],
        precheck=precheck,
        installed_menu_conflicts=[installed_conflict],
    )

    assert payload['ok'] is False
    assert payload['menuConflictOk'] is False
    assert payload['menuConflicts'][0]['value'] == 'demo:list'


def test_plugin_lifecycle_menu_conflict_payload_model_serializes_payload() -> None:
    """
    校验插件生命周期菜单冲突结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()
    installed_conflict = SimpleNamespace(
        kind='perms',
        plugin_id='demo',
        conflict_plugin_id='other',
        value='demo:list',
        message='权限已存在',
    )

    payload = PluginLifecycleMenuConflictPayload(
        plugin_id='demo',
        message='插件菜单与已安装菜单存在冲突，安装已中止',
        actions=[{'name': 'install_menus'}],
        precheck=precheck,
        installed_menu_conflicts=[installed_conflict],
    ).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件菜单与已安装菜单存在冲突，安装已中止'
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is False
    assert payload['menuConflictOk'] is False
    assert payload['menuConflicts'][0]['value'] == 'demo:list'
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_lifecycle_payload_builder_builds_upgrade_latest_payload() -> None:
    """
    校验插件生命周期负载构建器生成无需升级负载。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()

    payload = PluginLifecyclePayloadBuilder.build_upgrade_latest_payload(
        'demo',
        {'installed': True, 'installedVersion': '1.0.0', 'currentVersion': '1.0.0', 'needsUpgrade': False},
        precheck,
    )

    assert payload['ok'] is True
    assert payload['message'] == '插件已是最新版本，无需升级'
    assert payload['actions'] == []
    assert payload['needsUpgrade'] is False


def test_plugin_lifecycle_upgrade_latest_payload_model_serializes_payload() -> None:
    """
    校验插件生命周期无需升级结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()

    payload = PluginLifecycleUpgradeLatestPayload(
        plugin_id='demo',
        version_state={
            'installed': True,
            'installedVersion': '1.0.0',
            'currentVersion': '1.0.0',
            'needsUpgrade': False,
        },
        precheck=precheck,
    ).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件已是最新版本，无需升级'
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is False
    assert payload['actions'] == []
    assert payload['needsUpgrade'] is False


def test_plugin_lifecycle_operation_dry_run_payload_model_serializes_payload() -> None:
    """
    校验插件生命周期操作预演结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()

    payload = PluginLifecycleOperationDryRunPayload(
        plugin_id='demo',
        operation='upgrade',
        message='插件升级演练完成，未执行实际写入',
        actions=[{'name': 'upgrade_plugin'}],
        precheck=precheck,
        extra_payload={'needsUpgrade': True},
    ).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件升级演练完成，未执行实际写入'
    assert payload['pluginId'] == 'demo'
    assert payload['operation'] == 'upgrade'
    assert payload['dryRun'] is True
    assert payload['needsUpgrade'] is True
    assert payload['actions'][0]['name'] == 'upgrade_plugin'
    assert payload['precheck']['manifestOk'] is True
    assert payload['precheck']['dependencyOk'] is True
    assert payload['exit_code'] == SUCCESS


def test_plugin_lifecycle_payload_builder_builds_success_payload() -> None:
    """
    校验插件生命周期负载构建器生成成功负载。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()
    plugin = SimpleNamespace(model_dump=lambda by_alias=True: {'pluginId': 'demo'})
    config = SimpleNamespace(model_dump=lambda by_alias=True: {'key': 'api_key'})
    migration_result = SimpleNamespace(migration_path='migrations/001_init.sql')
    seed_result = SimpleNamespace(seed_path='seeds/001_seed.sql')
    hook_result = SimpleNamespace(hook='hooks:on_install')

    payload = PluginLifecyclePayloadBuilder.build_success_payload(
        'demo',
        message='插件安装完成',
        actions=[{'name': 'upsert_plugin'}],
        precheck=precheck,
        plugin=plugin,
        installed_configs=[config],
        migration_results=[migration_result],
        seed_results=[seed_result],
        hook_result=hook_result,
    )

    assert payload['ok'] is True
    assert payload['plugin'] == {'pluginId': 'demo'}
    assert payload['configs'] == [{'key': 'api_key'}]
    assert payload['migrations'][0]['migration_path'] == 'migrations/001_init.sql'
    assert payload['hooks'][0]['hook'] == 'hooks:on_install'


def test_plugin_lifecycle_success_payload_model_serializes_payload() -> None:
    """
    校验插件生命周期成功结构化模型可序列化为现有负载契约。

    :return: None
    """
    precheck = build_fake_lifecycle_precheck()
    plugin = SimpleNamespace(model_dump=lambda by_alias=True: {'pluginId': 'demo'})
    config = SimpleNamespace(model_dump=lambda by_alias=True: {'key': 'api_key'})
    migration_result = SimpleNamespace(migration_path='migrations/001_init.sql')
    seed_result = SimpleNamespace(seed_path='seeds/001_seed.sql')
    hook_result = SimpleNamespace(hook='hooks:on_install')

    payload = PluginLifecycleSuccessPayload(
        plugin_id='demo',
        message='插件安装完成',
        actions=[{'name': 'upsert_plugin'}],
        precheck=precheck,
        plugin=plugin,
        installed_configs=[config],
        migration_results=[migration_result],
        seed_results=[seed_result],
        hook_result=hook_result,
        extra_payload={'dependencyInstall': {'ok': True}},
    ).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件安装完成'
    assert payload['pluginId'] == 'demo'
    assert payload['dryRun'] is False
    assert payload['dependencyInstall'] == {'ok': True}
    assert payload['plugin'] == {'pluginId': 'demo'}
    assert payload['configs'] == [{'key': 'api_key'}]
    assert payload['migrations'][0]['migration_path'] == 'migrations/001_init.sql'
    assert payload['seeds'][0]['seed_path'] == 'seeds/001_seed.sql'
    assert payload['hooks'][0]['hook'] == 'hooks:on_install'


def test_plugin_enable_payload_builder_builds_dependency_payload() -> None:
    """
    校验插件启停负载构建器生成依赖检查负载。

    :return: None
    """
    result = PluginDependencyCheckResult(
        plugin_id='demo',
        items=[
            PluginDependencyCheckItem(
                plugin_id='demo',
                dependency_id='base',
                required_version='>=1.0.0',
                installed_version=None,
                status='missing',
                message='缺少依赖插件',
            )
        ],
    )

    payload = PluginEnablePayloadBuilder.build_dependency_payload(result)

    assert payload['pluginDependencyOk'] is False
    assert payload['pluginDependencyErrors'][0]['dependencyId'] == 'base'
    assert payload['pluginDependencies'][0]['level'] == 'error'


def test_plugin_enable_dependency_payload_model_serializes_payload() -> None:
    """
    校验插件启停依赖检查结构化模型可序列化为现有负载契约。

    :return: None
    """
    result = PluginDependencyCheckResult(
        plugin_id='demo',
        items=[
            PluginDependencyCheckItem(
                plugin_id='demo',
                dependency_id='base',
                required_version='>=1.0.0',
                installed_version=None,
                status='missing',
                message='缺少依赖插件',
            )
        ],
    )

    payload = PluginEnableDependencyPayload(result).to_payload()

    assert payload['pluginDependencyOk'] is False
    assert payload['pluginDependencyErrors'][0]['dependencyId'] == 'base'
    assert payload['pluginDependencies'][0]['level'] == 'error'


def test_plugin_enable_payload_builder_builds_dry_run_payload() -> None:
    """
    校验插件启停负载构建器生成预演负载。

    :return: None
    """
    payload = PluginEnablePayloadBuilder.build_dry_run_payload(
        'demo',
        operation='enable',
        enabled=True,
        dependency_payload={'pluginDependencyOk': True},
    )

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['operation'] == 'enable'
    assert payload['actions'][0]['name'] == 'check_plugin_dependencies'


def test_plugin_enable_state_payload_model_serializes_dry_run_payload() -> None:
    """
    校验插件启停结构化模型可序列化为现有预演负载契约。

    :return: None
    """
    payload = PluginEnableStatePayload(
        plugin_id='demo',
        operation='enable',
        enabled=True,
        dry_run=True,
        ok=True,
        message='插件启停演练完成，未执行实际写入',
        dependency_payload={'pluginDependencyOk': True},
    ).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件启停演练完成，未执行实际写入'
    assert payload['pluginId'] == 'demo'
    assert payload['operation'] == 'enable'
    assert payload['enabled'] is True
    assert payload['dryRun'] is True
    assert payload['pluginDependencyOk'] is True
    assert payload['actions'][0]['name'] == 'check_plugin_dependencies'


def test_plugin_enable_payload_builder_builds_blocker_payload() -> None:
    """
    校验插件启停负载构建器生成依赖阻断负载。

    :return: None
    """
    payload = PluginEnablePayloadBuilder.build_dependency_blocker_payload(
        'demo',
        operation='enable',
        enabled=True,
        dependency_payload={'pluginDependencyOk': False, 'pluginDependencyErrors': []},
    )

    assert payload['ok'] is False
    assert payload['message'] == '插件间依赖检查失败，启用已中止'
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_enable_dependency_blocker_payload_model_serializes_payload() -> None:
    """
    校验插件启停依赖阻断结构化模型可序列化为现有负载契约。

    :return: None
    """
    payload = PluginEnableDependencyBlockerPayload(
        plugin_id='demo',
        operation='enable',
        enabled=True,
        dependency_payload={'pluginDependencyOk': False, 'pluginDependencyErrors': []},
    ).to_payload()

    assert payload['ok'] is False
    assert payload['message'] == '插件间依赖检查失败，启用已中止'
    assert payload['pluginId'] == 'demo'
    assert payload['operation'] == 'enable'
    assert payload['enabled'] is True
    assert payload['dryRun'] is False
    assert payload['exit_code'] == DEPENDENCY_ERROR


def test_plugin_enable_update_failure_payload_model_serializes_payload() -> None:
    """
    校验插件启停写入失败结构化模型可序列化为现有负载契约。

    :return: None
    """
    payload = PluginEnableUpdateFailurePayload(
        plugin_id='demo',
        operation='disable',
        enabled=False,
        message='插件状态写入失败',
    ).to_payload()

    assert payload == {
        'ok': False,
        'message': '插件状态写入失败',
        'pluginId': 'demo',
        'operation': 'disable',
        'enabled': False,
        'dryRun': False,
        'exit_code': RUNTIME_ERROR,
    }


def test_plugin_enable_payload_builder_builds_success_and_uninstall_payload() -> None:
    """
    校验插件启停负载构建器生成成功和卸载负载。

    :return: None
    """
    enabled_payload = PluginEnablePayloadBuilder.build_success_payload(
        'demo',
        operation='disable',
        enabled=False,
        message='插件已停用',
        dependency_payload={},
    )
    uninstall_payload = PluginEnablePayloadBuilder.build_uninstall_payload(enabled_payload, dry_run=False)

    assert enabled_payload['ok'] is True
    assert enabled_payload['actions'][0]['name'] == 'update_plugin_enabled'
    assert uninstall_payload['operation'] == 'uninstall'
    assert uninstall_payload['safeMode'] is True
    assert uninstall_payload['removesSource'] is False


def test_plugin_safe_uninstall_payload_model_serializes_payload() -> None:
    """
    校验插件安全卸载结构化模型可序列化为现有负载契约。

    :return: None
    """
    payload = PluginSafeUninstallPayload(
        result={'ok': True, 'message': '插件已停用', 'pluginId': 'demo'},
        dry_run=False,
    ).to_payload()

    assert payload['ok'] is True
    assert payload['message'] == '插件已停用'
    assert payload['operation'] == 'uninstall'
    assert payload['safeMode'] is True
    assert payload['removesSource'] is False
    assert payload['removesMenus'] is True
