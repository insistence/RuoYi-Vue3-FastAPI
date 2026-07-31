import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from common.enums import PasswordCharacterType
from module_admin.controller.user_controller import reset_system_user_pwd
from module_admin.entity.vo.user_vo import EditUserModel
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
