import asyncio
import builtins
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import OidcConfig
from module_admin.entity.do.user_do import SysUser
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from module_identity.entity.do.oauth_grant_do import SysSsoSession
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.session_service import SsoSessionError, SsoSessionService
from utils.oidc_util import OidcUtil

_PEPPER = 's' * 32
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_COOKIE_SECRET_TEXT_LENGTH = 43
_SUBJECT_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'


class SessionFakeRedis:
    """覆盖 Session 服务所需字符串、Set 和 publish 语义的 FakeRedis。"""

    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float | None]] = {}
        self.sets: dict[str, set[str]] = {}
        self.set_expiries: dict[str, float] = {}
        self.expire_seconds: dict[str, int] = {}
        self.published: list[tuple[str, str]] = []
        self.lock = asyncio.Lock()

    async def set(self, key: str, value: str, ex: int | None = None, **kwargs: object) -> bool:
        async with self.lock:
            self.values[key] = (value, None if ex is None else asyncio.get_running_loop().time() + ex)
            return True

    async def get(self, key: str) -> str | None:
        async with self.lock:
            value = self.values.get(key)
            if value is not None and value[1] is not None and value[1] <= asyncio.get_running_loop().time():
                self.values.pop(key, None)
                return None
            return value[0] if value else None

    async def delete(self, *keys: str) -> int:
        async with self.lock:
            return sum(self.values.pop(key, None) is not None for key in keys)

    async def sadd(self, key: str, *members: str) -> int:
        self._expire_set_if_needed(key)
        current = self.sets.setdefault(key, set())
        before = len(current)
        current.update(members)
        return len(current) - before

    async def srem(self, key: str, *members: str) -> int:
        self._expire_set_if_needed(key)
        current = self.sets.setdefault(key, set())
        removed = sum(member in current for member in members)
        current.difference_update(members)
        return removed

    async def smembers(self, key: str) -> builtins.set[str]:
        self._expire_set_if_needed(key)
        return builtins.set(self.sets.get(key, builtins.set()))

    async def expire(self, key: str, seconds: int) -> bool:
        """设置 Set 的剩余 TTL。"""
        if key not in self.sets:
            return False
        self.set_expiries[key] = asyncio.get_running_loop().time() + seconds
        self.expire_seconds[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        """返回 Set 的 Redis 风格剩余 TTL。"""
        self._expire_set_if_needed(key)
        expiry = self.set_expiries.get(key)
        if key not in self.sets:
            return -2
        if expiry is None:
            return -1
        return max(0, int(expiry - asyncio.get_running_loop().time()))

    def _expire_set_if_needed(self, key: str) -> None:
        expiry = self.set_expiries.get(key)
        if expiry is not None and expiry <= asyncio.get_running_loop().time():
            self.sets.pop(key, None)
            self.set_expiries.pop(key, None)

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


@pytest.fixture(autouse=True)
def _configure_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """将全局 OIDC 配置固定为 Session 测试所需的基线。"""

    values = {
        'oidc_enabled': True,
        'oidc_sso_absolute_seconds': 8 * 60 * 60,
        'oidc_sso_remember_absolute_seconds': 7 * 24 * 60 * 60,
        'oidc_sso_idle_seconds': 1800,
        'oidc_sso_cookie_name': '__Host-ruoyi-sso',
        'oidc_sso_cookie_secure': True,
        'oidc_sso_cookie_samesite': 'lax',
        'oidc_sso_cookie_domain': '',
    }
    for name, value in values.items():
        monkeypatch.setattr(OidcConfig, name, value)


def _config() -> OidcConfig:
    """返回当前测试使用的全局 OIDC 配置。"""

    return OidcConfig


def _config_with_long_remember() -> OidcConfig:
    """创建超过协议上限的 remember-me 配置。"""
    config = _config()
    config.oidc_sso_remember_absolute_seconds = 8 * 24 * 60 * 60
    return config


async def _seed_identity(db: AsyncSession, *, auth_version: int = 2) -> None:
    """写入真实用户和 Subject 事实。"""
    db.add(SysUser(user_id=1, user_name='session-user', nick_name='Session User', status='0', del_flag='0'))
    db.add(SysIdentitySubject(user_id=1, subject_id=_SUBJECT_ID, auth_version=auth_version, create_by='test'))
    await db.flush()


async def _create(db: AsyncSession, redis: SessionFakeRedis, *, remember: bool = False) -> tuple[str, SysSsoSession]:
    """创建测试 Session。"""
    queue = AfterCommitCoordinator()
    result = await SsoSessionService.create(
        db,
        redis,
        1,
        _SUBJECT_ID,
        2,
        'pwd',
        ['pwd', 'captcha'],
        remember_me=remember,
        pepper=_PEPPER,
        now=_NOW,
        ip_address='127.0.0.1',
        user_agent='pytest-agent',
        coordinator=queue,
    )
    await queue.commit(db)
    return result


@pytest.mark.asyncio
async def test_create_validate_and_remember_absolute_ttl(data_session: AsyncSession) -> None:
    """创建持久化完整 Session，普通和 remember 绝对 TTL 均受配置约束。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, row = await _create(data_session, redis)
    assert cookie.startswith('ss1.')
    sid, secret = OidcUtil.parse_sso_cookie(cookie)
    UUID(sid)
    assert len(secret) == _COOKIE_SECRET_TEXT_LENGTH
    assert secret not in row.session_secret_hash
    assert cookie not in json.dumps(redis.values)
    user_set_key = 'oidc:user_sessions:1'
    assert redis.expire_seconds[user_set_key] == 8 * 60 * 60
    session_payload = json.loads(redis.values[OidcRedisKey.sso_session(row.sid)][0])
    assert 'session_secret_hash' not in session_payload
    queue = AfterCommitCoordinator()
    validated = await SsoSessionService.validate(
        data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue
    )
    await queue.commit(data_session)
    assert validated.subject_id == _SUBJECT_ID
    remember_cookie, remember_row = await _create(data_session, redis, remember=True)
    assert remember_cookie != cookie
    assert remember_row.absolute_expires_at == _NOW + timedelta(days=7)
    assert redis.expire_seconds[user_set_key] == 7 * 24 * 60 * 60

    queue = AfterCommitCoordinator()
    capped = await SsoSessionService.create(
        data_session,
        redis,
        1,
        _SUBJECT_ID,
        2,
        'pwd',
        ['pwd'],
        remember_me=True,
        pepper=_PEPPER,
        now=_NOW,
        coordinator=queue,
    )
    await queue.commit(data_session)
    assert capped[1].absolute_expires_at == _NOW + timedelta(days=7)


@pytest.mark.asyncio
async def test_user_session_set_ttl_never_shortens(data_session: AsyncSession) -> None:
    """先创建 remember Session 时，普通 Session 不得缩短用户 Set TTL。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    await _create(data_session, redis, remember=True)
    await _create(data_session, redis, remember=False)
    assert redis.expire_seconds['oidc:user_sessions:1'] == 7 * 24 * 60 * 60


@pytest.mark.asyncio
async def test_stale_cookie_index_does_not_reject_valid_database_session(data_session: AsyncSession) -> None:
    """错误 Redis Cookie 映射视为陈旧，DB 校验成功后覆盖为正确 sid。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, row = await _create(data_session, redis)
    sid, secret = OidcUtil.parse_sso_cookie(cookie)
    digest = OidcUtil.session_secret_digest(secret, _PEPPER)
    await redis.set(OidcRedisKey.sso_cookie(digest), str(uuid4()), ex=3600)
    coordinator = AfterCommitCoordinator()
    validated = await SsoSessionService.validate(
        data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=coordinator
    )
    await coordinator.commit(data_session)
    assert validated.sid == sid == row.sid
    assert await redis.get(OidcRedisKey.sso_cookie(digest)) == sid


@pytest.mark.asyncio
async def test_coordinator_runs_all_callbacks_after_first_failure(data_session: AsyncSession) -> None:
    """首个提交后回调失败不阻断后续回调，数据库提交仍视为成功。"""
    coordinator = AfterCommitCoordinator()
    called: list[str] = []

    async def fail() -> None:
        called.append('first')
        raise RuntimeError('副作用失败')

    async def succeed() -> None:
        called.append('second')

    await coordinator.register(fail)
    await coordinator.register(succeed)
    await coordinator.commit(data_session)
    assert called == ['first', 'second']
    assert len(coordinator.callback_errors) == 1


@pytest.mark.asyncio
async def test_wrong_secret_and_security_version_fail_closed(data_session: AsyncSession) -> None:
    """错误 Secret、Subject auth_version 变化都会撤销并清缓存。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, row = await _create(data_session, redis)
    sid, _ = OidcUtil.parse_sso_cookie(cookie)
    wrong_secret = 'a' * 43
    wrong = f'ss1.{sid}.{wrong_secret}'
    queue = AfterCommitCoordinator()
    with pytest.raises(SsoSessionError):
        await SsoSessionService.validate(data_session, redis, wrong, pepper=_PEPPER, now=_NOW, coordinator=queue)
    await queue.commit(data_session)
    assert row.status == 'active'

    cookie, row = await _create(data_session, redis)
    subject = await data_session.scalar(select(SysIdentitySubject).where(SysIdentitySubject.user_id == 1))
    subject.auth_version = 3
    await data_session.flush()
    queue = AfterCommitCoordinator()
    with pytest.raises(SsoSessionError):
        await SsoSessionService.validate(data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue)
    await queue.commit(data_session)
    assert row.status == 'revoked'


@pytest.mark.asyncio
async def test_touch_never_crosses_absolute_and_rotation_invalidates_old(data_session: AsyncSession) -> None:
    """滑动 touch 受 absolute 上界约束，Cookie 轮换立即淘汰旧 Secret。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, row = await _create(data_session, redis)
    row.absolute_expires_at = _NOW + timedelta(seconds=100)
    await data_session.flush()
    queue = AfterCommitCoordinator()
    touched = await SsoSessionService.touch(
        data_session,
        redis,
        cookie,
        pepper=_PEPPER,
        now=_NOW + timedelta(seconds=90),
        coordinator=queue,
    )
    await queue.commit(data_session)
    assert touched.idle_expires_at == _NOW + timedelta(seconds=100)
    queue = AfterCommitCoordinator()
    rotated = await SsoSessionService.rotate_cookie(
        data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue
    )
    await queue.commit(data_session)
    queue = AfterCommitCoordinator()
    with pytest.raises(SsoSessionError):
        await SsoSessionService.validate(data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue)
    await queue.commit(data_session)
    queue = AfterCommitCoordinator()
    assert (
        await SsoSessionService.validate(data_session, redis, rotated, pepper=_PEPPER, now=_NOW, coordinator=queue)
    ).sid == row.sid
    await queue.commit(data_session)


@pytest.mark.asyncio
async def test_expired_session_is_marked_expired(data_session: AsyncSession) -> None:
    """超过 absolute 后拒绝 Cookie 并把数据库事实标记为 expired。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, row = await _create(data_session, redis)
    queue = AfterCommitCoordinator()
    with pytest.raises(SsoSessionError):
        await SsoSessionService.validate(
            data_session,
            redis,
            cookie,
            pepper=_PEPPER,
            now=_NOW + timedelta(seconds=8 * 60 * 60 + 1),
            coordinator=queue,
        )
    await queue.commit(data_session)
    assert row.status == 'expired'


@pytest.mark.asyncio
async def test_db_revocation_invalidates_cached_hit_and_after_commit_order(data_session: AsyncSession) -> None:
    """跨服务 DB 撤销不会被缓存命中绕过，撤销清理可延迟到 after-commit。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, row = await _create(data_session, redis)
    await SsoSessionDao.revoke(data_session, row.sid, reason='external', now=_NOW)
    await data_session.commit()
    queue = AfterCommitCoordinator()
    with pytest.raises(SsoSessionError):
        await SsoSessionService.validate(data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue)
    await queue.commit(data_session)

    cookie, row = await _create(data_session, redis)
    coordinator = AfterCommitCoordinator()

    assert await SsoSessionService.revoke(
        data_session, redis, row.sid, reason='admin', now=_NOW, coordinator=coordinator
    )
    assert row.status == 'revoked'
    assert redis.values
    await coordinator.commit(data_session)
    assert not redis.values
    assert json.loads(redis.published[-1][1])['sid'] == row.sid


@pytest.mark.asyncio
async def test_revoke_db_failure_does_not_clear_cache(
    data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """数据库撤销失败时不能提前删除 Redis 状态。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    _, row = await _create(data_session, redis)

    async def fail(*args: object, **kwargs: object) -> bool:
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(SsoSessionDao, 'revoke', fail)
    queue = AfterCommitCoordinator()
    with pytest.raises(RuntimeError):
        await SsoSessionService.revoke(data_session, redis, row.sid, now=_NOW, coordinator=queue)
    assert redis.values


@pytest.mark.asyncio
async def test_revoke_rollback_keeps_cache_until_after_commit(data_session: AsyncSession) -> None:
    """数据库回滚时不执行 after-commit 清理，避免缓存先于事实源失效。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    _, row = await _create(data_session, redis)
    await data_session.commit()
    sid = row.sid
    coordinator = AfterCommitCoordinator()

    assert await SsoSessionService.revoke(data_session, redis, sid, now=_NOW, coordinator=coordinator)
    await coordinator.rollback(data_session)
    assert redis.values
    assert coordinator.pending_count == 0
    restored = await SsoSessionDao.get_by_sid(data_session, sid)
    assert restored is not None and restored.status == 'active'


@pytest.mark.asyncio
async def test_commit_failure_does_not_run_registered_cleanup(
    data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """数据库 commit 失败时不执行缓存删除或撤销事件。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    _, row = await _create(data_session, redis)
    queue = AfterCommitCoordinator()
    assert await SsoSessionService.revoke(data_session, redis, row.sid, now=_NOW, coordinator=queue)

    async def fail_commit() -> None:
        raise RuntimeError('commit failed')

    monkeypatch.setattr(data_session, 'commit', fail_commit)
    with pytest.raises(RuntimeError):
        await queue.commit(data_session)
    assert redis.values
    assert not redis.published


@pytest.mark.asyncio
async def test_inactive_validation_only_cleans_cache_without_event(data_session: AsyncSession) -> None:
    """已撤销 Session 的验证只清理陈旧缓存，不重复发布撤销事件。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, row = await _create(data_session, redis)
    await SsoSessionDao.revoke(data_session, row.sid, reason='external', now=_NOW)
    await data_session.commit()
    queue = AfterCommitCoordinator()
    with pytest.raises(SsoSessionError):
        await SsoSessionService.validate(data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue)
    await queue.commit(data_session)
    assert not redis.published


@pytest.mark.asyncio
async def test_create_requires_uuid_and_positive_integer_ttls(data_session: AsyncSession) -> None:
    """Subject 必须为 RFC4122 UUID，TTL 拒绝零值和 bool。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    queue = AfterCommitCoordinator()
    config = _config()
    config.oidc_sso_idle_seconds = True
    with pytest.raises(SsoSessionError):
        await SsoSessionService.create(
            data_session,
            redis,
            1,
            _SUBJECT_ID,
            2,
            'pwd',
            ['pwd'],
            pepper=_PEPPER,
            now=_NOW,
            coordinator=queue,
        )
    config.oidc_sso_idle_seconds = 0
    with pytest.raises(SsoSessionError):
        await SsoSessionService.create(
            data_session,
            redis,
            1,
            _SUBJECT_ID,
            2,
            'pwd',
            ['pwd'],
            pepper=_PEPPER,
            now=_NOW,
            coordinator=queue,
        )


@pytest.mark.asyncio
async def test_create_rotate_touch_cache_writes_wait_for_commit(data_session: AsyncSession) -> None:
    """创建、轮换和 touch 在事务回滚时都不提前写入或删除缓存。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    queue = AfterCommitCoordinator()
    await SsoSessionService.create(
        data_session,
        redis,
        1,
        _SUBJECT_ID,
        2,
        'pwd',
        ['pwd'],
        pepper=_PEPPER,
        now=_NOW,
        coordinator=queue,
    )
    assert not redis.values
    await data_session.rollback()
    assert not redis.values

    await _seed_identity(data_session)
    cookie, _ = await _create(data_session, redis)
    queue = AfterCommitCoordinator()
    await SsoSessionService.rotate_cookie(data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue)
    assert redis.values
    await data_session.rollback()
    assert redis.values


@pytest.mark.asyncio
async def test_touch_cache_write_waits_for_commit(data_session: AsyncSession) -> None:
    """touch 的缓存刷新在事务回滚时不执行。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, _ = await _create(data_session, redis)
    queue = AfterCommitCoordinator()
    await SsoSessionService.touch(data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue)
    await data_session.rollback()
    assert redis.values


@pytest.mark.asyncio
async def test_after_commit_uses_snapshot_and_publishes_when_cache_clear_fails(
    data_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """提交后回调不读取 ORM 后续突变，缓存清理失败仍发布失效事件。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    coordinator = AfterCommitCoordinator()
    cookie, row = await SsoSessionService.create(
        data_session,
        redis,
        1,
        _SUBJECT_ID,
        2,
        'pwd',
        ['pwd'],
        pepper=_PEPPER,
        now=_NOW,
        coordinator=coordinator,
    )
    row.status = 'revoked'
    await coordinator.commit(data_session)
    sid, _ = OidcUtil.parse_sso_cookie(cookie)
    payload = json.loads(redis.values[OidcRedisKey.sso_session(sid)][0])
    assert payload['status'] == 'active'

    snapshot = SsoSessionService._snapshot(row)

    async def fail_clear(*args: object, **kwargs: object) -> None:
        raise RuntimeError('redis clear failed')

    monkeypatch.setattr(SsoSessionService, '_clear_cache', fail_clear)
    await SsoSessionService._best_effort_cleanup(redis, snapshot, reason='logout')
    assert redis.published


@pytest.mark.asyncio
async def test_user_status_and_cookie_response_security(data_session: AsyncSession) -> None:
    """停用用户 fail-closed，响应 Cookie 强制 __Host 安全属性。"""
    await _seed_identity(data_session)
    redis = SessionFakeRedis()
    cookie, _ = await _create(data_session, redis)
    user = await data_session.scalar(select(SysUser).where(SysUser.user_id == 1))
    user.status = '1'
    await data_session.flush()
    queue = AfterCommitCoordinator()
    with pytest.raises(SsoSessionError):
        await SsoSessionService.validate(data_session, redis, cookie, pepper=_PEPPER, now=_NOW, coordinator=queue)
    await queue.commit(data_session)
    response = Response()
    OidcUtil.parse_sso_cookie(cookie)
    response.set_cookie(value=cookie, **SsoSessionService.cookie_parameters())
    header = response.headers['set-cookie']
    assert 'Secure' in header and 'HttpOnly' in header and 'Path=/' in header and 'SameSite=lax' in header
    cleared = Response()
    cleared.delete_cookie(**SsoSessionService.cookie_parameters())
    clear_header = cleared.headers['set-cookie']
    assert '__Host-ruoyi-sso=' in clear_header
    assert 'Secure' in clear_header and 'HttpOnly' in clear_header and 'Path=/' in clear_header


def test_cookie_parser_rejects_noncanonical_sid_and_invalid_cookie_policy() -> None:
    """Cookie sid 必须是服务端生成的规范 UUID，清理也不得绕过安全策略。"""
    secret = 'a' * _COOKIE_SECRET_TEXT_LENGTH
    sid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    with pytest.raises(ValueError):
        OidcUtil.parse_sso_cookie(f'ss1.{sid.upper()}.{secret}')
    with pytest.raises(ValueError):
        OidcUtil.parse_sso_cookie(f'ss1.{sid.replace("-", "")}.{secret}')

    insecure = _config()
    insecure.oidc_sso_cookie_secure = False
    with pytest.raises(SsoSessionError):
        SsoSessionService.cookie_parameters()


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['validate', 'validate_logout_cookie'])
@pytest.mark.parametrize(
    ('cookie', 'pepper', 'message'),
    [
        ('malformed-cookie', _PEPPER, '会话 Cookie 格式无效'),
        (f'ss1.{_SUBJECT_ID}.{"a" * _COOKIE_SECRET_TEXT_LENGTH}', 'short', '会话摘要密钥至少需要 32 字节'),
    ],
)
async def test_session_entry_points_preserve_domain_errors_for_invalid_credentials(
    data_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    cookie: str,
    pepper: str,
    message: str,
) -> None:
    """直接调用工具后，格式错误和摘要配置错误仍按会话异常处理。"""
    monkeypatch.setattr(OidcConfig, 'oidc_token_hash_pepper', pepper)
    with pytest.raises(SsoSessionError, match=message):
        if operation == 'validate_logout_cookie':
            await SsoSessionService.validate_logout_cookie(data_session, cookie)
        else:
            await SsoSessionService.validate(
                data_session,
                SessionFakeRedis(),
                cookie,
                pepper=pepper,
                now=_NOW,
                coordinator=AfterCommitCoordinator(),
            )
