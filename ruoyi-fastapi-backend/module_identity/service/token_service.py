from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import ValidationError
from redis.exceptions import RedisError

from common.constant import OidcAuditEvent
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_identity.dao.identity_user_dao import IdentityUserDao
from module_identity.dao.oauth_access_policy_dao import OAuthAccessPolicyDao
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.dao.oauth_token_dao import OAuthTokenDao
from module_identity.dao.oidc_key_dao import OidcKeyDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken
from module_identity.entity.vo.protocol_vo import TokenRequest
from module_identity.security.client_auth import (
    ClientAuthenticationError,
    authenticate_client,
    parse_client_secret_basic,
)
from module_identity.security.jwt_profile import JwtProfileError, encode_access_token, encode_id_token
from module_identity.security.opaque_token import (
    OpaqueTokenError,
    generate_refresh_token,
    parse_opaque_token,
    token_digest,
)
from module_identity.security.pkce import PkceError, verify_code_challenge
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.audit_service import AuditService
from module_identity.service.authorization_service import AuthorizationCodeReuseError, AuthorizationCodeService
from module_identity.service.identity_service import ClaimService, IdentitySubjectService
from module_identity.service.key_service import KeyService, KeyServiceError
from utils.time_util import TimezoneUtil

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from module_admin.entity.do.user_do import SysUser
    from module_identity.entity.do.identity_subject_do import SysIdentitySubject
    from module_identity.entity.do.oauth_client_do import SysOAuthClient
    from module_identity.entity.do.oauth_grant_do import SysSsoSession
    from module_identity.entity.do.oauth_resource_do import SysOAuthResource, SysOAuthScope


@dataclass(frozen=True, slots=True)
class TokenResult:
    """
    记录 Token Endpoint 生成的各类令牌
    """

    access_token: str
    expires_in: int
    refresh_token: str | None = None
    scope: str | None = None
    id_token: str | None = None

    @property
    def token_type(self) -> str:
        """
        返回 OAuth Bearer 令牌类型

        :return: 固定为 OAuth 2.0 Bearer token 类型的字符串
        """

        return 'Bearer'

    def as_dict(self) -> dict[str, Any]:
        """
        将令牌结果转换为 Token Endpoint 响应字典

        :return: 包含协议字段的字典
        """

        result: dict[str, Any] = {
            'access_token': self.access_token,
            'token_type': 'Bearer',
            'expires_in': self.expires_in,
        }
        if self.refresh_token is not None:
            result['refresh_token'] = self.refresh_token
        if self.scope is not None:
            result['scope'] = self.scope
        if self.id_token is not None:
            result['id_token'] = self.id_token
        return result

    def __getitem__(self, key: str) -> Any:
        """
        按字段名读取 Token Endpoint 响应值

        :param key: 要读取的 Token Endpoint 响应字段名
        :return: 对应字段的 Access Token、有效期或可选令牌值
        """

        return self.as_dict()[key]


class RefreshTokenReuseDetected(OAuthProtocolException):
    """
    Refresh Token 重放检测错误类型
    """

    must_commit = True

    def __init__(self) -> None:
        """
        保存 OAuth 撤销错误代码和描述

        :return: None
        """

        super().__init__('invalid_grant', 'The authorization grant is invalid or expired', 400)


class TokenService:
    """
    OAuth Token 模块服务层
    """

    _USERINFO_AUDIENCE_SUFFIX = '/oauth2/userinfo'
    _MACHINE_SCOPE_TYPE = 'resource'
    _ACTIVE_CLIENT_STATUSES = frozenset({'0', 0, 'active'})
    _ACTIVE_GRANT_STATUS = 'active'
    _ACTIVE_SESSION_STATUS = 'active'
    _MAX_RESOURCE_COUNT = 1
    _MIN_TOKEN_PEPPER_BYTES = 32

    @classmethod
    async def authenticate_client(
        cls,
        db: AsyncSession,
        *,
        authorization: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> tuple[SysOAuthClient, OAuthClientPrincipal]:
        """
        解析凭据并验证 OAuth Client 身份

        :param db: 异步数据库会话
        :param authorization: RFC 7617 Basic Header；机密 Client 必须使用该方式
        :param client_id: 公共 Client 的表单 Client ID
        :param client_secret: 仅用于拒绝公共 Client 的 body Secret
        :return: 已启用 Client 行和不可伪造的 Client Principal
        :raises OAuthProtocolException: Client 凭据无效时抛出 invalid_client
        """

        if authorization is not None and client_secret is not None:
            cls._invalid_client()
        lookup_id = client_id
        if authorization is not None:
            try:
                lookup_id, _ = parse_client_secret_basic(authorization)
            except (ClientAuthenticationError, TypeError, ValueError):
                cls._invalid_client()
        if not isinstance(lookup_id, str) or not lookup_id:
            cls._invalid_client()
        row = await OAuthClientDao.get_by_client_id(db, lookup_id, active_only=True)
        if row is None:
            cls._invalid_client()
        secrets = await OAuthClientDao.list_secrets(db, row.client_pk, active_only=True)
        matched_secret_hash: str | None = None

        def capture_secret_match(secret_hash: str) -> None:
            """
            保存认证过程中匹配的 Client Secret 哈希

            :param secret_hash: 已匹配的持久化 Secret 哈希
            :return: None
            """

            nonlocal matched_secret_hash
            matched_secret_hash = secret_hash

        try:
            principal = authenticate_client(
                row,
                authorization,
                client_id=client_id,
                client_secret=client_secret,
                secret_hashes=secrets,
                secret_match_callback=capture_secret_match,
            )
        except (ClientAuthenticationError, TypeError, ValueError):
            cls._invalid_client()
        if principal.client_type == 'confidential' and matched_secret_hash is not None:
            matched_secret_id = next(
                (
                    getattr(secret_row, 'secret_id', None)
                    for secret_row in secrets
                    if getattr(secret_row, 'secret_hash', None) == matched_secret_hash
                ),
                None,
            )
            if isinstance(matched_secret_id, str):
                await OAuthClientDao.mark_secret_used(db, matched_secret_id)
        return row, principal

    @classmethod
    async def _handle_authorization_code_reuse(
        cls,
        db: AsyncSession,
        redis: Redis,
        code: str,
        client_id: str,
        pepper: str | bytes,
    ) -> None:
        """
        撤销重用授权码关联的 Grant 并记录高风险审计

        :param db: 异步数据库会话
        :param redis: Authorization Code Redis 客户端
        :param code: 被重复提交的 Authorization Code 明文
        :param client_id: 已认证 Client 公开标识
        :param pepper: Authorization Code 摘要 Pepper
        :return: None
        :raises OAuthProtocolException: 撤销或审计无法安全持久化时抛出
        """

        try:
            consumed_payload = await AuthorizationCodeService.consumed_payload(redis, code, pepper=pepper)
            grant_id = consumed_payload.get('grantId') if consumed_payload else None
            if isinstance(grant_id, str) and callable(getattr(db, 'execute', None)):
                await OAuthGrantDao.revoke(db, grant_id, reason='authorization_code_reuse')
            await AuditService.record_independent(
                db,
                OidcAuditEvent.AUTHORIZATION_CODE_REUSED,
                'failure',
                risk_level='high',
                client_id=client_id,
                failure_code='authorization_code_reused',
            )
        except Exception:
            raise OAuthProtocolException('server_error', 'Token endpoint is unavailable', 500) from None

    @classmethod
    async def authorization_code(
        cls,
        db: AsyncSession,
        redis: Redis,
        request: TokenRequest | Mapping[str, Any],
        client: OAuthClientPrincipal,
        *,
        signing_key: RSAPrivateKey | None = None,
        kid: str | None = None,
        now: datetime | None = None,
        token_pepper: str | bytes | None = None,
    ) -> TokenResult:
        """
        消费授权码并签发用户令牌

        :param db: 异步数据库会话，调用方负责提交或回滚事务
        :param redis: Authorization Code 所在 Redis 客户端
        :param request: Token Endpoint 请求或字段映射
        :param client: 已完成 Client Authentication 的不可伪造主体
        :param signing_key: 可注入的 RSA 私钥；省略时从 KeyService 读取
        :param kid: 注入私钥对应的签名 Key ID
        :param now: 可注入 项目当前时间
        :param token_pepper: Refresh Token HMAC Pepper
        :return: 标准 Token 结果
        :raises OAuthProtocolException: 任一授权绑定或安全状态无效时抛出统一错误
        """

        current = cls._utc_datetime(now) or TimezoneUtil.utc_now()
        parsed = cls._request(request)
        if parsed.get('grant_type') != 'authorization_code':
            cls._invalid_request()
        client_row = await cls._resolve_client(db, client)
        await OAuthAccessPolicyDao.lock_client(db, client_row.client_pk)
        if parsed.get('client_id') not in (None, client_row.client_id) or (
            client_row.client_type == 'public' and parsed.get('client_id') != client_row.client_id
        ):
            cls._invalid_client()
        if 'authorization_code' not in cls._json_list(client_row.grant_types):
            cls._invalid_grant()
        code = parsed.get('code')
        if not isinstance(code, str):
            cls._invalid_grant()
        try:
            code_payload = await AuthorizationCodeService.consume(redis, code, pepper=cls._token_pepper(token_pepper))
        except AuthorizationCodeReuseError:
            await cls._handle_authorization_code_reuse(
                db,
                redis,
                code,
                client_row.client_id,
                cls._token_pepper(token_pepper),
            )
            raise
        except (OAuthProtocolException, OpaqueTokenError, RedisError) as exc:
            cls._map_oauth_failure(exc, 'invalid_grant')
        if code_payload.get('clientPk') != client_row.client_pk:
            cls._invalid_grant()
        if parsed.get('redirect_uri') != code_payload.get('redirectUri'):
            cls._invalid_grant()
        verifier = parsed.get('code_verifier')
        try:
            if not verify_code_challenge(verifier, code_payload['codeChallenge'], code_payload['codeChallengeMethod']):
                cls._invalid_grant()
        except (PkceError, TypeError, ValueError):
            cls._invalid_grant()
        user, subject = await cls._require_user_identity(
            db,
            int(code_payload['userId']),
            str(code_payload['subjectId']),
            int(code_payload['authVersion']),
        )
        session = await cls._require_session(
            db,
            str(code_payload['sid']),
            int(code_payload['userId']),
            str(code_payload['subjectId']),
            int(code_payload['authVersion']),
            current,
        )
        grant = await cls._require_grant(
            db,
            code_payload.get('grantId'),
            int(code_payload['userId']),
            client_row.client_pk,
            list(code_payload['scopes']),
            list(code_payload['resources']),
            current,
        )
        grant.last_used_at = current
        scopes, resources, resource = await cls._validate_client_scope_resource(
            db, client_row, list(code_payload['scopes']), list(code_payload['resources'])
        )
        access_token, expires_in = await cls._issue_access_token(
            db,
            client_row,
            user,
            subject,
            session,
            scopes,
            resources,
            resource,
            grant_type='authorization_code',
            grant_id=grant.grant_id,
            signing_key=signing_key,
            kid=kid,
            now=current,
        )
        refresh_token = None
        if 'offline_access' in scopes and 'refresh_token' in cls._json_list(client_row.grant_types):
            refresh_token = await cls._create_refresh_token(
                db,
                client_row,
                grant,
                user,
                subject,
                session,
                scopes,
                resources,
                current,
                token_pepper=cls._token_pepper(token_pepper),
            )
        id_token = None
        if 'openid' in scopes:
            id_token = await cls._issue_id_token(
                db,
                client_row,
                user,
                subject,
                session,
                scopes,
                code_payload['nonce'],
                access_token,
                signing_key=signing_key,
                kid=kid,
                now=current,
            )
        await SsoSessionDao.record_client(db, session.sid, client_row.client_pk, current)
        await AuditService.record(
            db,
            OidcAuditEvent.TOKEN_ISSUED,
            'success',
            client_id=client_row.client_id,
            subject_id=subject.subject_id,
            sid=session.sid,
            grant_id=getattr(grant, 'grant_id', None),
        )

        return TokenResult(access_token, expires_in, refresh_token, ' '.join(scopes), id_token)

    @classmethod
    async def refresh_token(  # noqa: PLR0915
        cls,
        db: AsyncSession,
        request: TokenRequest | Mapping[str, Any],
        client: OAuthClientPrincipal,
        *,
        signing_key: RSAPrivateKey | None = None,
        kid: str | None = None,
        now: datetime | None = None,
        token_pepper: str | bytes | None = None,
    ) -> TokenResult:
        """
        校验 Refresh Token 并完成令牌轮换

        :param db: 异步数据库会话，调用方负责提交或回滚事务
        :param request: Refresh Token 请求或字段映射
        :param client: 已完成 Client Authentication 的不可伪造主体
        :param signing_key: 可注入的 RSA 私钥
        :param kid: 注入私钥对应的 Key ID
        :param now: 可注入 项目当前时间
        :param token_pepper: Refresh Token HMAC Pepper
        :return: 新 Access Token 与轮换后的 Refresh Token
        :raises OAuthProtocolException: Token 无效、过期、重放或绑定状态失效
        :raises RefreshTokenReuseDetected: 检测到 Refresh Token 重放
        """

        current = cls._utc_datetime(now) or TimezoneUtil.utc_now()
        parsed = cls._request(request)
        if parsed.get('grant_type') != 'refresh_token' or not isinstance(parsed.get('refresh_token'), str):
            cls._invalid_request()
        client_row = await cls._resolve_client(db, client)
        await OAuthAccessPolicyDao.lock_client(db, client_row.client_pk)
        if parsed.get('client_id') not in (None, client_row.client_id) or (
            client_row.client_type == 'public' and parsed.get('client_id') != client_row.client_id
        ):
            cls._invalid_client()
        if 'refresh_token' not in cls._json_list(client_row.grant_types):
            cls._invalid_grant()
        pepper = cls._token_pepper(token_pepper)
        try:
            opaque = parse_opaque_token(parsed['refresh_token'], 'rt1')
            digest = token_digest(parsed['refresh_token'], pepper)
        except (OpaqueTokenError, TypeError, ValueError):
            cls._invalid_grant()
        row = await OAuthTokenDao.get_by_token_id(db, opaque.token_id, for_update=True)
        if row is None or not hmac.compare_digest(row.token_hash, digest):
            cls._invalid_grant()
        if row.client_pk != client_row.client_pk:
            cls._invalid_grant()
        if row.status != 'active':
            if row.status == 'used':
                await OAuthTokenDao.refresh_token_family_reuse(db, row.family_id, row.token_id, now=current)
                await AuditService.record(
                    db,
                    OidcAuditEvent.REFRESH_REUSE_DETECTED,
                    'failure',
                    risk_level='high',
                    client_id=client_row.client_id,
                    subject_id=row.subject_id,
                    sid=row.sid,
                    token_id=row.token_id,
                )
                raise RefreshTokenReuseDetected
            cls._invalid_grant()
        idle_expires = cls._utc_datetime(row.idle_expires_at)
        absolute_expires = cls._utc_datetime(row.absolute_expires_at)
        if idle_expires is None or absolute_expires is None or idle_expires <= current or absolute_expires <= current:
            row.status = 'expired'
            cls._invalid_grant()
        user, subject = await cls._require_user_identity(db, row.user_id, row.subject_id, row.auth_version)
        session = await cls._require_session(
            db, row.sid, row.user_id, row.subject_id, row.auth_version, current, allow_offline=True
        )
        grant = await cls._require_grant(
            db, row.grant_id, row.user_id, row.client_pk, row.scopes, row.resources, current
        )
        if grant is None:
            cls._invalid_grant()
        grant.last_used_at = current
        requested_scopes = cls._requested_scopes(parsed.get('scope'), row.scopes)
        requested_resources = cls._requested_resources(parsed.get('resource'), row.resources)
        if not set(requested_scopes).issubset(set(row.scopes)) or requested_resources != list(row.resources):
            cls._invalid_grant()
        scopes, resources, resource = await cls._validate_client_scope_resource(
            db, client_row, requested_scopes, requested_resources
        )
        new_token = generate_refresh_token()
        new_opaque = parse_opaque_token(new_token, 'rt1')
        # 先写入后继令牌，再更新即时校验的自引用外键
        new_refresh = await cls._create_refresh_token(
            db,
            client_row,
            grant,
            user,
            subject,
            session,
            scopes,
            resources,
            current,
            token_pepper=pepper,
            token=new_token,
            family_id=row.family_id,
            parent_token_id=row.token_id,
            absolute_expires_at=absolute_expires,
        )
        if not await OAuthTokenDao.mark_used(db, row.token_id, new_opaque.token_id, now=current):
            await OAuthTokenDao.refresh_token_family_reuse(db, row.family_id, row.token_id, now=current)
            await AuditService.record(
                db,
                OidcAuditEvent.REFRESH_REUSE_DETECTED,
                'failure',
                risk_level='high',
                client_id=client_row.client_id,
                subject_id=row.subject_id,
                sid=row.sid,
                token_id=row.token_id,
            )
            raise RefreshTokenReuseDetected
        access_token, expires_in = await cls._issue_access_token(
            db,
            client_row,
            user,
            subject,
            session,
            scopes,
            resources,
            resource,
            grant_type='refresh_token',
            grant_id=grant.grant_id,
            signing_key=signing_key,
            kid=kid,
            now=current,
        )
        await AuditService.record(
            db,
            OidcAuditEvent.REFRESH_ROTATED,
            'success',
            client_id=client_row.client_id,
            subject_id=subject.subject_id,
            sid=session.sid,
            grant_id=grant.grant_id,
        )

        return TokenResult(access_token, expires_in, new_refresh, ' '.join(scopes))

    @classmethod
    async def client_credentials(
        cls,
        db: AsyncSession,
        request: TokenRequest | Mapping[str, Any],
        client: OAuthClientPrincipal,
        *,
        signing_key: RSAPrivateKey | None = None,
        kid: str | None = None,
        now: datetime | None = None,
    ) -> TokenResult:
        """
        按 Client Credentials Grant 签发机器令牌

        :param db: 异步数据库会话，调用方负责提交事务
        :param request: Client Credentials 请求或字段映射
        :param client: 已完成 Client Authentication 的不可伪造主体
        :param signing_key: 可注入的 RSA 私钥
        :param kid: 注入私钥对应的 Key ID
        :param now: 可注入 项目当前时间
        :return: 不包含 Refresh/ID Token 的机器 Token 结果
        :raises OAuthProtocolException: Client、Scope 或 Resource 策略无效时抛出
        """

        current = cls._utc_datetime(now) or TimezoneUtil.utc_now()
        parsed = cls._request(request)
        if parsed.get('grant_type') != 'client_credentials':
            cls._invalid_request()
        client_row = await cls._resolve_client(db, client)
        if parsed.get('client_id') not in (None, client_row.client_id) or (
            client_row.client_type == 'public' and parsed.get('client_id') != client_row.client_id
        ):
            cls._invalid_client()
        if client_row.client_type != 'confidential' or 'client_credentials' not in cls._json_list(
            client_row.grant_types
        ):
            cls._invalid_client()
        if isinstance(client, OAuthClientPrincipal) and client.auth_method == 'none':
            cls._invalid_client()
        requested = cls._requested_scopes(parsed.get('scope'), [])
        if not requested:
            cls._invalid_scope()
        resource_value = parsed.get('resource')
        if not isinstance(resource_value, str) or not resource_value:
            cls._invalid_scope()
        scopes, resources, resource = await cls._validate_client_scope_resource(
            db, client_row, requested, [resource_value], machine_only=True
        )
        ttl = cls._access_ttl(client_row, resource)
        signer, signing_kid = await cls._resolve_signer(db, signing_key, kid, current)
        claims = {
            'iss': OidcConfig.oidc_issuer,
            'sub': f'client:{client_row.client_id}',
            'aud': resources,
            'client_id': client_row.client_id,
            'scope': ' '.join(scopes),
            'gty': 'client_credentials',
            'client_policy_version': client_row.policy_version,
            'iat': int(current.timestamp()),
            'nbf': int(current.timestamp()),
            'exp': int((current + timedelta(seconds=ttl)).timestamp()),
            'jti': str(uuid4()),
        }
        try:
            access = encode_access_token(claims, signer, signing_kid)
        except (JwtProfileError, TypeError, ValueError):
            cls._server_error()
        return TokenResult(access, ttl, scope=' '.join(scopes))

    @classmethod
    async def issue_token(
        cls,
        db: AsyncSession,
        redis: Redis,
        request: TokenRequest | Mapping[str, Any],
        client: OAuthClientPrincipal,
        **kwargs: Any,
    ) -> TokenResult:
        """
        根据 Grant Type 调度令牌签发流程

        :param db: 异步数据库会话
        :param redis: 异步 Redis 客户端
        :param request: 含 grant_type 等字段的 TokenRequest 或请求字段映射
        :param client: 已认证的 OAuthClientPrincipal 主体
        :param kwargs: 按 Grant Type 传给具体令牌签发方法的可选参数
        :return: 包含 Access Token 及有效期的 Token Endpoint 响应对象
        :raises AssertionError: 内部令牌状态不满足签发条件
        """

        if not isinstance(client, OAuthClientPrincipal):
            cls._invalid_client()
        grant_type = request.grant_type if isinstance(request, TokenRequest) else request.get('grant_type')
        if grant_type == 'authorization_code':
            return await cls.authorization_code(db, redis, request, client, **kwargs)
        if grant_type == 'refresh_token':
            return await cls.refresh_token(db, request, client, **kwargs)
        if grant_type == 'client_credentials':
            return await cls.client_credentials(db, request, client, **kwargs)
        cls._invalid_request()
        raise AssertionError('unreachable')

    @classmethod
    async def _issue_token_transaction(
        cls,
        db: AsyncSession,
        redis: Redis,
        request: TokenRequest | Mapping[str, Any],
        client: OAuthClientPrincipal,
        **kwargs: Any,
    ) -> TokenResult:
        """
        在事务边界内执行令牌签发

        :param db: 异步数据库会话，由本方法提交或回滚
        :param redis: Authorization Code 所在 Redis 客户端
        :param request: 已解析的 Token Endpoint 字段
        :param client: 已认证的 Client 主体
        :param kwargs: 传给令牌签发流程的可选参数
        :return: 标准 Token 领域结果
        :raises RefreshTokenReuseDetected: Family 撤销已写入但需映射为 invalid_grant
        :raises OAuthProtocolException: 业务失败且事务已回滚
        """

        try:
            result = await cls.issue_token(db, redis, request, client, **kwargs)
        except (RefreshTokenReuseDetected, AuthorizationCodeReuseError):
            # 令牌重放属于安全事件，撤销状态和审计记录必须持久化
            try:
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
                raise OAuthProtocolException('server_error', 'Token endpoint is unavailable', 500) from None
            raise
        except Exception:
            await db.rollback()
            raise
        await db.commit()

        return result

    @classmethod
    async def issue_token_request(
        cls,
        db: AsyncSession,
        redis: Redis,
        request: TokenRequest | Mapping[str, Any],
        *,
        authorization: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        **kwargs: Any,
    ) -> TokenResult:
        """
        认证 Client 并处理 Token Endpoint 请求

        :param db: 异步数据库会话，由本方法提交或回滚
        :param redis: Authorization Code 所在 Redis 客户端
        :param request: 已解析的 Token Endpoint 字段
        :param authorization: RFC 7617 Basic Header
        :param client_id: 表单 Client ID
        :param client_secret: 表单 Client Secret
        :param kwargs: 传给令牌签发流程的可选参数
        :return: 标准 Token 领域结果
        """

        try:
            _, principal = await cls.authenticate_client(
                db,
                authorization=authorization,
                client_id=client_id,
                client_secret=client_secret,
            )
        except Exception:
            await db.rollback()
            raise
        return await cls._issue_token_transaction(db, redis, request, principal, **kwargs)

    @classmethod
    async def _issue_access_token(  # noqa: PLR0913
        cls,
        db: AsyncSession,
        client: SysOAuthClient,
        user: SysUser,
        subject: SysIdentitySubject,
        session: SysSsoSession,
        scopes: list[str],
        resources: list[str],
        resource: SysOAuthResource | None,
        *,
        grant_type: str,
        grant_id: str | None = None,
        signing_key: RSAPrivateKey | None,
        kid: str | None,
        now: datetime,
    ) -> tuple[str, int]:
        """
        构造并签署 Access Token

        :param db: 异步数据库会话
        :param client: OAuth Client ORM（SysOAuthClient）
        :param user: 系统用户 ORM（SysUser）
        :param subject: 身份 Subject ORM（SysIdentitySubject）
        :param session: SSO Session ORM（SysSsoSession）
        :param scopes: 已授权且经 Client 绑定校验的 Scope code 列表
        :param resources: 已校验的 Resource audience 列表
        :param resource: 与 Resource audience 对应的 OAuth Resource ORM，或 None
        :param grant_type: 产生该 Access Token 的 OAuth Grant Type 字符串
        :param grant_id: 持久授权的 Grant ID，一次性在线授权为 None
        :param signing_key: 用于签署 Access Token JWT 的 RSA 私钥，或 None
        :param kid: 签名 JWT header 使用的 Key ID，或 None
        :param now: 生成 JWT 的 项目当前时间
        :return: 签名后的 JWT Access Token 文本及其有效秒数
        """

        ttl = cls._access_ttl(client, resource)
        claims = await cls._user_claims(db, client, user, subject, scopes, resource)
        auth_time = cls._numeric_time(session.auth_time)
        session_amr = cls._json_list(session.amr)
        claims.update(
            {
                'iss': OidcConfig.oidc_issuer,
                'sub': subject.subject_id,
                'aud': cls._audiences(OidcConfig.oidc_issuer, resources),
                'exp': int((now + timedelta(seconds=ttl)).timestamp()),
                'iat': int(now.timestamp()),
                'nbf': int(now.timestamp()),
                'jti': str(uuid4()),
                'client_id': client.client_id,
                'sid': session.sid,
                'scope': ' '.join(scopes),
                'auth_time': auth_time,
                'acr': session.acr,
                'amr': session_amr,
                'ver': int(subject.auth_version),
                'gty': grant_type,
                'grant_id': grant_id,
                'client_policy_version': client.policy_version,
            }
        )
        signer, signing_kid = await cls._resolve_signer(db, signing_key, kid, now)
        try:
            return encode_access_token(claims, signer, signing_kid), ttl
        except (JwtProfileError, TypeError, ValueError):
            cls._server_error()

    @classmethod
    async def _issue_id_token(  # noqa: PLR0913
        cls,
        db: AsyncSession,
        client: SysOAuthClient,
        user: SysUser,
        subject: SysIdentitySubject,
        session: SysSsoSession,
        scopes: list[str],
        nonce: str,
        access_token: str,
        *,
        signing_key: RSAPrivateKey | None,
        kid: str | None,
        now: datetime,
    ) -> str:
        """
        构造包含用户声明的 ID Token

        :param db: 异步数据库会话
        :param client: OAuth Client ORM（SysOAuthClient）
        :param user: 系统用户 ORM（SysUser）
        :param subject: 身份 Subject ORM（SysIdentitySubject）
        :param session: SSO Session ORM（SysSsoSession）
        :param scopes: 已授权并用于筛选 ID Token 用户声明的 Scope code 列表
        :param nonce: 授权请求绑定的 OIDC nonce 字符串
        :param access_token: 同一 Token Endpoint 响应中的 JWT Access Token 文本
        :param signing_key: 用于签署 ID Token JWT 的 RSA 私钥，或 None
        :param kid: 签名 JWT header 使用的 Key ID，或 None
        :param now: 生成 JWT 的 项目当前时间
        :return: 签名后的 OIDC ID Token JWT 文本
        """

        ttl = cls._id_ttl(client)
        resource = None
        claims = await cls._user_claims(db, client, user, subject, scopes, resource)
        claims.update(
            {
                'iss': OidcConfig.oidc_issuer,
                'sub': subject.subject_id,
                'aud': client.client_id,
                'exp': int((now + timedelta(seconds=ttl)).timestamp()),
                'iat': int(now.timestamp()),
                'auth_time': cls._numeric_time(session.auth_time),
                'nonce': nonce,
                'sid': session.sid,
                'acr': session.acr,
                'amr': cls._json_list(session.amr),
                'at_hash': cls._at_hash(access_token),
            }
        )
        signer, signing_kid = await cls._resolve_signer(db, signing_key, kid, now)
        try:
            return encode_id_token(claims, signer, signing_kid)
        except (JwtProfileError, TypeError, ValueError):
            cls._server_error()

    @classmethod
    async def _user_claims(
        cls,
        db: AsyncSession,
        client: SysOAuthClient,
        user: SysUser,
        subject: SysIdentitySubject,
        scopes: list[str],
        resource: SysOAuthResource | None,
    ) -> dict[str, Any]:
        """
        收集 ID Token 所需的用户声明

        :param db: 异步数据库会话
        :param client: OAuth Client ORM（SysOAuthClient）
        :param user: 系统用户 ORM（SysUser）
        :param subject: 身份 Subject ORM（SysIdentitySubject）
        :param scopes: 用于解析声明策略的 Scope code 列表
        :param resource: 目标 OAuth Resource ORM，或 None（ID Token 不绑定资源）
        :return: 按 Scope 策略生成的 OIDC 用户声明字典
        """

        policy, allowed = await ClaimService.resolve_scope_policy(
            db,
            client.client_pk,
            scopes,
            resource_allowed_claims=resource.allowed_claims if resource is not None else None,
        )
        roles, department = await ClaimService.load_roles_and_department(db, user.user_id)
        claims = ClaimService.build_claims(
            user,
            scopes,
            policy,
            allowed,
            subject_id=subject.subject_id,
            roles=roles,
            department=department,
        )

        return claims

    @classmethod
    async def _create_refresh_token(  # noqa: PLR0913
        cls,
        db: AsyncSession,
        client: SysOAuthClient,
        grant: SysOAuthGrant,
        user: SysUser,
        subject: SysIdentitySubject,
        session: SysSsoSession,
        scopes: list[str],
        resources: list[str],
        now: datetime,
        *,
        token_pepper: str | bytes | None,
        token: str | None = None,
        family_id: str | None = None,
        parent_token_id: str | None = None,
        absolute_expires_at: datetime | None = None,
    ) -> str:
        """
        创建并持久化 Refresh Token 记录

        :param db: 异步数据库会话
        :param client: OAuth Client ORM（SysOAuthClient）
        :param grant: 用户对该 Client 的 OAuth Grant ORM（SysOAuthGrant）
        :param user: 系统用户 ORM（SysUser）
        :param subject: 身份 Subject ORM（SysIdentitySubject）
        :param session: 绑定用户身份版本的 SSO Session ORM（SysSsoSession）
        :param scopes: 写入 Refresh Token 记录的 Scope code 列表
        :param resources: 写入 Refresh Token 记录的 Resource audience 列表
        :param now: 签发 Refresh Token 记录的 项目当前时间
        :param token_pepper: 用于 Refresh Token HMAC 摘要的配置值或覆盖值
        :param token: 可复用的 opaque Refresh Token 文本，或 None 表示新生成
        :param family_id: Refresh Token 轮换族标识，或 None 表示创建新族
        :param parent_token_id: 被轮换的父 Refresh Token ID，或 None
        :param absolute_expires_at: 轮换族已有的绝对过期时间，或 None
        :return: 新建 opaque Refresh Token 文本
        """

        raw = token or generate_refresh_token()
        parsed = parse_opaque_token(raw, 'rt1')
        pepper = cls._token_pepper(token_pepper)
        absolute = absolute_expires_at or now + timedelta(seconds=cls._refresh_absolute_ttl(client))
        absolute = min(absolute, now + timedelta(seconds=cls._refresh_absolute_ttl(client))) if absolute else absolute
        idle = min(now + timedelta(seconds=cls._refresh_idle_ttl(client)), absolute)
        row = SysOAuthRefreshToken(
            token_id=parsed.token_id,
            token_hash=token_digest(raw, pepper),
            family_id=family_id or str(uuid4()),
            parent_token_id=parent_token_id,
            grant_id=grant.grant_id,
            user_id=user.user_id,
            subject_id=subject.subject_id,
            auth_version=subject.auth_version,
            client_pk=client.client_pk,
            sid=session.sid,
            scopes=list(scopes),
            resources=list(resources),
            status='active',
            issued_at=now,
            idle_expires_at=idle,
            absolute_expires_at=absolute,
        )
        await OAuthTokenDao.create(db, row)

        return raw

    @classmethod
    async def _validate_client_scope_resource(
        cls,
        db: AsyncSession,
        client: SysOAuthClient,
        scopes: list[str],
        resources: list[str],
        *,
        machine_only: bool = False,
    ) -> tuple[list[str], list[str], SysOAuthResource | None]:
        """
        校验 Client 请求的 Scope 和 Resource

        :param db: 异步数据库会话
        :param client: OAuth Client ORM（SysOAuthClient）
        :param scopes: 请求或授权记录中的 Scope code 列表
        :param resources: 请求或授权记录中的 Resource audience 列表
        :param machine_only: 是否限制为 resource 类型的机器 Scope
        :return: 去重后的 Scope code 列表、Resource audience 列表及匹配的 Resource ORM
        """

        if len(resources) > cls._MAX_RESOURCE_COUNT or len(set(scopes)) != len(scopes):
            cls._invalid_scope()
        bindings = await OAuthClientDao.list_scope_bindings(db, client.client_pk)
        definitions = await OAuthClientDao.list_scope_definitions(db)
        by_pk = {item.scope_pk: item for item in definitions}
        bound: dict[str, SysOAuthScope] = {}
        for binding in bindings:
            definition = by_pk.get(binding.scope_pk)
            if definition is not None and definition.status == '0':
                bound[definition.scope_code] = definition
        if any(scope not in bound for scope in scopes):
            cls._invalid_scope()
        if machine_only and any(bound[scope].scope_type != cls._MACHINE_SCOPE_TYPE for scope in scopes):
            cls._invalid_scope()
        resource_rows = list(await OAuthClientDao.list_resources(db, client.client_pk))
        resource_by_audience = {row.audience: row for row in resource_rows if row.status == '0'}
        resource = resource_by_audience.get(resources[0]) if resources else None
        if resources and resource is None:
            cls._invalid_scope()
        for scope in scopes:
            definition = bound[scope]
            if definition.scope_type == 'resource' and (
                resource is None or definition.resource_pk != resource.resource_pk
            ):
                cls._invalid_scope()
        if resource is not None and resource.signing_alg != 'RS256':
            cls._invalid_scope()
        return list(dict.fromkeys(scopes)), list(dict.fromkeys(resources)), resource

    @classmethod
    async def _require_grant(
        cls,
        db: AsyncSession,
        grant_id: object,
        user_id: int,
        client_pk: int,
        scopes: list[str],
        resources: list[str],
        now: datetime,
    ) -> SysOAuthGrant:
        """
        加载并验证用户授权 Grant

        :param db: 异步数据库会话
        :param grant_id: 授权记录的非空 grant_id 字符串
        :param user_id: 系统用户主键
        :param client_pk: OAuth Client ORM 主键
        :param scopes: 需要包含在 Grant 授权范围内的 Scope code 列表
        :param resources: 需要包含在 Grant 授权范围内的 Resource audience 列表
        :param now: 检查 Grant 过期状态的 项目当前时间
        :return: 匹配请求范围的有效授权 Grant
        :raises OAuthProtocolException: 授权记录或用户访问策略无效
        """

        if not isinstance(grant_id, str) or not grant_id:
            cls._invalid_grant()
        if await OAuthAccessPolicyDao.is_blocked(db, user_id, client_pk, for_update=True):
            cls._invalid_grant()
        grant = await OAuthGrantDao.get_by_grant_id_for_update(db, grant_id, refresh=True)
        client = await OAuthClientDao.get_by_pk(db, client_pk, active_only=True)
        if (
            grant is None
            or client is None
            or grant.user_id != user_id
            or grant.client_pk != client_pk
            or grant.status != cls._ACTIVE_GRANT_STATUS
            or grant.client_policy_version != client.policy_version
            or (grant.expires_at is not None and cls._utc_datetime(grant.expires_at) <= now)
            or not set(scopes).issubset(set(grant.granted_scopes or []))
            or not set(resources).issubset(set(grant.granted_resources or []))
        ):
            cls._invalid_grant()
        return grant

    @classmethod
    async def _require_user_identity(
        cls, db: AsyncSession, user_id: int, subject_id: str, auth_version: int
    ) -> tuple[SysUser, SysIdentitySubject]:
        """
        验证用户与 Subject 的身份版本

        :param db: 异步数据库会话
        :param user_id: 系统用户主键
        :param subject_id: 身份 Subject 的稳定标识
        :param auth_version: 必须与用户 Subject 和 SSO Session 一致的认证版本
        :return: 通过状态、删除标记及认证版本校验的系统用户 ORM 与 Subject ORM
        """

        user = await IdentityUserDao.get_user(db, user_id)
        try:
            subject = await IdentitySubjectService.require_by_user_id(
                db,
                user_id,
                audit_writer=lambda missing_user_id: AuditService.record_independent(
                    db,
                    OidcAuditEvent.IDENTITY_SUBJECT_MISSING,
                    'failure',
                    risk_level='high',
                    user_id=missing_user_id,
                    failure_code='identity_integrity',
                ),
            )
        except OAuthProtocolException:
            cls._invalid_grant()
        if (
            user is None
            or user.status != '0'
            or user.del_flag != '0'
            or subject.subject_id != subject_id
            or subject.auth_version != auth_version
        ):
            cls._invalid_grant()
        return user, subject

    @classmethod
    async def _require_session(
        cls,
        db: AsyncSession,
        sid: str,
        user_id: int,
        subject_id: str,
        auth_version: int,
        now: datetime,
        *,
        allow_offline: bool = False,
    ) -> SysSsoSession:
        """
        加载并验证关联的 SSO Session

        :param db: 异步数据库会话
        :param sid: SSO Session 的 sid 字符串
        :param user_id: 系统用户主键
        :param subject_id: 必须与 Session 绑定一致的身份 Subject 标识
        :param auth_version: 必须与 Session 绑定一致的认证版本
        :param now: 检查 Session active 和过期状态的 项目当前时间
        :param allow_offline: 是否允许自然过期但未撤销的SSO会话继续离线续期
        :return: 与用户身份和 Token 绑定一致的 SSO Session
        """

        session = await SsoSessionDao.get_for_token(db, sid, now=now, allow_offline=allow_offline)
        if (
            session is None
            or session.status not in ({'active', 'expired'} if allow_offline else {'active'})
            or session.user_id != user_id
            or session.subject_id != subject_id
            or session.auth_version != auth_version
        ):
            cls._invalid_grant()
        return session

    @classmethod
    async def _resolve_client(cls, db: AsyncSession, client: OAuthClientPrincipal) -> SysOAuthClient:
        """
        确认 OAuth Client 处于可用状态

        :param db: 异步数据库会话
        :param client: 已认证的 OAuthClientPrincipal 主体
        :return: 通过 active 状态、Client 类型及认证方式校验的 OAuth Client ORM
        """

        if not isinstance(client, OAuthClientPrincipal):
            cls._invalid_client()
        row = await OAuthClientDao.get_by_client_id(db, client.client_id, active_only=True)
        if row is None:
            cls._invalid_client()
        if client.client_id != row.client_id:
            cls._invalid_client()
        expected_method = 'none' if row.client_type == 'public' else 'client_secret_basic'
        if client.client_type != row.client_type or client.auth_method != expected_method:
            cls._invalid_client()
        return row

    @classmethod
    async def _resolve_signer(
        cls,
        db: AsyncSession,
        signing_key: RSAPrivateKey | None,
        kid: str | None,
        now: datetime,
    ) -> tuple[RSAPrivateKey, str]:
        """
        加载或确认 JWT 签名密钥

        :param db: 异步数据库会话
        :param signing_key: 可注入的 RSA JWT 签名私钥，或 None
        :param kid: 注入私钥对应的 JWT Key ID，或 None
        :param now: 读取 active OIDC 签名密钥的 项目当前时间
        :return: 用于 JWT 签名的 RSA 私钥及其 Key ID
        """

        if signing_key is not None:
            if not isinstance(kid, str) or not kid:
                cls._server_error()
            return signing_key, kid
        record = await OidcKeyDao.get_active(db, alg='RS256')
        if record is None:
            cls._server_error()
        try:
            key = await KeyService.load_private_key_async(record, now=now)
        except (KeyServiceError, ValueError, OSError):
            cls._server_error()
        return key, record.kid

    @classmethod
    def _access_ttl(
        cls,
        client: SysOAuthClient,
        resource: SysOAuthResource | None,
    ) -> int:
        """
        计算 Access Token 的有效秒数

        :param client: OAuth Client ORM（SysOAuthClient）
        :param resource: 目标 OAuth Resource ORM，或 None
        :return: Access Token 有效秒数（取 Client、Resource 与 OIDC 上限的最小值）
        """

        values: list[int] = []
        if client.access_token_ttl_seconds is not None:
            values.append(client.access_token_ttl_seconds)
        if resource is not None and resource.access_token_ttl_seconds is not None:
            values.append(resource.access_token_ttl_seconds)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
            cls._server_error()
        if not values:
            values.append(OidcConfig.oidc_access_token_ttl_seconds)
        maximum = OidcConfig.oidc_max_access_token_ttl_seconds
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
            cls._server_error()
        return min(*values, maximum)

    @staticmethod
    def _id_ttl(client: SysOAuthClient) -> int:
        """
        计算 ID Token 的有效秒数

        :param client: OAuth Client ORM（此方法仅按统一签名接收）
        :return: OIDC ID Token 的有效秒数
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        value = OidcConfig.oidc_id_token_ttl_seconds
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise OAuthProtocolException('server_error', 'Token policy is unavailable', 500)
        return value

    @staticmethod
    def _refresh_idle_ttl(client: SysOAuthClient) -> int:
        """
        计算 Refresh Token 空闲有效秒数

        :param client: OAuth Client ORM（SysOAuthClient）
        :return: Refresh Token 空闲有效秒数（不超过 OIDC 配置上限）
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        value = client.refresh_token_idle_seconds
        if value is None:
            value = OidcConfig.oidc_refresh_token_idle_seconds
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise OAuthProtocolException('server_error', 'Token policy is unavailable', 500)
        maximum = OidcConfig.oidc_refresh_token_idle_seconds
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
            raise OAuthProtocolException('server_error', 'Token policy is unavailable', 500)
        return min(value, maximum)

    @staticmethod
    def _refresh_absolute_ttl(client: SysOAuthClient) -> int:
        """
        计算 Refresh Token 绝对有效秒数

        :param client: OAuth Client ORM（SysOAuthClient）
        :return: Refresh Token 绝对有效秒数（不超过 OIDC 配置上限）
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        value = client.refresh_token_absolute_seconds
        if value is None:
            value = OidcConfig.oidc_refresh_token_absolute_seconds
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise OAuthProtocolException('server_error', 'Token policy is unavailable', 500)
        maximum = OidcConfig.oidc_refresh_token_absolute_seconds
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
            raise OAuthProtocolException('server_error', 'Token policy is unavailable', 500)
        return min(value, maximum)

    @classmethod
    def _request(cls, request: TokenRequest | Mapping[str, Any]) -> dict[str, Any]:
        """
        将 TokenRequest 或映射转换为请求字典

        :param request: TokenRequest 实例或包含 Token Endpoint 字段的映射
        :return: 用于 Grant Type 分派的已验证 Token Endpoint 字段字典
        """

        if isinstance(request, TokenRequest):
            return request.model_dump()
        if isinstance(request, Mapping):
            try:
                return TokenRequest(**dict(request)).model_dump()
            except ValidationError:
                cls._invalid_request()
        cls._invalid_request()

        return {}

    @staticmethod
    def _json_list(value: Any) -> list[Any]:
        """
        将 Scope 或 Resource 字段规范化为列表

        :param value: DAO 返回的 JSON Scope 或 Resource 字段值
        :return: 当值为 list/tuple 时复制出的列表，否则为空列表
        """

        return list(value) if isinstance(value, (list, tuple)) else []

    @staticmethod
    def _token_pepper(override: str | bytes | None) -> str | bytes:
        """
        选择 Token HMAC Pepper 配置

        :param override: 覆盖配置
        :return: 用于令牌摘要计算的 Pepper 文本或字节串
        """

        value = OidcConfig.oidc_token_hash_pepper if override is None else override
        if not isinstance(value, (str, bytes)):
            TokenService._server_error()
        raw = value.encode('utf-8') if isinstance(value, str) else value
        if len(raw) < TokenService._MIN_TOKEN_PEPPER_BYTES:
            TokenService._server_error()
        return value

    @classmethod
    def _requested_scopes(cls, value: Any, fallback: Sequence[str]) -> list[str]:
        """
        解析请求中的 Scope 列表

        :param value: Token Endpoint 的 scope 字符串，或已解析的 Scope code 序列
        :param fallback: 请求未提供 scope 时使用的已持久化 Scope code 序列
        :return: 去重校验后的 Scope code 字符串列表
        """

        raw = fallback if value is None else value.split() if isinstance(value, str) else value
        if not isinstance(raw, (list, tuple)) or not raw or any(not isinstance(item, str) or not item for item in raw):
            cls._invalid_scope()
        if len(set(raw)) != len(raw):
            cls._invalid_scope()
        return list(raw)

    @classmethod
    def _requested_resources(cls, value: Any, fallback: Sequence[str]) -> list[str]:
        """
        解析请求中的 Resource 列表

        :param value: Token Endpoint 的 resource audience 字符串或序列
        :param fallback: 请求未提供 resource 时使用的已持久化 audience 序列
        :return: 通过单 Resource 限制校验的 audience 字符串列表
        """

        raw = fallback if value is None else [value] if isinstance(value, str) else value
        if not isinstance(raw, (list, tuple)) or len(raw) > cls._MAX_RESOURCE_COUNT:
            cls._invalid_scope()
        if any(not isinstance(item, str) or not item for item in raw):
            cls._invalid_scope()
        return list(raw)

    @staticmethod
    def _utc_datetime(value: datetime | None) -> datetime | None:
        """
        将输入时间统一转换为项目时间

        :param value: 携带时区的 datetime 输入
        :return: 带时区的 UTC datetime；输入为 None 时返回 None
        """

        return TimezoneUtil.to_utc(value) if value is not None else None

    @staticmethod
    def _numeric_time(value: datetime | None) -> int:
        """
        将时间值转换为整数时间戳

        :param value: 认证时间等需要编码进 JWT claim 的 datetime，或 None
        :return: Unix 整数时间戳
        """

        current = TokenService._utc_datetime(value)
        if current is None:
            TokenService._server_error()
        return int(current.timestamp())

    @staticmethod
    def _audiences(issuer: str, resources: Sequence[str]) -> list[str]:
        """
        将 aud 声明规范化为去重列表

        :param issuer: OIDC issuer URL
        :param resources: 已校验的 Resource audience 字符串序列
        :return: 包含 userinfo audience 和 Resource audience 的去重列表
        """

        result = [f'{issuer.rstrip("/")}{TokenService._USERINFO_AUDIENCE_SUFFIX}']
        result.extend(resources)

        return list(dict.fromkeys(result))

    @staticmethod
    def _at_hash(access_token: str) -> str:
        """
        计算 OIDC at_hash 值

        :param access_token: 待计算 OIDC at_hash 的 ASCII JWT Access Token 文本
        :return: SHA-256 前 128 bit 摘要的无填充 Base64URL 字符串
        """

        digest = hashlib.sha256(access_token.encode('ascii')).digest()[:16]

        return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')

    @staticmethod
    def _map_oauth_failure(error: Exception, fallback: str) -> None:
        """
        将底层异常映射为 OAuth 协议错误

        :param error: Authorization Code 消费等底层流程抛出的异常
        :param fallback: 非 OAuthProtocolException 时使用的 OAuth error code
        :return: None
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        if isinstance(error, OAuthProtocolException):
            raise OAuthProtocolException(error.error, 'The authorization grant is invalid or expired', 400) from None
        raise OAuthProtocolException(fallback, 'The authorization grant is invalid or expired', 400) from None

    @staticmethod
    def _invalid_request() -> None:
        """
        抛出 invalid_request 协议错误

        :return: None
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        raise OAuthProtocolException('invalid_request', 'Invalid token request', 400)

    @staticmethod
    def _invalid_client() -> None:
        """
        抛出 invalid_client 协议错误

        :return: None
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        raise OAuthProtocolException('invalid_client', 'Client authentication failed', 401)

    @staticmethod
    def _invalid_grant() -> None:
        """
        抛出 invalid_grant 协议错误

        :return: None
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        raise OAuthProtocolException('invalid_grant', 'The authorization grant is invalid or expired', 400)

    @staticmethod
    def _invalid_scope() -> None:
        """
        抛出 invalid_scope 协议错误

        :return: None
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        raise OAuthProtocolException('invalid_scope', 'Requested scope is not authorized', 400)

    @staticmethod
    def _server_error() -> None:
        """
        抛出 server_error 协议错误

        :return: None
        :raises OAuthProtocolException: 请求不符合 OAuth 协议约束
        """

        raise OAuthProtocolException('server_error', 'Token issuance is unavailable', 500)
