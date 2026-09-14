"""OAuth Resource/Scope 管理端 Controller 路由、权限和事务测试。"""

from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.routing import APIRoute
from starlette.responses import Response

from common.context import RequestContext
from module_admin.service.log_service import LogQueueService
from module_identity.controller.oauth_resource_controller import (
    delete_system_oauth_resources,
    delete_system_oauth_scopes,
    get_system_oauth_resource_list,
    get_system_oauth_scope_list,
    oauth_resource_controller,
    oauth_scope_controller,
)
from module_identity.service.oauth_management_service import (
    OAuthClientManagementError,
    OAuthResourceManagementService,
)


class _FakeSession:
    """记录 Controller 提交和回滚次数。"""

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
    """构造管理写请求。"""
    app = SimpleNamespace(state=SimpleNamespace())

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


def _route_map(router: object) -> dict[tuple[str, str], APIRoute]:
    """构造路由路径和方法索引。"""
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    return {(route.path, method): route for route in routes for method in route.methods}


def _assert_routes(router: object, expected: dict[tuple[str, str], str]) -> None:
    """断言路由路径、方法和权限依赖。"""
    routes = _route_map(router)
    assert set(routes) == set(expected)
    for key, permission in expected.items():
        dependency_calls = [getattr(item.call, 'perm', None) for item in routes[key].dependant.dependencies]
        assert permission in dependency_calls
    assert router.dependencies
    assert router.dependencies[0].dependency.__class__.__name__ == 'PreAuth'


def test_resource_and_scope_router_paths_methods_permissions_and_pre_auth() -> None:
    """Resource 与 Scope 路由必须完整覆盖规范并隔离权限前缀。"""
    _assert_routes(
        oauth_resource_controller,
        {
            ('/system/oauth/resource/list', 'GET'): 'system:oauthResource:list',
            ('/system/oauth/resource/{resource_id}', 'GET'): 'system:oauthResource:list',
            ('/system/oauth/resource', 'POST'): 'system:oauthResource:add',
            ('/system/oauth/resource', 'PUT'): 'system:oauthResource:edit',
            ('/system/oauth/resource/{resource_ids}', 'DELETE'): 'system:oauthResource:remove',
            ('/system/oauth/resource/changeStatus', 'PUT'): 'system:oauthResource:edit',
        },
    )
    _assert_routes(
        oauth_scope_controller,
        {
            ('/system/oauth/scope/list', 'GET'): 'system:oauthScope:list',
            ('/system/oauth/scope/{scope_code}', 'GET'): 'system:oauthScope:list',
            ('/system/oauth/scope', 'POST'): 'system:oauthScope:add',
            ('/system/oauth/scope', 'PUT'): 'system:oauthScope:edit',
            ('/system/oauth/scope/{scope_codes}', 'DELETE'): 'system:oauthScope:remove',
            ('/system/oauth/scope/changeStatus', 'PUT'): 'system:oauthScope:edit',
        },
    )


@pytest.mark.asyncio
async def test_resource_batch_failure_rolls_back_without_partial_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resource 批量停用任一项失败时整体回滚。"""
    session = _FakeSession()
    calls: list[str] = []

    async def fake_disable(*args: object, **kwargs: object) -> object:
        resource_id = args[1]
        calls.append(resource_id)
        if resource_id == 'resource-bad':
            raise OAuthClientManagementError('resource not found')
        return SimpleNamespace()

    monkeypatch.setattr(OAuthResourceManagementService, '_soft_disable_resource', fake_disable)
    response = await delete_system_oauth_resources(_request(), 'resource-good,resource-bad', session, _user())
    assert isinstance(response, Response)
    assert b'false' in response.body
    assert calls == ['resource-good', 'resource-bad']
    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_scope_batch_rejects_empty_duplicate_and_invalid_encoding() -> None:
    """Scope 批量路径拒绝空项、重复项和未解析的百分号编码。"""
    session = _FakeSession()
    user = _user()
    for value in ('scope-a,,scope-b', 'scope-a,scope-a', 'scope-a%2Fb'):
        response = await delete_system_oauth_scopes(_request(), value, session, user)
        assert b'false' in response.body
    assert session.commits == 0
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_resource_scope_lists_use_real_total_and_actor_failure_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resource/Scope 列表使用真实全量计数，缺少 actor 时不逃逸异常。"""
    session = _FakeSession()

    async def fake_rows(*args: object, **kwargs: object) -> list[str]:
        return ['row-1', 'row-2']

    async def fake_count(*args: object, **kwargs: object) -> int:
        return 37

    monkeypatch.setattr(OAuthResourceManagementService, 'list_resources', fake_rows)
    monkeypatch.setattr(OAuthResourceManagementService, 'count_resources', fake_count)
    resource_response = await get_system_oauth_resource_list(SimpleNamespace(), session)
    assert b'"total":37' in resource_response.body
    assert b'"rows":["row-1","row-2"]' in resource_response.body

    monkeypatch.setattr(OAuthResourceManagementService, 'list_scopes', fake_rows)
    monkeypatch.setattr(OAuthResourceManagementService, 'count_scopes', fake_count)
    scope_response = await get_system_oauth_scope_list(SimpleNamespace(), session)
    assert b'"total":37' in scope_response.body
    assert b'"rows":["row-1","row-2"]' in scope_response.body

    failed = await delete_system_oauth_resources(_request(), 'resource-a', session, SimpleNamespace(user=None))
    assert b'false' in failed.body
    assert b'actor' not in failed.body
    assert session.rollbacks == 0
