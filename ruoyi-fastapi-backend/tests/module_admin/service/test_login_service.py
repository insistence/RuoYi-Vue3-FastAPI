from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from common.enums import PasswordCharacterType
from exceptions.exception import ServiceException
from module_admin.dao.user_dao import UserDao
from module_admin.entity.vo.login_vo import UserRegister
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService
from module_admin.service.user_service import UserService
from utils.pwd_util import PwdUtil


def _current_user(user_name: str = 'admin') -> SimpleNamespace:
    return SimpleNamespace(user=SimpleNamespace(user_name=user_name))


@pytest.mark.asyncio
@pytest.mark.parametrize(('config_value', 'expected'), [(None, '0'), ('4', '4')])
async def test_get_sys_account_chrtype_uses_config_and_default(config_value: str | None, expected: str) -> None:
    redis = SimpleNamespace(get=AsyncMock(return_value=config_value))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))

    result = await LoginService.get_sys_account_chrtype(request)

    assert result == expected
    redis.get.assert_awaited_once_with('sys_config:sys.account.chrtype')


def test_current_user_model_exposes_password_character_type_alias() -> None:
    current_user = CurrentUserModel(permissions=[], roles=[], user=None, pwdChrtype='3')

    assert current_user.model_dump(by_alias=True)['pwdChrtype'] == '3'


@pytest.mark.asyncio
async def test_unlock_screen_rejects_empty_password() -> None:
    with (
        patch.object(UserDao, 'get_user_by_name', new_callable=AsyncMock) as get_user,
        pytest.raises(ServiceException) as exc_info,
    ):
        await LoginService.unlock_screen_services(object(), _current_user(), '')

    assert exc_info.value.message == '密码不能为空'
    get_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_unlock_screen_rejects_missing_current_user() -> None:
    with (
        patch.object(UserDao, 'get_user_by_name', new=AsyncMock(return_value=None)) as get_user,
        pytest.raises(ServiceException) as exc_info,
    ):
        await LoginService.unlock_screen_services(object(), _current_user(), 'password')

    assert exc_info.value.message == '服务器超时，请重新登录'
    get_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_unlock_screen_rejects_wrong_password() -> None:
    user = SimpleNamespace(password='hashed-password')
    with (
        patch.object(UserDao, 'get_user_by_name', new=AsyncMock(return_value=user)),
        patch.object(PwdUtil, 'verify_password', return_value=False) as verify_password,
        pytest.raises(ServiceException) as exc_info,
    ):
        await LoginService.unlock_screen_services(object(), _current_user(), 'wrong-password')

    assert exc_info.value.message == '密码错误，请重新输入'
    verify_password.assert_called_once_with('wrong-password', 'hashed-password')


@pytest.mark.asyncio
async def test_unlock_screen_accepts_correct_password() -> None:
    user = SimpleNamespace(password='hashed-password')
    with (
        patch.object(UserDao, 'get_user_by_name', new=AsyncMock(return_value=user)) as get_user,
        patch.object(PwdUtil, 'verify_password', return_value=True) as verify_password,
    ):
        result = await LoginService.unlock_screen_services(object(), _current_user('ry'), 'correct-password')

    assert result is True
    get_user.assert_awaited_once()
    assert get_user.await_args.args[1] == 'ry'
    verify_password.assert_called_once_with('correct-password', 'hashed-password')


@pytest.mark.asyncio
async def test_register_uses_front_end_default_password_rule() -> None:
    redis = SimpleNamespace(get=AsyncMock(side_effect=['true', 'false']))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    user_register = UserRegister(
        username='test_user',
        password='abcdef',
        confirmPassword='abcdef',
    )
    expected = object()

    with (
        patch.object(UserService, 'validate_password_services', new_callable=AsyncMock) as validate_password,
        patch.object(UserService, 'add_user_services', new=AsyncMock(return_value=expected)),
        patch.object(PwdUtil, 'get_password_hash', return_value='hashed-password'),
    ):
        result = await LoginService.register_user_services(request, object(), user_register)

    assert result is expected
    validate_password.assert_awaited_once_with(redis, 'abcdef', PasswordCharacterType.DEFAULT)
