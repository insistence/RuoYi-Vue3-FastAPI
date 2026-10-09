import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_plugin.controller.plugin_metrics_controller import (
    get_plugin_config_status,
    get_plugin_runtime_metrics,
    plugin_metrics_controller,
)
from plugins.core.runtime.metrics import PluginRuntimeMetrics
from plugins.core.runtime.metrics_store import PluginMetricsReporter


def test_runtime_metrics_endpoint_is_readonly_and_permission_gated() -> None:
    """运行指标仅通过受插件查询权限保护的 GET 接口公开。"""
    route = plugin_metrics_controller.routes[0]
    assert route.path == '/system/plugin/runtime/metrics'
    assert route.methods == {'GET'}
    assert any(
        isinstance(dependency.dependency, CheckUserInterfaceAuth)
        and dependency.dependency.perm == 'system:plugin:query'
        for dependency in route.dependencies
    )


@pytest.mark.asyncio
async def test_metrics_endpoint_without_explicit_runtime_reports_unsupported() -> None:
    """未加载显式插件时不可用状态不能伪装成全部指标为零。"""
    response = await get_plugin_runtime_metrics(Request({'type': 'http', 'app': FastAPI()}))
    payload = json.loads(response.body)['data']
    assert payload['supported'] is False
    assert payload['scope'] == 'unavailable'


@pytest.mark.asyncio
async def test_metrics_endpoint_forwards_plugin_filter() -> None:
    """接口保留报告器的采样范围并传递插件过滤条件。"""
    app = FastAPI()
    reporter = PluginMetricsReporter(PluginRuntimeMetrics())
    reporter.read = AsyncMock(return_value={'ok': True, 'scope': 'current_worker', 'series': []})
    app.state.plugin_metrics_reporter = reporter
    response = await get_plugin_runtime_metrics(Request({'type': 'http', 'app': app}), 'metric_demo')
    assert json.loads(response.body)['data']['scope'] == 'current_worker'
    reporter.read.assert_awaited_once_with('metric_demo')


@pytest.mark.asyncio
async def test_config_status_is_query_gated_and_never_exposes_config_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """读取敏感配置只用于计算版本，API 与无指标场景均不回显明文。"""
    route = next(route for route in plugin_metrics_controller.routes if route.path.endswith('/config/status'))
    assert route.methods == {'GET'}
    assert any(
        isinstance(dependency.dependency, CheckUserInterfaceAuth)
        and dependency.dependency.perm == 'system:plugin:query'
        for dependency in route.dependencies
    )
    runtime = SimpleNamespace(
        get_plugin_config=AsyncMock(
            return_value={
                'ok': True,
                'configs': [{'key': 'api_key', 'value': 'private-config-secret', 'secret': True}],
            }
        )
    )
    monkeypatch.setattr(
        'module_plugin.controller.plugin_metrics_controller.get_plugin_runtime_service',
        lambda: runtime,
    )
    response = await get_plugin_config_status(Request({'type': 'http', 'app': FastAPI()}), 'config_demo')
    data = json.loads(response.body)['data']
    assert data['state'] == 'unobserved' and data['scope'] == 'unavailable'
    assert 'private-config-secret' not in response.body.decode() and 'api_key' not in response.body.decode()
    runtime.get_plugin_config.assert_awaited_once_with('config_demo', reveal_secret=True)
    runtime.get_plugin_config.return_value = {'ok': False, 'message': 'private exception value'}
    failure = await get_plugin_config_status(Request({'type': 'http', 'app': FastAPI()}), 'config_demo')
    assert 'private exception value' not in failure.body.decode()
