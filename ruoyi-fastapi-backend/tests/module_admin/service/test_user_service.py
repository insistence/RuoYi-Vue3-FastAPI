from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from common.enums import PasswordCharacterType
from exceptions.exception import ServiceException
from module_admin.service.user_service import UserService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('pwd_chrtype', 'password'),
    [
        ('0', 'Abc123!'),
        ('1', '123456'),
        ('2', 'Abcdef'),
        ('3', 'Abc123'),
        ('4', 'Abc123!'),
    ],
)
async def test_validate_password_accepts_each_character_type(pwd_chrtype: str, password: str) -> None:
    redis = SimpleNamespace(get=AsyncMock(return_value=pwd_chrtype))

    await UserService.validate_password_services(redis, password)

    redis.get.assert_awaited_once_with('sys_config:sys.account.chrtype')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('pwd_chrtype', 'password', 'message'),
    [
        ('0', 'Abc<123', '密码不能包含非法字符：< > " \' \\ |'),
        ('1', '12345a', '密码只能为数字（0-9）'),
        ('2', 'Abc123', '密码只能为英文字母（a-z、A-Z）'),
        ('3', 'Abcdef', '密码必须同时包含字母和数字'),
        ('4', 'Abc123', '密码必须同时包含字母、数字和特殊字符（~!@#$%^&*()-=_+）'),
    ],
)
async def test_validate_password_rejects_invalid_character_type(pwd_chrtype: str, password: str, message: str) -> None:
    redis = SimpleNamespace(get=AsyncMock(return_value=pwd_chrtype))

    with pytest.raises(ServiceException) as exc_info:
        await UserService.validate_password_services(redis, password)

    assert exc_info.value.message == message


@pytest.mark.asyncio
@pytest.mark.parametrize('password', ['12345', '123456789012345678901'])
async def test_validate_password_rejects_invalid_length(password: str) -> None:
    redis = SimpleNamespace(get=AsyncMock(return_value='0'))

    with pytest.raises(ServiceException) as exc_info:
        await UserService.validate_password_services(redis, password)

    assert exc_info.value.message == '密码长度必须介于 6 和 20 之间'


@pytest.mark.asyncio
async def test_validate_password_uses_fixed_rule_without_reading_config() -> None:
    redis = SimpleNamespace(get=AsyncMock(return_value='4'))

    await UserService.validate_password_services(redis, 'abcdef', PasswordCharacterType.DEFAULT)

    redis.get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('config_value', [None, '', 'invalid'])
async def test_validate_password_falls_back_to_default_rule(config_value: str | None) -> None:
    redis = SimpleNamespace(get=AsyncMock(return_value=config_value))

    await UserService.validate_password_services(redis, 'abcdef')
