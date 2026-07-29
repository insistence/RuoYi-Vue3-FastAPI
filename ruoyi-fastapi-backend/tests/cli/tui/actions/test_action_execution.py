import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pytest import MonkeyPatch

BACKEND_DIR = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(BACKEND_DIR))
sys.modules.pop('cli.tui.capabilities', None)
sys.modules.pop('cli.tui.actions', None)
sys.modules.pop('cli', None)

capabilities_module = importlib.import_module('cli.tui.capabilities')
actions_module = importlib.import_module('cli.tui.actions')
action_bootstrap_module = importlib.import_module('cli.tui.actions.bootstrap')
action_execution_module = importlib.import_module('cli.tui.actions.execution')
adapters_module = importlib.import_module('cli.tui.adapters')


def build_record(key: str, title: str, *, status: str = 'ok') -> object:
    """构建动作解析测试使用的浏览记录。"""
    return adapters_module.BrowserRecordSnapshot(
        key=key,
        title=title,
        status=status,
        summary='测试摘要',
        metadata_lines=[],
        detail_sections=[],
    )


def test_capabilities_registry_only_exposes_in_process_actions() -> None:
    cache_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_browser_capabilities('cache')
    gen_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_browser_capabilities('gen')
    app_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_detail_capabilities('app')
    database_capabilities = capabilities_module.TUI_CAPABILITY_REGISTRY.get_detail_capabilities('database')

    assert [(item.slot, item.kind) for item in cache_capabilities] == [
        ('global', 'preview'),
        ('utility', 'low_risk_action'),
    ]
    assert [(item.slot, item.kind) for item in gen_capabilities] == [
        ('global', 'preview'),
        ('utility', 'low_risk_action'),
    ]
    assert [(item.slot, item.kind) for item in app_capabilities] == [
        ('primary', 'preview'),
        ('utility', 'command_hint'),
    ]
    assert [(item.slot, item.kind) for item in database_capabilities] == [
        ('global', 'preview'),
        ('utility', 'preview'),
    ]


def test_action_registry_builds_runtime_parameters_without_cli_arguments() -> None:
    job_record = build_record('job:101', '同步任务', status='warn')
    cache_record = build_record('cache:sys_config', 'sys_config')
    gen_record = build_record('gen:201', 'sys_user')

    run_once = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='jobs', slot='primary', record=job_record, env='dev'
    )
    resume = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='jobs', slot='secondary', record=job_record, env='dev'
    )
    clear_preview = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='cache', slot='global', record=cache_record, env='dev'
    )
    export_preview = actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='gen', slot='global', record=gen_record, env='dev'
    )

    assert run_once is not None
    assert run_once.parameters == {'job_id': 101}
    assert resume is not None
    assert resume.action_id == 'job-resume'
    assert resume.parameters == {'job_id': 101}
    assert clear_preview is not None
    assert clear_preview.action_id == 'cache-clear-dry-run'
    assert clear_preview.parameters == {'cache_name': 'sys_config', 'dry_run': True}
    assert export_preview is not None
    assert export_preview.parameters == {'table_name': 'sys_user', 'mode': 'zip', 'dry_run': True}
    assert all('进程内运行时动作' in '\n'.join(item.preview_lines) for item in (run_once, clear_preview))


def test_action_registry_prunes_external_wizard_slots() -> None:
    gen_record = build_record('gen:201', 'sys_user')

    assert (
        actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
            view_key='gen', slot='primary', record=gen_record, env='dev'
        )
        is None
    )
    assert (
        actions_module.TUI_ACTION_REGISTRY.resolve_browser_action(
            view_key='gen', slot='secondary', record=gen_record, env='dev'
        )
        is None
    )
    assert actions_module.TUI_ACTION_REGISTRY.resolve_detail_action(view_key='app', slot='global', env='dev') is None


def test_action_templates_build_typed_parameters() -> None:
    job_record = build_record('job:88', '通知任务')
    gen_record = build_record('gen:301', 'sys_notice')

    run_once = action_bootstrap_module._JOB_ACTION_TEMPLATE_FACTORY.create_run_once_template()
    toggle = action_bootstrap_module._JOB_ACTION_TEMPLATE_FACTORY.create_toggle_template()
    export = action_bootstrap_module._GEN_ACTION_TEMPLATE_FACTORY.create_export_dry_run_template()

    assert run_once.parameter_builder(job_record, 'dev') == {'job_id': 88}
    assert toggle.parameter_builder(job_record, 'dev') == {'job_id': 88}
    assert toggle.label_builder is not None
    assert toggle.label_builder(job_record, 'dev') == '暂停任务'
    assert export.parameter_builder(gen_record, 'dev') == {
        'table_name': 'sys_notice',
        'mode': 'zip',
        'dry_run': True,
    }


@pytest.mark.asyncio
async def test_action_execution_service_calls_runtime_directly() -> None:
    service = action_execution_module.TuiActionExecutionService()
    service.config_runtime.sync_config_cache = AsyncMock(
        return_value={'ok': True, 'message': '参数缓存刷新成功', 'count': 3}
    )
    spec = actions_module.TuiActionSpec(
        action_id='config-sync-cache',
        label='刷新参数缓存',
        parameters={},
        preview_title='刷新参数缓存',
        preview_lines=['line a'],
    )

    result = await service.execute(spec, 'dev')

    assert result.ok is True
    assert result.payload == {
        'ok': True,
        'message': '参数缓存刷新成功',
        'count': 3,
        'env': 'dev',
    }
    service.config_runtime.sync_config_cache.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_action_execution_service_dispatches_selected_job_id() -> None:
    service = action_execution_module.TuiActionExecutionService()
    service.job_runtime.run_job_once = AsyncMock(return_value={'ok': True, 'message': '任务执行完成', 'jobId': 42})
    spec = actions_module.TuiActionSpec(
        action_id='job-run-once',
        label='执行一次任务',
        parameters={'job_id': 42},
        preview_title='执行一次任务',
        preview_lines=[],
    )

    result = await service.execute(spec, 'dev')

    assert result.ok is True
    service.job_runtime.run_job_once.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_action_execution_service_rejects_unknown_action_without_fallback() -> None:
    service = action_execution_module.TuiActionExecutionService()
    service.operations_runtime.sync_jobs = AsyncMock(return_value={'ok': True})
    spec = actions_module.TuiActionSpec(
        action_id='job-unknown',
        label='未知动作',
        parameters={'job_id': 42},
        preview_title='未知动作',
        preview_lines=[],
    )

    result = await service.execute(spec, 'dev')

    assert result.ok is False
    assert result.payload is not None
    assert result.payload['message'] == '不支持的 TUI 动作：job-unknown'
    service.operations_runtime.sync_jobs.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_execution_service_times_out_and_cancels(
    monkeypatch: MonkeyPatch,
) -> None:
    service = action_execution_module.TuiActionExecutionService()
    cancelled = asyncio.Event()

    async def slow_sync() -> dict[str, object]:
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
        return {'ok': True}

    service.config_runtime.sync_config_cache = slow_sync
    monkeypatch.setattr(action_execution_module, 'TUI_ACTION_TIMEOUT_SECONDS', 0.01)
    spec = actions_module.TuiActionSpec(
        action_id='config-sync-cache',
        label='刷新参数缓存',
        parameters={},
        preview_title='刷新参数缓存',
        preview_lines=[],
    )

    result = await service.execute(spec, 'dev')

    assert result.ok is False
    assert result.payload is not None
    assert '超时' in str(result.payload.get('message'))
    assert cancelled.is_set()


def test_action_result_lines_surface_common_payload_fields() -> None:
    spec = actions_module.TuiActionSpec(
        action_id='job-run-once',
        label='执行一次任务',
        parameters={'job_id': 1},
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


def test_action_hints_match_reduced_action_surface() -> None:
    browser_hint = actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_browser_action_hint('gen')
    detail_hint = actions_module.TUI_ACTION_PRESENTATION_SERVICE.build_detail_action_hint('app')

    assert '[Y] 导出预演' in browser_hint
    assert '[W] 同步表结构' in browser_hint
    assert '[X]' not in browser_hint
    assert '[Z]' not in browser_hint
    assert '[X] 启动前检查' in detail_hint
    assert '[W] 安装补全' in detail_hint
    assert '[Y]' not in detail_hint
