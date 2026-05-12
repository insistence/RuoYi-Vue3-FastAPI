import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from pytest import MonkeyPatch

BACKEND_DIR = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(BACKEND_DIR))
sys.modules.pop('cli.tui.capabilities', None)
sys.modules.pop('cli.tui.actions', None)
sys.modules.pop('cli.wizard.flows.gen_import', None)
sys.modules.pop('cli', None)

capabilities_module = importlib.import_module('cli.tui.capabilities')
actions_module = importlib.import_module('cli.tui.actions')
action_assembly_module = importlib.import_module('cli.tui.actions.assembly')
action_bootstrap_module = importlib.import_module('cli.tui.actions.bootstrap')
action_execution_module = importlib.import_module('cli.tui.actions.execution')
adapters_module = importlib.import_module('cli.tui.adapters')


def test_capabilities_registry_describes_supported_views() -> None:
    """
    校验 TUI 能力注册表会集中描述页面支持的动作能力。

    :return: None
    """
    cache_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_browser_capabilities('cache')
    gen_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_browser_capabilities('gen')
    app_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_detail_capabilities('app')
    database_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_detail_capabilities('database')
    ops_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_detail_capabilities('ops')
    crypto_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_detail_capabilities('crypto')

    assert [capability.slot for capability in cache_capabilities] == ['global', 'utility']
    assert [capability.kind for capability in cache_capabilities] == ['wizard_entry', 'low_risk_action']
    assert [capability.hint_label for capability in cache_capabilities] == ['清理向导', '执行缓存预热']
    assert [capability.slot for capability in gen_capabilities] == ['primary', 'secondary', 'global', 'utility']
    assert [capability.kind for capability in gen_capabilities] == [
        'wizard_entry',
        'wizard_entry',
        'preview',
        'low_risk_action',
    ]
    assert [capability.hint_label for capability in gen_capabilities] == [
        '导出向导',
        '导入向导',
        '导出预演',
        '同步表结构',
    ]
    assert [capability.slot for capability in app_capabilities] == ['primary', 'global', 'utility']
    assert [capability.kind for capability in app_capabilities] == ['wizard_entry', 'wizard_entry', 'command_hint']
    assert [capability.hint_label for capability in app_capabilities] == ['直接启动', '打开启动向导', '安装补全']
    assert [capability.slot for capability in database_capabilities] == ['global', 'utility']
    assert [capability.kind for capability in database_capabilities] == ['wizard_entry', 'preview']
    assert [capability.hint_label for capability in database_capabilities] == ['打开升级向导', '初始化预演']
    assert [capability.slot for capability in ops_capabilities] == ['primary', 'secondary', 'global']
    assert [capability.kind for capability in ops_capabilities] == [
        'low_risk_action',
        'low_risk_action',
        'wizard_entry',
    ]
    assert [capability.hint_label for capability in ops_capabilities] == [
        '数据库探活',
        'Redis 探活',
        '打开生产巡检向导',
    ]
    assert [capability.slot for capability in crypto_capabilities] == ['primary', 'global']
    assert [capability.kind for capability in crypto_capabilities] == ['wizard_entry', 'preview']
    assert [capability.hint_label for capability in crypto_capabilities] == ['密钥生成', '执行轮换预演']


def test_action_registry_resolves_browser_action_for_job_record() -> None:
    """
    校验任务页会解析出执行一次、暂停/恢复和同步动作。

    :return: None
    """
    record = adapters_module.BrowserRecordSnapshot(
        key='job:101',
        title='同步任务',
        status='warn',
        summary='暂停 · Cron 0/30 * * * * ?',
        metadata_lines=[],
        detail_sections=[],
    )

    primary_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='jobs',
        slot='primary',
        record=record,
        env='dev',
    )
    secondary_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='jobs',
        slot='secondary',
        record=record,
        env='dev',
    )
    global_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='jobs',
        slot='global',
        record=record,
        env='dev',
    )

    assert primary_action is not None
    assert primary_action.command_args == ('job', 'run-once', '101')
    assert secondary_action is not None
    assert secondary_action.command_args == ('job', 'resume', '101')
    assert global_action is not None
    assert global_action.command_args == ('job', 'sync')


def test_action_registry_resolves_browser_action_for_cache_and_gen_entries() -> None:
    """
    校验缓存页和代码生成页会解析出外部向导动作。

    :return: None
    """
    cache_record = adapters_module.BrowserRecordSnapshot(
        key='cache:sys_config',
        title='sys_config',
        status='ok',
        summary='系统参数缓存',
        metadata_lines=[],
        detail_sections=[],
    )
    gen_record = adapters_module.BrowserRecordSnapshot(
        key='gen:201',
        title='sys_user',
        status='ok',
        summary='生成类 SysUser · 模块 system',
        metadata_lines=[],
        detail_sections=[],
    )

    cache_global_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='cache',
        slot='global',
        record=cache_record,
        env='dev',
    )
    cache_utility_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='cache',
        slot='utility',
        record=cache_record,
        env='dev',
    )
    gen_primary_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='gen',
        slot='primary',
        record=gen_record,
        env='dev',
    )
    gen_secondary_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='gen',
        slot='secondary',
        record=gen_record,
        env='dev',
    )
    gen_utility_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='gen',
        slot='utility',
        record=gen_record,
        env='dev',
    )
    gen_global_action = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='gen',
        slot='global',
        record=gen_record,
        env='dev',
    )

    assert cache_global_action is not None
    assert cache_global_action.execution_mode == 'external'
    assert cache_global_action.command_args == (
        'wizard',
        'cache-clear',
        '--output=text',
        '--default-env=dev',
        '--default-mode=cache-name',
        '--default-cache-name=sys_config',
        '--default-dry-run',
    )
    assert cache_utility_action is not None
    assert cache_utility_action.execution_mode == 'nested_json'
    assert gen_primary_action is not None
    assert gen_primary_action.execution_mode == 'external'
    assert gen_primary_action.command_args == (
        'wizard',
        'gen-export',
        '--output=text',
        '--default-env=dev',
        '--default-table-names=sys_user',
        '--default-mode=zip',
        '--default-dry-run',
    )
    assert gen_primary_action.refresh_view is False
    assert gen_secondary_action is not None
    assert gen_secondary_action.execution_mode == 'external'
    assert gen_secondary_action.command_args == (
        'wizard',
        'gen-import',
        '--output=text',
        '--default-env=dev',
        '--default-table-names=sys_user',
        '--default-dry-run',
    )
    assert gen_secondary_action.refresh_view is False
    assert gen_global_action is not None
    assert gen_global_action.execution_mode == 'nested_json'
    assert gen_global_action.command_args == ('gen', 'export', 'sys_user', '--dry-run', '--mode=zip')
    assert gen_utility_action is not None
    assert gen_utility_action.execution_mode == 'nested_json'
    assert gen_utility_action.command_args == ('gen', 'sync-db', 'sys_user')


def test_action_template_factories_build_expected_job_and_gen_templates() -> None:
    """
    校验领域动作模板工厂会生成符合预期的命令参数。

    :return: None
    """
    job_record = adapters_module.BrowserRecordSnapshot(
        key='job:88',
        title='通知任务',
        status='ok',
        summary='运行中 · Cron 0 0/5 * * * ?',
        metadata_lines=[],
        detail_sections=[],
    )
    gen_record = adapters_module.BrowserRecordSnapshot(
        key='gen:301',
        title='sys_notice',
        status='ok',
        summary='生成类 SysNotice · 模块 system',
        metadata_lines=[],
        detail_sections=[],
    )

    run_once_template = action_bootstrap_module._JOB_ACTION_TEMPLATE_FACTORY.create_run_once_template()
    toggle_template = action_bootstrap_module._JOB_ACTION_TEMPLATE_FACTORY.create_toggle_template()
    export_template = action_bootstrap_module._GEN_ACTION_TEMPLATE_FACTORY.create_export_wizard_template()

    assert run_once_template.command_builder(job_record, 'dev') == ('job', 'run-once', '88')
    assert toggle_template.command_builder(job_record, 'dev') == ('job', 'pause', '88')
    assert toggle_template.label_builder is not None
    assert toggle_template.label_builder(job_record, 'dev') == '暂停任务'
    assert export_template.command_builder(gen_record, 'dev') == (
        'wizard',
        'gen-export',
        '--output=text',
        '--default-env=dev',
        '--default-table-names=sys_notice',
        '--default-mode=zip',
        '--default-dry-run',
    )


def test_action_registry_builder_assembles_expected_slots() -> None:
    """
    校验动作注册表构建器会装配浏览页与详情页动作槽位。

    :return: None
    """
    registry = action_assembly_module.TuiActionRegistryBuilder(
        jobs=action_bootstrap_module._JOB_ACTION_TEMPLATE_FACTORY,
        cache=action_bootstrap_module._CACHE_ACTION_TEMPLATE_FACTORY,
        gen=action_bootstrap_module._GEN_ACTION_TEMPLATE_FACTORY,
        static=action_bootstrap_module._STATIC_ACTION_TEMPLATE_FACTORY,
        spec_factory=action_bootstrap_module._ACTION_SPEC_FACTORY,
    ).build()

    assert sorted(registry.browser_resolvers) == ['cache', 'configs', 'gen', 'jobs']
    assert sorted(registry.detail_resolvers) == ['app', 'crypto', 'database', 'ops']
    assert sorted(registry.browser_resolvers['gen'].slot_templates) == ['global', 'primary', 'secondary', 'utility']
    assert sorted(registry.detail_resolvers['ops'].slot_templates) == ['global', 'primary', 'secondary']


def test_action_registry_resolves_detail_action_for_database_and_ops_wizard_entries() -> None:
    """
    校验详情页会解析出数据库升级和生产巡检向导动作。

    :return: None
    """
    database_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='database',
        slot='global',
        env='dev',
    )
    database_utility_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='database',
        slot='utility',
        env='dev',
    )
    app_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='app',
        slot='global',
        env='dev',
    )
    app_primary_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='app',
        slot='primary',
        env='dev',
    )
    app_utility_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='app',
        slot='utility',
        env='dev',
    )
    ops_primary_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='ops',
        slot='primary',
        env='dev',
    )
    ops_secondary_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='ops',
        slot='secondary',
        env='dev',
    )
    ops_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='ops',
        slot='global',
        env='dev',
    )
    crypto_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='crypto',
        slot='global',
        env='dev',
    )
    crypto_primary_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='crypto',
        slot='primary',
        env='dev',
    )
    unknown_action = actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='dashboard',
        slot='global',
        env='dev',
    )

    assert app_primary_action is not None
    assert app_primary_action.execution_mode == 'external'
    assert app_primary_action.command_args == ('app', 'run', '--env=dev')
    assert app_primary_action.refresh_view is False
    assert app_action is not None
    assert app_action.execution_mode == 'external'
    assert app_action.command_args == ('wizard', 'app-run')
    assert app_action.refresh_view is False
    assert app_utility_action is not None
    assert app_utility_action.execution_mode == 'external'
    assert app_utility_action.command_args == ('completion', 'install', '--activate')
    assert app_utility_action.refresh_view is False
    assert database_action is not None
    assert database_action.execution_mode == 'external'
    assert database_action.command_args == (
        'wizard',
        'db-upgrade',
        '--output=text',
        '--default-env=dev',
        '--default-revision=head',
        '--default-dry-run',
    )
    assert database_utility_action is not None
    assert database_utility_action.execution_mode == 'nested_json'
    assert database_utility_action.command_args == ('db', 'init', '--dry-run')
    assert ops_primary_action is not None
    assert ops_primary_action.execution_mode == 'nested_json'
    assert ops_primary_action.command_args == ('ops', 'ping-db')
    assert ops_secondary_action is not None
    assert ops_secondary_action.execution_mode == 'nested_json'
    assert ops_secondary_action.command_args == ('ops', 'ping-redis')
    assert ops_action is not None
    assert ops_action.execution_mode == 'external'
    assert ops_action.command_args == (
        'wizard',
        'prod-check',
        '--output=text',
        '--default-env=dev',
        '--default-include-config',
    )
    assert crypto_primary_action is not None
    assert crypto_primary_action.execution_mode == 'external'
    assert crypto_primary_action.command_args == ('crypto', 'keygen', '--env=dev', '--output=text')
    assert crypto_primary_action.refresh_view is False
    assert crypto_action is not None
    assert crypto_action.execution_mode == 'nested_json'
    assert crypto_action.command_args == ('crypto', 'rotate', '--dry-run')
    assert unknown_action is None


def test_action_execution_service_execute_appends_env_output_and_yes(monkeypatch: MonkeyPatch) -> None:
    """
    校验 TUI 动作执行时会复用 CLI JSON 输出并自动附带确认参数。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    calls: list[tuple[str, ...]] = []

    def _fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        assert parse_json is True
        calls.append(arguments)
        return SimpleNamespace(payload={'ok': True, 'message': '参数缓存刷新成功'})

    monkeypatch.setattr(action_execution_module.NESTED_CLI_SUPPORT, 'run', _fake_run_nested_cli_command)
    spec = actions_module.TuiActionSpec(
        action_id='config-sync-cache',
        label='刷新参数缓存',
        command_args=('config', 'sync-cache'),
        preview_title='刷新参数缓存',
        preview_lines=['line a'],
    )

    result = actions_module.TUI_ACTION_EXECUTION_SERVICE.execute(spec, 'dev')

    assert result.ok is True
    assert calls == [('config', 'sync-cache', '--env=dev', '--output=json', '--yes')]


def test_action_execution_service_execute_skips_yes_for_readonly_action(monkeypatch: MonkeyPatch) -> None:
    """
    校验只读动作执行时不会错误追加 `--yes`。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    calls: list[tuple[str, ...]] = []

    def _fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        assert parse_json is True
        calls.append(arguments)
        return SimpleNamespace(payload={'ok': True, 'message': '数据库连接成功'})

    monkeypatch.setattr(action_execution_module.NESTED_CLI_SUPPORT, 'run', _fake_run_nested_cli_command)
    spec = actions_module.TuiActionSpec(
        action_id='ops-ping-db',
        label='数据库探活',
        command_args=('ops', 'ping-db'),
        preview_title='数据库探活',
        preview_lines=['line a'],
        append_yes=False,
    )

    result = actions_module.TUI_ACTION_EXECUTION_SERVICE.execute(spec, 'dev')

    assert result.ok is True
    assert calls == [('ops', 'ping-db', '--env=dev', '--output=json')]


def test_action_execution_service_execute_external_uses_live_nested_command(monkeypatch: MonkeyPatch) -> None:
    """
    校验外部交互动作会通过 live nested CLI helper 执行。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    calls: list[tuple[str, ...]] = []

    def _fake_run_nested_cli_command_live(*arguments: str) -> SimpleNamespace:
        calls.append(arguments)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(action_execution_module.NESTED_CLI_SUPPORT, 'run_live', _fake_run_nested_cli_command_live)
    spec = actions_module.TuiActionSpec(
        action_id='wizard-cache-clear',
        label='打开缓存清理向导',
        command_args=('wizard', 'cache-clear', '--output=text'),
        preview_title='打开缓存清理向导',
        preview_lines=['line a'],
        execution_mode='external',
    )

    result = actions_module.TUI_ACTION_EXECUTION_SERVICE.execute_external(spec)

    assert result.ok is True
    assert result.message == '外部交互命令已执行完成'
    assert calls == [('wizard', 'cache-clear', '--output=text')]


def test_action_presentation_service_build_browser_action_hint_matches_supported_views() -> None:
    """
    校验浏览页动作提示会按页面输出不同文案。

    :return: None
    """
    assert '[X]' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('jobs')
    assert '[Y]' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('configs')
    assert '[W]' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('cache')
    assert '[Y] 清理向导' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('cache')
    assert '[X] 导出向导' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('gen')
    assert '[Z] 导入向导' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('gen')
    assert '[Y] 导出预演' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('gen')
    assert '[W] 同步表结构' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('gen')
    assert '失败聚合' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('jobs')
    assert '浏览键' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('jobs')


def test_action_presentation_service_build_detail_action_hint_matches_supported_views() -> None:
    """
    校验详情页动作提示会按页面输出不同文案。

    :return: None
    """
    assert '[X] 直接启动' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('app')
    assert '[Y] 打开启动向导' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('app')
    assert '[W] 安装补全' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('app')
    assert '[Y] 打开升级向导' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('database')
    assert '[X] 数据库探活' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('ops')
    assert '[Z] Redis 探活' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('ops')
    assert '[Y] 打开生产巡检向导' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('ops')
    assert '[X] 密钥生成' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('crypto')
    assert '[Y] 执行轮换预演' in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('crypto')
    assert (
        '环境映射、应用配置、启动前检查、补全诊断和路由状态，再决定是安装补全、直接启动应用还是进入启动向导'
        in actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('app')
    )


def test_action_execution_service_build_result_lines_surfaces_common_payload_fields() -> None:
    """
    校验动作结果详情会提取常见结果字段。

    :return: None
    """
    spec = actions_module.TuiActionSpec(
        action_id='job-run-once',
        label='执行一次任务',
        command_args=('job', 'run-once', '1'),
        preview_title='执行一次任务',
        preview_lines=['line a'],
    )
    result = actions_module.TuiActionResult(
        spec=spec,
        payload={
            'ok': True,
            'message': '执行完成',
            'serviceMessage': '调度器已触发',
            'hint': '可继续刷新页面确认状态',
            'jobId': 1,
        },
    )

    lines = actions_module.TUI_ACTION_EXECUTION_SERVICE.build_result_lines(result)

    assert any('结果: 成功' in line for line in lines)
    assert any('服务反馈: 调度器已触发' in line for line in lines)
    assert any('摘要: 执行完成' in line for line in lines)
    assert any('建议: 可继续刷新页面确认状态' in line for line in lines)
    assert any('任务 ID: 1' in line for line in lines)


def test_action_execution_service_build_result_lines_surfaces_external_exit_code() -> None:
    """
    校验外部交互动作结果会展示退出码。

    :return: None
    """
    spec = actions_module.TuiActionSpec(
        action_id='wizard-gen-export',
        label='打开导出向导',
        command_args=('wizard', 'gen-export', '--output=text'),
        preview_title='打开导出向导',
        preview_lines=['line a'],
        execution_mode='external',
    )
    result = actions_module.TuiActionResult(
        spec=spec,
        external_exit_code=1,
        external_message='外部交互命令执行失败，退出码 1',
    )

    lines = actions_module.TUI_ACTION_EXECUTION_SERVICE.build_result_lines(result)

    assert any('结果: 失败' in line for line in lines)
    assert any('退出码: 1' in line for line in lines)
