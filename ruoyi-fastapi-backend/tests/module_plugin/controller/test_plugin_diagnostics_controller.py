import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request

from module_plugin.controller.plugin_controller import diagnose_system_plugin


@pytest.mark.asyncio
async def test_diagnose_api_attaches_runtime_without_changing_static_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    reporter = object()
    app.state.plugin_diagnostics_reporter = reporter
    app.state.redis = object()
    app.state.plugin_application_runtime = SimpleNamespace(ready_key='isolated:ready')
    operation = SimpleNamespace(
        diagnose_plugin_with_audit_services=AsyncMock(
            return_value={
                'ok': True,
                'pluginId': 'demo',
                'message': '插件诊断包生成完成',
                'audit': {'available': True},
            }
        )
    )
    read = AsyncMock(return_value={'state': 'unavailable', 'observedTotals': None})
    monkeypatch.setattr('module_plugin.controller.plugin_controller.get_plugin_operation_service', lambda: operation)
    monkeypatch.setattr('plugins.core.runtime.diagnostics_query.read_plugin_runtime_diagnostics', read)
    response = await diagnose_system_plugin(Request({'type': 'http', 'app': app}), object(), 'demo')
    payload = json.loads(response.body)['data']
    assert payload['ok'] is True
    assert payload['runtime'] == {'state': 'unavailable', 'observedTotals': None}
    read.assert_awaited_once_with('demo', reporter=reporter, redis=app.state.redis, ready_key='isolated:ready')


@pytest.mark.asyncio
@pytest.mark.parametrize('complete', [True, False])
async def test_failed_check_remains_visible_but_generation_failure_keeps_error_envelope(
    monkeypatch: pytest.MonkeyPatch, complete: bool
) -> None:
    payload = {'ok': False, 'message': '插件诊断包生成完成，发现问题', 'info': {'pluginId': 'demo'}}
    if complete:
        payload.update(check={'ok': False}, config={}, menuPlan={}, audit={})
    operation = SimpleNamespace(diagnose_plugin_with_audit_services=AsyncMock(return_value=payload))
    monkeypatch.setattr('module_plugin.controller.plugin_controller.get_plugin_operation_service', lambda: operation)
    monkeypatch.setattr(
        'plugins.core.runtime.diagnostics_query.read_plugin_runtime_diagnostics',
        AsyncMock(return_value={'state': 'observed'}),
    )
    response = await diagnose_system_plugin(Request({'type': 'http', 'app': FastAPI()}), object(), 'demo')
    result = json.loads(response.body)
    assert result['code'] == (200 if complete else 601)
    assert result['data']['ok'] is False
    assert result['data']['runtime'] == {'state': 'observed'}
