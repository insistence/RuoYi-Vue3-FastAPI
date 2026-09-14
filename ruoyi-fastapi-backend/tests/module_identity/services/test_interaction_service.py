"""Interaction Redis 状态机和 CSRF 服务测试。"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from exceptions.exception import OidcInteractionException
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.interaction_service import InteractionService
from tests.module_identity.support.redis_fakes import FakeRedis

_PEPPER = 'interaction-test-pepper-' + 'x' * 32
_CHALLENGE = 'A' * 43


def _payload(**overrides: object) -> dict[str, object]:
    """构造 AuthorizationContext 的内部白名单载荷。"""
    value: dict[str, object] = {
        'interactionId': 'context-id',
        'clientPk': 1001,
        'clientId': 'portal-client',
        'redirectUri': 'https://portal.example/callback',
        'responseType': 'code',
        'scopes': ['openid', 'profile'],
        'resources': ['https://api.example'],
        'state': 'opaque-state',
        'nonce': 'opaque-nonce',
        'codeChallenge': _CHALLENGE,
        'codeChallengeMethod': 'S256',
        'prompt': 'login',
        'maxAge': 3600,
        'consentRequired': True,
    }
    value.update(overrides)
    return value


@pytest.mark.asyncio
@pytest.mark.usefixtures('interaction_page_metadata')
async def test_create_uses_nx_ttl_and_returns_csrf_only_once() -> None:
    """验证 Interaction 创建使用 NX/TTL，Redis 仅存 csrfHash。"""
    redis = FakeRedis()
    created = await InteractionService.create(redis, _payload(), ttl_seconds=300, pepper=_PEPPER)
    record = await InteractionService.get_record(redis, created.interaction_id)
    csrf = created.csrf_token
    key = OidcRedisKey.interaction(created.interaction_id)
    stored = redis.values[key][0]
    assert record['status'] == 'awaiting_login'
    assert record['csrfHash'] not in csrf
    assert 'csrfHash' in stored
    assert csrf not in stored
    assert redis.set_calls[-1][1] == {'ex': 300, 'nx': True}
    page = await InteractionService.get(redis, created.interaction_id, object())
    assert page['expiresIn'] > 0


@pytest.mark.asyncio
@pytest.mark.parametrize('ttl', [0, False, -1])
async def test_create_rejects_explicit_invalid_ttl(ttl: object) -> None:
    """验证显式零值、布尔值和负数不会回退到默认 TTL。"""
    redis = FakeRedis()
    with pytest.raises(ValueError):
        await InteractionService.create(redis, _payload(), ttl_seconds=ttl, pepper=_PEPPER)  # type: ignore[arg-type]
    assert not redis.values


@pytest.mark.asyncio
@pytest.mark.usefixtures('interaction_page_metadata')
async def test_page_projection_never_leaks_internal_protocol_fields() -> None:
    """验证页面载荷不包含 Redirect、协议绑定、用户或 CSRF 内部字段。"""
    redis = FakeRedis()
    created = await InteractionService.create(redis, _payload(), pepper=_PEPPER)
    page = await InteractionService.get(redis, created.interaction_id, object())
    forbidden = {
        'redirectUri',
        'state',
        'nonce',
        'codeChallenge',
        'codeChallengeMethod',
        'csrfHash',
        'userId',
        'subjectId',
        'authVersion',
        'sid',
        'clientPk',
        'maxAge',
    }
    assert forbidden.isdisjoint(page)
    assert set(page) == {'interactionId', 'client', 'requestedScopes', 'nextAction', 'captchaEnabled', 'expiresIn'}
    assert page['nextAction'] == 'login'
    assert page['client']['clientName'] == '示例门户'
    assert page['client']['policyUri'] == 'https://portal.example/privacy'
    assert page['requestedScopes'][1]['name'] == '基本资料'
    assert page['requestedScopes'][1]['sensitive'] is True
    assert page['requestedScopes'][1]['required'] is False
    assert page['requestedScopes'][0]['required'] is True
    assert page['requestedScopes'][1]['description']
    assert 'private-' not in json.dumps(page)


@pytest.mark.asyncio
@pytest.mark.usefixtures('interaction_page_metadata')
async def test_csrf_is_constant_time_verified_and_not_rotated_by_read() -> None:
    """验证 CSRF 正确匹配、错误拒绝，读取页面不会重新建立 Token。"""
    redis = FakeRedis()
    created = await InteractionService.create(redis, _payload(), pepper=_PEPPER)
    record = await InteractionService.get_record(redis, created.interaction_id)
    csrf = created.csrf_token
    assert InteractionService.verify_csrf(record, csrf, pepper=_PEPPER) is True
    assert InteractionService.verify_csrf(record, csrf + 'x', pepper=_PEPPER) is False
    await InteractionService.get(redis, created.interaction_id, object())
    assert InteractionService.verify_csrf(record, csrf, pepper=_PEPPER) is True


@pytest.mark.asyncio
async def test_transition_uses_lua_cas_and_rejects_illegal_rollback() -> None:
    """验证状态流转保留 TTL，非法回退和终态回退均拒绝。"""
    redis = FakeRedis()
    created = await InteractionService.create(redis, _payload(), pepper=_PEPPER)
    updated = await InteractionService.transition(redis, created.interaction_id, {'awaiting_login'}, 'awaiting_consent')
    assert updated['nextAction'] == 'consent'
    assert redis.eval_calls
    with pytest.raises(ValueError):
        await InteractionService.transition(redis, created.interaction_id, {'awaiting_consent'}, 'awaiting_login')
    completed = await InteractionService.transition(redis, created.interaction_id, {'awaiting_consent'}, 'completed')
    assert completed['nextAction'] == 'redirect'
    with pytest.raises(ValueError):
        await InteractionService.transition(redis, created.interaction_id, {'completed'}, 'denied')


@pytest.mark.asyncio
async def test_prompt_none_fails_without_interactive_creation() -> None:
    """验证 prompt=none 不登录时返回 login_required，不写入交互状态。"""
    redis = FakeRedis()
    with pytest.raises(OidcInteractionException) as raised:
        await InteractionService.create(redis, _payload(prompt='none'), pepper=_PEPPER)
    assert raised.value.error == 'login_required'
    assert not redis.values

    with pytest.raises(OidcInteractionException) as raised:
        await InteractionService.create(redis, _payload(prompt='none', authenticatedSid='sid-1'), pepper=_PEPPER)
    assert raised.value.error == 'consent_required'
    assert not redis.values


@pytest.mark.asyncio
async def test_initial_status_respects_sso_prompt_and_consent() -> None:
    """验证已有 SSO、prompt 和同意要求共同决定初始状态。"""
    redis = FakeRedis()
    created = await InteractionService.create(
        redis, _payload(prompt=None, authenticatedSid='sid-1', consentRequired=True), pepper=_PEPPER
    )
    assert created.initial_status == 'awaiting_consent'

    login = await InteractionService.create(
        redis, _payload(prompt='login', authenticatedSid='sid-2', consentRequired=False), pepper=_PEPPER
    )
    assert login.initial_status == 'awaiting_login'

    silent = await InteractionService.create(
        redis, _payload(prompt='none', authenticatedSid='sid-3', consentRequired=False), pepper=_PEPPER
    )
    assert silent.initial_status == 'completed'
    assert (await InteractionService.get_record(redis, silent.interaction_id))['status'] == 'completed'


@pytest.mark.asyncio
async def test_record_validation_and_missing_ttl_fail_closed() -> None:
    """验证损坏记录和永久键不会进入状态机。"""
    redis = FakeRedis()
    created = await InteractionService.create(redis, _payload(), pepper=_PEPPER)
    key = OidcRedisKey.interaction(created.interaction_id)
    value, _ = redis.values[key]
    corrupted = value.replace('"version":1', '"version":-1')
    redis.values[key] = (corrupted, None)
    with pytest.raises(OidcInteractionException) as raised:
        await InteractionService.get(redis, created.interaction_id, object())
    assert raised.value.error == 'invalid_request'
    assert key not in redis.values


@pytest.mark.asyncio
async def test_transition_rejects_interaction_without_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务层将 Redis CAS 返回的无 TTL 哨兵转换为协议错误并清理键。"""
    redis = FakeRedis()
    created = await InteractionService.create(redis, _payload(), pepper=_PEPPER)
    key = OidcRedisKey.interaction(created.interaction_id)
    value, _ = redis.values[key]
    redis.values[key] = (value, None)

    async def get_record(*_args: object, **_kwargs: object) -> dict[str, object]:
        return json.loads(value)

    monkeypatch.setattr(InteractionService, '_get_record', classmethod(get_record))
    with pytest.raises(OidcInteractionException, match='TTL is invalid'):
        await InteractionService.transition(redis, created.interaction_id, {'awaiting_login'}, 'awaiting_consent')
    assert key not in redis.values


@pytest.mark.asyncio
async def test_transition_rejects_duplicate_scope_and_incomplete_identity() -> None:
    """验证创建和状态更新不接受重复 Scope 或不完整身份三元组。"""
    redis = FakeRedis()
    with pytest.raises(ValueError):
        await InteractionService.create(redis, _payload(scopes=['openid', 'openid']), pepper=_PEPPER)
    created = await InteractionService.create(redis, _payload(), pepper=_PEPPER)
    with pytest.raises(ValueError):
        await InteractionService.transition(
            redis, created.interaction_id, {'awaiting_login'}, 'awaiting_consent', {'userId': 1}
        )


def test_max_age_decision_uses_project_local_time() -> None:
    """验证 max_age 使用项目约定的本地无时区时间。"""
    now = datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc)
    assert InteractionService.requires_reauthentication(now - timedelta(seconds=10), 5, now) is True
    assert InteractionService.requires_reauthentication(now - timedelta(seconds=2), 5, now) is False
    assert InteractionService.requires_reauthentication(now, 5, now) is False


@pytest.mark.asyncio
@pytest.mark.usefixtures('interaction_page_metadata')
@pytest.mark.parametrize('change', ['client_disabled', 'scope_unbound'])
async def test_page_rejects_removed_application_or_scope(monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    """请求创建后停用应用或移除权限时，不继续展示陈旧授权选项。"""
    redis = FakeRedis()
    created = await InteractionService.create(redis, _payload(), pepper=_PEPPER)
    if change == 'client_disabled':
        monkeypatch.setattr(OAuthClientDao, 'get_by_pk', AsyncMock(return_value=None))
    else:
        monkeypatch.setattr(OAuthClientDao, 'list_scopes', AsyncMock(return_value=[]))
    with pytest.raises(OidcInteractionException):
        await InteractionService.get(redis, created.interaction_id, object())
