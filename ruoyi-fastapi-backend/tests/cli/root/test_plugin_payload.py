from cli.groups.plugin.payload import PluginCommandPayloadAdapter
from cli.groups.plugin.presenter import PluginCommandPresenter


def test_plugin_cli_payload_normalizes_database_enabled_enum() -> None:
    """校验 CLI 不再泄漏数据库 enabled 的 0/1 枚举。"""
    payload = {
        'ok': True,
        'plugin': {
            'pluginId': 'demo',
            'enabled': False,
            'status': 'error',
            'database': {
                'available': True,
                'enabled': '0',
                'status': 'error',
            },
        },
    }

    adapted_payload = PluginCommandPayloadAdapter.adapt(payload)

    assert adapted_payload['plugin']['runtimeEnabled'] is False
    assert 'enabled' not in adapted_payload['plugin']
    assert adapted_payload['plugin']['database']['configuredEnabled'] is True
    assert 'enabled' not in adapted_payload['plugin']['database']
    assert payload['plugin']['database']['enabled'] == '0'


def test_plugin_cli_payload_distinguishes_lifecycle_target_and_actions() -> None:
    """校验生命周期目标状态与动作执行状态不再共用 enabled。"""
    payload = {
        'ok': False,
        'pluginId': 'demo',
        'operation': 'enable',
        'enabled': True,
        'dryRun': False,
        'actions': [
            {
                'name': 'update_plugin_enabled',
                'label': '更新插件启停状态',
                'enabled': True,
            }
        ],
    }

    adapted_payload = PluginCommandPayloadAdapter.adapt(payload)

    assert adapted_payload['targetEnabled'] is True
    assert 'enabled' not in adapted_payload
    assert adapted_payload['actions'][0]['willRun'] is True
    assert 'enabled' not in adapted_payload['actions'][0]


def test_plugin_cli_payload_removes_irrelevant_purge_enabled_state() -> None:
    """校验物理清理结果不再输出无意义的 enabled 字段。"""
    payload = {
        'ok': False,
        'pluginId': 'demo',
        'operation': 'purge',
        'enabled': False,
        'dryRun': False,
    }

    adapted_payload = PluginCommandPayloadAdapter.adapt(payload)

    assert 'enabled' not in adapted_payload
    assert 'targetEnabled' not in adapted_payload


def test_plugin_cli_payload_normalizes_purge_and_batch_plan_items() -> None:
    """校验清理动作开关和批量计划插件状态使用各自语义字段。"""
    purge_payload = {
        'plan': {
            'items': [
                {
                    'name': 'remove_menus',
                    'label': '删除菜单',
                    'enabled': True,
                    'destructive': True,
                }
            ]
        }
    }
    batch_payload = {
        'plan': {
            'items': [
                {
                    'pluginId': 'demo',
                    'ready': True,
                    'enabled': '1',
                }
            ]
        }
    }

    adapted_purge_payload = PluginCommandPayloadAdapter.adapt(purge_payload)
    adapted_batch_payload = PluginCommandPayloadAdapter.adapt(batch_payload)

    assert adapted_purge_payload['plan']['items'][0]['willRun'] is True
    assert 'enabled' not in adapted_purge_payload['plan']['items'][0]
    assert adapted_batch_payload['plan']['items'][0]['configuredEnabled'] is False
    assert 'enabled' not in adapted_batch_payload['plan']['items'][0]


def test_plugin_cli_payload_names_manifest_job_default_state() -> None:
    """校验 manifest 任务启用配置明确标识为默认值。"""
    payload = {
        'plugin': {
            'pluginId': 'demo',
            'status': 'installed',
            'enabled': True,
            'backend': {
                'jobs': [
                    {
                        'id': 'cleanup',
                        'enabled': True,
                    }
                ]
            },
        }
    }

    adapted_payload = PluginCommandPayloadAdapter.adapt(payload)

    assert adapted_payload['plugin']['runtimeEnabled'] is True
    assert adapted_payload['plugin']['backend']['jobs'][0]['defaultEnabled'] is True
    assert 'enabled' not in adapted_payload['plugin']['backend']['jobs'][0]


def test_plugin_cli_payload_normalizes_persisted_plugin_model_state() -> None:
    """校验安装结果中的数据库插件模型不会被误标为运行时启用态。"""
    payload = {
        'ok': True,
        'pluginId': 'demo',
        'operation': 'install',
        'dryRun': False,
        'plugin': {
            'pluginId': 'demo',
            'status': 'installed',
            'enabled': '0',
        },
    }

    adapted_payload = PluginCommandPayloadAdapter.adapt(payload)

    assert adapted_payload['plugin']['configuredEnabled'] is True
    assert 'runtimeEnabled' not in adapted_payload['plugin']
    assert 'enabled' not in adapted_payload['plugin']


def test_plugin_cli_presenter_uses_explicit_enabled_labels() -> None:
    """校验 CLI 文本使用 runtime/configured/target/will_run 明确区分启停语义。"""
    presenter = PluginCommandPresenter()
    list_text = presenter.build_list_text(
        {
            'ok': True,
            'count': 1,
            'databaseAvailable': True,
            'databaseError': None,
            'plugins': [
                {
                    'pluginId': 'demo',
                    'name': 'Demo',
                    'version': '1.0.0',
                    'runtimeEnabled': True,
                    'status': 'installed',
                }
            ],
        }
    )
    info_text = presenter.build_info_text(
        {
            'ok': True,
            'plugin': {
                'pluginId': 'demo',
                'runtimeEnabled': False,
                'database': {
                    'available': True,
                    'installed': True,
                    'configuredEnabled': True,
                },
            },
        }
    )
    enabled_text = presenter.build_enabled_text(
        {
            'message': '启用失败',
            'pluginId': 'demo',
            'env': 'dev',
            'operation': 'enable',
            'targetEnabled': True,
            'dryRun': False,
            'actions': [
                {
                    'name': 'update_plugin_enabled',
                    'label': '更新插件启停状态',
                    'willRun': True,
                }
            ],
        }
    )

    assert 'database_available: true' in list_text
    assert 'runtime_enabled: true' in list_text
    assert 'runtime_enabled: false' in info_text
    assert 'configured_enabled: true' in info_text
    assert 'target_enabled: true' in enabled_text
    assert 'will_run: true' in enabled_text
