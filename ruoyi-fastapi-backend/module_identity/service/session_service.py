from __future__ import annotations

import asyncio
import hmac
import json
import logging
import secrets
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import uuid4

import jwt

from common.constant import OidcAuditEvent
from config.env import OidcConfig
from module_identity.dao.identity_subject_dao import IdentitySubjectDao
from module_identity.dao.identity_user_dao import IdentityUserDao
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_token_dao import OAuthTokenDao
from module_identity.dao.oidc_key_dao import OidcKeyDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.oauth_grant_do import SysSsoSession
from module_identity.redis_keys import OidcRedisKey
from module_identity.security.backchannel_transport import (
    BackchannelNotifier,
    PermanentBackchannelError,
    send_backchannel_once,
)
from module_identity.security.jwt_profile import (
    BACKCHANNEL_LOGOUT_EVENT,
    JwtProfileError,
    decode_id_token_hint,
    encode_logout_token,
)
from module_identity.security.uri_validator import (
    is_safe_backchannel_uri,
    public_dns_addresses,
    public_dns_only,
)
from module_identity.service.audit_service import AuditService
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.key_service import KeyService, KeyServiceError
from utils.oidc_util import OidcUtil
from utils.time_util import TimezoneUtil

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

_COOKIE_PREFIX = 'ss1'
_COOKIE_SECRET_BYTES = 32
_MAX_IP_ADDRESS_LENGTH = 128
_MAX_ACR_LENGTH = 100
_MAX_AMR_LENGTH = 50
_MAX_REMEMBER_SECONDS = 7 * 24 * 60 * 60
_SESSION_TTL_FIELDS = ('oidc_sso_idle_seconds', 'oidc_sso_absolute_seconds', 'oidc_sso_remember_absolute_seconds')
_SESSION_CACHE_TTL_FLOOR = 1
_SESSION_STATUS_ACTIVE = 'active'
_SESSION_STATUS_REVOKED = 'revoked'
_SESSION_STATUS_EXPIRED = 'expired'


class SsoSessionError(ValueError):
    """
    SSO Session 创建、校验和撤销错误类型
    """


@dataclass(frozen=True)
class SsoSessionSnapshot:
    """
    记录 SSO Session 缓存所需的不可变字段
    """

    sid: str
    user_id: int
    subject_id: str
    auth_version: int
    auth_time: datetime | None
    last_seen_at: datetime | None
    idle_expires_at: datetime | None
    absolute_expires_at: datetime | None
    acr: str
    amr: tuple[str, ...]
    remember_me: bool
    status: str
    session_secret_hash: str


class SsoSessionService:
    """
    OIDC SSO Session 模块服务层
    """

    @staticmethod
    def _require_coordinator(coordinator: AfterCommitCoordinator | None) -> AfterCommitCoordinator:
        """
        确认提交后副作用协调器可用

        :param coordinator: 只登记提交后副作用的协调器
        :return: 通过校验的协调器
        :raises SsoSessionError: 未提供有效协调器
        """

        if not isinstance(coordinator, AfterCommitCoordinator):
            raise SsoSessionError('缺少事务提交后副作用协调器')
        return coordinator

    @staticmethod
    def _validate_config_ttls() -> None:
        """
        检查会话相关 TTL 配置均为正整数

        :return: None
        :raises SsoSessionError: TTL 不是正整数
        """

        for field_name in _SESSION_TTL_FIELDS:
            value = getattr(OidcConfig, field_name, None)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SsoSessionError(f'{field_name} 必须为正整数')

    @staticmethod
    def _remaining_ttl(absolute_expires_at: datetime, now: datetime) -> int:
        """
        根据绝对过期时间计算 Redis 缓存剩余 TTL

        :param absolute_expires_at: Session 绝对过期时间
        :param now: 当前项目时间
        :return: 至少一秒的 Redis TTL
        :raises SsoSessionError: Session 已过期
        """

        seconds = int((absolute_expires_at - now).total_seconds())
        if seconds < _SESSION_CACHE_TTL_FLOOR:
            raise SsoSessionError('会话已过期')
        return seconds

    @classmethod
    def _snapshot(cls, row: SysSsoSession) -> SsoSessionSnapshot:
        """
        从 ORM 行提取不依赖数据库会话的 Session 快照

        :param row: 数据库 Session ORM 行
        :return: 不再依赖 ORM 生命周期的 Session 快照
        """

        return SsoSessionSnapshot(
            sid=row.sid,
            user_id=row.user_id,
            subject_id=row.subject_id,
            auth_version=row.auth_version,
            auth_time=TimezoneUtil.to_optional_utc(row.auth_time),
            last_seen_at=TimezoneUtil.to_optional_utc(row.last_seen_at),
            idle_expires_at=TimezoneUtil.to_optional_utc(row.idle_expires_at),
            absolute_expires_at=TimezoneUtil.to_optional_utc(row.absolute_expires_at),
            acr=row.acr,
            amr=tuple(row.amr or ()),
            remember_me=bool(row.remember_me),
            status=row.status,
            session_secret_hash=row.session_secret_hash,
        )

    @classmethod
    def _cache_payload(cls, row: SsoSessionSnapshot) -> dict[str, Any]:
        """
        将 Session 快照编码为 Redis 缓存载荷

        :param row: 数据库 Session
        :return: 可 JSON 序列化的缓存摘要
        """

        return {
            'sid': row.sid,
            'user_id': row.user_id,
            'subject_id': row.subject_id,
            'auth_version': row.auth_version,
            'auth_time': TimezoneUtil.to_optional_utc(row.auth_time).isoformat()
            if TimezoneUtil.to_optional_utc(row.auth_time)
            else None,
            'last_seen_at': TimezoneUtil.to_optional_utc(row.last_seen_at).isoformat()
            if TimezoneUtil.to_optional_utc(row.last_seen_at)
            else None,
            'idle_expires_at': TimezoneUtil.to_optional_utc(row.idle_expires_at).isoformat()
            if TimezoneUtil.to_optional_utc(row.idle_expires_at)
            else None,
            'absolute_expires_at': TimezoneUtil.to_optional_utc(row.absolute_expires_at).isoformat()
            if TimezoneUtil.to_optional_utc(row.absolute_expires_at)
            else None,
            'acr': row.acr,
            'amr': row.amr,
            'remember_me': row.remember_me,
            'status': row.status,
        }

    @classmethod
    async def _cache_row(cls, redis: Redis, row: SsoSessionSnapshot, now: datetime) -> None:
        """
        将 Session 快照写入会话、Cookie 和用户索引缓存

        :param redis: 异步 Redis 客户端
        :param row: SSO Session 快照
        :param now: 当前时间
        :return: None
        """

        ttl = cls._remaining_ttl(TimezoneUtil.to_optional_utc(row.absolute_expires_at) or now, now)
        payload = json.dumps(cls._cache_payload(row), ensure_ascii=False, separators=(',', ':'))
        await redis.set(OidcRedisKey.sso_session(row.sid), payload, ex=ttl)
        await redis.set(OidcRedisKey.sso_cookie(row.session_secret_hash), row.sid, ex=ttl)
        user_sessions_key = OidcRedisKey.user_sessions(row.user_id)
        await redis.sadd(user_sessions_key, row.sid)
        current_ttl = await redis.ttl(user_sessions_key)
        if current_ttl < ttl:
            await redis.expire(user_sessions_key, ttl)

    @classmethod
    async def _clear_cache(cls, redis: Redis, row: SsoSessionSnapshot, extra_secret_hash: str | None = None) -> None:
        """
        删除 Session、Cookie 和用户索引缓存

        :param redis: 异步 Redis 客户端
        :param row: SSO Session 快照
        :param extra_secret_hash: 需要额外清理的 Cookie Secret 摘要
        :return: None
        """

        hashes = {row.session_secret_hash}
        if extra_secret_hash:
            hashes.add(extra_secret_hash)
        await redis.delete(OidcRedisKey.sso_session(row.sid))
        await redis.srem(OidcRedisKey.user_sessions(row.user_id), row.sid)
        for digest in hashes:
            await redis.delete(OidcRedisKey.sso_cookie(digest))

    @classmethod
    async def _publish_revoked(cls, redis: Redis, sid: str, reason: str) -> None:
        """
        发布 Session 已撤销事件

        :param redis: 异步 Redis 客户端
        :param sid: Session 标识
        :param reason: 撤销原因
        :return: None
        """

        await redis.publish(
            OidcRedisKey.event_session_revoked(),
            json.dumps({'event': 'session_revoked', 'sid': sid, 'reason': reason}, separators=(',', ':')),
        )

    @classmethod
    async def _best_effort_cleanup(
        cls,
        redis: Redis,
        row: SsoSessionSnapshot,
        *,
        presented_digest: str | None = None,
        reason: str | None = None,
    ) -> None:
        """
        尽力清理 Session 缓存并发布撤销事件

        :param redis: 异步 Redis 客户端
        :param row: SSO Session 快照
        :param presented_digest: 当前 Cookie 摘要
        :param reason: 撤销原因
        :return: None
        """

        try:
            await cls._clear_cache(redis, row, presented_digest)
        except Exception:
            pass
        if reason is not None:
            try:
                await cls._publish_revoked(redis, row.sid, reason)
            except Exception:
                pass

    @classmethod
    async def create(  # noqa: PLR0913
        cls,
        db: AsyncSession,
        redis: Redis,
        user_id: int,
        subject_id: str,
        auth_version: int,
        acr: str,
        amr: Sequence[str],
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        remember_me: bool = False,
        pepper: str | bytes = OidcConfig.oidc_token_hash_pepper,
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> tuple[str, SysSsoSession]:
        """
        校验身份状态并创建 SSO Session 与 Cookie

        :param db: 异步数据库会话，调用方负责提交事务
        :param redis: Redis 热缓存客户端
        :param user_id: 本地用户 ID
        :param subject_id: 稳定 OIDC Subject
        :param auth_version: 创建时的身份安全版本
        :param acr: 认证上下文
        :param amr: 认证方式列表
        :param ip_address: 登录来源 IP
        :param user_agent: 登录 User-Agent，仅保存摘要
        :param remember_me: 是否使用 remember-me 绝对 TTL
        :param pepper: OIDC Token Pepper
        :param now: 可注入当前项目时间
        :param coordinator: 必须由调用方在数据库提交成功后执行缓存写入
        :return: ``(Cookie 原文, 数据库 Session)``
        :raises SsoSessionError: Session 状态或事务操作不符合要求
        """

        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        coordinator = cls._require_coordinator(coordinator)
        cls._validate_config_ttls()
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise SsoSessionError('用户编号 user_id 无效')
        if not isinstance(subject_id, str) or not OidcUtil.is_rfc4122_uuid(subject_id):
            raise SsoSessionError('用户主体标识 subject_id 无效')
        if not isinstance(auth_version, int) or isinstance(auth_version, bool) or auth_version < 1:
            raise SsoSessionError('身份安全版本 auth_version 无效')
        if not isinstance(acr, str) or not acr.strip() or len(acr) > _MAX_ACR_LENGTH:
            raise SsoSessionError('认证上下文 acr 无效')
        if not isinstance(amr, Sequence) or isinstance(amr, (str, bytes)) or not amr:
            raise SsoSessionError('认证方式列表 amr 无效')
        if any(not isinstance(item, str) or not item.strip() or len(item) > _MAX_AMR_LENGTH for item in amr):
            raise SsoSessionError('认证方式列表 amr 无效')
        if not isinstance(remember_me, bool):
            raise SsoSessionError('保持登录标识 remember_me 无效')
        if ip_address is not None and (not isinstance(ip_address, str) or len(ip_address) > _MAX_IP_ADDRESS_LENGTH):
            raise SsoSessionError('IP 地址无效')
        try:
            OidcUtil.session_pepper_bytes(pepper)
        except ValueError as exc:
            raise SsoSessionError(str(exc)) from exc
        user = await IdentityUserDao.get_user(db, user_id)
        subject = await IdentitySubjectDao.get_by_user_id(db, user_id)
        if (
            user is None
            or user.status != '0'
            or user.del_flag != '0'
            or subject is None
            or subject.subject_id != subject_id
            or subject.auth_version != auth_version
        ):
            raise SsoSessionError('用户身份安全状态无效')
        absolute_seconds = OidcConfig.oidc_sso_absolute_seconds
        if remember_me:
            absolute_seconds = min(OidcConfig.oidc_sso_remember_absolute_seconds, _MAX_REMEMBER_SECONDS)
        absolute = current + timedelta(seconds=absolute_seconds)
        idle = min(current + timedelta(seconds=OidcConfig.oidc_sso_idle_seconds), absolute)
        sid = str(uuid4())
        secret = secrets.token_urlsafe(_COOKIE_SECRET_BYTES)
        try:
            secret_hash = OidcUtil.session_secret_digest(secret, pepper)
            user_agent_hash = OidcUtil.session_user_agent_digest(user_agent, pepper)
        except ValueError as exc:
            raise SsoSessionError(str(exc)) from exc
        row = SysSsoSession(
            sid=sid,
            session_secret_hash=secret_hash,
            user_id=user_id,
            subject_id=subject_id,
            auth_version=auth_version,
            auth_time=current,
            last_seen_at=current,
            idle_expires_at=idle,
            absolute_expires_at=absolute,
            acr=acr,
            amr=list(amr),
            remember_me=int(remember_me),
            ip_address=ip_address,
            user_agent_hash=user_agent_hash,
            status=_SESSION_STATUS_ACTIVE,
        )
        row = await SsoSessionDao.create(db, row)
        snapshot = cls._snapshot(row)

        async def cache_after_commit() -> None:
            """
            在事务提交后写入新建 Session 的缓存

            :return: None
            """

            try:
                await cls._cache_row(redis, snapshot, current)
            except Exception:
                pass

        await coordinator.register(cache_after_commit)

        return f'{_COOKIE_PREFIX}.{sid}.{secret}', row

    @classmethod
    async def validate_logout_cookie(cls, db: AsyncSession, cookie: str) -> SysSsoSession:
        """
        校验退出确认时的浏览器会话归属

        允许用户显式退出自然过期的会话，并继续撤销其关联离线授权。

        :param db: orm对象
        :param cookie: 浏览器提交的SSO Cookie
        :return: 已校验归属的SSO会话
        :raises SsoSessionError: 会话不存在、已撤销或凭据不匹配
        """

        try:
            sid, secret = OidcUtil.parse_sso_cookie(cookie)
            digest = OidcUtil.session_secret_digest(secret, OidcConfig.oidc_token_hash_pepper)
        except ValueError as exc:
            raise SsoSessionError(str(exc)) from exc
        row = await SsoSessionDao.get_by_sid(db, sid, for_update=True)
        if (
            row is None
            or row.status not in {'active', 'expired'}
            or not hmac.compare_digest(row.session_secret_hash, digest)
        ):
            raise SsoSessionError('会话 Cookie 无效')
        return row

    @classmethod
    async def validate(  # noqa: PLR0915
        cls,
        db: AsyncSession,
        redis: Redis,
        cookie: str,
        *,
        pepper: str | bytes = OidcConfig.oidc_token_hash_pepper,
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> SysSsoSession:
        """
        验证 Cookie、Session 有效期和用户身份安全版本

        :param db: 异步数据库会话
        :param redis: Redis 热缓存客户端
        :param cookie: 客户端 Cookie 原文
        :param pepper: OIDC Token Pepper
        :param now: 可注入当前项目时间
        :param coordinator: 必须由调用方在数据库提交成功后执行缓存清理或失效事件
        :return: 已验证的数据库 Session
        :raises SsoSessionError: Cookie 或任何安全状态校验失败
        """

        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        coordinator = cls._require_coordinator(coordinator)
        try:
            sid, secret = OidcUtil.parse_sso_cookie(cookie)
            digest = OidcUtil.session_secret_digest(secret, pepper)
        except ValueError as exc:
            raise SsoSessionError(str(exc)) from exc
        try:
            await redis.get(OidcRedisKey.sso_cookie(digest))
        except Exception:
            pass
        row = await SsoSessionDao.get_by_sid(db, sid)
        if row is None:

            async def clear_missing_cookie() -> None:
                """
                在 Session 不存在时删除 Cookie 索引

                :return: None
                """

                try:
                    await redis.delete(OidcRedisKey.sso_cookie(digest))
                except Exception:
                    pass

            await coordinator.register(clear_missing_cookie)
            raise SsoSessionError('会话不存在')
        if not hmac.compare_digest(row.session_secret_hash, digest):

            async def clear_presented_cookie() -> None:
                """
                在 Cookie Secret 不匹配时删除当前索引

                :return: None
                """

                try:
                    await redis.delete(OidcRedisKey.sso_cookie(digest))
                except Exception:
                    pass

            await coordinator.register(clear_presented_cookie)
            raise SsoSessionError('会话密钥无效')
        absolute = TimezoneUtil.to_optional_utc(row.absolute_expires_at)
        idle = TimezoneUtil.to_optional_utc(row.idle_expires_at)
        if (
            row.status != _SESSION_STATUS_ACTIVE
            or absolute is None
            or idle is None
            or idle <= current
            or absolute <= current
        ):
            if row.status == _SESSION_STATUS_ACTIVE and absolute is not None and idle is not None:
                await SsoSessionDao.expire(db, row.sid, now=current)
                row.status = _SESSION_STATUS_EXPIRED
                snapshot = cls._snapshot(row)

                async def clear_expired() -> None:
                    """
                    在 Session 到期后清理缓存

                    :return: None
                    """

                    await cls._best_effort_cleanup(redis, snapshot, presented_digest=digest)

                await coordinator.register(clear_expired)
            else:
                await cls._invalidate(db, redis, row, digest, 'expired_or_inactive', current, coordinator)
            raise SsoSessionError('会话已过期或已失效')
        user = await IdentityUserDao.get_user(db, row.user_id)
        subject = await IdentitySubjectDao.get_by_user_id(db, row.user_id)
        if (
            user is None
            or user.status != '0'
            or user.del_flag != '0'
            or subject is None
            or subject.subject_id != row.subject_id
            or subject.auth_version != row.auth_version
        ):
            await cls._invalidate(db, redis, row, digest, 'identity_security_changed', current, coordinator)
            raise SsoSessionError('用户身份安全状态无效')

        snapshot = cls._snapshot(row)

        async def refresh_cache() -> None:
            """
            在校验成功后刷新 Session 缓存

            :return: None
            """

            try:
                await cls._cache_row(redis, snapshot, current)
            except Exception:
                pass

        await coordinator.register(refresh_cache)

        return row

    @classmethod
    async def _invalidate(
        cls,
        db: AsyncSession,
        redis: Redis,
        row: SysSsoSession,
        presented_digest: str,
        reason: str,
        now: datetime,
        coordinator: AfterCommitCoordinator,
    ) -> None:
        """
        将无效 Session 标记为撤销并登记提交后清理动作

        :param db: 异步数据库会话
        :param redis: 异步 Redis 客户端
        :param row: SSO Session ORM 记录
        :param presented_digest: 当前 Cookie 摘要
        :param reason: 撤销原因
        :param now: 当前时间
        :param coordinator: 事务提交协调器
        :return: None
        """

        changed = False
        if row.status == _SESSION_STATUS_ACTIVE:
            changed = await SsoSessionDao.revoke(db, row.sid, reason=reason, now=now)
            if changed:
                await AuditService.record(
                    db,
                    OidcAuditEvent.SESSION_REVOKED,
                    'success',
                    risk_level='high',
                    sid=row.sid,
                    user_id=row.user_id,
                    subject_id=row.subject_id,
                    detail={'reason': reason},
                )
        snapshot = cls._snapshot(row)

        async def cleanup() -> None:
            """
            在撤销或过期后清理 Session 缓存

            :return: None
            """

            await cls._best_effort_cleanup(
                redis,
                snapshot,
                presented_digest=presented_digest,
                reason=reason if changed else None,
            )

        await coordinator.register(cleanup)

    @classmethod
    async def touch(
        cls,
        db: AsyncSession,
        redis: Redis,
        cookie: str,
        *,
        pepper: str | bytes = OidcConfig.oidc_token_hash_pepper,
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> SysSsoSession:
        """
        刷新活动 Session 的最近访问时间和空闲过期时间

        :param db: 异步数据库会话
        :param redis: Redis 热缓存客户端
        :param cookie: 当前 Cookie 原文
        :param pepper: OIDC Token Pepper
        :param now: 可注入当前项目时间
        :param coordinator: 必须由调用方在数据库提交成功后执行缓存更新
        :return: 更新后的数据库 Session
        :raises SsoSessionError: Session 状态或事务操作不符合要求
        """

        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        coordinator = cls._require_coordinator(coordinator)
        cls._validate_config_ttls()
        row = await cls.validate(db, redis, cookie, pepper=pepper, now=current, coordinator=coordinator)
        absolute = TimezoneUtil.to_optional_utc(row.absolute_expires_at)
        if absolute is None:
            raise SsoSessionError('会话缺少绝对到期时间')
        idle = min(current + timedelta(seconds=OidcConfig.oidc_sso_idle_seconds), absolute)
        if not await SsoSessionDao.touch(db, row.sid, idle, now=current):
            raise SsoSessionError('会话续期被拒绝')
        refreshed = await SsoSessionDao.get_by_sid(db, row.sid)
        if refreshed is None:
            raise SsoSessionError('续期后的会话记录不存在')
        snapshot = cls._snapshot(refreshed)

        async def refresh_cache() -> None:
            """
            在校验成功后刷新 Session 缓存

            :return: None
            """

            try:
                await cls._cache_row(redis, snapshot, current)
            except Exception:
                pass

        await coordinator.register(refresh_cache)

        return refreshed

    @classmethod
    async def rotate_cookie(
        cls,
        db: AsyncSession,
        redis: Redis,
        cookie: str,
        *,
        pepper: str | bytes = OidcConfig.oidc_token_hash_pepper,
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> str:
        """
        轮换 Session Cookie Secret 并更新缓存索引

        :param db: 异步数据库会话
        :param redis: Redis 热缓存客户端
        :param cookie: 旧 Cookie 原文
        :param pepper: OIDC Token Pepper
        :param now: 可注入当前项目时间
        :param coordinator: 必须由调用方在数据库提交成功后执行缓存更新
        :return: 新 Cookie 原文
        :raises SsoSessionError: Session 状态或事务操作不符合要求
        """

        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        coordinator = cls._require_coordinator(coordinator)
        row = await cls.validate(db, redis, cookie, pepper=pepper, now=current, coordinator=coordinator)
        try:
            sid, old_secret = OidcUtil.parse_sso_cookie(cookie)
            new_secret = secrets.token_urlsafe(_COOKIE_SECRET_BYTES)
            old_digest = OidcUtil.session_secret_digest(old_secret, pepper)
            new_digest = OidcUtil.session_secret_digest(new_secret, pepper)
        except ValueError as exc:
            raise SsoSessionError(str(exc)) from exc
        if not await SsoSessionDao.rotate_secret(db, sid, old_digest, new_digest, now=current):
            raise SsoSessionError('会话 Cookie 轮换被拒绝')
        row.session_secret_hash = new_digest
        snapshot = cls._snapshot(row)

        async def refresh_rotated_cache() -> None:
            """
            在 Cookie 轮换后更新新旧缓存索引

            :return: None
            """

            try:
                await redis.delete(OidcRedisKey.sso_cookie(old_digest))
                await cls._cache_row(redis, snapshot, current)
            except Exception:
                pass

        await coordinator.register(refresh_rotated_cache)

        return f'{_COOKIE_PREFIX}.{sid}.{new_secret}'

    @classmethod
    async def revoke(
        cls,
        db: AsyncSession,
        redis: Redis,
        sid: str,
        *,
        reason: str = 'logout',
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> bool:
        """
        撤销指定 Session 并清理其 Cookie 凭据

        :param db: 异步数据库会话
        :param redis: Redis 热缓存客户端
        :param sid: 要撤销的 Session 标识
        :param reason: 撤销原因
        :param now: 可注入当前项目时间
        :param coordinator: 必须由调用方在数据库提交成功后执行清理闭包
        :return: 数据库状态实际改变时返回 True
        """

        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        coordinator = cls._require_coordinator(coordinator)
        row = await SsoSessionDao.get_by_sid(db, sid, for_update=True)
        if row is None:
            return False
        changed = await SsoSessionDao.revoke(db, sid, reason=reason, now=current)
        if changed:
            await AuditService.record(
                db,
                OidcAuditEvent.SESSION_REVOKED,
                'success',
                risk_level='high',
                sid=row.sid,
                user_id=row.user_id,
                subject_id=row.subject_id,
                detail={'reason': reason},
            )
        snapshot = cls._snapshot(row)

        async def cleanup() -> None:
            """
            在撤销或过期后清理 Session 缓存

            :return: None
            """

            await cls._best_effort_cleanup(redis, snapshot, reason=reason if changed else None)

        await coordinator.register(cleanup)

        return changed

    @classmethod
    async def revoke_user(
        cls,
        db: AsyncSession,
        redis: Redis,
        user_id: int,
        *,
        reason: str = 'logout_all',
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> int:
        """
        撤销指定用户全部在线及自然过期的 Session，终止其离线访问

        :param db: 异步数据库会话
        :param redis: Redis 热缓存客户端
        :param user_id: 本地用户 ID
        :param reason: 撤销原因
        :param now: 可注入当前项目时间
        :param coordinator: 必须由调用方在数据库提交成功后执行清理闭包
        :return: 数据库更新的 Session 数量
        """

        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        coordinator = cls._require_coordinator(coordinator)
        rows = list(await SsoSessionDao.list_for_user(db, user_id, for_update=True, revocable_only=True))
        changed_snapshots: list[SsoSessionSnapshot] = []
        for row in rows:
            if await SsoSessionDao.revoke(db, row.sid, reason=reason, now=current):
                changed_snapshots.append(cls._snapshot(row))
                await AuditService.record(
                    db,
                    OidcAuditEvent.SESSION_REVOKED,
                    'success',
                    risk_level='high',
                    sid=row.sid,
                    user_id=row.user_id,
                    subject_id=row.subject_id,
                    detail={'reason': reason},
                )

        async def cleanup() -> None:
            """
            在撤销或过期后清理 Session 缓存

            :return: None
            """

            for snapshot in changed_snapshots:
                await cls._best_effort_cleanup(redis, snapshot, reason=reason)

        await coordinator.register(cleanup)

        return len(changed_snapshots)

    @classmethod
    async def expire_due(
        cls,
        db: AsyncSession,
        redis: Redis,
        *,
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> int:
        """
        批量标记已到期的 Session 并登记缓存清理

        :param db: 异步数据库会话
        :param redis: Redis 热缓存客户端
        :param now: 可注入当前项目时间
        :param coordinator: 必须由调用方在数据库提交成功后执行缓存清理
        :return: 数据库更新数量
        """

        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        coordinator = cls._require_coordinator(coordinator)
        rows = list(await SsoSessionDao.list_due(db, now=current, for_update=True))
        changed_snapshots: list[SsoSessionSnapshot] = []
        for row in rows:
            if await SsoSessionDao.expire(db, row.sid, now=current):
                changed_snapshots.append(cls._snapshot(row))  # noqa: PERF401

        async def cleanup() -> None:
            """
            在撤销或过期后清理 Session 缓存

            :return: None
            """

            for snapshot in changed_snapshots:
                await cls._best_effort_cleanup(redis, snapshot)

        await coordinator.register(cleanup)

        return len(changed_snapshots)

    @classmethod
    def cookie_max_age(cls, session: SysSsoSession, *, now: datetime | None = None) -> int | None:
        """
        根据 Session 的绝对过期时间计算保持登录 Cookie 的剩余寿命

        :param session: 当前 SSO Session ORM
        :param now: 可注入当前项目时间
        :return: 保持登录 Cookie 的剩余秒数，普通登录返回 None
        :raises SsoSessionError: Session 缺少绝对过期时间或已过期
        """

        if not session.remember_me:
            return None
        absolute = TimezoneUtil.to_optional_utc(session.absolute_expires_at)
        if absolute is None:
            raise SsoSessionError('会话缺少绝对到期时间')
        return cls._remaining_ttl(absolute, TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now())

    @staticmethod
    def cookie_parameters(*, max_age: int | None = None) -> dict[str, str | bool | int]:
        """
        根据配置构造 SSO Cookie 的 HTTP 属性

        :param max_age: 可选 Cookie 最大寿命秒数
        :return: 由 Controller 传给 HTTP Response 的 Cookie 参数
        :raises SsoSessionError: Logout Session 校验失败
        """

        if not OidcConfig.oidc_sso_cookie_name.startswith('__Host-') or not OidcConfig.oidc_sso_cookie_secure:
            raise SsoSessionError('使用 __Host- 前缀的单点登录 Cookie 必须启用 Secure')
        if OidcConfig.oidc_sso_cookie_domain or OidcConfig.oidc_sso_cookie_samesite != 'lax':
            raise SsoSessionError('单点登录 Cookie 的安全配置无效')
        if max_age is not None and (isinstance(max_age, bool) or not isinstance(max_age, int) or max_age <= 0):
            raise SsoSessionError('单点登录 Cookie 的有效期无效')
        parameters: dict[str, str | bool | int] = {
            'key': OidcConfig.oidc_sso_cookie_name,
            'path': '/',
            'secure': True,
            'httponly': True,
            'samesite': 'lax',
        }
        if max_age is not None:
            parameters['max_age'] = max_age
        return parameters


LOGGER = logging.getLogger(__name__)
_RS256 = 'RS256'
_ID_TOKEN_TYPE = 'JWT'
_REMOTE_HEADERS = frozenset({'jku', 'x5u', 'jwk', 'x5c', 'crit'})
_VERIFYING_KEY_STATUSES = ('active', 'retiring')
_URI_BACKCHANNEL = 'backchannel_logout'
_URI_POST_LOGOUT = 'post_logout'
_MAX_STATE_LENGTH = 2048
_LOGOUT_TOKEN_TTL_SECONDS = 120
_BACKCHANNEL_TIMEOUT_SECONDS = 5.0
_MAX_BACKCHANNEL_TIMEOUT_SECONDS = 30.0
_BACKCHANNEL_MAX_ATTEMPTS = 3
_BACKCHANNEL_RETRY_DELAY_SECONDS = 0.05
_BACKCHANNEL_MAX_CONCURRENCY = 8
_JWT_DOT_COUNT = 2
_BACKCHANNEL_MAX_QUEUE_ATTEMPTS = 5
_BACKCHANNEL_MAX_QUEUE_ITEMS = 32
_BACKCHANNEL_QUEUE_MAX_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class LogoutResult:
    """
    记录 RP-Initiated Logout 的重定向结果和错误信息
    """

    redirect_uri: str | None
    state: str | None
    session_revoked: bool

    @property
    def is_local(self) -> bool:
        """
        判断退出回调是否指向本地地址

        :return: LogoutResult 未提供重定向 URI 时是否在本地完成退出
        """

        return self.redirect_uri is None


class LogoutServiceError(ValueError):
    """
    RP-Initiated Logout 参数或回调校验错误类型
    """


BackchannelAuditWriter = Callable[..., Awaitable[None]]
BackchannelRetryQueue = Callable[..., Awaitable[None]]


class LogoutService:
    """
    OIDC Logout 模块服务层
    """

    @classmethod
    async def execute_logout(  # noqa: PLR0913
        cls,
        db: AsyncSession,
        redis: Redis,
        *,
        id_token_hint: str | None = None,
        cookie: str | None = None,
        post_logout_redirect_uri: str | None = None,
        state: str | None = None,
        confirmed: bool = False,
        now: datetime | None = None,
        signing_key: RSAPrivateKey | None = None,
        signing_kid: str | None = None,
        notifier: BackchannelNotifier | None = None,
        audit_writer: BackchannelAuditWriter | None = None,
        retry_queue: BackchannelRetryQueue | None = None,
    ) -> LogoutResult:
        """
        编排 RP-Initiated Logout 的校验、撤销和响应

        :param db: 异步数据库会话
        :param redis: SSO 热缓存客户端
        :param id_token_hint: OIDC ID Token Hint
        :param cookie: 当前 SSO Cookie
        :param post_logout_redirect_uri: 请求的退出后重定向 URI
        :param state: 仅在重定向 URI 验证成功后返回的状态值
        :param now: 可注入的 项目当前时间
        :param signing_key: 测试或受控部署注入的 RSA 私钥
        :param signing_kid: 注入私钥对应的 kid
        :param notifier: 提交后的 Back-Channel 通知回调
        :param audit_writer: Back-Channel 失败审计回调
        :param retry_queue: Back-Channel 重试队列回调
        :param confirmed: 是否已通过当前浏览器的一次性退出确认
        :return: 不包含敏感材料的退出结果
        :raises Exception: 核心流程或数据库提交失败时原样抛出异常
        """

        coordinator = AfterCommitCoordinator()
        try:
            result = await cls._logout(
                db,
                redis,
                id_token_hint=id_token_hint,
                cookie=cookie,
                post_logout_redirect_uri=post_logout_redirect_uri,
                state=state,
                confirmed=confirmed,
                now=now,
                coordinator=coordinator,
                signing_key=signing_key,
                signing_kid=signing_kid,
                notifier=notifier,
                audit_writer=audit_writer,
                retry_queue=retry_queue,
            )
            await coordinator.commit(db)
            return result
        except Exception:
            try:
                await coordinator.rollback(db)
            except Exception:
                pass
            raise

    @classmethod
    async def _logout(  # noqa: PLR0912, PLR0913, PLR0915
        cls,
        db: AsyncSession,
        redis: Redis,
        *,
        id_token_hint: str | None = None,
        cookie: str | None = None,
        post_logout_redirect_uri: str | None = None,
        state: str | None = None,
        confirmed: bool = False,
        now: datetime | None = None,
        coordinator: AfterCommitCoordinator,
        signing_key: RSAPrivateKey | None = None,
        signing_kid: str | None = None,
        notifier: BackchannelNotifier | None = None,
        audit_writer: BackchannelAuditWriter | None = None,
        retry_queue: BackchannelRetryQueue | None = None,
    ) -> LogoutResult:
        """
        在事务中处理 Logout Hint、Session 撤销和通知登记

        :param db: 异步数据库会话；事务由公共编排入口提交或回滚
        :param redis: SSO 热缓存客户端，仅传递给 Session 服务
        :param id_token_hint: OIDC ID Token Hint，不会写入日志或响应
        :param cookie: 当前 ``__Host-`` SSO Cookie
        :param post_logout_redirect_uri: 待精确匹配的注册退出 URI
        :param state: 仅在 URI 已验证后附加的原始状态值
        :param now: 可注入的当前项目时间
        :param coordinator: 提交后副作用协调器
        :param signing_key: 测试或受控部署注入的 RSA 私钥
        :param signing_kid: 注入私钥对应的 kid
        :param notifier: 提交后的 Back-Channel 通知回调
        :param audit_writer: 审计写入回调
        :param retry_queue: 重试队列回调
        :param confirmed: 是否已通过当前浏览器的一次性退出确认
        :return: 不包含敏感材料的退出结果
        :raises LogoutServiceError: 请求违反安全边界
        """

        if not OidcConfig.oidc_enabled:
            raise LogoutServiceError('统一认证中心未启用')
        if not confirmed:
            raise LogoutServiceError('请在浏览器中确认退出操作')
        commit_coordinator = coordinator
        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        if state is not None and (not isinstance(state, str) or len(state) > _MAX_STATE_LENGTH):
            state = None
        session = None
        client = None
        validated_redirect: str | None = None
        hint_valid = False
        if id_token_hint:
            try:
                claims, client = await cls._validate_id_token_hint(db, id_token_hint, current)
                hint_valid = True
            except (JwtProfileError, KeyServiceError, LogoutServiceError, TypeError, ValueError, jwt.PyJWTError):
                client = None
            if hint_valid:
                sid = claims['sid']
                session = await SsoSessionDao.get_by_sid(db, sid, for_update=True)
            if hint_valid and (
                session is None or session.status not in {'active', 'expired'} or session.subject_id != claims['sub']
            ):
                session = None
                hint_valid = False
            if hint_valid and post_logout_redirect_uri and OidcUtil.is_safe_post_logout_uri(post_logout_redirect_uri):
                registered = await OAuthClientDao.find_exact_uri(
                    db, client.client_pk, _URI_POST_LOGOUT, post_logout_redirect_uri
                )
                if registered is not None and registered.status == '0':
                    validated_redirect = post_logout_redirect_uri
                else:
                    state = None
            elif hint_valid and post_logout_redirect_uri:
                state = None
        browser_session = None
        if cookie:
            try:
                browser_session = await SsoSessionService.validate_logout_cookie(db, cookie)
            except (SsoSessionError, TypeError, ValueError):
                browser_session = None
        if browser_session is not None:
            if session is None or session.sid != browser_session.sid:
                # 其他账号的退出提示不得用于终止该账号会话
                validated_redirect = None
                client = None
            session = browser_session
        if session is None:
            return LogoutResult(None, None, False)

        refresh_rows = await cls._lock_session_refresh_tokens(db, session.sid)
        client_ids = {row.client_pk for row in refresh_rows}
        if client is not None:
            client_ids.add(client.client_pk)
        for participant_id in await SsoSessionDao.client_ids_for_sid(db, session.sid):
            participant = await OAuthClientDao.get_by_client_id(db, participant_id, active_only=True)
            if participant is not None:
                client_ids.add(participant.client_pk)
        await cls._revoke_session_state(db, redis, session.sid, refresh_rows, current, commit_coordinator)
        await cls._register_backchannel(
            db,
            redis,
            session.sid,
            client_ids,
            now=current,
            coordinator=commit_coordinator,
            signing_key=signing_key,
            signing_kid=signing_kid,
            notifier=notifier,
            audit_writer=audit_writer,
            retry_queue=retry_queue,
        )

        return LogoutResult(validated_redirect, state if validated_redirect else None, True)

    @classmethod
    async def _validate_id_token_hint(cls, db: AsyncSession, token: str, now: datetime) -> tuple[dict[str, Any], Any]:
        """
        验证 ID Token Hint 的签名、发行者和 Session 绑定

        :param db: 异步数据库会话
        :param token: 令牌值
        :param now: 当前时间
        :return: 包含协议字段的字典
        :raises LogoutServiceError: Logout 参数或回调地址不符合要求
        """

        if not isinstance(token, str) or not token or token.count('.') != _JWT_DOT_COUNT:
            raise LogoutServiceError('退出请求中的身份令牌提示 id_token_hint 无效')
        try:
            header = jwt.get_unverified_header(token)
            if (
                header.get('alg') != _RS256
                or header.get('typ') != _ID_TOKEN_TYPE
                or _REMOTE_HEADERS.intersection(header)
                or not isinstance(header.get('kid'), str)
                or not header['kid']
            ):
                raise LogoutServiceError('身份令牌提示 id_token_hint 的头部无效')
            unverified = jwt.decode(token, options={'verify_signature': False, 'verify_aud': False})
            audience = unverified.get('aud')
            if not isinstance(audience, str) or not audience:
                raise LogoutServiceError('身份令牌的受众无效')
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            raise LogoutServiceError('退出请求中的身份令牌提示 id_token_hint 无效') from exc
        client = await OAuthClientDao.get_by_client_id(db, audience, active_only=True)
        if client is None or client.status != '0':
            raise LogoutServiceError('身份令牌的受众不是有效客户端')
        key_record = await OidcKeyDao.get_verifying(db, header['kid'], now)
        if key_record is None or key_record.status not in _VERIFYING_KEY_STATUSES:
            raise LogoutServiceError('签名密钥不存在或不可用')
        public_jwk = OidcUtil.normalize_public_jwk(key_record)
        verification_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(public_jwk, separators=(',', ':')))
        claims = decode_id_token_hint(
            token,
            verification_key=verification_key,
            issuer=OidcConfig.oidc_issuer.rstrip('/'),
            audience=client.client_id,
            clock_skew=OidcConfig.oidc_allowed_clock_skew_seconds,
        )

        return claims, client

    @classmethod
    async def _lock_session_refresh_tokens(cls, db: AsyncSession, sid: str) -> list[Any]:
        """
        锁定指定 Session 关联的 Refresh Token 记录

        :param db: 异步数据库会话
        :param sid: Session 标识
        :return: 规范化后的列表
        """

        return list(await OAuthTokenDao.list_for_sid_for_update(db, sid))

    @classmethod
    async def _revoke_session_state(
        cls,
        db: AsyncSession,
        redis: Redis,
        sid: str,
        refresh_rows: list[Any],
        now: datetime,
        coordinator: AfterCommitCoordinator,
    ) -> None:
        """
        标记 Session 及其 Refresh Token 为撤销并登记缓存清理

        :param db: 异步数据库会话
        :param redis: 异步 Redis 客户端
        :param sid: Session 标识
        :param refresh_rows: Refresh 记录集合
        :param now: 当前时间
        :param coordinator: 事务提交协调器
        :return: None
        """

        await SsoSessionService.revoke(db, redis, sid, reason='rp_initiated_logout', now=now, coordinator=coordinator)
        for family_id in {row.family_id for row in refresh_rows}:
            await OAuthTokenDao.revoke_family(db, family_id, reason='rp_initiated_logout')

    @classmethod
    async def _register_backchannel(  # noqa: PLR0913
        cls,
        db: AsyncSession,
        redis: Redis,
        sid: str,
        client_pks: set[int],
        *,
        now: datetime,
        coordinator: AfterCommitCoordinator,
        signing_key: RSAPrivateKey | None,
        signing_kid: str | None,
        notifier: BackchannelNotifier | None,
        audit_writer: BackchannelAuditWriter | None,
        retry_queue: BackchannelRetryQueue | None,
    ) -> None:
        """
        为已撤销 Session 登记各 Client 的 Back-Channel 通知

        :param db: 异步数据库会话
        :param redis: 异步 Redis 客户端
        :param sid: Session 标识
        :param client_pks: 客户端主键集合
        :param now: 当前时间
        :param coordinator: 事务提交协调器
        :param signing_key: 签名密钥
        :param signing_kid: 签名密钥标识
        :param notifier: 通知器
        :param audit_writer: 审计写入回调
        :param retry_queue: 重试队列回调
        :return: None
        """

        effective_retry_queue = retry_queue or cls._redis_retry_queue(redis)
        effective_audit_writer = audit_writer or cls._audit_writer(db)
        callbacks: list[Callable[[], Awaitable[None]]] = []
        for client_pk in client_pks:
            client = await OAuthClientDao.get_by_pk(db, client_pk, active_only=True)
            if client is None:
                continue
            uris = await OAuthClientDao.list_uris(db, client_pk, uri_type=_URI_BACKCHANNEL, active_only=True)
            session = await SsoSessionDao.get_by_sid(db, sid)
            subject_id = getattr(session, 'subject_id', None)
            include_sid = bool(getattr(client, 'backchannel_logout_session_required', 1))
            event_jti = str(uuid4())
            try:
                token = await cls._make_logout_token(
                    client.client_id,
                    sid,
                    subject_id=subject_id,
                    include_sid=include_sid,
                    event_jti=event_jti,
                    now=now,
                    signing_key=signing_key,
                    signing_kid=signing_kid,
                    db=db,
                )
            except (KeyServiceError, JwtProfileError, TypeError, ValueError):
                token = None
            timeout_seconds = cls._backchannel_timeout()
            for uri_row in uris:
                uri = uri_row.uri
                safe = await cls._safe_backchannel_uri(uri)
                if not safe:

                    async def permanent_failure(uri_value: str = uri, client_value: str = client.client_id) -> None:
                        """
                        记录 Back-Channel 通知的永久失败

                        :param uri_value: URI 值
                        :param client_value: 客户端值
                        :return: None
                        """

                        await cls._write_backchannel_audit(
                            effective_audit_writer,
                            OidcAuditEvent.BACKCHANNEL_LOGOUT_FAILED,
                            uri_value,
                            client_value,
                            sid,
                        )

                    await coordinator.register(permanent_failure)
                    continue
                if token is None:

                    async def signing_failure(
                        uri_value: str = uri,
                        client_value: str = client.client_id,
                        event_jti_value: str = event_jti,
                        subject_id_value: str | None = subject_id,
                        include_sid_value: bool = include_sid,
                    ) -> None:
                        """
                        记录 Logout Token 签名失败

                        :param uri_value: URI 值
                        :param client_value: 客户端值
                        :param event_jti_value: 事件 JTI
                        :param subject_id_value: Subject 标识
                        :param include_sid_value: 是否包含 Session 标识
                        :return: None
                        """

                        await cls._write_backchannel_audit(
                            effective_audit_writer,
                            OidcAuditEvent.BACKCHANNEL_LOGOUT_FAILED,
                            uri_value,
                            client_value,
                            sid,
                        )
                        await cls._enqueue_backchannel_retry(
                            effective_retry_queue,
                            uri_value,
                            client_value,
                            sid,
                            event_jti=event_jti_value,
                            subject_id=subject_id_value,
                            include_sid=include_sid_value,
                        )

                    await coordinator.register(signing_failure)
                    continue
                callback = cls._notification_callback(
                    uri,
                    token,
                    notifier,
                    timeout_seconds=timeout_seconds,
                    client_id=client.client_id,
                    sid=sid,
                    subject_id=subject_id,
                    include_sid=include_sid,
                    event_jti=event_jti,
                    audit_writer=effective_audit_writer,
                    retry_queue=effective_retry_queue,
                )
                callbacks.append(callback)
        if callbacks:
            semaphore = asyncio.Semaphore(_BACKCHANNEL_MAX_CONCURRENCY)

            async def notify_all() -> None:
                """
                向已登记的 Client 发送退出通知

                :return: None
                """

                async def run(callback: Callable[[], Awaitable[None]]) -> None:
                    """
                    执行一次通知回调并统一处理发送异常

                    :param callback: 提交后回调
                    :return: None
                    """

                    async with semaphore:
                        await callback()

                await asyncio.gather(*(run(callback) for callback in callbacks))

            await coordinator.register(notify_all)

    @classmethod
    async def consume_backchannel_retry(  # noqa: PLR0912, PLR0915
        cls,
        db: AsyncSession,
        redis: Redis,
        *,
        now: datetime | None = None,
        notifier: BackchannelNotifier | None = None,
        max_items: int = _BACKCHANNEL_MAX_QUEUE_ITEMS,
    ) -> int:
        """
        读取并处理 Back-Channel Logout 重试队列

        :param db: 异步数据库会话
        :param redis: Redis 队列客户端
        :param now: 可注入当前时间
        :param notifier: 测试或受控网络发送器
        :param max_items: 单轮最大任务数
        :return: 已取出的任务数
        :raises PermanentBackchannelError: Back-Channel 通知达到永久失败条件
        :raises ValueError: 输入值不符合约束
        """

        limit = max(1, min(int(max_items), _BACKCHANNEL_MAX_QUEUE_ITEMS))
        current = TimezoneUtil.to_optional_utc(now) or TimezoneUtil.utc_now()
        processed = 0
        for _ in range(limit):
            raw = await redis.lpop(OidcRedisKey.backchannel_retry_queue())
            if raw is None:
                break
            processed += 1
            item: dict[str, Any] | None = None
            try:
                try:
                    item = json.loads(raw)
                except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise PermanentBackchannelError('invalid retry payload', '后端退出通知重试载荷无效') from exc
                if not isinstance(item, dict):
                    raise PermanentBackchannelError('invalid retry payload', '后端退出通知重试载荷无效')
                uri = item['uri']
                client_id = item['client_id']
                sid = item['sid']
                event_jti = item['event_jti']
                subject_id = item.get('subject_id')
                include_sid = bool(item.get('include_sid', True))
                attempt = int(item.get('attempt', 1))
                next_attempt = int(item.get('nextAttemptAt', 0))
                if next_attempt > int(current.timestamp()):
                    await redis.rpush(OidcRedisKey.backchannel_retry_queue(), json.dumps(item, separators=(',', ':')))
                    break
                if (
                    not isinstance(uri, str)
                    or not isinstance(client_id, str)
                    or not isinstance(sid, str)
                    or not isinstance(event_jti, str)
                    or not event_jti
                    or attempt < 1
                ):
                    raise PermanentBackchannelError('invalid retry task', '后端退出通知重试任务无效')
                client = await OAuthClientDao.get_by_client_id(db, client_id, active_only=True)
                registered = (
                    await OAuthClientDao.find_exact_uri(db, client.client_pk, _URI_BACKCHANNEL, uri) if client else None
                )
                if (
                    client is None
                    or registered is None
                    or registered.status != '0'
                    or not await cls._safe_backchannel_uri(uri)
                ):
                    raise PermanentBackchannelError('stale retry registration', '后端退出通知的重试注册信息已失效')
                token = await cls._make_logout_token(
                    client_id,
                    sid,
                    subject_id=subject_id,
                    include_sid=include_sid,
                    event_jti=event_jti,
                    now=current,
                    signing_key=None,
                    signing_kid=None,
                    db=db,
                )
                if token is None:
                    raise ValueError('签名密钥不可用')
                await cls._send_backchannel_once(uri, token, notifier, cls._backchannel_timeout())
                await cls._write_backchannel_audit(
                    cls._audit_writer(db), OidcAuditEvent.BACKCHANNEL_LOGOUT_SUCCEEDED, uri, client_id, sid
                )
            except PermanentBackchannelError as exc:
                dead_key = OidcRedisKey.backchannel_retry_queue() + ':dead'
                dead_item = item if isinstance(item, dict) else {'error': 'invalid_retry_payload'}
                await redis.rpush(dead_key, json.dumps(dead_item, separators=(',', ':')))
                await redis.ltrim(dead_key, -_BACKCHANNEL_QUEUE_MAX_LENGTH, -1)
                await cls._write_backchannel_audit(
                    cls._audit_writer(db),
                    OidcAuditEvent.BACKCHANNEL_LOGOUT_FAILED,
                    str(dead_item.get('uri', '')),
                    str(dead_item.get('client_id', '')),
                    str(dead_item.get('sid', '')),
                    failure_code=exc.failure_code,
                )
            except Exception:
                if isinstance(item, dict):
                    attempt = int(item.get('attempt', 1)) if str(item.get('attempt', 1)).isdigit() else 1
                    if attempt < _BACKCHANNEL_MAX_QUEUE_ATTEMPTS:
                        item['attempt'] = attempt + 1
                        item['nextAttemptAt'] = int(current.timestamp()) + min(300, 2**attempt)
                        await redis.rpush(
                            OidcRedisKey.backchannel_retry_queue(), json.dumps(item, separators=(',', ':'))
                        )
                        await redis.ltrim(OidcRedisKey.backchannel_retry_queue(), -_BACKCHANNEL_QUEUE_MAX_LENGTH, -1)
                    else:
                        dead_key = OidcRedisKey.backchannel_retry_queue() + ':dead'
                        await redis.rpush(dead_key, json.dumps(item, separators=(',', ':')))
                        await redis.ltrim(dead_key, -_BACKCHANNEL_QUEUE_MAX_LENGTH, -1)
                    await cls._write_backchannel_audit(
                        cls._audit_writer(db),
                        OidcAuditEvent.BACKCHANNEL_LOGOUT_FAILED,
                        str(item.get('uri', '')),
                        str(item.get('client_id', '')),
                        str(item.get('sid', '')),
                    )
        return processed

    @staticmethod
    async def _safe_backchannel_uri(uri: Any) -> bool:
        """
        验证 Back-Channel URI 使用允许的网络地址

        :param uri: 回调 URI
        :return: URI 是否通过 Back-Channel 网络地址安全检查
        """

        return await is_safe_backchannel_uri(uri)

    @staticmethod
    async def _public_dns_only(hostname: str, port: int) -> bool:
        """
        解析主机名并确认所有地址均为公网地址

        :param hostname: 主机名
        :param port: 端口
        :return: 主机解析得到的所有地址是否均为公网地址
        """

        return await public_dns_only(hostname, port)

    @staticmethod
    async def _verified_addresses(hostname: str, port: int) -> set[str]:
        """
        获取通过公网地址校验的主机地址集合

        :param hostname: 主机名
        :param port: 端口
        :return: 通过校验的地址集合
        """

        return await public_dns_addresses(hostname, port)

    @classmethod
    async def _make_logout_token(
        cls,
        client_id: str,
        sid: str,
        *,
        subject_id: str | None = None,
        include_sid: bool = True,
        event_jti: str | None = None,
        now: datetime,
        signing_key: RSAPrivateKey | None,
        signing_kid: str | None,
        db: AsyncSession,
    ) -> str | None:
        """
        为指定 Client 和 Session 签发 Back-Channel Logout Token

        :param client_id: 客户端标识
        :param sid: Session 标识
        :param subject_id: Subject 标识
        :param include_sid: 是否包含 Session 标识
        :param event_jti: 事件 JTI
        :param now: 当前时间
        :param signing_key: 签名密钥
        :param signing_kid: 签名密钥标识
        :param db: 异步数据库会话
        :return: 已签名的 Back-Channel Logout JWT，签名材料不可用时返回 None
        """

        if signing_key is None or signing_kid is None:
            record = await OidcKeyDao.get_active(db, alg=_RS256)
            if record is None:
                return None
            signing_key = await KeyService.load_private_key_async(record, now=now)
            signing_kid = record.kid
        try:
            return encode_logout_token(
                {
                    'iss': OidcConfig.oidc_issuer.rstrip('/'),
                    'aud': client_id,
                    'iat': int(now.timestamp()),
                    'exp': int(now.timestamp()) + _LOGOUT_TOKEN_TTL_SECONDS,
                    'events': {BACKCHANNEL_LOGOUT_EVENT: {}},
                    'jti': event_jti or str(uuid4()),
                    **({'sid': sid} if include_sid else {'sub': subject_id}),
                },
                signing_key,
                signing_kid,
            )
        except (JwtProfileError, TypeError, ValueError):
            return None

    @staticmethod
    def _notification_callback(  # noqa: PLR0913
        uri: str,
        token: str,
        notifier: BackchannelNotifier | None,
        *,
        timeout_seconds: float = _BACKCHANNEL_TIMEOUT_SECONDS,
        client_id: str = '',
        sid: str = '',
        subject_id: str | None = None,
        include_sid: bool = True,
        event_jti: str | None = None,
        audit_writer: BackchannelAuditWriter | None = None,
        retry_queue: BackchannelRetryQueue | None = None,
    ) -> Callable[[], Awaitable[None]]:
        """
        创建发送 Back-Channel Logout 通知并处理失败的回调

        :param uri: 回调 URI
        :param token: 令牌值
        :param notifier: 通知器
        :param timeout_seconds: Back-Channel 请求超时时间
        :param client_id: 客户端标识
        :param sid: Session 标识
        :param subject_id: Subject 标识
        :param include_sid: 是否包含 Session 标识
        :param event_jti: 事件 JTI
        :param audit_writer: 审计写入回调
        :param retry_queue: 重试队列回调
        :return: 异步回调
        """

        async def notify() -> None:
            """
            发送一次 Back-Channel Logout 通知

            :return: None
            """

            last_error: Exception | None = None
            for attempt in range(_BACKCHANNEL_MAX_ATTEMPTS):
                try:
                    await LogoutService._send_backchannel_once(uri, token, notifier, timeout_seconds)
                    await LogoutService._write_backchannel_audit(
                        audit_writer, 'backchannel_logout_succeeded', uri, client_id, sid
                    )
                    return
                except PermanentBackchannelError as exc:  # noqa: PERF203
                    await LogoutService._write_backchannel_audit(
                        audit_writer,
                        OidcAuditEvent.BACKCHANNEL_LOGOUT_FAILED,
                        uri,
                        client_id,
                        sid,
                        failure_code=exc.failure_code,
                    )
                    return
                except Exception as exc:
                    last_error = exc
                    if attempt + 1 < _BACKCHANNEL_MAX_ATTEMPTS:
                        await asyncio.sleep(_BACKCHANNEL_RETRY_DELAY_SECONDS * (attempt + 1))
            await LogoutService._enqueue_backchannel_retry(
                retry_queue,
                uri,
                client_id,
                sid,
                event_jti=event_jti,
                subject_id=subject_id,
                include_sid=include_sid,
            )
            await LogoutService._write_backchannel_audit(audit_writer, 'backchannel_logout_failed', uri, client_id, sid)
            LOGGER.warning(
                '后端退出通知发送失败，事件=%s，客户端=%s，会话=%s，异常类型=%s',
                'backchannel_logout_failed',
                client_id,
                sid,
                type(last_error).__name__ if last_error else '未知',
            )

        return notify

    @staticmethod
    async def _send_backchannel_once(
        uri: str, token: str, notifier: BackchannelNotifier | None, timeout_seconds: float
    ) -> None:
        """
        向 Client 的 Back-Channel URI 发送 Logout Token

        :param uri: 已注册的 Back-Channel URI
        :param token: 仅存在于本次内存请求中的 Logout Token
        :param notifier: 可注入发送器
        :param timeout_seconds: 有界网络超时
        :return: None
        :raises LogoutServiceError: Logout 参数或回调地址不符合要求
        """

        addresses: set[str] | None = None
        if notifier is None:
            parsed = urlsplit(uri)
            hostname = parsed.hostname or ''
            addresses = await LogoutService._verified_addresses(hostname, parsed.port or 443)
            if not addresses:
                raise LogoutServiceError('后端退出通知目标不是公网地址')
        await send_backchannel_once(
            uri,
            token,
            notifier,
            timeout_seconds,
            addresses=addresses,
        )

    @staticmethod
    def _audit_writer(db: AsyncSession) -> BackchannelAuditWriter:
        """
        创建绑定数据库会话的 Back-Channel 审计写入器

        :param db: 异步数据库会话
        :return: 绑定当前数据库会话的 Back-Channel 审计写入器
        """

        async def write(
            event: str,
            uri: str,
            client_id: str,
            sid: str,
            *,
            failure_code: str | None = None,
        ) -> None:
            """
            写入一次 Back-Channel 审计事件

            :param event: 事件类型
            :param uri: 回调 URI
            :param client_id: 客户端标识
            :param sid: Session 标识
            :param failure_code: 失败代码
            :return: None
            """

            try:
                await AuditService.record_independent(
                    db,
                    event,
                    'success' if event == OidcAuditEvent.BACKCHANNEL_LOGOUT_SUCCEEDED else 'failure',
                    client_id=client_id,
                    sid=sid,
                    failure_code=failure_code,
                    detail={'uri': uri},
                )
            except Exception:
                LOGGER.warning('后端退出通知审计写入失败，事件=%s，客户端=%s，会话=%s', event, client_id, sid)

        return write

    @staticmethod
    async def _write_backchannel_audit(
        audit_writer: BackchannelAuditWriter | None,
        event: str,
        uri: str,
        client_id: str,
        sid: str,
        failure_code: str | None = None,
    ) -> None:
        """
        记录一次 Back-Channel 通知结果

        :param audit_writer: 审计写入回调
        :param event: 事件类型
        :param uri: 回调 URI
        :param client_id: 客户端标识
        :param sid: Session 标识
        :param failure_code: 失败代码
        :return: None
        """

        if audit_writer is not None:
            try:
                await audit_writer(event, uri, client_id, sid, failure_code=failure_code)
            except Exception:
                LOGGER.warning('后端退出通知审计写入失败，事件=%s', event)

    @staticmethod
    async def _enqueue_backchannel_retry(
        retry_queue: BackchannelRetryQueue | None,
        uri: str,
        client_id: str,
        sid: str,
        *,
        event_jti: str | None = None,
        subject_id: str | None = None,
        include_sid: bool = True,
    ) -> None:
        """
        将失败的 Back-Channel 通知加入重试队列

        :param retry_queue: 重试队列回调
        :param uri: 回调 URI
        :param client_id: 客户端标识
        :param sid: Session 标识
        :param event_jti: 事件 JTI
        :param subject_id: Subject 标识
        :param include_sid: 是否包含 Session 标识
        :return: None
        """

        if retry_queue is not None:
            try:
                await retry_queue(
                    uri,
                    client_id,
                    sid,
                    event_jti=event_jti,
                    subject_id=subject_id,
                    include_sid=include_sid,
                )
            except Exception:
                LOGGER.warning('后端退出通知重试任务入队失败')

    @staticmethod
    def _redis_retry_queue(redis: Redis) -> BackchannelRetryQueue:
        """
        创建基于 Redis 的 Back-Channel 重试队列适配器

        :param redis: 异步 Redis 客户端
        :return: 基于 Redis 的 Back-Channel 重试队列适配器
        """

        async def enqueue(
            uri: str,
            client_id: str,
            sid: str,
            *,
            event_jti: str | None = None,
            subject_id: str | None = None,
            include_sid: bool = True,
        ) -> None:
            """
            加入一条 Back-Channel 重试任务

            :param uri: 回调 URI
            :param client_id: 客户端标识
            :param sid: Session 标识
            :param event_jti: 事件 JTI
            :param subject_id: Subject 标识
            :param include_sid: 是否包含 Session 标识
            :return: None
            """

            payload = json.dumps(
                {
                    'uri': uri,
                    'client_id': client_id,
                    'sid': sid,
                    'event_jti': event_jti or str(uuid4()),
                    'subject_id': subject_id,
                    'include_sid': include_sid,
                    'attempt': 1,
                    'nextAttemptAt': int(TimezoneUtil.utc_now().timestamp()),
                },
                separators=(',', ':'),
            )
            await redis.rpush(OidcRedisKey.backchannel_retry_queue(), payload)
            await redis.ltrim(OidcRedisKey.backchannel_retry_queue(), -_BACKCHANNEL_QUEUE_MAX_LENGTH, -1)

        return enqueue

    @staticmethod
    def _backchannel_timeout() -> float:
        """
        读取 Back-Channel 请求超时配置

        :return: 超时时间（秒）
        """

        value = getattr(OidcConfig, 'oidc_backchannel_logout_timeout_seconds', _BACKCHANNEL_TIMEOUT_SECONDS)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
            or value > _MAX_BACKCHANNEL_TIMEOUT_SECONDS
        ):
            return _BACKCHANNEL_TIMEOUT_SECONDS
        return float(value)
