from __future__ import annotations

import hmac
import math
from typing import TYPE_CHECKING, Any

from common.constant import OidcAuditEvent
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_identity.dao.identity_subject_dao import IdentitySubjectDao
from module_identity.dao.identity_user_dao import IdentityUserDao
from module_identity.dao.oauth_access_policy_dao import OAuthAccessPolicyDao
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.dao.oauth_resource_dao import OAuthResourceDao
from module_identity.dao.oauth_token_dao import OAuthTokenDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.redis_keys import OidcRedisKey
from module_identity.security.jwt_profile import JwtProfileError, decode_access_token
from module_identity.security.opaque_token import OpaqueTokenError, parse_opaque_token, token_digest
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.audit_service import AuditService
from module_identity.service.identity_service import ClaimService
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.token_service import TokenService
from utils.time_util import TimezoneUtil

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession


class IntrospectionService:
    """
    OAuth Token 内省模块服务层
    """

    _USERINFO_SUFFIX = '/oauth2/userinfo'
    _ACTIVE_CLIENT_STATUS = '0'
    _ACTIVE_USER_STATUS = '0'
    _ACTIVE_GRANT_STATUS = 'active'
    _ACTIVE_SESSION_STATUS = 'active'
    _ACTIVE_TOKEN_STATUS = 'active'
    _REFRESH_PREFIX = 'rt1'
    _STANDARD_CLAIMS = frozenset(
        {'scope', 'client_id', 'token_type', 'exp', 'iat', 'nbf', 'sub', 'aud', 'iss', 'jti', 'sid'}
    )

    @classmethod
    async def introspect(
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        caller: OAuthClientPrincipal,
        *,
        verification_keys: Any = None,
        verification_key: Any = None,
        now: datetime | None = None,
        token_type_hint: str | None = None,
        pepper: str | bytes | None = None,
    ) -> dict[str, Any]:
        """
        验证 Token 并生成 OAuth Introspection 响应

        :param db: 异步数据库会话
        :param redis: 统一认证中心 Redis 客户端
        :param token: 待内省的 OAuth Access Token 或 Refresh Token
        :param caller: 已完成认证的 OAuth Client 主体
        :param verification_keys: 按 kid 索引的 Access Token 公钥
        :param verification_key: 单个 Access Token 公钥
        :param now: 可注入的当前项目时间
        :param token_type_hint: 可选的 Token 类型提示
        :param pepper: 可选 Token HMAC Pepper 覆盖值
        :return: 有效 Token 的声明，或严格的 ``{'active': False}``
        """

        try:
            current = cls._utc_datetime(now) or TimezoneUtil.utc_now()
            client = await cls._resolve_caller(db, caller)
            if client is None or not isinstance(token, str) or not token:
                return {'active': False}
            if token_type_hint == 'refresh_token' or token.startswith('rt1.'):
                return await cls._introspect_refresh(db, token, client, current, pepper)
            if token_type_hint not in (None, 'access_token'):
                return {'active': False}
            return await cls._introspect_access(
                db,
                redis,
                token,
                client,
                current,
                verification_keys,
                verification_key,
            )
        except (JwtProfileError, OpaqueTokenError, TypeError, ValueError, KeyError):
            # 格式和令牌状态错误统一返回 inactive，不向调用方暴露校验细节
            return {'active': False}

    @classmethod
    async def _introspect_transaction(
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        caller: OAuthClientPrincipal,
        *,
        verification_keys: Any = None,
        verification_key: Any = None,
        now: datetime | None = None,
        token_type_hint: str | None = None,
        pepper: str | bytes | None = None,
    ) -> dict[str, Any]:
        """
        在事务边界内执行 Token 内省

        :param db: 异步数据库会话，由本方法提交或回滚
        :param redis: 认证中心 Redis 客户端
        :param token: 待内省的 OAuth Access Token 或 Refresh Token
        :param caller: 已认证的 OAuth Client 主体
        :param verification_keys: Access Token 公钥集合
        :param verification_key: 当前 Token 对应的公钥
        :param now: 可注入的 项目当前时间
        :param token_type_hint: Token 类型提示
        :param pepper: Refresh Token HMAC Pepper
        :return: OAuth Introspection 响应
        """

        try:
            result = await cls.introspect(
                db,
                redis,
                token,
                caller,
                verification_keys=verification_keys,
                verification_key=verification_key,
                now=now,
                token_type_hint=token_type_hint,
                pepper=pepper,
            )
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def introspect_request(
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        *,
        authorization: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        verification_key: Any = None,
        verification_key_loader: Callable[[AsyncSession, str], Awaitable[Any]] | None = None,
        token_type_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        认证调用 Client 并处理内省请求

        :param db: 异步数据库会话，由本方法提交或回滚
        :param redis: 认证中心 Redis 客户端
        :param token: 待内省的 OAuth Access Token 或 Refresh Token
        :param authorization: RFC 7617 Basic Header
        :param client_id: 表单 Client ID
        :param client_secret: 表单 Client Secret
        :param verification_key: 当前 Access Token 的本地公钥
        :param verification_key_loader: 验证密钥加载回调
        :param token_type_hint: Token 类型提示
        :return: OAuth Introspection 响应
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        try:
            client_row, principal = await TokenService.authenticate_client(
                db,
                authorization=authorization,
                client_id=client_id,
                client_secret=client_secret,
            )
            if client_row.client_type != 'confidential':
                raise OAuthProtocolException('invalid_client', 'Client authentication failed', 401)
            if verification_key_loader is not None:
                verification_key = await verification_key_loader(db, token)
        except Exception:
            await db.rollback()
            raise
        return await cls._introspect_transaction(
            db,
            redis,
            token,
            principal,
            verification_key=verification_key,
            token_type_hint=token_type_hint,
        )

    @classmethod
    async def _resolve_caller(cls, db: AsyncSession, caller: OAuthClientPrincipal) -> Any:
        """
        确认内省调用方 Client 处于有效状态

        :param db: 异步数据库会话
        :param caller: 已认证的 OAuth Client 主体
        :return: 已启用且认证方式匹配的 OAuth Client ORM 对象，不满足条件时返回 None
        """

        if not isinstance(caller, OAuthClientPrincipal) or caller.auth_method != 'client_secret_basic':
            return None
        client = await OAuthClientDao.get_by_client_id(db, caller.client_id, active_only=True)
        if (
            client is None
            or client.status != cls._ACTIVE_CLIENT_STATUS
            or client.client_type != 'confidential'
            or client.client_id != caller.client_id
            or client.client_type != caller.client_type
            or client.token_endpoint_auth_method != 'client_secret_basic'
        ):
            return None
        return client

    @staticmethod
    def _utc_datetime(value: datetime | None) -> datetime | None:
        """
        将输入时间统一转换为项目时间

        :param value: 可选的待规范化 datetime 时间
        :return: 带时区的 UTC datetime；输入为空时返回 None
        """

        return TimezoneUtil.to_utc(value) if value is not None else None

    @staticmethod
    def _json_list(value: Any) -> list[Any]:
        """
        将 Scope 或 Resource 字段规范化为列表

        :param value: JSON 编码的 Scope 或 Resource 列表值
        :return: Scope 或 Resource 元素列表；输入不是 JSON 数组时返回空列表
        """

        return list(value) if isinstance(value, (list, tuple)) else []

    @classmethod
    async def _introspect_access(  # noqa: PLR0912
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        caller: Any,
        now: datetime,
        verification_keys: Any,
        verification_key: Any,
    ) -> dict[str, Any]:
        """
        验证 Access Token 并生成内省声明

        :param db: 异步数据库会话
        :param redis: 异步 Redis 客户端
        :param token: 待内省的 Access Token
        :param caller: 已认证且拥有 Resource 内省权限的 OAuth Client ORM
        :param now: 当前时间
        :param verification_keys: 验证密钥集合
        :param verification_key: 验证密钥
        :return: 有效 Access Token 的 Introspection 声明，或严格的 ``{'active': False}``
        """

        claims = decode_access_token(
            token,
            verification_keys,
            issuer=OidcConfig.oidc_issuer,
            clock_skew=OidcConfig.oidc_allowed_clock_skew_seconds,
            verification_key=verification_key,
        )
        jti = claims.get('jti')
        if not isinstance(jti, str) or await cls._redis_key_exists(redis, OidcRedisKey.revoked_jti(jti)):
            return {'active': False}
        audiences = cls._audiences(claims.get('aud'))
        resources = cls._resource_audiences(audiences)
        if not resources or not await cls._resources_owned_by_caller(db, audiences, caller.client_pk):
            return {'active': False}
        issuer_client_id = claims.get('client_id')
        if not isinstance(issuer_client_id, str) or not issuer_client_id:
            return {'active': False}
        issuer_client = await OAuthClientDao.get_by_client_id(db, issuer_client_id, active_only=True)
        if issuer_client is None or issuer_client.status != cls._ACTIVE_CLIENT_STATUS:
            return {'active': False}
        if not await cls._client_allows_access(db, issuer_client, claims, resources):
            return {'active': False}
        grant_type = claims.get('gty')
        user_state = None
        if grant_type == 'client_credentials':
            if (
                issuer_client.client_type != 'confidential'
                or 'client_credentials' not in cls._json_list(issuer_client.grant_types)
                or claims.get('sub') != f'client:{issuer_client.client_id}'
            ):
                return {'active': False}
        elif grant_type not in {'authorization_code', 'refresh_token'}:
            return {'active': False}
        else:
            user_state = await cls._access_user_state(db, claims, issuer_client, resources, now)
            if user_state is None:
                return {'active': False}
        result: dict[str, Any] = {'active': True, 'token_type': 'Bearer'}
        for name in cls._STANDARD_CLAIMS:
            if name in claims:
                result[name] = claims[name]
        result['token_type'] = 'Bearer'
        result['gty'] = grant_type
        if user_state is not None:
            result['username'] = user_state.user_name
            result['ver'] = claims['ver']
        return result

    @classmethod
    async def _access_user_state(
        cls, db: AsyncSession, claims: dict[str, Any], client: Any, resources: list[str], now: datetime
    ) -> Any:
        """
        验证 Access Token 对应的用户、Session 和授权来源

        :param db: 异步数据库会话
        :param claims: 令牌声明
        :param client: 签发该 Access Token 的 OAuth Client ORM
        :param resources: Access Token 声明中的 Resource Audience 列表
        :param now: 当前时间
        :return: 当前身份对应的启用用户 ORM 对象，安全状态或授权来源不匹配时返回 None
        """

        subject_id = claims.get('sub')
        version = claims.get('ver')
        sid = claims.get('sid')
        scope = claims.get('scope')
        if (
            not isinstance(subject_id, str)
            or not subject_id
            or isinstance(version, bool)
            or not isinstance(version, int)
            or not isinstance(sid, str)
            or not sid
            or not isinstance(scope, str)
            or not scope.strip()
        ):
            return None
        subject = await IdentitySubjectDao.get_by_subject_id(db, subject_id)
        if subject is None or subject.auth_version != version:
            return None
        user = await IdentityUserDao.get_user(db, subject.user_id)
        if (
            user is None
            or user.status != cls._ACTIVE_USER_STATUS
            or user.del_flag != cls._ACTIVE_USER_STATUS
            or not isinstance(user.user_name, str)
            or not user.user_name
        ):
            return None
        session = await SsoSessionDao.get_for_token(
            db,
            sid,
            now=now,
            allow_offline=claims.get('gty') == 'refresh_token' or 'offline_access' in scope.split(),
        )
        if (
            session is None
            or session.user_id != subject.user_id
            or session.subject_id != subject_id
            or session.auth_version != version
        ):
            return None
        scopes = scope.split()
        grant_id = claims.get('grant_id')
        if not isinstance(grant_id, str) or not grant_id:
            # 升级前未绑定具体授权的用户令牌须重新授权，避免撤销范围不明确。
            return None
        if await OAuthAccessPolicyDao.is_blocked(db, subject.user_id, client.client_pk):
            return None
        grant = await OAuthGrantDao.get_by_grant_id(db, grant_id)
        if not cls._grant_active(grant, subject.user_id, subject_id, client, scopes, resources, now):
            return None
        return user

    @classmethod
    async def _client_allows_access(
        cls, db: AsyncSession, client: Any, claims: dict[str, Any], resources: list[str]
    ) -> bool:
        """
        检查当前 Client 策略是否仍允许令牌中的 Scope 和 Resource

        :param db: 异步数据库会话
        :param client: 签发该 Access Token 的 OAuth Client ORM
        :param claims: 已验证签名的 Access Token 声明
        :param resources: 待检查的 Resource Audience 列表
        :return: 策略版本及 Scope、Resource 绑定均有效时为 True
        """

        scope = claims.get('scope')
        if not isinstance(scope, str) or not scope.strip():
            return False
        if 'client_policy_version' in claims:
            version = claims['client_policy_version']
            if isinstance(version, bool) or not isinstance(version, int) or version != client.policy_version:
                return False
        try:
            await TokenService._validate_client_scope_resource(
                db, client, scope.split(), resources, machine_only=claims.get('gty') == 'client_credentials'
            )
        except OAuthProtocolException:
            return False
        return True

    @classmethod
    async def _introspect_refresh(
        cls,
        db: AsyncSession,
        token: str,
        caller: Any,
        now: datetime,
        pepper: str | bytes | None,
    ) -> dict[str, Any]:
        """
        验证 Refresh Token 并生成内省声明

        :param db: 异步数据库会话
        :param token: 待内省的 Refresh Token
        :param caller: 已认证且拥有 Resource 内省权限的 OAuth Client ORM
        :param now: 当前时间
        :param pepper: 摘要 Pepper
        :return: 有效 Refresh Token 的 Introspection 声明，或严格的 ``{'active': False}``
        """

        parsed = parse_opaque_token(token, cls._REFRESH_PREFIX)
        secret_pepper = OidcConfig.oidc_token_hash_pepper if pepper is None else pepper
        digest = token_digest(token, secret_pepper)
        row = await OAuthTokenDao.get_by_token_id(db, parsed.token_id, for_update=False)
        if row is None or not hmac.compare_digest(row.token_hash, digest) or row.status != cls._ACTIVE_TOKEN_STATUS:
            return {'active': False}
        issuer_client = await OAuthClientDao.get_by_pk(db, row.client_pk, active_only=True)
        if issuer_client is None or issuer_client.status != cls._ACTIVE_CLIENT_STATUS:
            return {'active': False}
        if cls._utc_datetime(row.idle_expires_at) <= now or cls._utc_datetime(row.absolute_expires_at) <= now:
            return {'active': False}
        if not await cls._refresh_family_active(db, row.family_id):
            return {'active': False}
        user = await IdentityUserDao.get_user(db, row.user_id)
        subject = await IdentitySubjectDao.get_by_user_id(db, row.user_id)
        if (
            user is None
            or user.status != cls._ACTIVE_USER_STATUS
            or user.del_flag != cls._ACTIVE_USER_STATUS
            or subject is None
            or subject.subject_id != row.subject_id
            or subject.auth_version != row.auth_version
        ):
            return {'active': False}
        session = await SsoSessionDao.get_for_token(db, row.sid, now=now, allow_offline=True)
        if (
            session is None
            or session.subject_id != row.subject_id
            or session.user_id != row.user_id
            or session.auth_version != row.auth_version
        ):
            return {'active': False}
        if await OAuthAccessPolicyDao.is_blocked(db, row.user_id, row.client_pk):
            return {'active': False}
        grant = await OAuthGrantDao.get_by_grant_id(db, row.grant_id)
        if not cls._grant_active(
            grant,
            row.user_id,
            row.subject_id,
            issuer_client,
            cls._json_list(row.scopes),
            cls._json_list(row.resources),
            now,
        ):
            return {'active': False}
        resources = cls._audiences(row.resources)
        if not resources or not await cls._resources_owned_by_caller(db, resources, caller.client_pk):
            return {'active': False}
        result: dict[str, Any] = {
            'active': True,
            'client_id': issuer_client.client_id,
            'token_type': 'refresh_token',
            'scope': ' '.join(str(item) for item in cls._json_list(row.scopes)),
            'sub': row.subject_id,
            'username': user.user_name,
            'aud': resources,
            'jti': parsed.token_id,
            'sid': row.sid,
            'iat': cls._timestamp(row.issued_at),
            'exp': cls._timestamp(row.absolute_expires_at),
        }

        return result

    @classmethod
    async def _refresh_family_active(cls, db: AsyncSession, family_id: str) -> bool:
        """
        检查 Refresh Token Family 是否仍处于活动状态

        :param db: 异步数据库会话
        :param family_id: Refresh Family 标识
        :return: 仅在存在记录且没有全族终止状态时返回真
        """

        return await OAuthTokenDao.family_is_active(db, family_id)

    @classmethod
    def _grant_active(
        cls,
        grant: Any,
        user_id: int,
        subject_id: str,
        client: Any,
        scopes: list[Any],
        resources: list[Any],
        now: datetime,
    ) -> bool:
        """
        检查 Grant 是否匹配当前身份、Client 和授权范围

        :param grant: Grant 对象
        :param user_id: 用户标识
        :param subject_id: Subject 标识
        :param client: 签发该 Token 的 OAuth Client ORM
        :param scopes: Token 授权的 Scope 列表
        :param resources: Token 授权的 Resource Audience 列表
        :param now: 当前时间
        :return: Grant 匹配用户、Subject、OAuth Client、Scope、Resource 且未过期时为 True
        """

        return bool(
            grant is not None
            and grant.user_id == user_id
            and grant.subject_id == subject_id
            and grant.client_pk == client.client_pk
            and grant.status == cls._ACTIVE_GRANT_STATUS
            and grant.client_policy_version == client.policy_version
            and (grant.expires_at is None or cls._utc_datetime(grant.expires_at) > now)
            and set(scopes).issubset(set(cls._json_list(grant.granted_scopes)))
            and set(resources).issubset(set(cls._json_list(grant.granted_resources)))
        )

    @classmethod
    async def _resources_owned_by_caller(cls, db: AsyncSession, audiences: list[str], client_pk: int) -> bool:
        """
        检查调用方是否拥有资源的内省权限

        :param db: 异步数据库会话
        :param audiences: Token 声明中的 Audience 列表
        :param client_pk: 已认证 OAuth Client 的主键
        :return: 所有业务 Resource Audience 均归属于该 OAuth Client 的内省权限时为 True
        """

        userinfo = f'{OidcConfig.oidc_issuer.rstrip("/")}{cls._USERINFO_SUFFIX}'
        resource_audiences = [value for value in audiences if value != userinfo]
        if not resource_audiences:
            return False
        rows = {row.audience: row for row in await OAuthResourceDao.active_by_audiences(db, resource_audiences)}

        return len(rows) == len(set(resource_audiences)) and all(
            rows[value].introspection_client_pk == client_pk for value in resource_audiences
        )

    @classmethod
    def _resource_audiences(cls, audiences: list[str]) -> list[str]:
        """
        移除 UserInfo audience 并保留业务资源

        :param audiences: Token 声明中的 Audience 列表
        :return: 移除 UserInfo Audience 后的业务 Resource Audience 列表
        """

        userinfo = f'{OidcConfig.oidc_issuer.rstrip("/")}{cls._USERINFO_SUFFIX}'

        return [value for value in audiences if value != userinfo]

    @staticmethod
    async def _redis_key_exists(redis: Redis, key: str) -> bool:
        """
        检查 Redis 撤销键是否存在

        :param redis: Redis 异步客户端
        :param key: 待检查的 Redis 撤销键
        :return: 键存在时返回 True
        """

        return bool(await redis.exists(key))

    @staticmethod
    def _audiences(value: Any) -> list[str]:
        """
        将 aud 声明规范化为去重列表

        :param value: OAuth Token 的 Audience 声明值
        :return: 去重后的 Audience 列表；格式非法时返回空列表
        """

        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list) or not values or any(not isinstance(item, str) or not item for item in values):
            return []
        return list(dict.fromkeys(values))

    @staticmethod
    def _timestamp(value: datetime | None) -> int | None:
        """
        将 datetime 转换为有限的 Unix 时间戳

        :param value: 可选的 Token 签发时间或过期时间
        :return: 有限的 Unix 时间戳；输入为空或时间戳非有限时返回 None
        """

        if value is None:
            return None
        timestamp = value.timestamp()

        return int(timestamp) if math.isfinite(timestamp) else None


class RevocationError(ValueError):
    """
    令牌撤销参数错误类型
    """

    def __init__(self, error: str, description: str) -> None:
        """
        保存 OAuth 撤销错误代码和描述

        :param error: OAuth 错误代码
        :param description: 可向上层映射的安全错误描述
        :return: None
        """

        super().__init__(description)
        self.error = error
        self.description = description


class RevocationService:
    """
    OAuth Token 撤销模块服务层
    """

    _REFRESH_PREFIX = 'rt1'

    @classmethod
    async def revoke(
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        caller: OAuthClientPrincipal,
        *,
        verification_keys: Any = None,
        verification_key: Any = None,
        now: datetime | None = None,
        token_type_hint: str | None = None,
        pepper: str | bytes | None = None,
        coordinator: AfterCommitCoordinator | None = None,
    ) -> None:
        """
        按 Token 类型撤销 Access Token 或 Refresh Token

        :param db: 异步数据库会话；事务由提交协调器或调用方管理
        :param redis: 统一认证中心 Redis 客户端
        :param token: 待撤销的 OAuth Access Token 或 Refresh Token；未知 Token 幂等成功
        :param caller: 已认证的 OAuth Client 主体
        :param verification_keys: 按 kid 索引的 Access Token 公钥
        :param verification_key: 单个 Access Token 公钥
        :param now: 可注入的当前项目时间
        :param token_type_hint: 可选 Token 类型提示
        :param pepper: 可选 Token HMAC Pepper 覆盖值
        :param coordinator: 提交后副作用协调器；Access 撤销必须提供
        :return: None
        :raises RevocationError: Client 未认证或副作用边界不可用
        """

        current = cls._utc_datetime(now) or TimezoneUtil.utc_now()
        client = await cls._resolve_caller(db, caller)
        if client is None:
            raise RevocationError('invalid_client', 'Client authentication failed')
        if not isinstance(token, str) or not token:
            return
        if token_type_hint not in (None, 'refresh_token', 'access_token'):
            return
        if token_type_hint == 'refresh_token' or token.startswith('rt1.'):
            await cls._revoke_refresh(db, token, client, current, pepper)
            return
        await cls._revoke_access(
            db,
            redis,
            token,
            client,
            current,
            verification_keys,
            verification_key,
            coordinator,
        )

        return

    @classmethod
    async def _revoke_transaction(
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        caller: OAuthClientPrincipal,
        *,
        verification_keys: Any = None,
        verification_key: Any = None,
        now: datetime | None = None,
        token_type_hint: str | None = None,
        pepper: str | bytes | None = None,
    ) -> bool:
        """
        在事务边界内执行 Token 撤销

        :param db: 异步数据库会话，由本方法提交或回滚
        :param redis: 认证中心 Redis 客户端
        :param token: 待撤销的完整 Token
        :param caller: 已认证的 OAuth Client 主体
        :param verification_keys: Access Token 公钥集合
        :param verification_key: 当前 Token 对应的公钥
        :param now: 可注入的 项目当前时间
        :param token_type_hint: Token 类型提示
        :param pepper: Refresh Token HMAC Pepper
        :return: 提交后副作用全部成功时为 True
        :raises RevocationError: 令牌撤销失败且事务已回滚
        """

        coordinator = AfterCommitCoordinator()
        try:
            await cls.revoke(
                db,
                redis,
                token,
                caller,
                verification_keys=verification_keys,
                verification_key=verification_key,
                now=now,
                token_type_hint=token_type_hint,
                pepper=pepper,
                coordinator=coordinator,
            )
            await coordinator.commit(db)
        except Exception:
            await coordinator.rollback(db)
            raise
        return not coordinator.callback_errors

    @classmethod
    async def revoke_request(
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        *,
        authorization: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        verification_key: Any = None,
        verification_key_loader: Callable[[AsyncSession, str], Awaitable[Any]] | None = None,
        token_type_hint: str | None = None,
    ) -> bool:
        """
        认证调用 Client 并处理撤销请求

        :param db: 异步数据库会话，由本方法提交或回滚
        :param redis: 认证中心 Redis 客户端
        :param token: 待撤销的完整 Token
        :param authorization: RFC 7617 Basic Header
        :param client_id: 表单 Client ID
        :param client_secret: 表单 Client Secret
        :param verification_key: 当前 Access Token 的本地公钥
        :param verification_key_loader: 验证密钥加载回调
        :param token_type_hint: Token 类型提示
        :return: 提交后副作用全部成功时为 True
        """

        try:
            _, principal = await TokenService.authenticate_client(
                db,
                authorization=authorization,
                client_id=client_id,
                client_secret=client_secret,
            )
            if verification_key_loader is not None:
                verification_key = await verification_key_loader(db, token)
        except Exception:
            await db.rollback()
            raise
        return await cls._revoke_transaction(
            db,
            redis,
            token,
            principal,
            verification_key=verification_key,
            token_type_hint=token_type_hint,
        )

    @staticmethod
    async def _resolve_caller(db: AsyncSession, caller: OAuthClientPrincipal) -> Any:
        """
        确认内省调用方 Client 处于有效状态

        :param db: 异步数据库会话
        :param caller: 已认证的 OAuth Client 主体
        :return: 已通过认证和资源校验的 OAuth Client ORM 对象，不满足条件时返回 None
        """

        if not isinstance(caller, OAuthClientPrincipal):
            return None
        client = await OAuthClientDao.get_by_client_id(db, caller.client_id, active_only=True)
        if (
            client is None
            or client.status != '0'
            or client.client_id != caller.client_id
            or client.client_type != caller.client_type
            or (
                client.client_type == 'public'
                and (caller.auth_method != 'none' or client.token_endpoint_auth_method != 'none')
            )
            or (
                client.client_type == 'confidential'
                and (
                    caller.auth_method != 'client_secret_basic'
                    or client.token_endpoint_auth_method != 'client_secret_basic'
                )
            )
        ):
            return None
        if client.client_type not in {'public', 'confidential'}:
            return None
        return client

    @classmethod
    async def _revoke_refresh(
        cls,
        db: AsyncSession,
        token: str,
        client: Any,
        now: datetime,
        pepper: str | bytes | None,
    ) -> None:
        """
        撤销 Refresh Token 及其 Family

        :param db: 异步数据库会话
        :param token: 待撤销的 Refresh Token
        :param client: 发起撤销请求的 OAuth Client ORM
        :param now: 当前时间
        :param pepper: 摘要 Pepper
        :return: None
        """

        try:
            parsed = parse_opaque_token(token, cls._REFRESH_PREFIX)
            secret_pepper = OidcConfig.oidc_token_hash_pepper if pepper is None else pepper
            digest = token_digest(token, secret_pepper)
            row = await OAuthTokenDao.get_by_token_id(db, parsed.token_id, for_update=True)
        except (OpaqueTokenError, TypeError, ValueError):
            return
        if row is None or not hmac.compare_digest(row.token_hash, digest) or row.client_pk != client.client_pk:
            return
        if row.status in {'revoked', 'expired', 'reuse_detected'}:
            return
        await OAuthTokenDao.revoke_family(db, row.family_id, reason='client_revocation')
        await AuditService.record(
            db,
            OidcAuditEvent.TOKEN_REVOKED,
            'success',
            client_id=client.client_id,
            subject_id=getattr(row, 'subject_id', None),
            sid=getattr(row, 'sid', None),
            grant_id=getattr(row, 'grant_id', None),
            token_id=parsed.token_id,
        )

        return

    @classmethod
    async def _revoke_access(
        cls,
        db: AsyncSession,
        redis: Redis,
        token: str,
        client: Any,
        now: datetime,
        verification_keys: Any,
        verification_key: Any,
        coordinator: AfterCommitCoordinator | None,
    ) -> None:
        """
        验证并撤销 Access Token

        :param db: 异步数据库会话
        :param redis: 异步 Redis 客户端
        :param token: 待撤销的 Access Token
        :param client: 发起撤销请求的 OAuth Client ORM
        :param now: 当前时间
        :param verification_keys: 验证密钥集合
        :param verification_key: 验证密钥
        :param coordinator: 事务提交协调器
        :return: None
        :raises RevocationError: 令牌撤销操作失败
        """

        try:
            claims = decode_access_token(
                token,
                verification_keys,
                issuer=OidcConfig.oidc_issuer,
                clock_skew=OidcConfig.oidc_allowed_clock_skew_seconds,
                verification_key=verification_key,
            )
        except Exception:
            return
        if claims.get('client_id') != client.client_id:
            return
        jti = claims.get('jti')
        exp = claims.get('exp')
        if not isinstance(jti, str) or not jti or isinstance(exp, bool) or not isinstance(exp, (int, float)):
            return
        remaining = exp - now.timestamp() + OidcConfig.oidc_allowed_clock_skew_seconds
        if not math.isfinite(remaining) or remaining <= 0:
            return
        if coordinator is None or not isinstance(coordinator, AfterCommitCoordinator):
            raise RevocationError('server_error', 'A transaction coordinator is required')
        ttl = max(1, math.ceil(remaining))
        key = OidcRedisKey.revoked_jti(jti)

        async def write_revocation() -> None:
            """
            执行 write_revocation 的校验和转换

            :return: None
            """

            await redis.set(key, '1', ex=ttl)
            await AuditService.record_independent(
                db,
                OidcAuditEvent.TOKEN_REVOKED,
                'success',
                client_id=client.client_id,
                token_id=jti,
            )

        await coordinator.register(write_revocation)

        return

    @staticmethod
    def _utc_datetime(value: datetime | None) -> datetime | None:
        """
        将输入时间统一转换为项目时间

        :param value: 数据库读取的可选时间
        :return: 带时区的 UTC 时间或 None
        """

        return TimezoneUtil.to_utc(value) if value is not None else None


class UserInfoService:
    """
    OIDC UserInfo 模块服务层
    """

    @classmethod
    async def build(cls, db: AsyncSession, claims: dict[str, Any], redis: Redis | None) -> dict[str, Any]:
        """
        验证 Access Token 声明并构造 UserInfo 响应

        :param db: 异步数据库会话
        :param claims: 令牌声明
        :param redis: 异步 Redis 客户端
        :return: 包含协议字段的字典
        :raises ValueError: 输入值不符合约束
        """

        client = await OAuthClientDao.get_by_client_id(db, claims['client_id'], active_only=True)
        if client is None or client.status != '0':
            raise ValueError('client is inactive')
        resources = IntrospectionService._resource_audiences(IntrospectionService._audiences(claims.get('aud')))
        if not await IntrospectionService._client_allows_access(db, client, claims, resources):
            raise ValueError('client policy is inactive')
        user = await IntrospectionService._access_user_state(db, claims, client, resources, TimezoneUtil.utc_now())
        if user is None:
            raise ValueError('authorization is inactive')
        await cls._check_revocation(redis, claims['jti'])

        scopes = str(claims.get('scope', '')).split()
        policy, allowed = await ClaimService.resolve_scope_policy(db, client.client_pk, scopes)
        roles, department = await ClaimService.load_roles_and_department(db, user.user_id)

        return ClaimService.build_claims(
            user,
            scopes,
            policy,
            allowed,
            subject_id=claims['sub'],
            roles=roles,
            department=department,
        )

    @staticmethod
    async def _check_revocation(redis: Redis | None, jti: str) -> None:
        """
        检查 Access Token 是否已被撤销

        :param redis: 异步 Redis 客户端
        :param jti: 令牌 JTI
        :return: None
        :raises ValueError: 输入值不符合约束
        """

        if redis is None:
            raise ValueError('token is revoked')
        try:
            revoked = bool(await redis.exists(OidcRedisKey.revoked_jti(jti)))
        except (ConnectionError, TimeoutError, OSError):
            raise ValueError('token status unavailable') from None
        if revoked:
            raise ValueError('token is revoked')
