import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_plugin.controller import plugin_release_controller as controller

DIGEST = 'a' * 64


def test_artifact_http_endpoints_are_get_only_and_require_query_permission() -> None:
    """验证制品 HTTP 接口只接受查询且要求插件查询权限。"""
    routes = controller.plugin_release_controller.routes
    assert {route.path for route in routes} == {
        '/system/plugin/artifacts/list',
        '/system/plugin/release/status',
        '/system/plugin/release/plan',
    }
    for route in routes:
        assert route.methods == {'GET'}
        assert any(
            isinstance(dependency.dependency, CheckUserInterfaceAuth)
            and dependency.dependency.perm == 'system:plugin:query'
            for dependency in route.dependencies
        )


@pytest.mark.asyncio
async def test_readonly_endpoints_forward_filters_and_plan_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证只读接口正确传递过滤条件与目标制品信息。"""
    service = SimpleNamespace(
        catalog=SimpleNamespace(list_artifacts=AsyncMock(return_value={'ok': True, 'artifacts': []})),
        status=AsyncMock(return_value={'ok': True, 'releases': []}),
        plan=AsyncMock(return_value={'ok': True, 'pluginId': 'demo', 'digest': DIGEST}),
    )
    monkeypatch.setattr(controller, 'get_plugin_deployment_service', lambda: service)
    responses = [
        await controller.list_plugin_artifacts('demo'),
        await controller.get_plugin_release_status('demo'),
        await controller.plan_plugin_release('demo', DIGEST),
    ]
    assert all(json.loads(response.body)['success'] for response in responses)
    service.catalog.list_artifacts.assert_awaited_once_with('demo')
    service.status.assert_awaited_once_with('demo')
    service.plan.assert_awaited_once_with('demo', DIGEST)


@pytest.mark.asyncio
async def test_disabled_feature_returns_clear_blocked_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证功能关闭时返回明确的受限响应。"""

    def unavailable() -> None:
        raise ValueError('签名制品发布功能未启用')

    monkeypatch.setattr(controller, 'get_plugin_deployment_service', unavailable)
    body = json.loads((await controller.get_plugin_release_status()).body)
    assert body['success'] is False
    assert body['data']['status'] == 'blocked'
    assert '未启用' in body['msg']


@pytest.mark.asyncio
async def test_unexpected_database_error_does_not_expose_connection_details(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证意外数据库异常不会将连接细节返回客户端。"""

    def unavailable() -> None:
        raise RuntimeError('mysql://secret-user:secret-password@host')

    monkeypatch.setattr(controller, 'get_plugin_deployment_service', unavailable)
    response = await controller.list_plugin_artifacts()
    assert json.loads(response.body)['success'] is False
    assert b'secret-password' not in response.body
