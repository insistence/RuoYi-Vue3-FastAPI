"""OAuth 审计分页与导出脱敏测试。"""

from datetime import datetime, timezone
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from common.annotation.rate_limit_annotation import ApiRateLimit
from common.context import RequestContext
from module_admin.service.log_service import LogQueueService
from module_identity.controller.oauth_audit_controller import (
    list_oauth_audit,
    oauth_audit_controller,
)
from module_identity.dao.oauth_audit_dao import OAuthAuditDao
from module_identity.entity.vo.oauth_session_vo import AuditPageQueryModel
from module_identity.service.audit_service import AuditService


class _Session:
    """提供只读回滚边界。"""

    def __init__(self) -> None:
        self.rollbacks = 0

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_audit_routes_use_list_and_export_permissions() -> None:
    """审计路由必须具备 PreAuth 和精确权限。"""
    routes = {
        (route.path, method): route
        for route in oauth_audit_controller.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert 'monitor:oauthAudit:list' in [
        getattr(dep.call, 'perm', None) for dep in routes[('/monitor/oauth/audit/list', 'GET')].dependant.dependencies
    ]
    assert 'monitor:oauthAudit:export' in [
        getattr(dep.call, 'perm', None)
        for dep in routes[('/monitor/oauth/audit/export', 'POST')].dependant.dependencies
    ]
    assert oauth_audit_controller.dependencies[0].dependency.__class__.__name__ == 'PreAuth'


def test_audit_export_uses_form_content_type() -> None:
    """导出接口必须接受前端 proxy.download 发送的表单，而非 JSON body。"""
    app = FastAPI()
    app.include_router(oauth_audit_controller)
    content = app.openapi()['paths']['/monitor/oauth/audit/export']['post']['requestBody']['content']
    assert 'application/x-www-form-urlencoded' in content
    assert 'application/json' not in content


@pytest.mark.asyncio
async def test_audit_list_uses_real_total_and_safe_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    """审计列表返回服务层真实总数且不含 detail。"""
    rows = [
        SimpleNamespace(
            event_id=1,
            event_type='token_failed',
            result='failure',
            risk_level='high',
            client_id='c1',
            resource_id=None,
            user_id=1,
            subject_id='s',
            sid='sid',
            failure_code='invalid_client',
            create_time=datetime.now(timezone.utc),
            detail={'access_token': 'redact'},
        ),
        SimpleNamespace(
            event_id=2,
            event_type='login',
            result='success',
            risk_level='normal',
            client_id='c1',
            resource_id=None,
            user_id=1,
            subject_id='s',
            sid='sid',
            failure_code=None,
            create_time=datetime.now(timezone.utc),
            detail={'password': 'redact'},
        ),
    ]

    async def list_page(*args: object, **kwargs: object) -> list[object]:
        return rows

    async def count(*args: object, **kwargs: object) -> int:
        return 37

    monkeypatch.setattr(OAuthAuditDao, 'list_admin_page', list_page)
    monkeypatch.setattr(OAuthAuditDao, 'count_admin', count)
    response = await list_oauth_audit(AuditPageQueryModel(page_num=1, page_size=2), _Session())
    assert b'"total":37' in response.body
    assert b'"detail"' not in response.body
    assert b'access_token' not in response.body


@pytest.mark.asyncio
async def test_audit_export_runs_rate_limit_and_operation_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 审计导出经过完整装饰器链，保留文件响应并记录操作日志。"""

    query = AuditPageQueryModel()
    db = _Session()
    user = SimpleNamespace(user=SimpleNamespace(user_id=1, user_name='admin', dept=None))
    route = next(
        route
        for route in oauth_audit_controller.routes
        if isinstance(route, APIRoute) and route.path == '/monitor/oauth/audit/export'
    )
    app = FastAPI()
    app.state.redis = SimpleNamespace()
    app.include_router(oauth_audit_controller)
    for dependency in route.dependant.dependencies:
        if dependency.name == 'query_db':
            app.dependency_overrides[dependency.call] = lambda: db
        else:
            app.dependency_overrides[dependency.call] = lambda: None
    rate_limit = AsyncMock(return_value={'allowed': True, 'remaining': 9, 'reset_at': 60})
    export = AsyncMock(return_value=b'audit-workbook')
    operation_log = AsyncMock()
    monkeypatch.setattr(ApiRateLimit, '_acquire_rate_limit', rate_limit)
    monkeypatch.setattr(AuditService, 'export_admin', export)
    monkeypatch.setattr(LogQueueService, 'enqueue_operation_log', operation_log)
    token = RequestContext.set_current_user(user)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
            response = await client.post(
                '/monitor/oauth/audit/export', data=query.model_dump(by_alias=True, exclude_none=True)
            )
    finally:
        RequestContext.reset_current_user(token)
    assert response.status_code == HTTPStatus.OK
    assert response.headers['content-disposition'] == 'attachment; filename="oauth-audit.xlsx"'
    assert response.content == b'audit-workbook'
    export.assert_awaited_once_with(db, query)
    rate_limit.assert_awaited_once()
    operation_log.assert_awaited_once()
    logged_request, logged_operation, _ = operation_log.call_args.args
    assert isinstance(logged_request, Request)
    assert logged_request is rate_limit.call_args.args[-1]
    assert logged_operation.oper_url == '/monitor/oauth/audit/export'
