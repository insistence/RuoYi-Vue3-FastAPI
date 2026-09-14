"""OAuth Client 管理端 Controller 路由、权限和事务测试。"""

from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.routing import APIRoute
from starlette.responses import Response

from common.context import RequestContext
from module_admin.service.log_service import LogQueueService
from module_identity.controller.oauth_client_controller import (
    add_system_oauth_client,
    delete_system_oauth_clients,
    get_system_oauth_client_list,
    oauth_client_controller,
    rotate_system_oauth_client_secret,
)
from module_identity.entity.vo.oauth_client_vo import ClientSecretResponseModel, SecretRotationModel
from module_identity.service.oauth_management_service import (
    OAuthClientManagementError,
    OAuthClientManagementService,
)
from module_identity.service.runtime_service import OidcRuntimeService


class _FakeSession:
    """记录 Controller 的 commit/rollback 边界。"""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _request_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """为日志装饰器提供当前用户上下文。"""
    monkeypatch.setattr(RequestContext, 'get_current_user', staticmethod(_user))

    async def enqueue_operation_log(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(LogQueueService, 'enqueue_operation_log', enqueue_operation_log)


def _user() -> SimpleNamespace:
    """构造最小当前用户对象。"""
    return SimpleNamespace(user=SimpleNamespace(user_name='admin', dept=SimpleNamespace(dept_name='测试部门')))


def _request() -> Request:
    """构造带可观察 CORS 快照的请求。"""
    app = SimpleNamespace(state=SimpleNamespace(oidc_registered_cors_origins=('https://old.example',)))

    async def receive() -> dict[str, object]:
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    return Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/',
            'headers': [],
            'query_string': b'',
            'app': app,
        },
        receive=receive,
    )


def _routes() -> list[APIRoute]:
    """返回 Client Router 的 HTTP 路由。"""
    return [route for route in oauth_client_controller.routes if isinstance(route, APIRoute)]


def test_client_router_paths_methods_permissions_and_pre_auth() -> None:
    """Client 路由必须完整覆盖规范路径并逐端点声明权限。"""
    expected = {
        ('/system/oauth/client/list', 'GET'): 'system:oauthClient:list',
        ('/system/oauth/client/{client_id}', 'GET'): 'system:oauthClient:query',
        ('/system/oauth/client', 'POST'): 'system:oauthClient:add',
        ('/system/oauth/client', 'PUT'): 'system:oauthClient:edit',
        ('/system/oauth/client/{client_ids}', 'DELETE'): 'system:oauthClient:remove',
        ('/system/oauth/client/changeStatus', 'PUT'): 'system:oauthClient:edit',
        ('/system/oauth/client/{client_id}/secret', 'POST'): 'system:oauthClient:rotateSecret',
        ('/system/oauth/client/{client_id}/secret/{secret_id}', 'DELETE'): 'system:oauthClient:rotateSecret',
        ('/system/oauth/client/{client_id}/uri', 'POST'): 'system:oauthClient:edit',
        ('/system/oauth/client/{client_id}/uri/{uri_id}', 'DELETE'): 'system:oauthClient:edit',
    }
    routes = {(route.path, method): route for route in _routes() for method in route.methods}
    assert set(routes) == set(expected)
    for key, permission in expected.items():
        dependency_calls = [getattr(item.call, 'perm', None) for item in routes[key].dependant.dependencies]
        assert permission in dependency_calls
    assert oauth_client_controller.dependencies
    assert oauth_client_controller.dependencies[0].dependency.__class__.__name__ == 'PreAuth'


@pytest.mark.asyncio
async def test_client_create_commits_and_secret_is_only_in_rotation_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功写操作提交事务，轮换响应含明文而普通错误不包含敏感字段。"""
    session = _FakeSession()
    payload = SimpleNamespace()

    async def fake_create(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(model_dump=lambda **_: {'clientId': 'cli_test'})

    monkeypatch.setattr(OAuthClientManagementService, 'create_client', fake_create)
    response = await add_system_oauth_client(_request(), payload, session, _user())
    assert isinstance(response, Response)
    assert session.commits == 0 and session.rollbacks == 0

    secret = ClientSecretResponseModel(
        client_id='cli_test',
        secret_id='secret-1',
        client_secret='cs1.one-time-secret',
        secret_hint='...cret',
        not_before='2026-01-01T00:00:00Z',
    )

    async def fake_rotate(*args: object, **kwargs: object) -> ClientSecretResponseModel:
        return secret

    monkeypatch.setattr(OAuthClientManagementService, 'rotate_secret', fake_rotate)
    rotation_response = await rotate_system_oauth_client_secret(
        _request(), 'cli_test', session, _user(), SecretRotationModel()
    )
    assert b'cs1.one-time-secret' in rotation_response.body
    assert session.commits == 0

    async def fake_fail(*args: object, **kwargs: object) -> object:
        raise OAuthClientManagementError('OAuth Client request rejected')

    monkeypatch.setattr(OAuthClientManagementService, 'create_client', fake_fail)
    failed = await add_system_oauth_client(_request(), payload, session, _user())
    assert b'secret_hash' not in failed.body
    assert b'cs1.' not in failed.body
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_client_batch_failure_rolls_back_all_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """批量停用任一项失败时整体回滚，不提前提交。"""
    session = _FakeSession()
    calls: list[str] = []

    async def fake_disable(*args: object, **kwargs: object) -> object:
        client_id = args[1]
        calls.append(client_id)
        if client_id == 'cli_bad':
            raise OAuthClientManagementError('client not found')
        return SimpleNamespace()

    monkeypatch.setattr(OAuthClientManagementService, '_soft_disable', fake_disable)
    response = await delete_system_oauth_clients(_request(), 'cli_good,cli_bad', session, _user())
    assert b'false' in response.body
    assert calls == ['cli_good', 'cli_bad']
    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_cors_snapshot_refresh_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """提交后 CORS 快照刷新失败时清空旧快照，确保失败闭合。"""
    request = _request()

    async def fail_refresh(*args: object, **kwargs: object) -> tuple[str, ...]:
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(OidcRuntimeService, 'refresh_cors_snapshot', fail_refresh)
    await OidcRuntimeService.cors_snapshot_callback(request.scope['app'])()
    assert request.app.state.oidc_registered_cors_origins == ()


@pytest.mark.asyncio
async def test_client_list_uses_real_total_and_actor_failure_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """列表返回服务层全量计数，actor 缺失时稳定返回业务失败。"""
    session = _FakeSession()

    async def fake_rows(*args: object, **kwargs: object) -> list[str]:
        return ['row-1', 'row-2']

    async def fake_count(*args: object, **kwargs: object) -> int:
        return 37

    monkeypatch.setattr(OAuthClientManagementService, 'list_clients', fake_rows)
    monkeypatch.setattr(OAuthClientManagementService, 'count_clients', fake_count)
    response = await get_system_oauth_client_list(SimpleNamespace(), session)
    assert b'"total":37' in response.body
    assert b'"rows":["row-1","row-2"]' in response.body

    failed = await add_system_oauth_client(_request(), SimpleNamespace(), session, SimpleNamespace(user=None))
    assert b'false' in failed.body
    assert b'actor' not in failed.body
    assert session.rollbacks == 0
