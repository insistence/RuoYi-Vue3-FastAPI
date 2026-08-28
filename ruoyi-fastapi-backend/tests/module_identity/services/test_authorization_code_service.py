"""Authorization Code Redis 服务测试。"""

import asyncio

import pytest

from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.authorization_service import AuthorizationCodeReuseError, AuthorizationCodeService
from tests.module_identity.support.redis_fakes import FakeRedis

_PEPPER = 'authorization-code-test-pepper-' + 'x' * 32
_CHALLENGE = 'A' * 43
_CLIENT_PK = 1001
_LONG_CODE_TTL = 600


def _payload(**overrides: object) -> dict[str, object]:
    """构造服务端授权码白名单载荷。"""
    value: dict[str, object] = {
        'clientPk': 1001,
        'redirectUri': 'https://portal.example/callback',
        'userId': 2001,
        'subjectId': 'subject-2001',
        'authVersion': 4,
        'sid': 'sid-2001',
        'grantId': 'grant-2001',
        'scopes': ['openid', 'profile'],
        'resources': ['https://api.example'],
        'nonce': 'nonce-2001',
        'codeChallenge': _CHALLENGE,
        'codeChallengeMethod': 'S256',
        'authTime': '2026-08-24T04:00:00+00:00',
    }
    value.update(overrides)
    return value


@pytest.mark.asyncio
async def test_issue_uses_ac_key_nx_ttl_and_never_stores_plain_code() -> None:
    """验证授权码使用独立 key、NX/TTL，并只保存摘要。"""
    redis = FakeRedis()
    code = await AuthorizationCodeService.issue(redis, _payload(), ttl_seconds=90, pepper=_PEPPER)
    assert code.startswith('ac1.')
    key = OidcRedisKey.authorization_code(code.split('.')[1])
    stored = redis.values[key][0]
    assert code not in stored
    assert 'codeHash' in stored
    assert redis.set_calls[-1][1] == {'ex': 90, 'nx': True}


@pytest.mark.asyncio
@pytest.mark.parametrize('ttl', [0, False, -1])
async def test_issue_rejects_explicit_invalid_ttl(ttl: object) -> None:
    """验证显式零值、布尔值和负数不会回退到默认 Code TTL。"""
    redis = FakeRedis()
    with pytest.raises(ValueError):
        await AuthorizationCodeService.issue(redis, _payload(), ttl_seconds=ttl, pepper=_PEPPER)  # type: ignore[arg-type]
    assert not redis.values


@pytest.mark.asyncio
async def test_wrong_secret_does_not_consume_and_correct_secret_consumes_once() -> None:
    """验证错误 Secret 不删除 Code，正确消费具备一次性语义。"""
    redis = FakeRedis()
    code = await AuthorizationCodeService.issue(redis, _payload(), pepper=_PEPPER)
    parts = code.split('.')
    replacement = 'A' if parts[2][0] != 'A' else 'B'
    wrong = f'{parts[0]}.{parts[1]}.{replacement}{parts[2][1:]}'
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationCodeService.consume(redis, wrong, pepper=_PEPPER)
    assert raised.value.error == 'invalid_grant'
    assert await redis.get(OidcRedisKey.authorization_code(parts[1])) is not None
    assert await redis.get(OidcRedisKey.authorization_code_consumed(parts[1])) is None
    consumed = await AuthorizationCodeService.consume(redis, code, pepper=_PEPPER)
    assert consumed['clientPk'] == _CLIENT_PK
    assert await redis.get(OidcRedisKey.authorization_code_consumed(parts[1])) == 'consumed'
    assert (await AuthorizationCodeService.consumed_payload(redis, code, pepper=_PEPPER))['grantId'] == 'grant-2001'
    with pytest.raises(OAuthProtocolException) as reused:
        await AuthorizationCodeService.consume(redis, code, pepper=_PEPPER)
    assert isinstance(reused.value, AuthorizationCodeReuseError)


@pytest.mark.asyncio
async def test_reuse_tombstone_ttl_covers_long_authorization_code_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证授权码 TTL 超过最小墓碑 TTL 时，重用墓碑覆盖完整 Code 生命周期。"""
    monkeypatch.setattr(OidcConfig, 'oidc_authorization_code_ttl_seconds', _LONG_CODE_TTL)
    redis = FakeRedis()
    code = await AuthorizationCodeService.issue(redis, _payload(), pepper=_PEPPER)

    await AuthorizationCodeService.consume(redis, code, pepper=_PEPPER)

    assert redis.eval_calls[-1][1][-1] == _LONG_CODE_TTL


@pytest.mark.asyncio
async def test_concurrent_correct_consumption_only_succeeds_once() -> None:
    """验证两个并发正确消费请求只有一个能取得载荷。"""
    redis = FakeRedis()
    code = await AuthorizationCodeService.issue(redis, _payload(), pepper=_PEPPER)
    results = await asyncio.gather(
        AuthorizationCodeService.consume(redis, code, pepper=_PEPPER),
        AuthorizationCodeService.consume(redis, code, pepper=_PEPPER),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, OAuthProtocolException) for result in results) == 1
    assert sum(isinstance(result, AuthorizationCodeReuseError) for result in results) == 1


@pytest.mark.asyncio
async def test_invalid_payload_and_format_fail_closed_without_redis_write() -> None:
    """验证缺失、未知对象和畸形 Code 均 fail closed。"""
    redis = FakeRedis()
    with pytest.raises(ValueError):
        await AuthorizationCodeService.issue(redis, _payload(extra='unknown'), pepper=_PEPPER)
    with pytest.raises(ValueError):
        await AuthorizationCodeService.issue(redis, _payload(scopes=['openid'], codeChallenge='short'), pepper=_PEPPER)
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationCodeService.consume(redis, 'ac1.invalid.short', pepper=_PEPPER)
    assert raised.value.error == 'invalid_grant'
    assert not redis.values


@pytest.mark.asyncio
async def test_expired_code_is_invalid_grant() -> None:
    """验证 Redis TTL 到期后返回统一 invalid_grant。"""
    redis = FakeRedis()
    code = await AuthorizationCodeService.issue(redis, _payload(), ttl_seconds=1, pepper=_PEPPER)
    key = OidcRedisKey.authorization_code(code.split('.')[1])
    redis.values[key] = (redis.values[key][0], 0)
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationCodeService.consume(redis, code, pepper=_PEPPER)
    assert raised.value.error == 'invalid_grant'
    assert await redis.get(OidcRedisKey.authorization_code_consumed(code.split('.')[1])) is None


@pytest.mark.asyncio
async def test_invalid_auth_time_and_duplicate_lists_are_rejected() -> None:
    """验证授权码时间必须为 UTC，Scope/Resource 列表不得重复。"""
    redis = FakeRedis()
    with pytest.raises(ValueError):
        await AuthorizationCodeService.issue(redis, _payload(authTime='2026-08-24T04:00:00'), pepper=_PEPPER)
    with pytest.raises(ValueError):
        await AuthorizationCodeService.issue(redis, _payload(scopes=['openid', 'openid']), pepper=_PEPPER)
    with pytest.raises(ValueError):
        await AuthorizationCodeService.issue(redis, _payload(resources=['api', 'api']), pepper=_PEPPER)


@pytest.mark.asyncio
async def test_consumed_corrupt_payload_is_invalid_grant() -> None:
    """验证 Lua 已删除但载荷校验失败仍返回统一 OAuth 错误。"""
    redis = FakeRedis()
    code = await AuthorizationCodeService.issue(redis, _payload(), pepper=_PEPPER)
    key = OidcRedisKey.authorization_code(code.split('.')[1])
    value, expiry = redis.values[key]
    redis.values[key] = (value.replace('"authTime":"2026-08-24T04:00:00+00:00"', '"authTime":"bad"'), expiry)
    with pytest.raises(OAuthProtocolException) as raised:
        await AuthorizationCodeService.consume(redis, code, pepper=_PEPPER)
    assert raised.value.error == 'invalid_grant'
