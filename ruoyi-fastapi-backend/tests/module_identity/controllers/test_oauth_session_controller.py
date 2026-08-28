"""SSO Session 与 Grant 管理端路由和事务测试。"""

from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.routing import APIRoute

from common.context import RequestContext
from module_admin.service.log_service import LogQueueService
from module_identity.controller.oauth_session_controller import (
    get_oauth_grant,
    oauth_grant_controller,
    oauth_session_controller,
    revoke_oauth_grants,
    revoke_oauth_sessions,
)
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.service.audit_service import AuditService
from module_identity.service.oauth_session_management_service import OAuthSessionManagementService
from module_identity.service.session_service import SsoSessionService


class _Session:
    """记录 Controller 事务边界。"""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _user() -> SimpleNamespace:
    """构造最小管理用户。"""
    return SimpleNamespace(user=SimpleNamespace(user_name='admin', user_id=1, dept=None))


def _request() -> Request:
    """构造含最小 Redis 状态的管理请求。"""
    app = SimpleNamespace(state=SimpleNamespace(redis=SimpleNamespace()))

    async def receive() -> dict[str, object]:
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    return Request(
        {'type': 'http', 'method': 'DELETE', 'path': '/', 'query_string': b'', 'headers': [], 'app': app}, receive
    )


def _route_map(router: object) -> dict[tuple[str, str], APIRoute]:
    """索引路由路径、方法。"""
    return {
        (route.path, method): route
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def test_session_and_grant_routes_have_pre_auth_and_exact_permissions() -> None:
    """Session/Grant 路由必须使用规范权限。"""
    expected = {
        ('/system/oauth/session/list', 'GET'): 'system:oauthSession:list',
        ('/system/oauth/session/{sid}', 'GET'): 'system:oauthSession:list',
        ('/system/oauth/session/{sids}', 'DELETE'): 'system:oauthSession:revoke',
        ('/system/oauth/session/user/{user_id}', 'DELETE'): 'system:oauthSession:revoke',
    }
    routes = _route_map(oauth_session_controller)
    for key, perm in expected.items():
        assert perm in [getattr(dep.call, 'perm', None) for dep in routes[key].dependant.dependencies]
    assert oauth_session_controller.dependencies[0].dependency.__class__.__name__ == 'PreAuth'
    expected_grants = {
        ('/system/oauth/grant/list', 'GET'): 'system:oauthGrant:list',
        ('/system/oauth/grant/{grant_id}', 'GET'): 'system:oauthGrant:list',
        ('/system/oauth/grant/{grant_ids}', 'DELETE'): 'system:oauthGrant:revoke',
    }
    routes = _route_map(oauth_grant_controller)
    for key, perm in expected_grants.items():
        assert perm in [getattr(dep.call, 'perm', None) for dep in routes[key].dependant.dependencies]


@pytest.mark.asyncio
async def test_batch_revoke_is_atomic_and_reason_does_not_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    """批量撤销失败时回滚且不回显内部敏感字段。"""
    db = _Session()

    async def audit(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(AuditService, 'record', audit)

    async def enqueue(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(LogQueueService, 'enqueue_operation_log', enqueue)

    async def revoke(*args: object, **kwargs: object) -> bool:
        if args[2] == 'bad':
            raise ValueError('refresh_token_hash=do-not-leak')
        return True

    monkeypatch.setattr(SsoSessionService, 'revoke', revoke)
    token = RequestContext.set_current_user(_user())
    try:
        response = await revoke_oauth_sessions.__wrapped__(
            'good,bad', SimpleNamespace(reason='管理员操作'), db, _user(), _request()
        )
    finally:
        RequestContext.reset_current_user(token)
    assert b'false' in response.body
    assert b'refresh_token_hash' not in response.body
    assert db.commits == 0 and db.rollbacks == 1

    async def grant_revoke(*args: object, **kwargs: object) -> bool:
        return True

    monkeypatch.setattr(OAuthGrantDao, 'revoke', grant_revoke)
    token = RequestContext.set_current_user(_user())
    try:
        response = await revoke_oauth_grants.__wrapped__.__wrapped__(
            'grant-1', SimpleNamespace(reason='撤销'), db, _user()
        )
    finally:
        RequestContext.reset_current_user(token)
    assert b'true' in response.body
    assert db.commits == 1


@pytest.mark.asyncio
async def test_session_controller_injects_redis_without_passing_request_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session 管理 Controller 向 Service 传入精确 Redis 依赖，而非 FastAPI Request。"""
    db = _Session()
    request = _request()
    captured: dict[str, object] = {}

    async def revoke_sessions(*args: object, **kwargs: object) -> int:
        captured['args'] = args
        captured['kwargs'] = kwargs
        return 1

    monkeypatch.setattr(OAuthSessionManagementService, 'revoke_sessions', revoke_sessions)

    async def enqueue_operation_log(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(LogQueueService, 'enqueue_operation_log', enqueue_operation_log)
    token = RequestContext.set_current_user(_user())
    try:
        response = await revoke_oauth_sessions.__wrapped__(
            'sid-1', SimpleNamespace(reason='管理员操作'), db, _user(), request
        )
    finally:
        RequestContext.reset_current_user(token)
    assert b'true' in response.body
    assert captured['args'][1] is request.app.state.redis
    assert not isinstance(captured['args'][1], Request)


@pytest.mark.asyncio
async def test_grant_detail_never_returns_refresh_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grant 详情只返回安全 DTO。"""
    row = SimpleNamespace(
        grant_id='g1',
        user_id=1,
        subject_id='s1',
        client_pk=2,
        granted_scopes=['openid'],
        granted_resources=[],
        status='active',
        consented_at=None,
        expires_at=None,
        refresh_token_hash='must-not-return',
    )

    async def get_grant(*args: object, **kwargs: object) -> object:
        return row

    async def execute(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(all=list, scalars=lambda: SimpleNamespace(all=list))

    monkeypatch.setattr(OAuthGrantDao, 'get_by_grant_id', get_grant)

    async def client_id(*args: object, **kwargs: object) -> str:
        return 'client-2'

    monkeypatch.setattr(OAuthClientDao, 'id_for_pk', client_id)
    db = _Session()
    db.execute = execute
    response = await get_oauth_grant('g1', db)
    assert b'refresh_token_hash' not in response.body
