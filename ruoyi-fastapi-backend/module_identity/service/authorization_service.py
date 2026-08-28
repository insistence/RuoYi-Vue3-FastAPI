import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException, OidcInteractionException
from module_identity.dao._helpers import local_datetime
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_grant_dao import OAuthGrantDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysSsoSession
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.entity.vo.protocol_vo import AuthorizeRequest
from module_identity.redis_keys import OidcRedisKey
from module_identity.security.opaque_token import (
    OpaqueTokenError,
    generate_authorization_code,
    parse_opaque_token,
    token_digest,
)
from module_identity.service.audit_service import AuditService
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.interaction_service import InteractionFlowService, InteractionService
from module_identity.service.session_service import SsoSessionError, SsoSessionService

_S256_CHALLENGE = re.compile(r'^[A-Za-z0-9_-]{43}$')
_MAX_STATE_LENGTH = 1024


@dataclass(frozen=True, slots=True)
class ClientSnapshot:
    """
    授权流程使用的 Client 只读标量快照
    """

    client_pk: int
    client_id: str
    policy_version: int
    grant_types: tuple[str, ...]
    response_types: tuple[str, ...]
    require_pkce: bool
    require_consent: bool
    trusted_client: bool

    def __post_init__(self) -> None:
        """
        拒绝可变容器，确保冻结快照不会被原地修改

        :return: None
        :raises TypeError: Grant 或 Response 类型不是不可变元组时抛出
        """
        if not isinstance(self.grant_types, tuple) or not isinstance(self.response_types, tuple):
            raise TypeError('ClientSnapshot grant_types and response_types must be tuples')


@dataclass(frozen=True, slots=True)
class ScopeSnapshot:
    """
    授权流程使用的 Scope 只读标量快照
    """

    scope_pk: int
    scope_code: str
    scope_type: str
    resource_pk: int | None
    consent_required: bool


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """
    授权流程使用的 Resource 只读标量快照
    """

    resource_pk: int
    audience: str


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """
    已完成协议校验的不可变授权上下文

    上下文只保存后续交互和签码所需的白名单字段，不携带未定义查询参数
    """

    client: ClientSnapshot
    redirect_uri: str
    scopes: tuple[str, ...]
    scope_models: tuple[ScopeSnapshot, ...]
    pre_authorized_scopes: frozenset[str]
    resource: ResourceSnapshot | None
    state: str | None
    nonce: str | None
    code_challenge: str
    code_challenge_method: str
    prompt: str | None
    max_age: int | None
    required_scopes: frozenset[str] = frozenset({'openid'})

    @property
    def requires_consent(self) -> bool:
        """
        判断当前请求是否存在尚未预授权的用户 Scope

        :return: 需要显示同意页时为 True
        """
        consentable = set(self.scopes) - set(self.required_scopes)
        if 'consent' in frozenset((self.prompt or '').split()):
            return bool(consentable)
        if not self.client.require_consent:
            return False
        return any(scope not in self.pre_authorized_scopes for scope in consentable)

    @property
    def resources(self) -> tuple[str, ...]:
        """
        返回授权上下文中的 Resource audience

        :return: 最多一个 audience 的元组
        """
        return (self.resource.audience,) if self.resource is not None else ()

    def to_internal_payload(self, interaction_id: str) -> dict[str, Any]:
        """
        构建仅供服务端 Redis Interaction 使用的完整绑定载荷

        :param interaction_id: 服务端生成的 Interaction ID
        :return: 包含后续签码所需绑定字段且不含 ORM 对象的内部载荷
        """
        return {
            'interactionId': interaction_id,
            'clientPk': self.client.client_pk,
            'clientId': self.client.client_id,
            'redirectUri': self.redirect_uri,
            'responseType': 'code',
            'scopes': list(self.scopes),
            'resources': list(self.resources),
            'codeChallenge': self.code_challenge,
            'codeChallengeMethod': self.code_challenge_method,
            'maxAge': self.max_age,
            'state': self.state,
            'nonce': self.nonce,
            'prompt': self.prompt,
            'consentRequired': self.requires_consent,
        }

    def to_interaction_payload(self, interaction_id: str) -> dict[str, Any]:
        """
        构建交互页面可见的非敏感载荷

        :param interaction_id: 服务端生成的 Interaction ID
        :return: 不包含 state、nonce 和 PKCE challenge 的页面载荷
        """
        return {
            'interactionId': interaction_id,
            'clientId': self.client.client_id,
            'responseType': 'code',
            'scopes': list(self.scopes),
            'resources': list(self.resources),
            'consentRequired': self.requires_consent,
        }


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """
    授权流程完成后交给 HTTP Controller 的纯领域结果
    """

    location: str
    status_code: int = 303


class AuthorizationService:
    """
    授权模块服务层

    校验顺序固定为 Client、精确 Redirect、响应类型、PKCE、Scope 和 Resource，
    只有 Redirect 已验证后才允许协议错误携带 redirect_uri 和 state
    """

    @classmethod
    async def _parse_request(cls, db: AsyncSession, raw: dict[str, str]) -> tuple[AuthorizeRequest, str]:
        """
        先验证 Client 和完整 Redirect，再解析其余协议字段

        :param db: 异步数据库会话
        :param raw: 已拒绝重复键的 Query 参数
        :return: 解析后的授权请求及已验证 Redirect URI
        :raises OAuthProtocolException: Client、Redirect 或协议字段无效
        """
        client_id = raw.get('client_id')
        redirect_uri = raw.get('redirect_uri')
        if not isinstance(client_id, str) or not isinstance(redirect_uri, str):
            raise OAuthProtocolException('invalid_request', 'client_id and redirect_uri are required')
        verified_redirect = await cls.verified_redirect(db, client_id, redirect_uri)
        try:
            return AuthorizeRequest.model_validate(raw), verified_redirect
        except ValidationError as exc:
            state = raw.get('state') if len(raw.get('state', '')) <= _MAX_STATE_LENGTH else None
            raise OAuthProtocolException(
                'invalid_request',
                'Invalid authorization request',
                400,
                redirect_uri=verified_redirect,
                state=state,
                redirect_uri_verified=True,
                issuer=OidcConfig.oidc_issuer,
            ) from exc

    @classmethod
    async def process_authorization_request(
        cls,
        db: AsyncSession,
        redis: Any,
        raw: dict[str, str],
        *,
        sso_cookie: str | None = None,
    ) -> AuthorizationResult:
        """
        执行授权请求业务流程并在服务层完成数据库事务

        :param db: 异步数据库会话，由本方法提交或回滚
        :param redis: 认证中心 Redis 客户端
        :param raw: Controller 已解析且去重的 Query 参数
        :param sso_cookie: Controller 提取的 SSO Cookie 原文
        :return: 交互页面或 Client 回调的 URL 结果
        :raises OAuthProtocolException: 协议错误，必要时携带已验证 Redirect
        """
        request, verified_redirect = await cls._parse_request(db, raw)
        if request.resource and await cls.has_disabled_resource(db, request):
            raise OAuthProtocolException('not_found', 'Resource is unavailable', 404)
        context = await cls.validate_request(db, request)
        coordinator = AfterCommitCoordinator()
        try:
            session = await cls._load_sso_session(db, redis, sso_cookie, coordinator)
            if (
                session is not None
                and context.max_age is not None
                and cls._requires_reauthentication(session.auth_time, context.max_age)
            ):
                session = None
            grant = None
            if session is not None:
                grant = await cls.valid_grant(db, session.user_id, context.client.client_pk)
            consent_required = context.requires_consent and not cls.consent_is_satisfied(context, grant)
            payload = context.to_internal_payload('pending')
            if session is not None:
                payload.update(
                    {
                        'authenticatedSid': session.sid,
                        'userId': session.user_id,
                        'subjectId': session.subject_id,
                        'authVersion': session.auth_version,
                    }
                )
            payload['consentRequired'] = consent_required
            payload['grantId'] = grant.grant_id if grant is not None and not consent_required else None
            created = await InteractionService.create(redis, payload, pepper=OidcConfig.oidc_token_hash_pepper)
            await AuditService.record(
                db,
                OidcAuditEvent.AUTHORIZE_REQUESTED,
                'success',
                client_id=request.client_id,
                detail={'response_type': request.response_type},
            )
            await coordinator.commit(db)
        except OidcInteractionException as exc:
            await coordinator.rollback(db)
            await cls._record_failure_audit(
                db, OidcAuditEvent.AUTHORIZE_DENIED, client_id=request.client_id, failure_code=exc.error
            )
            raise cls._with_verified_redirect(exc, verified_redirect, request.state) from exc
        except Exception as exc:
            await coordinator.rollback(db)
            raise OAuthProtocolException(
                'server_error',
                'Authorization service is unavailable',
                500,
                redirect_uri=verified_redirect,
                state=request.state,
                redirect_uri_verified=True,
                issuer=OidcConfig.oidc_issuer,
            ) from exc
        if created.initial_status == 'completed':
            return await cls._complete_authorization(db, redis, created.interaction_id)
        base = (
            OidcConfig.oidc_interaction_consent_url
            if created.initial_status == 'awaiting_consent'
            else OidcConfig.oidc_interaction_login_url
        )
        return AuthorizationResult(cls._interaction_url(base, created.interaction_id, created.csrf_token))

    @staticmethod
    async def _load_sso_session(
        db: AsyncSession,
        redis: Any,
        cookie: str | None,
        coordinator: AfterCommitCoordinator,
    ) -> SysSsoSession | None:
        """
        只读取认证中心 SSO Cookie，拒绝 Legacy Token 作为登录态

        :param db: 异步数据库会话
        :param redis: Redis 客户端
        :param cookie: SSO Cookie 值
        :param coordinator: 提交后副作用协调器
        :return: SSO Session 或 None
        """
        if cookie is None:
            return None
        try:
            return await SsoSessionService.validate(
                db,
                redis,
                cookie,
                pepper=OidcConfig.oidc_token_hash_pepper,
                now=datetime.now(),
                coordinator=coordinator,
            )
        except SsoSessionError:
            return None

    @classmethod
    async def _complete_authorization(cls, db: AsyncSession, redis: Any, interaction_id: str) -> AuthorizationResult:
        """
        消费已完成 Interaction 并生成一次性授权码回调结果

        :param db: 异步数据库会话
        :param redis: Redis 客户端
        :param interaction_id: 交互流程标识
        :return: 授权码重定向结果
        """
        record = await InteractionService.get_record(redis, interaction_id)
        if record.get('status') != 'completed':
            raise OidcInteractionException(interaction_id, 'Interaction is not complete', error='interaction_required')
        marker = await cls._reserve_completion(redis, interaction_id)
        if marker is None:
            raise OidcInteractionException(
                interaction_id, 'Interaction has already completed', error='invalid_request', status_code=409
            )
        code: str | None = None
        try:
            client_pk = record['clientPk']
            redirect_uri = record['redirectUri']
            registered_uri = await cls.verified_redirect_for_client(db, client_pk, redirect_uri)
            if registered_uri is None:
                raise OAuthProtocolException('server_error', 'Validated redirect URI is unavailable', 500)
            session = await cls.active_session(db, record.get('authenticatedSid', ''), now=datetime.now())
            if session is None:
                raise OAuthProtocolException('login_required', 'A current login is required', 400)
            payload = {
                'clientPk': client_pk,
                'redirectUri': redirect_uri,
                'userId': session.user_id,
                'subjectId': session.subject_id,
                'authVersion': session.auth_version,
                'sid': session.sid,
                'grantId': record.get('grantId'),
                'scopes': record['scopes'],
                'resources': record['resources'],
                'nonce': record['nonce'],
                'codeChallenge': record['codeChallenge'],
                'codeChallengeMethod': record['codeChallengeMethod'],
                'authTime': _protocol_datetime(session.auth_time).isoformat(),
            }
            code = await AuthorizationCodeService.issue(redis, payload, pepper=OidcConfig.oidc_token_hash_pepper)
            await AuditService.record(
                db,
                OidcAuditEvent.AUTHORIZE_SUCCEEDED,
                'success',
                client_id=record.get('clientId'),
                user_id=session.user_id,
                subject_id=str(session.subject_id),
                sid=session.sid,
            )
            await db.commit()
            return AuthorizationResult(cls._success_url(registered_uri, code, record.get('state')))
        except Exception as exc:
            if code is not None:
                try:
                    await AuthorizationCodeService.invalidate(redis, code)
                except Exception:
                    pass
            await cls._best_effort_delete(redis, marker)
            await db.rollback()
            if isinstance(exc, OAuthProtocolException):
                raise
            raise OAuthProtocolException('server_error', 'Authorization code could not be completed', 500) from exc

    @staticmethod
    async def _reserve_completion(redis: Any, interaction_id: str) -> str | None:
        """
        以 Interaction 剩余 TTL 保留一次终态完成权

        :param redis: Redis 客户端
        :param interaction_id: 交互流程标识
        :return: 完成标记 Key 或 None
        """
        ttl = await redis.ttl(OidcRedisKey.interaction(interaction_id))
        if not isinstance(ttl, int) or ttl <= 0:
            return None
        marker = OidcRedisKey.interaction(f'{interaction_id}-completion')
        reserved = await redis.set(marker, 'reserved', ex=ttl, nx=True)
        return marker if reserved else None

    @staticmethod
    async def _best_effort_delete(redis: Any, marker: str) -> None:
        """
        尽力删除授权完成 marker

        :param redis: Redis 客户端
        :param marker: 完成标记 Key
        :return: None
        """
        try:
            await redis.delete(marker)
        except Exception:
            return

    @staticmethod
    def _requires_reauthentication(auth_time: datetime | None, max_age: int) -> bool:
        """
        判断 SSO Session 是否超过授权请求的 max_age

        :param auth_time: 认证时间
        :param max_age: 最大认证时效
        :return: 是否需要重新认证
        """
        if auth_time is None:
            return True
        current = local_datetime(auth_time)
        return (datetime.now() - current).total_seconds() > max_age

    @staticmethod
    def _interaction_url(base: str, interaction_id: str, csrf_token: str) -> str:
        """
        构建只把原始 CSRF 放入 URL Fragment 的交互地址

        :param base: 交互地址基址
        :param interaction_id: 交互流程标识
        :param csrf_token: CSRF Token
        :return: 交互页面 URL
        """
        parsed = urlsplit(base)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query['interaction'] = interaction_id
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), f'csrf={csrf_token}'))

    @staticmethod
    def _success_url(redirect_uri: str, code: str, state: str | None) -> str:
        """
        构建已验证 Client Redirect 的授权码回调地址

        :param redirect_uri: 已验证的重定向 URI
        :param code: Authorization Code
        :param state: 协议 state 值
        :return: 授权码回调 URL
        """
        parsed = urlsplit(redirect_uri)
        if parsed.fragment or not parsed.scheme or not parsed.netloc:
            raise OAuthProtocolException('server_error', 'Validated redirect URI is invalid', 500)
        fields = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key not in {'code', 'error', 'error_description', 'error_uri', 'iss', 'state'}
        ]
        fields.append(('code', code))
        if state is not None:
            fields.append(('state', state))
        fields.append(('iss', OidcConfig.oidc_issuer))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(fields), ''))

    @staticmethod
    def _with_verified_redirect(
        exc: OidcInteractionException, redirect_uri: str, state: str | None
    ) -> OAuthProtocolException:
        """
        把 Interaction 错误绑定到已验证 Redirect

        :param exc: 协议异常
        :param redirect_uri: 待核验的请求重定向 URI
        :param state: 协议 state 值
        :return: 绑定重定向的协议异常
        """
        return OAuthProtocolException(
            exc.error,
            exc.message,
            exc.status_code,
            redirect_uri=redirect_uri,
            state=state,
            redirect_uri_verified=True,
            issuer=OidcConfig.oidc_issuer,
        )

    @staticmethod
    async def _record_failure_audit(db: AsyncSession, event_type: str, **fields: Any) -> None:
        """
        尝试记录授权失败审计，审计异常不改变原协议错误响应

        :param db: 异步数据库会话
        :param event_type: 审计事件类型
        :param fields: 失败审计字段映射
        :return: None
        """
        try:
            await AuditService.record_independent(db, event_type, 'failure', risk_level='high', **fields)
        except Exception as exc:
            raise OAuthProtocolException('server_error', 'Authorization audit service is unavailable', 503) from exc

    @staticmethod
    async def verified_redirect(db: AsyncSession, client_id: str, redirect_uri: str) -> str:
        """
        返回已注册的精确 Redirect URI

        :param db: 异步数据库会话
        :param client_id: OAuth Client 标识
        :param redirect_uri: 已验证的重定向 URI
        :return: 已注册的精确重定向 URI
        """
        client = await OAuthClientDao.get_by_client_id(db, client_id, active_only=True)
        if client is None:
            raise OAuthProtocolException('unauthorized_client', 'Client is not registered')
        registered = await OAuthClientDao.find_exact_uri(db, client.client_pk, 'redirect', redirect_uri)
        if registered is None:
            raise OAuthProtocolException('invalid_request', 'redirect_uri is not registered')
        return registered.uri

    @staticmethod
    async def verified_redirect_for_client(db: AsyncSession, client_pk: int, redirect_uri: str) -> str | None:
        """
        按内部 Client 主键确认已注册的 Redirect URI

        :param db: 异步数据库会话
        :param client_pk: OAuth Client 主键
        :param redirect_uri: 已验证的重定向 URI
        :return: 匹配的重定向 URI 或 None
        """
        registered = await OAuthClientDao.find_exact_uri(db, client_pk, 'redirect', redirect_uri)
        return registered.uri if registered is not None else None

    @staticmethod
    async def valid_grant(db: AsyncSession, user_id: int, client_pk: int) -> SysOAuthGrant | None:
        """
        读取用户对 Client 的有效 Grant

        :param db: 异步数据库会话
        :param user_id: 本地用户 ID
        :param client_pk: OAuth Client 主键
        :return: 有效 Grant 或 None
        """
        return await OAuthGrantDao.get_valid_for_user_client(db, user_id, client_pk)

    @staticmethod
    async def has_disabled_resource(db: AsyncSession, request: AuthorizeRequest) -> bool:
        """
        判断请求 Resource 是否为该 Client 已绑定的停用资源

        :param db: 异步数据库会话
        :param request: 当前 HTTP 请求
        :return: 是否存在禁用 Resource
        """
        return bool(request.resource) and await OAuthClientDao.has_disabled_bound_resource(
            db, request.client_id, request.resource
        )

    @staticmethod
    async def active_session(db: AsyncSession, sid: str, now: datetime | None = None) -> SysSsoSession | None:
        """
        读取当前有效 SSO Session

        :param db: 异步数据库会话
        :param sid: SSO Session 标识
        :param now: 当前时间
        :return: 活动 SSO Session 或 None
        """
        return await SsoSessionDao.get_active(db, sid, now=local_datetime(now) or datetime.now())

    @classmethod
    async def validate_request(cls, db: AsyncSession, request: AuthorizeRequest) -> AuthorizationContext:  # noqa: PLR0912, PLR0915
        """
        校验授权请求并构建不可变授权上下文

        :param db: 异步数据库会话
        :param request: 已完成基础字段校验的 Authorization 请求
        :return: 可交给 Interaction 和 Authorization Code 服务的上下文
        :raises OAuthProtocolException: 请求不符合 OAuth/OIDC 协议时抛出
        """
        if not OidcConfig.oidc_enabled:
            raise OAuthProtocolException('temporarily_unavailable', 'OIDC provider is disabled', 503)

        client = await OAuthClientDao.get_by_client_id(db, request.client_id, active_only=True)
        if client is None:
            raise OAuthProtocolException('unauthorized_client', 'Client is not registered')

        registered_uri = await OAuthClientDao.find_exact_uri(db, client.client_pk, 'redirect', request.redirect_uri)
        if registered_uri is None:
            raise OAuthProtocolException('invalid_request', 'redirect_uri is not registered')

        redirect_uri = registered_uri.uri
        state = request.state
        if 'authorization_code' not in (client.grant_types or []) or 'code' not in (client.response_types or []):
            raise cls._redirect_error(
                'unauthorized_client', 'Authorization code is not allowed for this client', redirect_uri, state
            )
        if request.response_type != 'code':
            raise cls._redirect_error(
                'unsupported_response_type', 'Only authorization code is supported', redirect_uri, state
            )
        if request.code_challenge_method != 'S256':
            raise cls._redirect_error('invalid_request', 'Only PKCE S256 is supported', redirect_uri, state)
        if not _S256_CHALLENGE.fullmatch(request.code_challenge):
            raise cls._redirect_error(
                'invalid_request', 'PKCE S256 code_challenge must contain 43 characters', redirect_uri, state
            )
        if 'S256' not in OidcConfig.pkce_method_list or (
            OidcConfig.oidc_require_pkce and not bool(client.require_pkce)
        ):
            raise cls._redirect_error(
                'invalid_request', 'Client PKCE policy is weaker than provider policy', redirect_uri, state
            )
        cls._validate_prompt(request.prompt, redirect_uri, state)
        if request.max_age is not None and request.max_age < 0:
            raise cls._redirect_error('invalid_request', 'max_age must be non-negative', redirect_uri, state)

        requested_scopes = tuple(dict.fromkeys(request.scope.split()))
        if 'openid' not in requested_scopes:
            raise cls._redirect_error('invalid_scope', 'openid scope is required', redirect_uri, state)
        if not request.nonce:
            raise cls._redirect_error(
                'invalid_request', 'nonce is required for OpenID Connect authorization', redirect_uri, state
            )

        bindings = await OAuthClientDao.list_scope_bindings(db, client.client_pk)
        scope_models = await cls._load_scope_models(db, bindings)
        scope_by_code = {scope.scope_code: scope for scope in scope_models if scope.status == '0'}
        unknown_scopes = [scope for scope in requested_scopes if scope not in scope_by_code]
        if unknown_scopes:
            raise cls._redirect_error(
                'invalid_scope', 'Requested scope is not allowed for this client', redirect_uri, state
            )
        allowed_scope_codes = {scope.scope_pk for scope in scope_models}
        if any(binding.scope_pk not in allowed_scope_codes for binding in bindings):
            raise cls._redirect_error(
                'invalid_scope', 'Requested scope is not allowed for this client', redirect_uri, state
            )
        bound_scope_codes = {
            scope.scope_code
            for scope in scope_models
            if any(binding.scope_pk == scope.scope_pk for binding in bindings)
        }
        if any(scope not in bound_scope_codes for scope in requested_scopes):
            raise cls._redirect_error(
                'invalid_scope', 'Requested scope is not allowed for this client', redirect_uri, state
            )

        resources = await OAuthClientDao.list_resources(db, client.client_pk)
        resource_bindings = await OAuthClientDao.list_resource_bindings(db, client.client_pk)
        resource = cls._resolve_resource(
            request.resource,
            resources,
            resource_bindings,
            [scope_by_code[code] for code in requested_scopes],
            redirect_uri,
            state,
        )
        selected_resource_pk = resource.resource_pk if resource is not None else None
        if any(
            scope.scope_type == 'resource'
            and (selected_resource_pk is None or scope.resource_pk != selected_resource_pk)
            for scope in (scope_by_code[code] for code in requested_scopes)
        ):
            raise cls._redirect_error(
                'invalid_target', 'Requested scope does not belong to the selected resource', redirect_uri, state
            )

        prompt = request.prompt
        requested_scope_models = [scope_by_code[code] for code in requested_scopes]
        pre_authorized = frozenset(
            scope.scope_code
            for scope in requested_scope_models
            for binding in bindings
            if binding.scope_pk == scope.scope_pk and bool(binding.pre_authorized)
        )
        required_scopes = frozenset(
            {'openid'} | {scope.scope_code for scope in requested_scope_models if not bool(scope.consent_required)}
        )
        return AuthorizationContext(
            client=ClientSnapshot(
                client_pk=client.client_pk,
                client_id=client.client_id,
                policy_version=client.policy_version,
                grant_types=tuple(client.grant_types or ()),
                response_types=tuple(client.response_types or ()),
                require_pkce=bool(client.require_pkce),
                require_consent=bool(client.require_consent),
                trusted_client=bool(client.trusted_client),
            ),
            redirect_uri=redirect_uri,
            scopes=requested_scopes,
            scope_models=tuple(
                ScopeSnapshot(
                    scope_pk=scope_by_code[code].scope_pk,
                    scope_code=scope_by_code[code].scope_code,
                    scope_type=scope_by_code[code].scope_type,
                    resource_pk=scope_by_code[code].resource_pk,
                    consent_required=bool(scope_by_code[code].consent_required),
                )
                for code in requested_scopes
            ),
            pre_authorized_scopes=pre_authorized,
            resource=ResourceSnapshot(resource.resource_pk, resource.audience) if resource is not None else None,
            state=state,
            nonce=request.nonce,
            code_challenge=request.code_challenge,
            code_challenge_method=request.code_challenge_method,
            prompt=prompt,
            max_age=request.max_age,
            required_scopes=required_scopes,
        )

    @staticmethod
    def _validate_prompt(prompt: str | None, redirect_uri: str, state: str | None) -> None:
        """
        校验服务端实际支持的 prompt 组合

        :param prompt: 空格分隔的 prompt 值
        :param redirect_uri: 已精确验证的 Redirect URI
        :param state: 客户端原样 state
        :return: 规范化的 prompt 校验结果
        :raises OAuthProtocolException: prompt 不是受支持的组合时抛出
        """
        if prompt is None:
            return
        prompts = prompt.split()
        if (
            not prompts
            or len(set(prompts)) != len(prompts)
            or any(item not in {'login', 'consent', 'none'} for item in prompts)
            or ('none' in prompts and len(prompts) > 1)
        ):
            raise AuthorizationService._redirect_error(
                'invalid_request', 'prompt contains an unsupported combination', redirect_uri, state
            )

    @staticmethod
    async def _load_scope_models(
        db: AsyncSession, bindings: list[SysOAuthClientScope] | tuple[SysOAuthClientScope, ...]
    ) -> list[SysOAuthScope]:
        """
        加载 Client Scope 绑定对应的有效 Scope 定义

        :param db: 异步数据库会话
        :param bindings: Client-Scope 绑定集合
        :return: Scope 定义列表
        """
        scope_ids = {binding.scope_pk for binding in bindings}
        if not scope_ids:
            return []
        definitions = await OAuthClientDao.list_scope_definitions(db, active_only=False)
        return [scope for scope in definitions if scope.scope_pk in scope_ids]

    @staticmethod
    async def load_scope_models(
        db: AsyncSession, bindings: list[SysOAuthClientScope] | tuple[SysOAuthClientScope, ...]
    ) -> list[SysOAuthScope]:
        """
        加载 Client Scope 绑定对应的 Scope 定义

        :param db: 异步数据库会话
        :param bindings: Client-Scope 绑定集合
        :return: Scope 定义列表
        """
        return await AuthorizationService._load_scope_models(db, bindings)

    @staticmethod
    def _resolve_resource(
        requested_resource: str | None,
        resources: list[SysOAuthResource] | tuple[SysOAuthResource, ...],
        resource_bindings: list[SysOAuthClientResource] | tuple[SysOAuthClientResource, ...],
        requested_scopes: list[SysOAuthScope],
        redirect_uri: str,
        state: str | None,
    ) -> SysOAuthResource | None:
        """
        解析并校验最多一个 Resource audience

        :param requested_resource: 请求中的 Resource audience
        :param resources: Client 已注册的 Resource 集合
        :param resource_bindings: Client 与 Resource 的显式绑定集合
        :param requested_scopes: 已确认属于 Client 的 Scope 定义
        :param redirect_uri: 已精确验证的 Redirect URI
        :param state: 原样绑定的客户端 state
        :return: 选中的 Resource，或无 Resource 时返回 None
        """
        resource_scopes = [scope for scope in requested_scopes if scope.scope_type == 'resource']
        if requested_resource:
            resource = next((item for item in resources if item.audience == requested_resource), None)
            if resource is None:
                raise AuthorizationService._redirect_error(
                    'invalid_target', 'Requested resource is not allowed for this client', redirect_uri, state
                )
            return resource
        if not resource_scopes:
            return None
        default_pks = {binding.resource_pk for binding in resource_bindings if bool(binding.is_default)}
        defaults = [resource for resource in resources if resource.resource_pk in default_pks]
        if len(defaults) != 1:
            raise AuthorizationService._redirect_error(
                'invalid_target', 'A resource audience is required for resource scope', redirect_uri, state
            )
        return defaults[0]

    @staticmethod
    def _redirect_error(error: str, description: str, redirect_uri: str, state: str | None) -> OAuthProtocolException:
        """
        创建已完成 Redirect 校验后的安全协议异常

        :param error: OAuth 标准错误码
        :param description: 不泄漏内部数据的错误描述
        :param redirect_uri: 已注册的完整 Redirect URI
        :param state: 客户端原样 state
        :return: 标记为可安全重定向的协议异常
        """
        return OAuthProtocolException(
            error,
            description,
            400,
            redirect_uri=redirect_uri,
            state=state,
            redirect_uri_verified=True,
            issuer=OidcConfig.oidc_issuer,
        )

    @staticmethod
    def consent_is_satisfied(context: AuthorizationContext, grant: SysOAuthGrant | None) -> bool:
        """
        判断有效 Grant 是否覆盖当前授权请求

        :param context: 已验证授权上下文
        :param grant: 当前用户和 Client 的 Grant
        :return: Grant 有效且覆盖全部非预授权 Scope/Resource 时为 True
        """
        if not context.requires_consent:
            return True
        prompt_tokens = frozenset((context.prompt or '').split())
        if (
            'consent' in prompt_tokens
            or grant is None
            or grant.status != 'active'
            or grant.client_policy_version != context.client.policy_version
        ):
            return False
        expires_at = local_datetime(grant.expires_at)
        if expires_at is not None and expires_at <= datetime.now():
            return False
        non_pre_authorized = set(context.scopes) - set(context.pre_authorized_scopes) - set(context.required_scopes)
        expected_resources = set(context.resources)
        return non_pre_authorized.issubset(set(grant.granted_scopes or [])) and expected_resources.issubset(
            set(grant.granted_resources or [])
        )


class AuthorizationCodeReuseError(OAuthProtocolException):
    """
    表示一个已成功消费的 Authorization Code 被再次提交
    """

    def __init__(self) -> None:
        """
        初始化对象状态

        :return: None
        """
        super().__init__('invalid_grant', 'Authorization code is invalid or expired', 400)
        self.must_commit = True


class AuthorizationCodeService:
    """
    授权码模块服务层

    Redis 只保存 codeHash 和服务端白名单字段，不保存 Authorization Code 明文
    """

    _CONSUME_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value then
    if redis.call('EXISTS', KEYS[2]) == 1 then
        local consumed = redis.call('GET', KEYS[3])
        if consumed then
            local ok_consumed, consumed_payload = pcall(cjson.decode, consumed)
            if ok_consumed and type(consumed_payload) == 'table' and consumed_payload.codeHash
                and consumed_payload.codeHash ~= ARGV[1] then
                return -3
            end
        end
        return -4
    end
    return nil
end
local ok, payload = pcall(cjson.decode, value)
if not ok or type(payload) ~= 'table' then return -2 end
if tostring(payload.version) ~= ARGV[2] or payload.codeHash ~= ARGV[1] then return -3 end
redis.call('DEL', KEYS[1])
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[4])
redis.call('SET', KEYS[3], value, 'EX', ARGV[4])
return value
"""
    _CODE_CHALLENGE = re.compile(r'^[A-Za-z0-9_-]{43}$')
    _REQUIRED_FIELDS = frozenset(
        {
            'clientPk',
            'redirectUri',
            'userId',
            'subjectId',
            'authVersion',
            'sid',
            'grantId',
            'scopes',
            'resources',
            'nonce',
            'codeChallenge',
            'codeChallengeMethod',
            'authTime',
        }
    )
    _MAX_SCOPES = 100
    _MAX_RESOURCES = 1
    _REUSE_TOMBSTONE_TTL_SECONDS = 300
    _CONSUMED_TOMBSTONE_RESULT = -4

    @classmethod
    async def issue(
        cls,
        redis: Redis,
        payload: Mapping[str, Any],
        *,
        ttl_seconds: int | None = None,
        pepper: str | None = None,
    ) -> str:
        """
        签发短期 Authorization Code 并以 NX 写入 Redis

        :param redis: 异步 Redis 客户端
        :param payload: 已由服务端构建的白名单标量载荷
        :param ttl_seconds: 可选 Code TTL，省略时使用配置
        :param pepper: 独立 OIDC Token Hash Pepper
        :return: 仅返回一次的 Authorization Code 明文
        :raises ValueError: 载荷或 Pepper 不符合安全约束
        :raises OAuthProtocolException: Redis 写入失败时抛出
        """
        record = cls._validate_payload(payload)
        code = generate_authorization_code()
        parsed = parse_opaque_token(code, 'ac1')
        digest = token_digest(code, pepper or OidcConfig.oidc_token_hash_pepper)
        record['codeHash'] = digest
        record['version'] = 1
        serialized = cls._serialize(record)
        ttl = OidcConfig.oidc_authorization_code_ttl_seconds if ttl_seconds is None else ttl_seconds
        if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
            raise ValueError('authorization code ttl must be a positive integer')
        created = await redis.set(OidcRedisKey.authorization_code(parsed.token_id), serialized, ex=ttl, nx=True)
        if not created:
            raise OAuthProtocolException('server_error', 'Authorization code could not be created', 500)
        return code

    @classmethod
    async def consume(
        cls,
        redis: Redis,
        code: str,
        *,
        pepper: str | None = None,
    ) -> dict[str, Any]:
        """
        使用 Redis Lua 原子校验并消费 Authorization Code

        :param redis: 异步 Redis 客户端
        :param code: 客户端提交的 Authorization Code 明文
        :param pepper: 独立 OIDC Token Hash Pepper
        :return: 去除内部 codeHash/version 后的服务端载荷
        :raises OAuthProtocolException: Code 格式、Secret、状态或 TTL 无效时抛出统一错误
        """
        try:
            parsed = parse_opaque_token(code, 'ac1')
            digest = token_digest(code, pepper or OidcConfig.oidc_token_hash_pepper)
        except (OpaqueTokenError, TypeError, ValueError):
            raise OAuthProtocolException('invalid_grant', 'Authorization code is invalid') from None
        value = await redis.eval(
            cls._CONSUME_SCRIPT,
            3,
            OidcRedisKey.authorization_code(parsed.token_id),
            OidcRedisKey.authorization_code_consumed(parsed.token_id),
            OidcRedisKey.authorization_code_consumed_payload(parsed.token_id),
            digest,
            '1',
            'consumed',
            max(OidcConfig.oidc_authorization_code_ttl_seconds, cls._REUSE_TOMBSTONE_TTL_SECONDS),
        )
        if value == cls._CONSUMED_TOMBSTONE_RESULT:
            raise AuthorizationCodeReuseError
        if (isinstance(value, int) and value in {-2, -3}) or not value:
            raise OAuthProtocolException('invalid_grant', 'Authorization code is invalid or expired')
        try:
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            payload = json.loads(value)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            raise OAuthProtocolException('invalid_grant', 'Authorization code state is invalid') from None
        if not isinstance(payload, dict):
            raise OAuthProtocolException('invalid_grant', 'Authorization code state is invalid')
        payload.pop('codeHash', None)
        payload.pop('version', None)
        try:
            return cls._validate_payload(payload)
        except ValueError:
            raise OAuthProtocolException('invalid_grant', 'Authorization code state is invalid') from None

    @classmethod
    async def consumed_payload(
        cls,
        redis: Redis,
        code: str,
        *,
        pepper: str | None = None,
    ) -> dict[str, Any] | None:
        """
        读取已消费授权码的短期绑定载荷

        :param redis: Authorization Code Redis 客户端
        :param code: 客户端提交的 Authorization Code 明文
        :param pepper: 独立 OIDC Token Hash Pepper
        :return: 与授权码摘要匹配的绑定载荷，不存在或摘要不匹配时返回 None
        """
        try:
            parsed = parse_opaque_token(code, 'ac1')
            digest = token_digest(code, pepper or OidcConfig.oidc_token_hash_pepper)
        except (OpaqueTokenError, TypeError, ValueError):
            return None
        value = await redis.get(OidcRedisKey.authorization_code_consumed_payload(parsed.token_id))
        if not value:
            return None
        try:
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            payload = json.loads(value)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get('codeHash') != digest:
            return None
        payload.pop('codeHash', None)
        payload.pop('version', None)
        try:
            return cls._validate_payload(payload)
        except ValueError:
            return None

    @classmethod
    async def invalidate(cls, redis: Redis, code: str) -> None:
        """
        精确删除一个已签发但未安全完成交付的授权码

        :param redis: Authorization Code Redis 客户端
        :param code: 仅用于解析 code_id，不会写入 Redis
        :return: None
        """
        try:
            parsed = parse_opaque_token(code, 'ac1')
        except (OpaqueTokenError, TypeError, ValueError):
            return
        await redis.delete(OidcRedisKey.authorization_code(parsed.token_id))
        await redis.delete(OidcRedisKey.authorization_code_consumed_payload(parsed.token_id))

    @classmethod
    def _validate_payload(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
        """
        校验 Authorization Code 的服务端白名单标量载荷

        :param payload: 待校验映射
        :return: 可稳定 JSON 序列化的复制载荷
        :raises ValueError: 存在未知、缺失或类型不安全字段时抛出
        """
        if not isinstance(payload, Mapping):
            raise ValueError('authorization code payload must be a mapping')
        keys = set(payload)
        if keys != cls._REQUIRED_FIELDS:
            raise ValueError('authorization code payload fields are not allowed')
        cls._positive_int(payload['clientPk'], 'clientPk')
        cls._positive_int(payload['userId'], 'userId')
        cls._nonnegative_int(payload['authVersion'], 'authVersion')
        cls._string(payload['redirectUri'], 'redirectUri', 1000)
        cls._string(payload['subjectId'], 'subjectId', 36)
        cls._string(payload['sid'], 'sid', 36)
        grant_id = payload['grantId']
        if grant_id is not None:
            cls._string(grant_id, 'grantId', 36)
        cls._string(payload['nonce'], 'nonce', 1024)
        challenge = cls._string(payload['codeChallenge'], 'codeChallenge', 128)
        if not cls._CODE_CHALLENGE.fullmatch(challenge):
            raise ValueError('codeChallenge must be an unpadded base64url SHA-256 value')
        if payload['codeChallengeMethod'] != 'S256':
            raise ValueError('codeChallengeMethod must be S256')
        auth_time = cls._string(payload['authTime'], 'authTime', 64)
        try:
            parsed_auth_time = datetime.fromisoformat(auth_time.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('authTime must be an ISO-8601 timestamp') from exc
        if parsed_auth_time.tzinfo is None or parsed_auth_time.utcoffset() != timedelta(0):
            raise ValueError('authTime must be a timezone-aware UTC timestamp')
        scopes = cls._string_list(payload['scopes'], 'scopes', cls._MAX_SCOPES)
        resources = cls._string_list(payload['resources'], 'resources', cls._MAX_RESOURCES)
        if 'openid' not in scopes or len(set(scopes)) != len(scopes):
            raise ValueError('scopes must include openid and contain no duplicates')
        if len(set(resources)) != len(resources):
            raise ValueError('resources must not contain duplicates')
        if len(resources) > cls._MAX_RESOURCES:
            raise ValueError('only one resource is supported')
        return {
            'clientPk': payload['clientPk'],
            'redirectUri': payload['redirectUri'],
            'userId': payload['userId'],
            'subjectId': payload['subjectId'],
            'authVersion': payload['authVersion'],
            'sid': payload['sid'],
            'grantId': grant_id,
            'scopes': scopes,
            'resources': resources,
            'nonce': payload['nonce'],
            'codeChallenge': challenge,
            'codeChallengeMethod': 'S256',
            'authTime': payload['authTime'],
        }

    @staticmethod
    def _positive_int(value: Any, field: str) -> int:
        """
        校验正整数标量

        :param value: 待校验的正整数
        :param field: 字段名称
        :return: 校验后的正整数
        """
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f'{field} must be a positive integer')
        return value

    @staticmethod
    def _nonnegative_int(value: Any, field: str) -> int:
        """
        校验非负整数标量

        :param value: 待校验的非负整数
        :param field: 字段名称
        :return: 校验后的非负整数
        """
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f'{field} must be a non-negative integer')
        return value

    @staticmethod
    def _string(value: Any, field: str, limit: int) -> str:
        """
        校验非空字符串及长度

        :param value: 待校验的字符串
        :param field: 字段名称
        :param limit: 字符串的最大长度
        :return: 校验后的字符串
        """
        if not isinstance(value, str) or not value or len(value) > limit:
            raise ValueError(f'{field} must be a non-empty string')
        return value

    @classmethod
    def _string_list(cls, value: Any, field: str, limit: int) -> list[str]:
        """
        校验字符串列表并复制为 JSON 安全列表

        :param value: 待校验的字符串列表
        :param field: 字段名称
        :param limit: 字符串列表的最大长度
        :return: 校验后的字符串列表
        """
        if not isinstance(value, (list, tuple)) or len(value) > limit:
            raise ValueError(f'{field} must be a bounded string list')
        return [cls._string(item, field, 500) for item in value]

    @staticmethod
    def _serialize(record: Mapping[str, Any]) -> str:
        """
        生成稳定、无空白的 Redis JSON

        :param record: 交互记录
        :return: 序列化 JSON 字符串
        """
        try:
            return json.dumps(record, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('authorization code payload must be JSON serializable') from exc


class InteractionCompletionService:
    """
    交互完成模块服务层
    """

    @staticmethod
    async def complete(redis: Redis, interaction_id: str, db: AsyncSession) -> 'InteractionCompletionResult':
        """
        完成服务端校验并跳转至已注册的 Client Redirect URI

        :param redis: 交互 Redis
        :param interaction_id: Interaction 标识
        :param db: 异步数据库会话
        :return: 外部 Client 重定向响应
        """
        record = await InteractionService.get_record(redis, interaction_id)
        if record.get('status') not in {'completed', 'denied'}:
            raise OidcInteractionException(interaction_id, 'Interaction is not complete', error='interaction_required')
        marker = await InteractionFlowService.reserve_completion(redis, interaction_id)
        if marker is None:
            raise OidcInteractionException(
                interaction_id, 'Interaction has already completed', error='invalid_request', status_code=409
            )
        redirect_uri = record.get('redirectUri')
        try:
            registered = await OAuthClientDao.find_exact_uri(db, record['clientPk'], 'redirect', redirect_uri)
        except Exception:
            await InteractionFlowService.best_effort_delete(redis, marker)
            await InteractionFlowService.rollback(db)
            raise OAuthProtocolException('server_error', 'Validated redirect URI is unavailable', 500) from None
        if registered is None:
            await InteractionFlowService.best_effort_delete(redis, marker)
            raise OAuthProtocolException('server_error', 'Validated redirect URI is unavailable', 500)
        if record['status'] == 'denied':
            try:
                await db.commit()
            except Exception:
                await InteractionFlowService.best_effort_delete(redis, marker)
                await InteractionFlowService.rollback(db)
                raise OAuthProtocolException('server_error', 'Authorization completion failed', 500) from None
            return InteractionCompletionService._redirect(registered.uri, record, error='access_denied')
        return await InteractionCompletionService._issue_code(db, redis, record, registered.uri, marker)

    @staticmethod
    async def active_session(db: AsyncSession, record: dict[str, Any]) -> SysSsoSession | None:
        """
        读取活动会话

        :param db: 异步数据库会话
        :param record: 交互记录
        :return: 活动 SSO Session 或 None
        """
        sid = record.get('authenticatedSid')
        if not isinstance(sid, str):
            return None
        session = await SsoSessionDao.get_active(db, sid, now=datetime.now())
        if session is None:
            return None
        if (
            session.user_id != record.get('userId')
            or session.subject_id != record.get('subjectId')
            or session.auth_version != record.get('authVersion')
        ):
            return None
        return session

    @staticmethod
    async def _issue_code(
        db: AsyncSession, redis: Any, record: dict[str, Any], redirect_uri: str, marker: str
    ) -> 'InteractionCompletionResult':
        """
        签发授权码

        :param db: 异步数据库会话
        :param redis: Redis 客户端
        :param record: 交互记录
        :param redirect_uri: 已验证的重定向 URI
        :param marker: 完成标记 Key
        :return: 授权码
        """
        try:
            active = await InteractionCompletionService.active_session(db, record)
        except Exception:
            await InteractionFlowService.best_effort_delete(redis, marker)
            await InteractionFlowService.rollback(db)
            raise OAuthProtocolException('server_error', 'Current login could not be verified', 500) from None
        if active is None:
            await InteractionFlowService.best_effort_delete(redis, marker)
            raise OAuthProtocolException('login_required', 'A current login is required', 400)
        payload = {
            'clientPk': record['clientPk'],
            'redirectUri': redirect_uri,
            'userId': active.user_id,
            'subjectId': active.subject_id,
            'authVersion': active.auth_version,
            'sid': active.sid,
            'grantId': record.get('grantId'),
            'scopes': record['scopes'],
            'resources': record['resources'],
            'nonce': record['nonce'],
            'codeChallenge': record['codeChallenge'],
            'codeChallengeMethod': record['codeChallengeMethod'],
            'authTime': _protocol_datetime(active.auth_time).isoformat(),
        }
        code: str | None = None
        try:
            code = await AuthorizationCodeService.issue(redis, payload, pepper=OidcConfig.oidc_token_hash_pepper)
            await AuditService.record(
                db,
                OidcAuditEvent.AUTHORIZE_SUCCEEDED,
                'success',
                client_id=record.get('clientId'),
                user_id=active.user_id,
                subject_id=str(active.subject_id),
                sid=active.sid,
            )
            await db.commit()
        except Exception:
            if code is not None:
                try:
                    await AuthorizationCodeService.invalidate(redis, code)
                except Exception:
                    pass
            await InteractionFlowService.best_effort_delete(redis, marker)
            await InteractionFlowService.rollback(db)
            raise OAuthProtocolException('server_error', 'Authorization code could not be completed', 500) from None
        return InteractionCompletionService._redirect(redirect_uri, record, code=code)

    @staticmethod
    def _redirect(
        redirect_uri: str,
        record: dict[str, Any],
        *,
        code: str | None = None,
        error: str | None = None,
    ) -> 'InteractionCompletionResult':
        """
        构建重定向响应

        :param redirect_uri: 已验证的重定向 URI
        :param record: 交互记录
        :param code: 授权码或验证码
        :param error: 协议错误码
        :return: 重定向结果
        """
        parsed = urlsplit(redirect_uri)
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key not in {'code', 'error', 'state', 'iss'}
        ]
        if code is not None:
            query.append(('code', code))
        if error is not None:
            query.append(('error', error))
        if record.get('state') is not None:
            query.append(('state', record['state']))
        query.append(('iss', OidcConfig.oidc_issuer))
        location = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ''))
        return InteractionCompletionResult(location=location)


@dataclass(frozen=True)
class InteractionCompletionResult:
    """
    完成交互后的重定向目标；Controller 负责构造 HTTP 跳转
    """

    location: str


def _protocol_datetime(value: datetime | None) -> datetime:
    """
    将项目时间转换为协议时间

    :param value: 可选的数据库时间
    :return: 带时区的协议时间
    """
    if value is None:
        return datetime.now(timezone.utc)
    return value.astimezone(timezone.utc)
