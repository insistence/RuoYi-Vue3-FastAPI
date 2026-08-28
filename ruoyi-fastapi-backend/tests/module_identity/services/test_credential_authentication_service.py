"""凭据协调服务的 Legacy/OIDC 安全边界测试。"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from common.enums import RedisInitKeyConfig
from config.env import OidcConfig
from exceptions.exception import LoginException
from module_admin.entity.vo.login_vo import UserLogin
from module_admin.service.login_service import LoginService
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.identity_service import (
    CredentialAuthenticationError,
    CredentialAuthenticationService,
)
from utils.pwd_util import PwdUtil

_OIDC_FAILURE_SCRIPT_KEY_COUNT = 2
_OIDC_FAILURE_SCRIPT_ARGUMENT_COUNT = 4


class _Redis:
    """记录认证服务访问的 Redis 最小异步替身。"""

    def __init__(self, values: dict[str, object] | None = None, eval_values: list[object] | None = None) -> None:
        self.values = values or {}
        self.eval_values = list(eval_values or [])
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, object, object]] = []
        self.delete_calls: list[str] = []
        self.eval_calls: list[tuple[str, int, tuple[object, ...]]] = []

    async def get(self, key: str) -> object:
        self.get_calls.append(key)
        return self.values.get(key)

    async def set(self, key: str, value: object, *, ex: object) -> None:
        self.values[key] = value
        self.set_calls.append((key, value, ex))

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.delete_calls.append(key)

    async def eval(self, script: str, count: int, *keys_and_args: object) -> object:
        self.eval_calls.append((script, count, keys_and_args))
        return self.eval_values.pop(0) if self.eval_values else None


class _AtomicFailureRedis(_Redis):
    """按 OIDC 错误 Lua 脚本语义执行 INCR、锁定和锁前检查。"""

    async def eval(self, script: str, count: int, *keys_and_args: object) -> object:
        self.eval_calls.append((script, count, keys_and_args))
        if "redis.call('incr'" not in script:
            return self.eval_values.pop(0) if self.eval_values else None
        failure_key, lock_key, threshold, _ttl = keys_and_args
        if self.values.get(lock_key):
            return -1
        current = int(self.values.get(failure_key, 0)) + 1
        if current > int(threshold):
            self.values.pop(failure_key, None)
            self.values[lock_key] = '1'
            return -1
        self.values[failure_key] = current
        return current


def _request(redis: _Redis, *, host: str = '127.0.0.1') -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
        client=SimpleNamespace(host=host),
        headers={},
    )


def _user(user_name: str = 'alice', *, status: str = '0', update_date: object = None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=7,
        user_name=user_name,
        password='stored-hash',
        status=status,
        pwd_update_date=update_date,
    )


@pytest.mark.asyncio
async def test_oidc_unknown_user_and_wrong_password_are_equivalent_and_dummy_verify_runs() -> None:
    redis = _Redis()
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=None),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=False) as verify,
        pytest.raises(CredentialAuthenticationError) as unknown,
    ):
        await CredentialAuthenticationService.authenticate_oidc(redis, object(), user_name='alice', password='wrong')
    verify.assert_called_once_with('wrong', '$2b$12$ySHJfAWxzh49cIc7M5L21e5GlPyA7QhE2GkLn9XuUTqmKIRqhWIja')
    redis_keys = [item[0] for item in redis.set_calls]
    assert unknown.value.reason == 'invalid_credentials'
    assert all('alice' not in key for key in redis_keys)

    redis = _Redis()
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(_user(), None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=False),
        pytest.raises(CredentialAuthenticationError) as wrong,
    ):
        await CredentialAuthenticationService.authenticate_oidc(redis, object(), user_name='alice', password='wrong')
    assert wrong.value.reason == unknown.value.reason


@pytest.mark.asyncio
async def test_oidc_captcha_is_atomically_consumed_and_success_does_not_write_legacy_token_key() -> None:
    redis = _Redis(eval_values=['1234', None])
    user = _user()
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(user, None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=True),
    ):
        result = await CredentialAuthenticationService.authenticate_oidc(
            redis,
            object(),
            user_name='alice',
            password='correct',
            code='1234',
            uuid='captcha-id',
            captcha_enabled=True,
            remember_me=True,
        )
        assert result.amr == ('pwd', 'captcha')
        assert result.remember_me is True
        with pytest.raises(CredentialAuthenticationError) as replay:
            await CredentialAuthenticationService.authenticate_oidc(
                redis,
                object(),
                user_name='alice',
                password='correct',
                code='1234',
                uuid='captcha-id',
                captcha_enabled=True,
            )
    assert replay.value.reason == 'captcha_missing'
    assert redis.eval_calls and redis.eval_calls[0][1] == 1
    assert not any(key.startswith(f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:') for key, _, _ in redis.set_calls)


@pytest.mark.asyncio
async def test_oidc_disabled_user_is_rejected() -> None:
    status, expected_reason = '1', 'user_disabled'
    redis = _Redis()
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(_user(status=status), None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=True),
        pytest.raises(CredentialAuthenticationError) as exc_info,
    ):
        await CredentialAuthenticationService.authenticate_oidc(redis, object(), user_name='alice', password='correct')
    assert exc_info.value.reason == expected_reason


@pytest.mark.asyncio
async def test_oidc_initial_and_expired_password_flags_handle_naive_and_aware_dates() -> None:
    redis = _Redis(
        {
            'sys_config:sys.account.initPasswordModify': '1',
            'sys_config:sys.account.passwordValidateDays': '30',
        }
    )
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(_user(update_date=None), None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=True),
    ):
        result = await CredentialAuthenticationService.authenticate_oidc(
            redis, object(), user_name='alice', password='correct'
        )
    assert result.password_change_required is True
    assert result.password_change_reason == 'initial_password'


@pytest.mark.asyncio
async def test_oidc_expired_aware_password_is_reported_without_datetime_error() -> None:
    redis = _Redis({'sys_config:sys.account.passwordValidateDays': '30'})
    old_date = datetime.now(timezone.utc) - timedelta(days=31)
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(_user(update_date=old_date), None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=True),
    ):
        result = await CredentialAuthenticationService.authenticate_oidc(
            redis, object(), user_name='alice', password='correct'
        )
    assert result.password_change_required is True
    assert result.password_change_reason == 'password_expired'


@pytest.mark.asyncio
async def test_oidc_hashed_error_state_locks_without_plain_username() -> None:
    redis = _Redis(eval_values=[-1])
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(_user(), None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=False),
        pytest.raises(CredentialAuthenticationError) as exc_info,
    ):
        digest = OidcRedisKey.hash_sensitive_identifier('alice', 'p' * 32)
        redis.values[OidcRedisKey.login_user_rate_limit(digest)] = 5
        await CredentialAuthenticationService.authenticate_oidc(redis, object(), user_name='alice', password='wrong')
    assert exc_info.value.reason == 'account_locked'
    assert all('alice' not in key for key, _, _ in redis.set_calls)


@pytest.mark.asyncio
async def test_oidc_error_counter_uses_atomic_incr_expire_and_lock_script() -> None:
    redis = _Redis(eval_values=[1])
    with (
        patch.object(OidcConfig, 'oidc_token_hash_pepper', 'p' * 32),
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(_user(), None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=False),
        pytest.raises(CredentialAuthenticationError),
    ):
        await CredentialAuthenticationService.authenticate_oidc(redis, object(), user_name='alice', password='wrong')
    script, key_count, arguments = redis.eval_calls[-1]
    assert "redis.call('incr'" in script
    assert "redis.call('expire'" in script
    assert key_count == _OIDC_FAILURE_SCRIPT_KEY_COUNT
    assert len(arguments) == _OIDC_FAILURE_SCRIPT_ARGUMENT_COUNT
    assert all('alice' not in str(value) for value in arguments[:2])


@pytest.mark.asyncio
async def test_oidc_failure_script_stays_locked_after_atomic_lock_transition() -> None:
    """建锁后的并发等效第二次脚本调用不得重建错误计数。"""
    redis = _AtomicFailureRedis({})
    failure_key = 'oidc:rate_limit:login:user:' + 'a' * 64
    lock_key = f'{failure_key}:lock'
    redis.values[failure_key] = 5
    with pytest.raises(CredentialAuthenticationError) as first:
        await CredentialAuthenticationService._record_oidc_password_error(redis, failure_key, lock_key)
    with pytest.raises(CredentialAuthenticationError) as second:
        await CredentialAuthenticationService._record_oidc_password_error(redis, failure_key, lock_key)
    assert first.value.reason == 'account_locked'
    assert second.value.reason == 'account_locked'
    assert failure_key not in redis.values
    assert redis.values[lock_key] == '1'
    assert "exists', KEYS[2]" in redis.eval_calls[0][0]


@pytest.mark.asyncio
async def test_legacy_success_and_wrong_password_keep_legacy_keys_and_messages() -> None:
    user = _user()
    redis = _Redis()
    with (
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(user, None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=True),
    ):
        result = await LoginService.authenticate_user(
            _request(redis), object(), UserLogin(userName='alice', password='correct', captchaEnabled=False)
        )
    assert result[0] is user
    assert f'{RedisInitKeyConfig.PASSWORD_ERROR_COUNT.key}:alice' in redis.delete_calls
    assert not any(key.startswith('oidc:') for key, _, _ in redis.set_calls)

    redis = _Redis()
    with (
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=(user, None)),
        ),
        patch.object(PwdUtil, 'verify_password', return_value=False),
        pytest.raises(LoginException) as exc_info,
    ):
        await LoginService.authenticate_user(
            _request(redis), object(), UserLogin(userName='alice', password='wrong', captchaEnabled=False)
        )
    assert exc_info.value.message == '密码错误'
    assert any(key == 'password_error_count:alice' for key, _, _ in redis.set_calls)


@pytest.mark.asyncio
async def test_legacy_unknown_user_keeps_message_and_does_not_create_error_key() -> None:
    redis = _Redis()
    with (
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(LoginException) as exc_info,
    ):
        await LoginService.authenticate_user(
            _request(redis), object(), UserLogin(userName='alice', password='wrong', captchaEnabled=False)
        )
    assert exc_info.value.message == '用户不存在'
    assert not any(key.startswith('password_error_count:') for key, _, _ in redis.set_calls)


@pytest.mark.asyncio
async def test_legacy_lock_captcha_and_blacklist_keep_original_messages_and_keys() -> None:
    lock_redis = _Redis({'account_lock:alice': 'alice'})
    with (
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(),
        ) as login_by_account,
        pytest.raises(LoginException) as locked,
    ):
        await LoginService.authenticate_user(
            _request(lock_redis), object(), UserLogin(userName='alice', password='wrong', captchaEnabled=False)
        )
    assert locked.value.message == '账号已锁定，请稍后再试'
    login_by_account.assert_not_awaited()
    assert 'account_lock:alice' in lock_redis.get_calls

    captcha_redis = _Redis()
    with (
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(),
        ) as login_by_account,
        pytest.raises(LoginException) as captcha_error,
    ):
        await LoginService.authenticate_user(
            _request(captcha_redis),
            object(),
            UserLogin(userName='alice', password='wrong', code='1', uuid='u', captchaEnabled=True),
        )
    assert captcha_error.value.message == '验证码已失效'
    login_by_account.assert_not_awaited()
    assert 'captcha_codes:u' in captcha_redis.get_calls

    ip_redis = _Redis({'sys_config:sys.login.blackIPList': '127.0.0.1'})
    with (
        patch(
            'module_identity.service.identity_service.login_by_account',
            new=AsyncMock(),
        ) as login_by_account,
        pytest.raises(LoginException) as ip_error,
    ):
        await LoginService.authenticate_user(
            _request(ip_redis), object(), UserLogin(userName='alice', password='wrong', captchaEnabled=False)
        )
    assert ip_error.value.message == '当前IP禁止登录'
    login_by_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_service_delegates_and_maps_original_login_exception() -> None:
    login_user = UserLogin(userName='alice', password='wrong', captchaEnabled=False)
    request = _request(_Redis())
    with (
        patch.object(
            CredentialAuthenticationService,
            'authenticate_legacy',
            new=AsyncMock(side_effect=CredentialAuthenticationError('invalid_credentials', '密码错误')),
        ),
        pytest.raises(LoginException) as exc_info,
    ):
        await LoginService.authenticate_user(request, object(), login_user)
    assert exc_info.value.message == '密码错误'
