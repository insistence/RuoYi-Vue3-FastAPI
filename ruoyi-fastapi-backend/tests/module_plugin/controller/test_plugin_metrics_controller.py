import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_plugin.controller.plugin_metrics_controller import get_plugin_runtime_metrics, plugin_metrics_controller
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
