"""OAuth 审计分页与导出脱敏测试。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from module_identity.controller.oauth_audit_controller import (
    list_oauth_audit,
    oauth_audit_controller,
)
from module_identity.dao.oauth_audit_dao import OAuthAuditDao
from module_identity.entity.vo.oauth_session_vo import AuditPageQueryModel


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
