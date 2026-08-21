import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from common.enums import PasswordCharacterType
from module_admin.controller.user_controller import change_system_user_profile_info, reset_system_user_pwd
from module_admin.entity.vo.user_vo import EditUserModel, UpdateUserProfileModel
from module_admin.service.user_service import UserService
from utils.pwd_util import PwdUtil


@pytest.mark.asyncio
async def test_admin_reset_password_uses_front_end_default_rule() -> None:
    redis = SimpleNamespace()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    reset_user = EditUserModel(userId=2, password='abcdef')
    current_user = SimpleNamespace(user=SimpleNamespace(admin=True, user_name='admin'))
    expected = object()

    with (
        patch.object(UserService, 'check_user_allowed_services', new_callable=AsyncMock),
        patch.object(UserService, 'validate_password_services', new_callable=AsyncMock) as validate_password,
        patch.object(
            UserService,
            'edit_user_services',
            new=AsyncMock(return_value=SimpleNamespace(message='重置成功')),
        ),
        patch.object(PwdUtil, 'get_password_hash', return_value='hashed-password'),
        patch(
            'module_admin.controller.user_controller.ResponseUtil.success',
            return_value=expected,
        ),
    ):
        result = await inspect.unwrap(reset_system_user_pwd)(
            request,
            reset_user,
            object(),
            current_user,
            object(),
        )

    assert result is expected
    validate_password.assert_awaited_once_with(redis, 'abcdef', PasswordCharacterType.DEFAULT)


@pytest.mark.parametrize(
    'management_field',
    [
        {'deptId': 200},
        {'password': 'attacker-controlled'},
        {'status': '1'},
        {'delFlag': '2'},
        {'userType': '99'},
        {'createBy': 'attacker'},
    ],
)
def test_update_user_profile_model_rejects_management_fields(management_field: dict) -> None:
    with pytest.raises(ValidationError):
        UpdateUserProfileModel(nickName='普通用户', **management_field)


@pytest.mark.asyncio
async def test_update_user_profile_only_forwards_editable_fields() -> None:
    request = SimpleNamespace()
    user_info = UpdateUserProfileModel(
        nickName='新昵称',
        email='user@example.com',
        phonenumber='13800138000',
        sex='2',
    )
    current_user = SimpleNamespace(
        user=SimpleNamespace(
            user_id=2,
            user_name='user',
            role_ids='2',
            post_ids='3',
            role=[],
        )
    )
    expected = object()

    with (
        patch.object(
            UserService,
            'edit_user_services',
            new=AsyncMock(return_value=SimpleNamespace(message='更新成功')),
        ) as edit_user_services,
        patch(
            'module_admin.controller.user_controller.ResponseUtil.success',
            return_value=expected,
        ),
    ):
        result = await inspect.unwrap(change_system_user_profile_info)(
            request,
            user_info,
            object(),
            current_user,
        )

    assert result is expected
    edit_user = edit_user_services.await_args.args[1]
    update_fields = edit_user.model_dump(exclude_unset=True)
    assert update_fields['nick_name'] == '新昵称'
    assert update_fields['email'] == 'user@example.com'
    assert update_fields['phonenumber'] == '13800138000'
    assert update_fields['sex'] == '2'
    assert not {
        'dept_id',
        'password',
        'status',
        'del_flag',
        'user_type',
        'create_by',
        'create_time',
    }.intersection(update_fields)
