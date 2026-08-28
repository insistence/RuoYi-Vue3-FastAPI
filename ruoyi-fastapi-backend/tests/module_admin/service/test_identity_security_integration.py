"""现有用户、角色服务接入 OIDC 安全事件的回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_admin.dao.role_dao import RoleDao
from module_admin.dao.user_dao import UserDao
from module_admin.entity.vo.role_vo import AddRoleModel
from module_admin.entity.vo.user_vo import AddUserModel, ResetUserModel
from module_admin.service.role_service import RoleService
from module_admin.service.user_service import UserService
from module_identity.service.identity_service import IdentitySecurityEventService, IdentitySubjectService


@pytest.mark.asyncio
async def test_add_user_creates_subject_before_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """新增用户必须在同一会话提交前建立稳定 Subject。"""
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(UserService, 'check_user_name_unique_services', AsyncMock(return_value=True))
    monkeypatch.setattr(UserDao, 'add_user_dao', AsyncMock(return_value=SimpleNamespace(user_id=7)))
    create_subject = AsyncMock()
    monkeypatch.setattr(IdentitySubjectService, 'create_for_new_user', create_subject)
    payload = AddUserModel(userName='new-user', nickName='New User', createBy='admin')

    await UserService.add_user_services(db, payload)

    create_subject.assert_awaited_once_with(db, user_id=7, create_by='admin')
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_security_failure_rolls_back_user_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """密码安全失效失败时不得提交已写入的新密码。"""
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(UserDao, 'edit_user_dao', AsyncMock())
    monkeypatch.setattr('module_admin.service.user_service.PwdUtil.get_password_hash', lambda value: f'hash:{value}')
    security_event = AsyncMock(side_effect=RuntimeError('security state unavailable'))
    monkeypatch.setattr(IdentitySecurityEventService, 'handle_user_event', security_event)
    payload = ResetUserModel(userId=8, password='New123!', updateBy='admin')

    with pytest.raises(RuntimeError, match='security state unavailable'):
        await UserService.reset_user_services(db, payload)

    security_event.assert_awaited_once_with(db, 8, 'password_changed', actor='admin')
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabling_role_invalidates_members_before_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """角色停用必须在角色更新事务中处理受影响用户。"""
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(
        RoleService,
        'role_detail_services',
        AsyncMock(return_value=AddRoleModel(roleId=5, roleName='普通角色', roleKey='common', roleSort=1, status='0')),
    )
    monkeypatch.setattr(RoleDao, 'edit_role_dao', AsyncMock())
    security_event = AsyncMock()
    monkeypatch.setattr(IdentitySecurityEventService, 'handle_role_event', security_event)
    payload = AddRoleModel(
        roleId=5,
        roleName='普通角色',
        roleKey='common',
        roleSort=1,
        status='1',
        type='status',
        updateBy='admin',
    )

    await RoleService.edit_role_services(db, payload)

    security_event.assert_awaited_once_with(db, 5, 'role_disabled', actor='admin')
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_changing_role_key_invalidates_external_role_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """角色标识变化必须让成员的旧外部角色声明失效。"""
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(
        RoleService,
        'role_detail_services',
        AsyncMock(return_value=AddRoleModel(roleId=5, roleName='普通角色', roleKey='reader', roleSort=1, status='0')),
    )
    monkeypatch.setattr(RoleDao, 'edit_role_dao', AsyncMock())
    monkeypatch.setattr(RoleDao, 'delete_role_menu_dao', AsyncMock())
    monkeypatch.setattr(RoleDao, 'add_role_menu_dao', AsyncMock())
    monkeypatch.setattr(RoleDao, 'list_role_menu_ids', AsyncMock(return_value=[]))
    monkeypatch.setattr(RoleService, 'check_role_name_unique_services', AsyncMock(return_value=True))
    monkeypatch.setattr(RoleService, 'check_role_key_unique_services', AsyncMock(return_value=True))
    security_event = AsyncMock()
    monkeypatch.setattr(IdentitySecurityEventService, 'handle_role_event', security_event)
    payload = AddRoleModel(
        roleId=5,
        roleName='普通角色',
        roleKey='auditor',
        roleSort=1,
        status='0',
        menuIds=[],
        updateBy='admin',
    )

    await RoleService.edit_role_services(db, payload)

    security_event.assert_awaited_once_with(db, 5, 'role_claim_changed', actor='admin')
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_changing_role_menu_invalidates_external_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """角色菜单授权变化必须让成员的旧外部声明失效。"""
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    role = AddRoleModel(roleId=5, roleName='普通角色', roleKey='reader', roleSort=1, status='0')
    monkeypatch.setattr(RoleService, 'role_detail_services', AsyncMock(return_value=role))
    monkeypatch.setattr(RoleDao, 'list_role_menu_ids', AsyncMock(return_value=[10]))
    monkeypatch.setattr(RoleDao, 'edit_role_dao', AsyncMock())
    monkeypatch.setattr(RoleDao, 'delete_role_menu_dao', AsyncMock())
    monkeypatch.setattr(RoleDao, 'add_role_menu_dao', AsyncMock())
    monkeypatch.setattr(RoleService, 'check_role_name_unique_services', AsyncMock(return_value=True))
    monkeypatch.setattr(RoleService, 'check_role_key_unique_services', AsyncMock(return_value=True))
    security_event = AsyncMock()
    monkeypatch.setattr(IdentitySecurityEventService, 'handle_role_event', security_event)
    payload = AddRoleModel(
        roleId=5,
        roleName='普通角色',
        roleKey='reader',
        roleSort=1,
        status='0',
        menuIds=[11],
        updateBy='admin',
    )

    await RoleService.edit_role_services(db, payload)

    security_event.assert_awaited_once_with(db, 5, 'role_claim_changed', actor='admin')
    db.commit.assert_awaited_once()
