from collections.abc import Callable
from typing import Any

from fastapi.routing import APIRoute

from common.annotation.rate_limit_annotation import ApiRateLimit
from common.constant import ApiNamespace
from module_identity.controller.oauth_audit_controller import oauth_audit_controller
from module_identity.controller.oauth_client_controller import oauth_client_controller
from module_identity.controller.oauth_resource_controller import oauth_resource_controller, oauth_scope_controller
from module_identity.controller.oauth_session_controller import oauth_grant_controller, oauth_session_controller
from module_identity.controller.oidc_key_controller import oidc_key_controller


def _route(router: Any, path: str, method: str) -> APIRoute:
    """查找指定方法的路由。"""
    for route in router.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f'route not found: {method} {path}')


def _rate_limit(endpoint: Callable[..., Any]) -> ApiRateLimit:
    """从 ``functools.wraps`` 生成的限流包装器闭包读取配置。"""
    pending: list[Callable[..., Any]] = [endpoint]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        for cell in getattr(current, '__closure__', None) or ():
            value = cell.cell_contents
            if isinstance(value, ApiRateLimit):
                return value
            if callable(value) and hasattr(value, '__closure__'):
                pending.append(value)
    raise AssertionError(f'route is missing ApiRateLimit: {endpoint!r}')


def test_high_risk_identity_routes_have_independent_rate_limit_namespaces() -> None:
    """高风险写操作必须使用限流预设且不能共享命名空间。"""
    expected = [
        (oauth_client_controller, '/system/oauth/client', 'POST', ApiNamespace.SYSTEM_OAUTH_CLIENT_CREATE),
        (oauth_client_controller, '/system/oauth/client', 'PUT', ApiNamespace.SYSTEM_OAUTH_CLIENT_UPDATE),
        (
            oauth_client_controller,
            '/system/oauth/client/{client_id}/secret',
            'POST',
            ApiNamespace.SYSTEM_OAUTH_CLIENT_SECRET_ROTATE,
        ),
        (oauth_session_controller, '/system/oauth/session/{sids}', 'DELETE', ApiNamespace.SYSTEM_OAUTH_SESSION_REVOKE),
        (oauth_grant_controller, '/system/oauth/grant/{grant_ids}', 'DELETE', ApiNamespace.SYSTEM_OAUTH_GRANT_REVOKE),
        (oidc_key_controller, '/system/oauth/key/rotate', 'POST', ApiNamespace.SYSTEM_OAUTH_KEY_ROTATE),
        (oidc_key_controller, '/system/oauth/key/{kid}/retire', 'PUT', ApiNamespace.SYSTEM_OAUTH_KEY_RETIRE),
        (oauth_audit_controller, '/monitor/oauth/audit/export', 'POST', ApiNamespace.MONITOR_OAUTH_AUDIT_EXPORT),
        (oauth_resource_controller, '/system/oauth/resource', 'PUT', ApiNamespace.SYSTEM_OAUTH_RESOURCE_UPDATE),
        (oauth_scope_controller, '/system/oauth/scope', 'PUT', ApiNamespace.SYSTEM_OAUTH_SCOPE_UPDATE),
    ]
    limits = [_rate_limit(_route(router, path, method).endpoint) for router, path, method, _ in expected]
    assert [limit.namespace for limit in limits] == [namespace for _, _, _, namespace in expected]
    assert len({limit.namespace for limit in limits}) == len(limits)
    assert all(
        limit.preset_name
        in {'USER_COMMON_MUTATION', 'USER_SECURITY_MUTATION', 'USER_DESTRUCTIVE_MUTATION', 'USER_RESOURCE_EXPORT'}
        for limit in limits
    )
