"""OIDC UserInfo Controller 测试。"""

from types import SimpleNamespace
from typing import Any

import pytest

from module_admin.entity.do.user_do import SysUser
from module_identity.controller import token_controller as controller
from module_identity.dependencies import AccessTokenContext
from module_identity.service import token_protocol_service as service

_OK = 200
_NOT_FOUND = 404
_UNAUTHORIZED = 401


def _request(redis: object | None = None) -> SimpleNamespace:
    """构造 UserInfo 请求替身。"""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis or object())))


class _ActiveRedis:
    """模拟未命中撤销列表的 Redis。"""

    async def exists(self, key: str) -> bool:
        return False


@pytest.mark.asyncio
async def test_userinfo_returns_only_minimal_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """UserInfo 按当前数据库 Scope、角色和部门生成最小 Claims。"""
    monkeypatch.setattr(controller.OidcConfig, 'oidc_enabled', True)
    client = SimpleNamespace(client_pk=1, client_id='client-1', status='0')
    user = SysUser(user_id=2, user_name='alice', nick_name='数据库用户', status='0', del_flag='0')
    subject = SimpleNamespace(subject_id='subject-1', user_id=2, auth_version=3)
    session = SimpleNamespace(user_id=2, subject_id='subject-1', auth_version=3)
    definitions = [
        SimpleNamespace(scope_pk=1, scope_code='openid', claims=['sub'], status='0'),
        SimpleNamespace(scope_pk=2, scope_code='profile', claims=['name'], status='0'),
        SimpleNamespace(scope_pk=3, scope_code='roles', claims=['roles'], status='0'),
        SimpleNamespace(scope_pk=4, scope_code='dept', claims=['dept_id', 'dept_name'], status='0'),
    ]
    bindings = [
        SimpleNamespace(
            scope_pk=1,
            claim_filter={
                'claims': ['sub', 'name', 'roles', 'dept_id', 'dept_name'],
                'allowed_role_keys': ['database-role'],
            },
        ),
        SimpleNamespace(scope_pk=2, claim_filter=['name']),
        SimpleNamespace(
            scope_pk=3,
            claim_filter={
                'claims': ['sub', 'name', 'roles', 'dept_id', 'dept_name'],
                'allowed_role_keys': ['database-role'],
            },
        ),
        SimpleNamespace(
            scope_pk=4,
            claim_filter={
                'claims': ['sub', 'name', 'roles', 'dept_id', 'dept_name'],
                'allowed_role_keys': ['database-role'],
            },
        ),
    ]

    monkeypatch.setattr(service.OAuthClientDao, 'get_by_client_id', lambda *args, **kwargs: _async(client))
    monkeypatch.setattr(service.IdentitySubjectDao, 'get_by_subject_id', lambda *args, **kwargs: _async(subject))
    monkeypatch.setattr(service.IdentityUserDao, 'get_user', lambda *args, **kwargs: _async(user))
    monkeypatch.setattr(service.SsoSessionDao, 'get_active', lambda *args, **kwargs: _async(session))
    monkeypatch.setattr(
        service.OAuthClientDao,
        'list_scope_bindings',
        lambda *args, **kwargs: _async(bindings),
    )
    monkeypatch.setattr(
        service.OAuthClientDao,
        'list_scope_definitions',
        lambda *args, **kwargs: _async(definitions),
    )
    monkeypatch.setattr(
        service.ClaimService,
        'load_roles_and_department',
        lambda *args, **kwargs: _async((['database-role'], SimpleNamespace(dept_id=7, dept_name='数据库部门'))),
    )
    context = AccessTokenContext(
        'token',
        {
            'sub': 'subject-1',
            'scope': 'openid profile roles dept',
            'name': '伪造名称',
            'roles': ['伪造角色'],
            'user_id': 123,
            'sid': 'sid-1',
            'client_id': 'client-1',
            'jti': 'jti-1',
            'ver': 3,
            'exp': 1,
        },
    )
    response = await controller.userinfo(_request(_ActiveRedis()), context, SimpleNamespace())
    assert response.status_code == _OK
    assert b'"sub":"subject-1"' in response.body
    assert '数据库用户'.encode() in response.body
    assert '数据库部门'.encode() in response.body
    assert b'database-role' in response.body
    assert '伪造名称'.encode() not in response.body
    assert '伪造角色'.encode() not in response.body
    assert b'user_id' not in response.body
    assert b'"sid"' not in response.body


@pytest.mark.asyncio
async def test_userinfo_uses_current_database_claims_not_token_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token 中篡改 name/roles 不得污染按当前数据库策略重建的 UserInfo。"""
    monkeypatch.setattr(controller.OidcConfig, 'oidc_enabled', True)
    client = SimpleNamespace(client_pk=1, status='0')
    user = SimpleNamespace(user_id=2, user_name='alice', nick_name='当前用户', status='0', del_flag='0')
    subject = SimpleNamespace(subject_id='subject-1', user_id=2, auth_version=3)
    session = SimpleNamespace(user_id=2, subject_id='subject-1', auth_version=3)
    definitions = [
        SimpleNamespace(scope_pk=1, scope_code='openid', claims=['sub'], status='0'),
        SimpleNamespace(scope_pk=2, scope_code='roles', claims=['roles'], status='0'),
    ]
    bindings = [
        SimpleNamespace(
            scope_pk=1,
            claim_filter={
                'claims': ['sub', 'name', 'roles', 'dept_id', 'dept_name'],
                'allowed_role_keys': ['database-role'],
            },
        ),
        SimpleNamespace(
            scope_pk=2,
            claim_filter={
                'claims': ['sub', 'name', 'roles', 'dept_id', 'dept_name'],
                'allowed_role_keys': ['database-role'],
            },
        ),
    ]
    monkeypatch.setattr(service.OAuthClientDao, 'get_by_client_id', lambda *args, **kwargs: _async(client))
    monkeypatch.setattr(service.IdentitySubjectDao, 'get_by_subject_id', lambda *args, **kwargs: _async(subject))
    monkeypatch.setattr(service.IdentityUserDao, 'get_user', lambda *args, **kwargs: _async(user))
    monkeypatch.setattr(service.SsoSessionDao, 'get_active', lambda *args, **kwargs: _async(session))
    monkeypatch.setattr(service.OAuthClientDao, 'list_scope_bindings', lambda *args, **kwargs: _async(bindings))
    monkeypatch.setattr(service.OAuthClientDao, 'list_scope_definitions', lambda *args, **kwargs: _async(definitions))
    monkeypatch.setattr(
        service.ClaimService,
        'load_roles_and_department',
        lambda *args, **kwargs: _async((['database-role'], None)),
    )
    context = AccessTokenContext(
        'token',
        {
            'sub': 'subject-1',
            'scope': 'openid roles',
            'name': 'Forged Name',
            'roles': ['forged-role'],
            'client_id': 'client-1',
            'sid': 'sid-1',
            'jti': 'jti-1',
            'ver': 3,
        },
    )
    response = await controller.userinfo(_request(_ActiveRedis()), context, SimpleNamespace())
    assert b'subject-1' in response.body
    assert b'Forged Name' not in response.body
    assert b'database-role' in response.body
    assert b'forged-role' not in response.body


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['revoked', 'version', 'session', 'redis'])
async def test_userinfo_live_state_failures_are_bearer_401(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    """撤销 JTI、版本/Session 失效和 Redis 异常均统一返回 401。"""
    monkeypatch.setattr(controller.OidcConfig, 'oidc_enabled', True)
    client = SimpleNamespace(client_id='client-1', status='0')
    subject = SimpleNamespace(subject_id='subject-1', user_id=2, auth_version=3)
    user = SysUser(user_id=2, user_name='alice', nick_name='Alice', status='0', del_flag='0')
    monkeypatch.setattr(service.OAuthClientDao, 'get_by_client_id', lambda *args, **kwargs: _async(client))
    monkeypatch.setattr(service.IdentitySubjectDao, 'get_by_subject_id', lambda *args, **kwargs: _async(subject))
    monkeypatch.setattr(service.IdentityUserDao, 'get_user', lambda *args, **kwargs: _async(user))

    class _Redis:
        async def exists(self, key: str) -> bool:
            if failure == 'redis':
                raise RuntimeError('redis unavailable')
            return failure == 'revoked'

    claims = {
        'sub': 'subject-1',
        'scope': 'openid',
        'sid': 'sid-1',
        'client_id': 'client-1',
        'jti': 'jti-1',
        'ver': 4 if failure == 'version' else 3,
    }
    monkeypatch.setattr(
        service.SsoSessionDao,
        'get_active',
        lambda *args, **kwargs: _async(
            None if failure == 'session' else SimpleNamespace(user_id=2, subject_id='subject-1', auth_version=3)
        ),
    )
    response = await controller.userinfo(_request(_Redis()), AccessTokenContext('token', claims), SimpleNamespace())
    assert response.status_code == _UNAUTHORIZED
    assert response.headers['www-authenticate'] == 'Bearer error="invalid_token"'
    assert b'redis unavailable' not in response.body


@pytest.mark.asyncio
async def test_userinfo_disabled_is_local_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """OIDC 关闭时 UserInfo 返回本地 404，不进入重定向流程。"""
    monkeypatch.setattr(controller.OidcConfig, 'oidc_enabled', False)
    response = await controller.userinfo(_request(), SimpleNamespace(), SimpleNamespace())
    assert response.status_code == _NOT_FOUND
    assert b'not_found' in response.body


def _async(value: object) -> Any:
    """构造异步测试结果。"""

    async def result() -> object:
        return value

    return result()
