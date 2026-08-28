import hashlib
import ipaddress
import secrets
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypeVar
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from config.env import OidcConfig
from exceptions.exception import ServiceException
from module_identity.dao._helpers import current_time, local_datetime
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.dao.oauth_resource_dao import OAuthResourceDao
from module_identity.entity.do.oauth_client_do import SysOAuthClient, SysOAuthClientSecret, SysOAuthClientUri
from module_identity.entity.do.oauth_resource_do import SysOAuthResource, SysOAuthScope
from module_identity.entity.vo.oauth_client_vo import (
    ClientCreateModel,
    ClientPageQueryModel,
    ClientSecretResponseModel,
    ClientStatusModel,
    ClientUpdateModel,
    ClientUriModel,
    ClientViewModel,
)
from module_identity.entity.vo.oauth_resource_vo import (
    ResourceCreateModel,
    ResourcePageQueryModel,
    ResourceStatusModel,
    ResourceUpdateModel,
    ResourceViewModel,
    ScopeModel,
    ScopePageQueryModel,
    ScopeStatusModel,
)
from module_identity.security.client_auth import generate_client_secret, hash_client_secret
from module_identity.security.uri_validator import is_safe_backchannel_uri
from module_identity.service.audit_service import AuditService

T = TypeVar('T')


@dataclass(frozen=True, slots=True)
class ResourceInvalidationTargets:
    """
    保存 Resource 变更后需要撤销的 Grant 和 Refresh Token 标识
    """

    resource_id: str
    client_ids: tuple[str, ...]
    grant_ids: tuple[str, ...]
    refresh_token_ids: tuple[str, ...]


class OAuthClientManagementError(ServiceException):
    """
    表示 OAuth Client 管理错误
    """

    def __init__(self, message: str) -> None:
        """
        初始化 OAuth Client 管理异常

        :param message: 错误消息
        :return: None
        """
        super().__init__(message=message)
        self.args = (message,)


class OAuthManagementBaseService:
    """
    OAuth 管理模块公共服务层
    """

    @classmethod
    async def _transaction(
        cls,
        db: AsyncSession,
        operation: Callable[[], Awaitable[T]],
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> T:
        """
        执行事务操作

        :param db: 异步数据库会话
        :param operation: 事务内的管理变更操作
        :param after_commit: 事务提交成功后执行的异步回调
        :return: operation 回调的返回值
        :raises OAuthClientManagementError: 敏感凭据相关 ServiceException 被转换为安全管理异常
        """
        try:
            result = await operation()
            await db.commit()
        except Exception as error:
            await db.rollback()
            if isinstance(error, IntegrityError):
                raise OAuthClientManagementError('OAuth resource or binding already exists') from error
            if isinstance(error, ServiceException) and any(
                field in str(error).lower() for field in ('secret_hash', 'secret_key', 'token_hash', 'client_secret')
            ):
                raise OAuthClientManagementError('OAuth 管理请求被拒绝') from error
            raise
        if after_commit is not None:
            await after_commit()
        return result

    _OAUTH_RESPONSE_QUERY_KEYS = frozenset({'code', 'error', 'error_description', 'error_uri', 'state', 'iss'})
    _MAX_AUDIENCE_LENGTH = 500
    _MAX_CLAIMS = 64
    _MAX_CLAIM_NAME_LENGTH = 64
    _MAX_CLIENT_ID_LENGTH = 64
    _URI_TYPES = (
        ('redirect', 'redirect_uris'),
        ('post_logout', 'post_logout_redirect_uris'),
        ('backchannel_logout', 'backchannel_logout_uris'),
        ('cors_origin', 'cors_origins'),
    )
    _ALLOWED_CLAIMS = frozenset(
        {
            'sub',
            'name',
            'preferred_username',
            'picture',
            'updated_at',
            'email',
            'email_verified',
            'phone_number',
            'phone_number_verified',
            'dept_id',
            'dept_name',
            'roles',
            'client_id',
            'scope',
            'sid',
        }
    )

    @staticmethod
    async def _record_audit(
        db: AsyncSession,
        event_type: str,
        actor: str,
        *,
        client_id: str | None = None,
        resource_id: str | None = None,
        sid: str | None = None,
        grant_id: str | None = None,
        detail: dict[str, str] | None = None,
    ) -> None:
        """
        记录管理审计

        :param db: 异步数据库会话
        :param event_type: 审计事件类型
        :param actor: 操作人标识
        :param client_id: 客户端标识
        :param resource_id: 资源标识
        :param sid: Session 标识
        :param grant_id: Grant 标识
        :param detail: 审计详情
        :return: None
        """
        safe_detail = {'actor': actor[:64]}
        if detail:
            safe_detail.update({key: value[:200] for key, value in detail.items() if key in {'reason', 'action'}})
        await AuditService.record(
            db,
            event_type,
            'success',
            client_id=client_id,
            resource_id=resource_id,
            sid=sid,
            grant_id=grant_id,
            detail=safe_detail,
        )

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        """
        将输入时间规范化为项目时间

        :param value: 调用方提供的当前时间值
        :return: 规范化后的本地无时区时间
        :raises OAuthClientManagementError: now 不是 datetime 时抛出
        """
        if value is None:
            return current_time()
        if not isinstance(value, datetime):
            raise OAuthClientManagementError('now must be a datetime')
        return local_datetime(value)

    @staticmethod
    def _actor(actor: str) -> str:
        """
        校验操作人标识

        :param actor: 操作人标识
        :return: 规范化后的操作者标识
        :raises OAuthClientManagementError: actor 为空或不是字符串时抛出
        """
        if not isinstance(actor, str) or not actor.strip():
            raise OAuthClientManagementError('actor is required')
        return actor[:64]

    @classmethod
    def _validate_client_ttls(cls, payload: ClientCreateModel) -> None:
        """
        校验 Client 令牌时效策略

        :param payload: Client 创建参数
        :return: None
        :raises OAuthClientManagementError: Client TTL 非正数、超出平台上限或闲置 TTL 超过绝对 TTL 时抛出
        """
        access = payload.access_token_ttl_seconds or OidcConfig.oidc_access_token_ttl_seconds
        refresh_idle = payload.refresh_token_idle_seconds or OidcConfig.oidc_refresh_token_idle_seconds
        refresh_absolute = payload.refresh_token_absolute_seconds or OidcConfig.oidc_refresh_token_absolute_seconds
        values = (access, refresh_idle, refresh_absolute, OidcConfig.oidc_max_access_token_ttl_seconds)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
            raise OAuthClientManagementError('Client token TTL policy is invalid')
        if access > OidcConfig.oidc_max_access_token_ttl_seconds:
            raise OAuthClientManagementError('Client access token TTL exceeds platform maximum')
        if refresh_idle > OidcConfig.oidc_refresh_token_idle_seconds:
            raise OAuthClientManagementError('Client refresh idle TTL exceeds platform idle maximum')
        if refresh_absolute > OidcConfig.oidc_refresh_token_absolute_seconds:
            raise OAuthClientManagementError('Client refresh absolute TTL exceeds platform maximum')
        if refresh_idle > refresh_absolute:
            raise OAuthClientManagementError('Client refresh idle TTL exceeds absolute TTL')

    @classmethod
    def _validate_resource_ttls(cls, payload: ResourceCreateModel) -> None:
        """
        校验 Resource Access Token 时效策略

        :param payload: Resource 创建或更新参数
        :return: None
        :raises OAuthClientManagementError: Resource TTL 非正数或超出平台上限时抛出
        """
        value = payload.access_token_ttl_seconds or OidcConfig.oidc_access_token_ttl_seconds
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise OAuthClientManagementError('Resource access token TTL policy is invalid')
        if value > OidcConfig.oidc_max_access_token_ttl_seconds:
            raise OAuthClientManagementError('Resource access token TTL exceeds platform maximum')

    @staticmethod
    def _client_id() -> str:
        """
        生成客户端标识

        :return: 带 cli_ 前缀的随机 Client 标识
        """
        return f'cli_{secrets.token_urlsafe(24)}'

    @classmethod
    def _validate_uri(cls, uri_type: str, uri: str) -> str:
        """
        校验并规范化 Client 注册 URI

        :param uri_type: URI 类型
        :param uri: 回调 URI
        :return: 校验后的完整 URI
        :raises OAuthClientManagementError: URI 格式不合法、包含保留参数或 Back-Channel 地址不安全时抛出
        """
        try:
            value = ClientUriModel(uri_type=uri_type, uri=uri).uri
        except (TypeError, ValueError) as exc:
            raise OAuthClientManagementError(str(exc)) from exc
        if uri_type == 'backchannel_logout':
            parsed = urlsplit(value)
            if parsed.scheme != 'https':
                raise OAuthClientManagementError('backchannel_logout URI must use HTTPS')
            try:
                address = ipaddress.ip_address(parsed.hostname or '')
            except ValueError:
                address = None
            if address is not None and (
                address.is_loopback
                or address.is_private
                or address.is_link_local
                or address.is_multicast
                or address.is_unspecified
                or address.is_reserved
            ):
                raise OAuthClientManagementError(
                    'backchannel_logout URI must not use loopback/private/reserved IP literal'
                )
        if uri_type == 'redirect':
            query_keys = {key for key, _ in parse_qsl(urlsplit(value).query, keep_blank_values=True)}
            forbidden = query_keys & cls._OAUTH_RESPONSE_QUERY_KEYS
            if forbidden:
                raise OAuthClientManagementError('redirect URI contains reserved OAuth response parameter')
        return value

    @classmethod
    def _uri_values(cls, payload: ClientCreateModel) -> dict[str, list[str]]:
        """
        收集并校验 Client 注册 URI

        :param payload: Client 创建参数
        :return: 按 URI 类型分组的注册地址映射
        :raises OAuthClientManagementError: URI 重复或格式不合法时抛出
        """
        values: dict[str, list[str]] = {}
        for uri_type, field_name in cls._URI_TYPES:
            uris = list(getattr(payload, field_name))
            if len(set(uris)) != len(uris):
                raise OAuthClientManagementError(f'{field_name} must not contain duplicates')
            values[uri_type] = [cls._validate_uri(uri_type, uri) for uri in uris]
        return values

    @classmethod
    async def _uri_values_async(cls, payload: ClientCreateModel) -> dict[str, list[str]]:
        """
        收集 URI 并执行 Back-Channel DNS 校验

        :param payload: Client 创建参数
        :return: 完成 DNS 校验的注册地址映射
        :raises OAuthClientManagementError: Back-Channel URI DNS 目标不是公网地址时抛出
        """
        values = cls._uri_values(payload)
        backchannels = values.get('backchannel_logout', [])
        for uri in backchannels:
            if not await is_safe_backchannel_uri(uri):
                raise OAuthClientManagementError('backchannel_logout URI DNS target is not public')
        return values

    @staticmethod
    def _unique_codes(values: Iterable[str], field_name: str) -> list[str]:
        """
        校验 Scope 或 Resource 编码并去重

        :param values: Scope 或 Resource 编码列表
        :param field_name: 字段名称
        :return: 去重后的编码列表
        :raises OAuthClientManagementError: 编码为空、包含空白或重复时抛出
        """
        result: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip() or value.strip() != value:
                raise OAuthClientManagementError(f'{field_name} contains invalid code')
            if value in result:
                raise OAuthClientManagementError(f'{field_name} must not contain duplicates')
            result.append(value)
        return result

    @classmethod
    async def _load_bindings(
        cls, db: AsyncSession, payload: ClientCreateModel
    ) -> tuple[list[SysOAuthScope], list[SysOAuthResource]]:
        """
        查询并校验 Client 的 Scope 与 Resource 绑定

        :param db: 异步数据库会话
        :param payload: Client 创建参数
        :return: 已校验的 Scope ORM 列表和 Resource ORM 列表
        :raises OAuthClientManagementError: Scope 或 Resource 不存在、未启用或绑定关系不合法时抛出
        """
        scope_codes = cls._unique_codes(payload.scope_codes, 'scope_codes')
        resource_ids = cls._unique_codes(payload.resource_ids, 'resource_ids')
        pre_authorized = set(cls._unique_codes(payload.pre_authorized_scope_codes, 'pre_authorized_scope_codes'))
        if not pre_authorized.issubset(scope_codes):
            raise OAuthClientManagementError('pre_authorized_scope_codes must be a subset of scope_codes')

        scopes: list[SysOAuthScope] = []
        if scope_codes:
            scopes = list(await OAuthClientDao.get_active_scopes_by_codes(db, scope_codes))
            if {scope.scope_code for scope in scopes} != set(scope_codes):
                raise OAuthClientManagementError('scope_codes contains an inactive or unknown scope')

        resources: list[SysOAuthResource] = []
        if resource_ids:
            resources = list(await OAuthClientDao.get_active_resources_by_ids(db, resource_ids))
            if {resource.resource_id for resource in resources} != set(resource_ids):
                raise OAuthClientManagementError('resource_ids contains an inactive or unknown resource')

        resource_pks = {resource.resource_pk for resource in resources}
        if any(scope.scope_type == 'resource' and scope.resource_pk not in resource_pks for scope in scopes):
            raise OAuthClientManagementError('resource scope must bind an authorized resource')
        return scopes, resources

    @classmethod
    async def _replace_bindings(
        cls,
        db: AsyncSession,
        client_pk: int,
        payload: ClientCreateModel,
        scopes: Sequence[SysOAuthScope],
        resources: Sequence[SysOAuthResource],
        now: datetime,
    ) -> None:
        """
        写入 Client 的 Scope、Resource 与 URI 绑定

        :param db: 异步数据库会话
        :param client_pk: 客户端主键
        :param payload: Client 创建参数
        :param scopes: Scope 集合
        :param resources: Resource 集合
        :param now: 当前时间
        :return: None
        """
        uri_values = await cls._uri_values_async(payload)
        await OAuthClientDao.replace_bindings(
            db,
            client_pk,
            scopes,
            resources,
            uri_values,
            set(payload.pre_authorized_scope_codes),
            now,
        )

    @staticmethod
    def _client_values(payload: ClientCreateModel) -> dict[str, object]:
        """
        转换 Client DTO 为 ORM 字段

        :param payload: Client 创建参数
        :return: 可写入 Client ORM 的字段映射
        """
        return {
            'client_name': payload.client_name,
            'client_type': payload.client_type,
            'token_endpoint_auth_method': payload.token_endpoint_auth_method,
            'grant_types': list(payload.grant_types),
            'response_types': list(payload.response_types),
            'require_pkce': int(payload.require_pkce),
            'require_consent': int(payload.require_consent),
            'trusted_client': int(payload.trusted_client),
            'access_token_ttl_seconds': payload.access_token_ttl_seconds,
            'refresh_token_idle_seconds': payload.refresh_token_idle_seconds,
            'refresh_token_absolute_seconds': payload.refresh_token_absolute_seconds,
            'logo_uri': payload.logo_uri,
            'policy_uri': payload.policy_uri,
            'tos_uri': payload.tos_uri,
            'remark': payload.remark,
        }

    @staticmethod
    def _secret_response(client_id: str, secret: SysOAuthClientSecret, plaintext: str) -> ClientSecretResponseModel:
        """
        构造 Client Secret 返回模型

        :param client_id: 客户端标识
        :param secret: 已保存的 Client Secret ORM 记录
        :param plaintext: 明文密钥
        :return: 包含一次性明文的 ClientSecretResponseModel
        """
        return ClientSecretResponseModel(
            client_id=client_id,
            secret_id=secret.secret_id,
            client_secret=plaintext,
            secret_hint=secret.secret_hint,
            not_before=secret.not_before,
            expires_at=secret.expires_at,
        )

    @classmethod
    async def _new_secret(
        cls,
        db: AsyncSession,
        client: SysOAuthClient,
        actor: str,
        created_at: datetime,
        *,
        not_before: datetime,
        expires_at: datetime | None = None,
    ) -> ClientSecretResponseModel:
        """
        创建并 flush Client Secret ORM 记录

        :param db: 异步数据库会话
        :param client: Client ORM 记录
        :param actor: 操作人标识
        :param created_at: 创建时间
        :param not_before: 生效时间
        :param expires_at: 过期时间
        :return: 已 flush 的 ClientSecretResponseModel
        """
        plaintext = generate_client_secret()
        secret = SysOAuthClientSecret(
            secret_id=str(uuid4()),
            client_pk=client.client_pk,
            secret_hash=hash_client_secret(plaintext),
            secret_hint=f'...{plaintext[-6:]}',
            status='active',
            not_before=not_before,
            expires_at=expires_at,
            create_by=actor,
            create_time=created_at,
        )
        await OAuthClientDao.add_secret(db, secret)
        return cls._secret_response(client.client_id, secret, plaintext)

    @classmethod
    def _validate_audience(cls, audience: str) -> str:
        """
        校验 Resource audience URI

        :param audience: Resource audience
        :return: 校验后的 Resource audience URI
        :raises OAuthClientManagementError: audience 不是无用户信息的绝对 HTTPS URI 时抛出
        """
        if not isinstance(audience, str) or not audience or len(audience) > cls._MAX_AUDIENCE_LENGTH:
            raise OAuthClientManagementError('audience must be a non-empty URI')
        parsed = urlsplit(audience)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.fragment:
            raise OAuthClientManagementError('audience must be an absolute HTTPS URI without fragment')
        if parsed.username is not None or parsed.password is not None:
            raise OAuthClientManagementError('audience must not contain userinfo')
        try:
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError as exc:
            raise OAuthClientManagementError('audience host or port is invalid') from exc
        if not hostname:
            raise OAuthClientManagementError('audience must contain a host')
        return audience

    @classmethod
    def _validate_claims(cls, values: Iterable[str], field_name: str = 'claims') -> list[str]:
        """
        校验 Resource Claim 白名单

        :param values: Resource Claim 名称列表
        :param field_name: 字段名称
        :return: 已校验的 Resource Claim 名称列表
        :raises OAuthClientManagementError: Claim 列表不是允许的字符串列表或包含重复项时抛出
        """
        if not isinstance(values, list) or len(values) > cls._MAX_CLAIMS:
            raise OAuthClientManagementError(f'{field_name} must be a list with at most 64 items')
        result: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value or len(value) > cls._MAX_CLAIM_NAME_LENGTH:
                raise OAuthClientManagementError(f'{field_name} contains an invalid claim')
            if value not in cls._ALLOWED_CLAIMS:
                raise OAuthClientManagementError(f'{field_name} contains a disallowed claim')
            if value in result:
                raise OAuthClientManagementError(f'{field_name} must not contain duplicates')
            result.append(value)
        return result

    @staticmethod
    def _resource_values(payload: ResourceCreateModel) -> dict[str, object]:
        """
        转换 Resource DTO 为 ORM 字段

        :param payload: Resource 创建或更新参数
        :return: 可写入 Resource ORM 的字段映射
        """
        return {
            'resource_name': payload.resource_name,
            'audience': payload.audience,
            'token_format': payload.token_format,
            'signing_alg': payload.signing_alg,
            'access_token_ttl_seconds': payload.access_token_ttl_seconds,
            'allowed_claims': list(payload.allowed_claims),
            'remark': payload.remark,
        }

    @classmethod
    async def _resolve_introspection_client(cls, db: AsyncSession, client_id: str | None) -> SysOAuthClient | None:
        """
        解析 Resource 使用的 introspection Client

        :param db: 异步数据库会话
        :param client_id: 客户端标识
        :return: 启用的 introspection Client ORM 记录或 None
        :raises OAuthClientManagementError: introspection Client 不存在、未启用或不是机密 Client 时抛出
        """
        if client_id is None:
            return None
        if not isinstance(client_id, str) or not client_id or len(client_id) > cls._MAX_CLIENT_ID_LENGTH:
            raise OAuthClientManagementError('introspection_client_id is invalid')
        client = await OAuthClientDao.find_active_introspection_client(db, client_id)
        if client is None:
            raise OAuthClientManagementError('introspection client must be an active confidential client')
        return client

    @staticmethod
    def _resource_view(resource: SysOAuthResource, introspection_client_id: str | None = None) -> ResourceViewModel:
        """
        转换 Resource ORM 记录为 ResourceViewModel

        :param resource: Resource ORM 记录
        :param introspection_client_id: 用于内省的客户端标识
        :return: ResourceViewModel 管理视图
        """
        return ResourceViewModel.model_validate(
            {
                'resource_id': resource.resource_id,
                'resource_name': resource.resource_name,
                'audience': resource.audience,
                'token_format': resource.token_format,
                'signing_alg': resource.signing_alg,
                'access_token_ttl_seconds': resource.access_token_ttl_seconds,
                'introspection_client_id': introspection_client_id,
                'allowed_claims': list(resource.allowed_claims or []),
                'status': resource.status,
                'remark': resource.remark,
            }
        )

    @staticmethod
    def _scope_view(scope: SysOAuthScope, resource_id: str | None) -> ScopeModel:
        """
        转换 Scope ORM 记录为 ScopeModel

        :param scope: Scope ORM 记录
        :param resource_id: 资源标识
        :return: ScopeModel 管理视图
        """
        return ScopeModel.model_validate(
            {
                'scope_code': scope.scope_code,
                'scope_name': scope.scope_name,
                'scope_type': scope.scope_type,
                'resource_id': resource_id,
                'claims': list(scope.claims or []),
                'consent_required': bool(scope.consent_required),
                'sensitive': bool(scope.sensitive),
                'status': scope.status,
                'remark': scope.remark,
            }
        )

    @classmethod
    async def _lock_resource_clients(cls, db: AsyncSession, resource_pk: int) -> list[SysOAuthClient]:
        """
        锁定关联 Resource 的 Client 记录

        :param db: 异步数据库会话
        :param resource_pk: 资源主键
        :return: 已锁定的 Client ORM 记录列表
        """
        return list(await OAuthClientDao.lock_clients_for_resource(db, resource_pk))

    @staticmethod
    def _bump_clients(clients: Iterable[SysOAuthClient], actor: str, now: datetime) -> None:
        """
        递增 Client 策略版本并记录操作者

        :param clients: 需要递增策略版本的客户端集合
        :param actor: 操作人标识
        :param now: 当前时间
        :return: None
        """
        for client in clients:
            client.policy_version = int(client.policy_version or 0) + 1
            client.update_by, client.update_time = actor, now

    @staticmethod
    async def _revoke_client_credentials(db: AsyncSession, client_pk: int, now: datetime) -> None:
        """
        撤销 Client 的 Grant 与 Refresh Token

        :param db: 异步数据库会话
        :param client_pk: 客户端主键
        :param now: 当前时间
        :return: None
        """
        await OAuthClientDao.revoke_client_credentials(db, client_pk, now)


class OAuthClientManagementService(OAuthManagementBaseService):
    """
    OAuth Client 管理模块服务层
    """

    @classmethod
    async def create_client(
        cls,
        db: AsyncSession,
        payload: ClientCreateModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ClientViewModel:
        """
        创建 OAuth Client 及其绑定配置

        :param db: 异步数据库会话
        :param payload: Client 创建参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 创建后的 Client 详情
        """
        return await cls._transaction(db, lambda: cls._create_client(db, payload, actor=actor, now=now), after_commit)

    @classmethod
    async def update_client(
        cls,
        db: AsyncSession,
        payload: ClientUpdateModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ClientViewModel:
        """
        更新 OAuth Client 及其绑定配置

        :param db: 异步数据库会话
        :param payload: Client 更新参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 更新后的 Client 详情
        """
        return await cls._transaction(db, lambda: cls._update_client(db, payload, actor=actor, now=now), after_commit)

    @classmethod
    async def disable_clients(
        cls,
        db: AsyncSession,
        identifiers: list[str],
        actor: str,
        *,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """
        禁用指定 OAuth Client 并撤销其凭据

        :param db: 异步数据库会话
        :param identifiers: Client 公开标识列表
        :param actor: 操作者标识
        :param after_commit: 事务提交成功后执行的异步回调
        :return: None
        """

        async def operation() -> None:
            """
            在同一事务中批量禁用指定 Client

            :return: None
            """
            for identifier in identifiers:
                await cls._soft_disable(db, identifier, actor=actor)

        await cls._transaction(db, operation, after_commit)

    @classmethod
    async def change_client_status(
        cls,
        db: AsyncSession,
        payload: ClientStatusModel,
        actor: str,
        *,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ClientViewModel:
        """
        变更 OAuth Client 启用状态

        :param db: 异步数据库会话
        :param payload: Client 状态变更参数
        :param actor: 操作者标识
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 更新后的 Client 详情
        """
        return await cls._transaction(db, lambda: cls._change_status(db, payload, actor=actor), after_commit)

    @classmethod
    async def rotate_secret(
        cls,
        db: AsyncSession,
        client_id: str,
        actor: str,
        *,
        not_before: datetime | None = None,
        expires_at: datetime | None = None,
        retirement_seconds: int | None = None,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ClientSecretResponseModel:
        """
        轮换 OAuth Client Secret 并撤销旧凭据

        :param db: 异步数据库会话
        :param client_id: Client 公开标识
        :param actor: 操作者标识
        :param not_before: 生效时间
        :param expires_at: 过期时间
        :param retirement_seconds: 退役等待秒数
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 只包含一次性明文的 Secret 响应
        """
        return await cls._transaction(
            db,
            lambda: cls._rotate_secret(
                db,
                client_id,
                actor=actor,
                not_before=not_before,
                expires_at=expires_at,
                retirement_seconds=retirement_seconds,
                now=now,
            ),
            after_commit,
        )

    @classmethod
    async def revoke_secret(
        cls,
        db: AsyncSession,
        client_id: str,
        secret_id: str,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> bool:
        """
        撤销指定 Client Secret

        :param db: 异步数据库会话
        :param client_id: Client 公开标识
        :param secret_id: Secret 标识
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 本次是否发生状态变更
        """
        return await cls._transaction(
            db, lambda: cls._revoke_secret(db, client_id, secret_id, actor=actor, now=now), after_commit
        )

    @classmethod
    async def add_uri(
        cls,
        db: AsyncSession,
        client_id: str,
        payload: ClientUriModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> int:
        """
        添加注册 URI

        :param db: 异步数据库会话
        :param client_id: Client 公开标识
        :param payload: URI 注册参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 新增 URI 的内部标识
        """
        return await cls._transaction(
            db, lambda: cls._add_uri(db, client_id, payload, actor=actor, now=now), after_commit
        )

    @classmethod
    async def remove_uri(
        cls,
        db: AsyncSession,
        client_id: str,
        uri_id: int,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> bool:
        """
        删除注册 URI

        :param db: 异步数据库会话
        :param client_id: Client 公开标识
        :param uri_id: URI 内部标识
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 本次是否发生状态变更
        """
        return await cls._transaction(
            db, lambda: cls._remove_uri(db, client_id, uri_id, actor=actor, now=now), after_commit
        )

    @classmethod
    async def _create_client(
        cls,
        db: AsyncSession,
        payload: ClientCreateModel,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> ClientViewModel:
        """
        在事务中创建 Client ORM 记录及关联配置

        :param db: 异步数据库会话
        :param payload: Client 创建参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ClientViewModel 详情
        :raises OAuthClientManagementError: Client DTO 校验失败或公开标识已存在时抛出
        """
        if not isinstance(payload, ClientCreateModel) or isinstance(payload, ClientUpdateModel):
            raise OAuthClientManagementError('payload must be ClientCreateModel')
        actor_value, current = cls._actor(actor), cls._now(now)
        cls._validate_client_ttls(payload)
        scopes, resources = await cls._load_bindings(db, payload)
        client = SysOAuthClient(
            client_id=cls._client_id(),
            subject_type='public',
            policy_version=1,
            status='0',
            create_by=actor_value,
            create_time=current,
            update_by=actor_value,
            update_time=current,
            **cls._client_values(payload),
        )
        await OAuthClientDao.add_client(db, client)
        await cls._replace_bindings(db, client.client_pk, payload, scopes, resources, current)
        await cls._record_audit(db, OidcAuditEvent.CLIENT_CREATED, actor_value, client_id=client.client_id)
        return await cls.detail(db, client.client_id)

    @classmethod
    async def _update_client(
        cls,
        db: AsyncSession,
        payload: ClientUpdateModel,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> ClientViewModel:
        """
        在事务中更新 Client ORM 记录及关联配置

        :param db: 异步数据库会话
        :param payload: Client 更新参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ClientViewModel 详情
        :raises OAuthClientManagementError: Client 不存在、DTO 校验失败或策略绑定不合法时抛出
        """
        if not isinstance(payload, ClientUpdateModel):
            raise OAuthClientManagementError('payload must be ClientUpdateModel')
        actor_value, current = cls._actor(actor), cls._now(now)
        cls._validate_client_ttls(payload)
        client = await OAuthClientDao.get_by_client_id(db, payload.client_id, active_only=False, for_update=True)
        if client is None:
            raise OAuthClientManagementError('client not found')
        if client.client_type != payload.client_type:
            raise OAuthClientManagementError('client_type is immutable')
        if client.client_type == 'public' and payload.token_endpoint_auth_method != 'none':
            raise OAuthClientManagementError('public client cannot use a secret authentication method')
        current_view = await cls.detail(db, client.client_id)
        policy_changed = cls._client_policy_changed(current_view, payload)
        scopes, resources = await cls._load_bindings(db, payload)
        for key, value in cls._client_values(payload).items():
            setattr(client, key, value)
        client.update_by, client.update_time = actor_value, current
        if policy_changed:
            client.policy_version = int(client.policy_version or 0) + 1
            await cls._replace_bindings(db, client.client_pk, payload, scopes, resources, current)
        await OAuthClientDao.persist_client_policy_change(db, client)
        if policy_changed:
            await cls._record_audit(
                db,
                OidcAuditEvent.SECURITY_VERSION_CHANGED,
                actor_value,
                client_id=client.client_id,
                detail={'action': 'client_updated'},
            )
        return await cls.detail(db, client.client_id)

    @staticmethod
    def _client_policy_changed(current: ClientViewModel, payload: ClientUpdateModel) -> bool:
        """
        比较 Client 授权与令牌策略是否变化

        :param current: 当前客户端 ORM 记录
        :param payload: Client 更新参数
        :return: Client 授权或令牌策略是否发生变化
        """
        scalar_fields = (
            'client_type',
            'token_endpoint_auth_method',
            'require_pkce',
            'require_consent',
            'trusted_client',
            'access_token_ttl_seconds',
            'refresh_token_idle_seconds',
            'refresh_token_absolute_seconds',
        )
        if any(getattr(current, field) != getattr(payload, field) for field in scalar_fields):
            return True
        unordered_fields = ('grant_types', 'response_types', 'scope_codes', 'pre_authorized_scope_codes')
        if any(set(getattr(current, field)) != set(getattr(payload, field)) for field in unordered_fields):
            return True
        ordered_fields = (
            'resource_ids',
            'redirect_uris',
            'post_logout_redirect_uris',
            'backchannel_logout_uris',
            'cors_origins',
        )
        return any(tuple(getattr(current, field)) != tuple(getattr(payload, field)) for field in ordered_fields)

    @classmethod
    async def detail(cls, db: AsyncSession, client_id: str) -> ClientViewModel:
        """
        查询 OAuth Client 详情

        :param db: 异步数据库会话
        :param client_id: 客户端标识
        :return: ClientViewModel 详情
        :raises OAuthClientManagementError: Client 不存在时抛出
        """
        detail_rows = await OAuthClientDao.get_client_detail_rows(db, client_id)
        if detail_rows is None:
            raise OAuthClientManagementError('client not found')
        client, scope_rows, resource_ids, uri_rows = detail_rows
        uri_map = {uri_type: [] for uri_type, _ in cls._URI_TYPES}
        for row in uri_rows:
            if row.status != '0':
                continue
            uri_map.setdefault(row.uri_type, []).append(row.uri)
        payload = {
            'client_id': client.client_id,
            'client_name': client.client_name,
            'client_type': client.client_type,
            'token_endpoint_auth_method': client.token_endpoint_auth_method,
            'grant_types': list(client.grant_types or []),
            'response_types': list(client.response_types or []),
            'require_pkce': bool(client.require_pkce),
            'require_consent': bool(client.require_consent),
            'trusted_client': bool(client.trusted_client),
            'scope_codes': [scope.scope_code for scope, _ in scope_rows],
            'pre_authorized_scope_codes': [scope.scope_code for scope, pre in scope_rows if bool(pre)],
            'resource_ids': list(resource_ids),
            'redirect_uris': uri_map['redirect'],
            'post_logout_redirect_uris': uri_map['post_logout'],
            'backchannel_logout_uris': uri_map['backchannel_logout'],
            'cors_origins': uri_map['cors_origin'],
            'access_token_ttl_seconds': client.access_token_ttl_seconds,
            'refresh_token_idle_seconds': client.refresh_token_idle_seconds,
            'refresh_token_absolute_seconds': client.refresh_token_absolute_seconds,
            'logo_uri': client.logo_uri,
            'policy_uri': client.policy_uri,
            'tos_uri': client.tos_uri,
            'remark': client.remark,
            'status': client.status,
            'policy_version': client.policy_version,
            'create_time': client.create_time,
            'update_time': client.update_time,
        }
        return ClientViewModel.model_validate(payload)

    @classmethod
    async def _add_uri(
        cls,
        db: AsyncSession,
        client_id: str,
        payload: ClientUriModel,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> int:
        """
        添加 Client 注册 URI

        :param db: 异步数据库会话
        :param client_id: 客户端标识
        :param payload: URI 注册参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: 新增 URI 的内部主键
        :raises OAuthClientManagementError: Client 不存在或 URI 已注册时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        client = await OAuthClientDao.get_by_client_id(db, client_id, active_only=False, for_update=True)
        if client is None:
            raise OAuthClientManagementError('client not found')
        uri = cls._validate_uri(payload.uri_type, payload.uri)
        if payload.uri_type == 'backchannel_logout' and not await is_safe_backchannel_uri(uri):
            raise OAuthClientManagementError('backchannel_logout URI DNS target is not public')
        uri_hash = hashlib.sha256(uri.encode('utf-8')).hexdigest()
        if await OAuthClientDao.find_uri(db, client.client_pk, payload.uri_type, uri_hash, uri) is not None:
            raise OAuthClientManagementError('URI is already registered')
        row = SysOAuthClientUri(
            client_pk=client.client_pk,
            uri_type=payload.uri_type,
            uri=uri,
            uri_hash=uri_hash,
            is_default=int(payload.is_default),
            status=payload.status,
            create_time=current,
        )
        await OAuthClientDao.add_uri(db, row)
        client.policy_version = int(client.policy_version or 0) + 1
        client.update_by, client.update_time = actor_value, current
        await OAuthClientDao.persist_client_policy_change(db, client)
        await cls._record_audit(
            db,
            OidcAuditEvent.SECURITY_VERSION_CHANGED,
            actor_value,
            client_id=client_id,
            detail={'action': 'uri_added'},
        )
        return row.uri_id

    @classmethod
    async def _remove_uri(
        cls, db: AsyncSession, client_id: str, uri_id: int, *, actor: str, now: datetime | None = None
    ) -> bool:
        """
        删除 Client 注册 URI

        :param db: 异步数据库会话
        :param client_id: 客户端标识
        :param uri_id: 待删除的 URI 主键
        :param actor: 操作人标识
        :param now: 当前时间
        :return: 本次是否停用注册 URI
        :raises OAuthClientManagementError: Client 不存在或注册 URI 不存在
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        client = await OAuthClientDao.get_by_client_id(db, client_id, active_only=False, for_update=True)
        if client is None:
            raise OAuthClientManagementError('client not found')
        row = await OAuthClientDao.get_uri_for_update(db, uri_id)
        if row is None:
            raise OAuthClientManagementError('URI not found')
        if row.client_pk != client.client_pk:
            raise OAuthClientManagementError('URI does not belong to client')
        if row.status == '1':
            return False
        row.status = '1'
        client.policy_version = int(client.policy_version or 0) + 1
        client.update_by, client.update_time = actor_value, current
        await OAuthClientDao.persist_client_policy_change(db, client)
        await cls._record_audit(
            db,
            OidcAuditEvent.SECURITY_VERSION_CHANGED,
            actor_value,
            client_id=client_id,
            detail={'action': 'uri_removed'},
        )
        return True

    @classmethod
    async def list_clients(cls, db: AsyncSession, query: ClientPageQueryModel | None = None) -> list[ClientViewModel]:
        """
        分页查询 OAuth Client

        :param db: 异步数据库会话
        :param query: Client 分页查询参数
        :return: ClientViewModel 列表
        """
        page = query or ClientPageQueryModel()
        rows = await OAuthClientDao.list_clients_page(db, page)
        return [await cls.detail(db, item.client_id) for item in rows]

    @classmethod
    async def count_clients(cls, db: AsyncSession, query: ClientPageQueryModel | None = None) -> int:
        """
        统计 OAuth Client 数量

        :param db: 异步数据库会话
        :param query: Client 分页统计参数
        :return: Client 数量
        """
        page = query or ClientPageQueryModel()
        return await OAuthClientDao.count_clients(db, page)

    @classmethod
    async def _change_status(
        cls, db: AsyncSession, payload: ClientStatusModel, *, actor: str, now: datetime | None = None
    ) -> ClientViewModel:
        """
        在事务中变更 Client 状态

        :param db: 异步数据库会话
        :param payload: Client 状态变更参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ClientViewModel 详情
        :raises OAuthClientManagementError: Client 不存在或状态值不合法时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        client = await OAuthClientDao.get_by_client_id(db, payload.client_id, active_only=False, for_update=True)
        if client is None:
            raise OAuthClientManagementError('client not found')
        if client.status != payload.status:
            if payload.status == '1':
                await OAuthClientDao.revoke_client_credentials(db, client.client_pk, current)
            client.status = payload.status
            client.policy_version = int(client.policy_version or 0) + 1
            client.update_by, client.update_time = actor_value, current
            await OAuthClientDao.persist_client_policy_change(db, client)
            await cls._record_audit(
                db,
                OidcAuditEvent.CLIENT_DISABLED if payload.status == '1' else OidcAuditEvent.SECURITY_VERSION_CHANGED,
                actor_value,
                client_id=client.client_id,
                detail={'action': 'status_changed'},
            )
        return await cls.detail(db, client.client_id)

    @classmethod
    async def _soft_disable(
        cls, db: AsyncSession, client_id: str, *, actor: str, now: datetime | None = None
    ) -> ClientViewModel:
        """
        在事务中禁用 Client 并撤销凭据

        :param db: 异步数据库会话
        :param client_id: 客户端标识
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ClientViewModel 详情
        """
        return await cls._change_status(db, ClientStatusModel(client_id=client_id, status='1'), actor=actor, now=now)

    @classmethod
    async def _rotate_secret(
        cls,
        db: AsyncSession,
        client_id: str,
        *,
        actor: str,
        now: datetime | None = None,
        not_before: datetime | None = None,
        expires_at: datetime | None = None,
        retirement_seconds: int | None = None,
    ) -> ClientSecretResponseModel:
        """
        在事务中创建新的 Client Secret

        :param db: 异步数据库会话
        :param client_id: 客户端标识
        :param actor: 操作人标识
        :param now: 当前时间
        :param not_before: 生效时间
        :param expires_at: 过期时间
        :param retirement_seconds: 退役等待秒数
        :return: ClientSecretResponseModel（含一次性明文）
        :raises OAuthClientManagementError: Client 不存在或 Secret 时效不合法时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        retirement_ttl = retirement_seconds
        if retirement_ttl is None:
            retirement_ttl = getattr(
                OidcConfig,
                'oidc_client_secret_retirement_seconds',
                OidcConfig.oidc_key_rotation_overlap_seconds,
            )
        if isinstance(retirement_ttl, bool) or not isinstance(retirement_ttl, int) or retirement_ttl <= 0:
            raise OAuthClientManagementError('secret retirement TTL must be a positive integer')
        effective = cls._now(not_before) if not_before is not None else current
        expiry = cls._now(expires_at) if expires_at is not None else None
        if expiry is not None and expiry <= effective:
            raise OAuthClientManagementError('expires_at must be after not_before')
        client = await OAuthClientDao.get_by_client_id(db, client_id, active_only=False, for_update=True)
        if client is None:
            raise OAuthClientManagementError('client not found')
        if client.client_type != 'confidential' or client.token_endpoint_auth_method != 'client_secret_basic':
            raise OAuthClientManagementError('public clients cannot rotate a secret')
        old_secrets = await OAuthClientDao.list_secrets(db, client.client_pk, active_only=False, for_update=True)
        old_secrets = [secret for secret in old_secrets if secret.status == 'active']
        for old_secret in old_secrets:
            if old_secret.expires_at is not None and effective >= cls._now(old_secret.expires_at):
                raise OAuthClientManagementError('not_before leaves no active secret overlap')
        retirement_end = max(current, effective) + timedelta(seconds=retirement_ttl)
        for old_secret in old_secrets:
            old_secret.status = 'retiring'
            old_expiry = cls._now(old_secret.expires_at) if old_secret.expires_at is not None else None
            if old_expiry is None or old_expiry > retirement_end:
                old_secret.expires_at = retirement_end
        secret = await cls._new_secret(db, client, actor_value, current, not_before=effective, expires_at=expiry)
        client.policy_version = int(client.policy_version or 0) + 1
        client.update_by, client.update_time = actor_value, current
        await OAuthClientDao.persist_client_policy_change(db, client)
        await cls._record_audit(db, OidcAuditEvent.CLIENT_SECRET_ROTATED, actor_value, client_id=client.client_id)
        return secret

    @classmethod
    async def _revoke_secret(
        cls, db: AsyncSession, client_id: str, secret_id: str, *, actor: str, now: datetime | None = None
    ) -> bool:
        """
        在事务中撤销 Client Secret

        :param db: 异步数据库会话
        :param client_id: 客户端标识
        :param secret_id: 待撤销的 Secret 主键
        :param actor: 操作人标识
        :param now: 当前时间
        :return: 本次是否撤销 Client Secret
        :raises OAuthClientManagementError: Client Secret 不存在或已经撤销时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        client = await OAuthClientDao.get_by_client_id(db, client_id, active_only=False, for_update=True)
        if client is None:
            raise OAuthClientManagementError('client not found')
        secret = await OAuthClientDao.get_secret_for_update(db, secret_id)
        if secret is None:
            raise OAuthClientManagementError('secret not found')
        if secret.client_pk != client.client_pk:
            raise OAuthClientManagementError('secret does not belong to client')
        if secret.status == 'revoked':
            return False
        secret.status, secret.revoked_by, secret.revoked_at = 'revoked', actor_value, current
        client.policy_version = int(client.policy_version or 0) + 1
        client.update_by, client.update_time = actor_value, current
        await OAuthClientDao.persist_client_policy_change(db, client)
        await cls._record_audit(
            db,
            OidcAuditEvent.CLIENT_SECRET_ROTATED,
            actor_value,
            client_id=client.client_id,
            detail={'action': 'secret_revoked'},
        )
        return True

    @staticmethod
    async def list_active_cors_origins(db: AsyncSession) -> tuple[str, ...]:
        """
        查询当前启用的 CORS Origin

        :param db: 异步数据库会话
        :return: 启用的 CORS Origin 元组
        """
        return await OAuthClientDao.list_cors_origins(db)


class OAuthResourceManagementService(OAuthManagementBaseService):
    """
    OAuth Resource 和 Scope 管理模块服务层
    """

    @classmethod
    async def create_resource(
        cls,
        db: AsyncSession,
        payload: ResourceCreateModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ResourceViewModel:
        """
        创建 OAuth Resource 及其 Claim 配置

        :param db: 异步数据库会话
        :param payload: Resource 创建参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 创建后的 Resource 详情
        """
        return await cls._transaction(
            db,
            lambda: cls._create_resource(db, payload, actor=actor, now=now),
            after_commit,
        )

    @classmethod
    async def update_resource(
        cls,
        db: AsyncSession,
        payload: ResourceUpdateModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ResourceViewModel:
        """
        更新 OAuth Resource 及其 Claim 配置

        :param db: 异步数据库会话
        :param payload: Resource 更新参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 更新后的 Resource 详情
        """
        return await cls._transaction(
            db,
            lambda: cls._update_resource(db, payload, actor=actor, now=now),
            after_commit,
        )

    @classmethod
    async def disable_resources(
        cls,
        db: AsyncSession,
        identifiers: list[str],
        actor: str,
        *,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """
        禁用指定 OAuth Resource 并失效关联授权

        :param db: 异步数据库会话
        :param identifiers: Resource 公开标识列表
        :param actor: 操作者标识
        :param after_commit: 事务提交成功后执行的异步回调
        :return: None
        """

        async def operation() -> None:
            """
            在同一事务中批量禁用指定 Resource

            :return: None
            """
            for identifier in identifiers:
                await cls._soft_disable_resource(db, identifier, actor=actor)

        await cls._transaction(db, operation, after_commit)

    @classmethod
    async def change_resource_status(
        cls,
        db: AsyncSession,
        payload: ResourceStatusModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ResourceViewModel:
        """
        变更 OAuth Resource 启用状态

        :param db: 异步数据库会话
        :param payload: Resource 状态变更参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 更新后的 Resource 详情
        """
        return await cls._transaction(
            db, lambda: cls._change_resource_status(db, payload, actor=actor, now=now), after_commit
        )

    @classmethod
    async def create_scope(
        cls,
        db: AsyncSession,
        payload: ScopeModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ScopeModel:
        """
        创建 OAuth Scope 及其 Resource 关联

        :param db: 异步数据库会话
        :param payload: Scope 创建参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 创建后的 Scope 详情
        """
        return await cls._transaction(db, lambda: cls._create_scope(db, payload, actor=actor, now=now), after_commit)

    @classmethod
    async def update_scope(
        cls,
        db: AsyncSession,
        payload: ScopeModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ScopeModel:
        """
        更新 OAuth Scope 及其 Resource 关联

        :param db: 异步数据库会话
        :param payload: Scope 更新参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 更新后的 Scope 详情
        """
        return await cls._transaction(db, lambda: cls._update_scope(db, payload, actor=actor, now=now), after_commit)

    @classmethod
    async def disable_scopes(
        cls,
        db: AsyncSession,
        identifiers: list[str],
        actor: str,
        *,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """
        禁用指定 OAuth Scope 并失效关联授权

        :param db: 异步数据库会话
        :param identifiers: Scope 编码列表
        :param actor: 操作者标识
        :param after_commit: 事务提交成功后执行的异步回调
        :return: None
        """

        async def operation() -> None:
            """
            在同一事务中批量禁用指定 Scope

            :return: None
            """
            for identifier in identifiers:
                await cls._soft_disable_scope(db, identifier, actor=actor)

        await cls._transaction(db, operation, after_commit)

    @classmethod
    async def change_scope_status(
        cls,
        db: AsyncSession,
        payload: ScopeStatusModel,
        actor: str,
        *,
        now: datetime | None = None,
        after_commit: Callable[[], Awaitable[None]] | None = None,
    ) -> ScopeModel:
        """
        变更 OAuth Scope 启用状态

        :param db: 异步数据库会话
        :param payload: Scope 状态变更参数
        :param actor: 操作者标识
        :param now: 当前时间
        :param after_commit: 事务提交成功后执行的异步回调
        :return: 更新后的 Scope 详情
        """
        return await cls._transaction(
            db, lambda: cls._change_scope_status(db, payload, actor=actor, now=now), after_commit
        )

    @classmethod
    async def _create_resource(
        cls,
        db: AsyncSession,
        payload: ResourceCreateModel,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> ResourceViewModel:
        """
        在事务中创建 Resource ORM 记录

        :param db: 异步数据库会话
        :param payload: Resource 创建参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ResourceViewModel 详情
        :raises OAuthClientManagementError: Resource DTO 校验失败或 resource_id/audience 已存在时抛出
        """
        if not isinstance(payload, ResourceCreateModel) or isinstance(payload, ResourceUpdateModel):
            raise OAuthClientManagementError('payload must be ResourceCreateModel')
        actor_value, current = cls._actor(actor), cls._now(now)
        cls._validate_resource_ttls(payload)
        cls._validate_audience(payload.audience)
        allowed_claims = cls._validate_claims(payload.allowed_claims, 'allowed_claims')
        if await OAuthResourceDao.find_resource_duplicate(db, payload.resource_id, payload.audience):
            raise OAuthClientManagementError('resource_id or audience is already registered')
        client = await cls._resolve_introspection_client(db, payload.introspection_client_id)
        resource = SysOAuthResource(
            resource_id=payload.resource_id,
            create_by=actor_value,
            create_time=current,
            update_by=actor_value,
            update_time=current,
            introspection_client_pk=client.client_pk if client else None,
            status='0',
            **{**cls._resource_values(payload), 'allowed_claims': allowed_claims},
        )
        await OAuthResourceDao.add_resource(db, resource)
        await cls._record_audit(
            db,
            OidcAuditEvent.RESOURCE_POLICY_CHANGED,
            actor_value,
            resource_id=resource.resource_id,
            detail={'action': 'resource_created'},
        )
        return cls._resource_view(resource, payload.introspection_client_id)

    @classmethod
    async def _update_resource(
        cls,
        db: AsyncSession,
        payload: ResourceUpdateModel,
        *,
        actor: str,
        now: datetime | None = None,
    ) -> ResourceViewModel:
        """
        在事务中更新 Resource ORM 记录

        :param db: 异步数据库会话
        :param payload: Resource 更新参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ResourceViewModel 详情
        :raises OAuthClientManagementError: Resource 不存在、DTO 校验失败或关联 Client 不存在时抛出
        """
        if not isinstance(payload, ResourceUpdateModel):
            raise OAuthClientManagementError('payload must be ResourceUpdateModel')
        actor_value, current = cls._actor(actor), cls._now(now)
        cls._validate_resource_ttls(payload)
        cls._validate_audience(payload.audience)
        allowed_claims = cls._validate_claims(payload.allowed_claims, 'allowed_claims')
        resource = await OAuthResourceDao.get_resource(db, payload.resource_id, for_update=True)
        if resource is None:
            raise OAuthClientManagementError('resource not found')
        if resource.audience != payload.audience:
            raise OAuthClientManagementError('audience is immutable; create a new resource')
        client = await cls._resolve_introspection_client(db, payload.introspection_client_id)
        policy_changed = (
            resource.token_format != payload.token_format
            or resource.signing_alg != payload.signing_alg
            or resource.access_token_ttl_seconds != payload.access_token_ttl_seconds
            or set(resource.allowed_claims or ()) != set(allowed_claims)
            or resource.introspection_client_pk != (client.client_pk if client else None)
            or resource.status != payload.status
        )
        clients = await cls._lock_resource_clients(db, resource.resource_pk) if policy_changed else []
        resource.resource_name = payload.resource_name
        resource.token_format = payload.token_format
        resource.signing_alg = payload.signing_alg
        resource.access_token_ttl_seconds = payload.access_token_ttl_seconds
        resource.allowed_claims = allowed_claims
        resource.introspection_client_pk = client.client_pk if client else None
        resource.status = payload.status
        resource.remark = payload.remark
        resource.update_by, resource.update_time = actor_value, current
        if policy_changed:
            cls._bump_clients(clients, actor_value, current)
        await OAuthResourceDao.persist_resource_change(db, resource)
        if policy_changed:
            await cls._record_audit(
                db,
                OidcAuditEvent.RESOURCE_POLICY_CHANGED,
                actor_value,
                resource_id=resource.resource_id,
                detail={'action': 'resource_updated'},
            )
        return cls._resource_view(resource, payload.introspection_client_id)

    @classmethod
    async def detail_resource(cls, db: AsyncSession, resource_id: str) -> ResourceViewModel:
        """
        查询 OAuth Resource 详情

        :param db: 异步数据库会话
        :param resource_id: 资源标识
        :return: ResourceViewModel 详情
        :raises OAuthClientManagementError: Resource 不存在时抛出
        """
        resource = await OAuthResourceDao.get_resource(db, resource_id)
        if resource is None:
            raise OAuthClientManagementError('resource not found')
        view = cls._resource_view(resource)
        if resource.introspection_client_pk is None:
            return view
        client_id = await OAuthClientDao.id_for_pk(db, resource.introspection_client_pk)
        return view.model_copy(update={'introspection_client_id': client_id})

    @classmethod
    async def list_resources(
        cls, db: AsyncSession, query: ResourcePageQueryModel | None = None
    ) -> list[ResourceViewModel]:
        """
        分页查询 OAuth Resource

        :param db: 异步数据库会话
        :param query: Resource 分页查询参数
        :return: ResourceViewModel 列表
        """
        page = query or ResourcePageQueryModel()
        rows = await OAuthResourceDao.list_resources_page(db, page)
        return [await cls.detail_resource(db, row.resource_id) for row in rows]

    @classmethod
    async def count_resources(cls, db: AsyncSession, query: ResourcePageQueryModel | None = None) -> int:
        """
        统计 OAuth Resource 数量

        :param db: 异步数据库会话
        :param query: Resource 分页统计参数
        :return: Resource 数量
        """
        page = query or ResourcePageQueryModel()
        return await OAuthResourceDao.count_resources(db, page)

    @classmethod
    async def _change_resource_status(
        cls, db: AsyncSession, payload: ResourceStatusModel, *, actor: str, now: datetime | None = None
    ) -> ResourceViewModel:
        """
        在事务中变更 Resource 状态

        :param db: 异步数据库会话
        :param payload: Resource 状态变更参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ResourceViewModel 详情
        :raises OAuthClientManagementError: Resource 不存在或状态值不合法时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        resource = await OAuthResourceDao.get_resource(db, payload.resource_id, for_update=True)
        if resource is None:
            raise OAuthClientManagementError('resource not found')
        if resource.status != payload.status:
            clients = await cls._lock_resource_clients(db, resource.resource_pk)
            resource.status = payload.status
            resource.update_by, resource.update_time = actor_value, current
            cls._bump_clients(clients, actor_value, current)
            await OAuthResourceDao.persist_resource_change(db, resource)
            await cls._record_audit(
                db,
                OidcAuditEvent.RESOURCE_POLICY_CHANGED,
                actor_value,
                resource_id=resource.resource_id,
                detail={'action': 'resource_status_changed'},
            )
        return await cls.detail_resource(db, resource.resource_id)

    @classmethod
    async def _soft_disable_resource(
        cls, db: AsyncSession, resource_id: str, *, actor: str, now: datetime | None = None
    ) -> ResourceViewModel:
        """
        在事务中禁用 Resource 并失效关联授权

        :param db: 异步数据库会话
        :param resource_id: 资源标识
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ResourceViewModel 详情
        """
        return await cls._change_resource_status(
            db, ResourceStatusModel(resource_id=resource_id, status='1'), actor=actor, now=now
        )

    @classmethod
    async def _create_scope(
        cls, db: AsyncSession, payload: ScopeModel, *, actor: str, now: datetime | None = None
    ) -> ScopeModel:
        """
        在事务中创建 Scope ORM 记录

        :param db: 异步数据库会话
        :param payload: Scope 创建参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ScopeModel 详情
        :raises OAuthClientManagementError: Scope DTO 校验失败、编码重复或关联 Resource 不存在时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        claims = cls._validate_claims(payload.claims)
        if payload.scope_code == 'openid' and (
            payload.scope_type != 'identity'
            or payload.resource_id is not None
            or payload.status != '0'
            or claims != ['sub']
        ):
            raise OAuthClientManagementError('openid scope has a fixed identity policy')
        if await OAuthResourceDao.find_scope_duplicate(db, payload.scope_code):
            raise OAuthClientManagementError('scope_code is already registered')
        resource = None
        if payload.scope_type == 'resource':
            resource = await cls._get_active_resource(db, payload.resource_id)
        scope = SysOAuthScope(
            scope_code=payload.scope_code,
            scope_name=payload.scope_name,
            scope_type=payload.scope_type,
            resource_pk=resource.resource_pk if resource else None,
            claims=claims,
            consent_required=int(payload.consent_required),
            sensitive=int(payload.sensitive),
            status=payload.status,
            create_by=actor_value,
            create_time=current,
            update_by=actor_value,
            update_time=current,
            remark=payload.remark,
        )
        await OAuthResourceDao.add_scope(db, scope)
        await cls._record_audit(
            db, OidcAuditEvent.SCOPE_POLICY_CHANGED, actor_value, detail={'action': 'scope_created'}
        )
        return cls._scope_view(scope, resource.resource_id if resource else None)

    @classmethod
    async def _get_active_resource(cls, db: AsyncSession, resource_id: str | None) -> SysOAuthResource:
        """
        查询启用的 Resource ORM 记录

        :param db: 异步数据库会话
        :param resource_id: 资源标识
        :return: 启用的 Resource ORM 记录
        :raises OAuthClientManagementError: Resource 标识为空、未知或 Resource 未启用时抛出
        """
        if not resource_id:
            raise OAuthClientManagementError('resource scope requires an active resource')
        resource = await OAuthResourceDao.active_resource(db, resource_id)
        if resource is None:
            raise OAuthClientManagementError('scope resource does not exist or is inactive')
        return resource

    @classmethod
    async def _update_scope(
        cls, db: AsyncSession, payload: ScopeModel, *, actor: str, now: datetime | None = None
    ) -> ScopeModel:
        """
        在事务中更新 Scope ORM 记录

        :param db: 异步数据库会话
        :param payload: Scope 更新参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ScopeModel 详情
        :raises OAuthClientManagementError: Scope 不存在、DTO 校验失败或关联 Resource 不存在时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        claims = cls._validate_claims(payload.claims)
        scope = await OAuthResourceDao.get_scope(db, payload.scope_code, for_update=True)
        if scope is None:
            raise OAuthClientManagementError('scope not found')
        if scope.scope_code == 'openid' and (
            payload.scope_type != 'identity'
            or payload.resource_id is not None
            or payload.status != '0'
            or claims != ['sub']
        ):
            raise OAuthClientManagementError('openid scope cannot be disabled or moved')
        resource = None
        if payload.scope_type == 'resource':
            resource = await cls._get_active_resource(db, payload.resource_id)
        resource_pk = resource.resource_pk if resource else None
        policy_changed = (
            scope.scope_type != payload.scope_type
            or scope.resource_pk != resource_pk
            or set(scope.claims or ()) != set(claims)
            or bool(scope.consent_required) != payload.consent_required
            or bool(scope.sensitive) != payload.sensitive
            or scope.status != payload.status
        )
        clients = await cls._lock_scope_clients(db, scope.scope_pk) if policy_changed else []
        scope.scope_name = payload.scope_name
        scope.scope_type = payload.scope_type
        scope.resource_pk = resource_pk
        scope.claims = claims
        scope.consent_required = int(payload.consent_required)
        scope.sensitive = int(payload.sensitive)
        scope.status = payload.status
        scope.update_by, scope.update_time = actor_value, current
        scope.remark = payload.remark
        if policy_changed:
            cls._bump_clients(clients, actor_value, current)
        await OAuthResourceDao.persist_scope_change(db, scope)
        if policy_changed:
            await cls._record_audit(
                db, OidcAuditEvent.SCOPE_POLICY_CHANGED, actor_value, detail={'action': 'scope_updated'}
            )
        return cls._scope_view(scope, resource.resource_id if resource else None)

    @classmethod
    async def _lock_scope_clients(cls, db: AsyncSession, scope_pk: int) -> list[SysOAuthClient]:
        """
        锁定关联 Scope 的 Client 记录

        :param db: 异步数据库会话
        :param scope_pk: Scope 主键
        :return: 已锁定的 Client ORM 记录列表
        """
        return list(await OAuthResourceDao.lock_scope_clients(db, scope_pk))

    @classmethod
    async def detail_scope(cls, db: AsyncSession, scope_code: str) -> ScopeModel:
        """
        查询 OAuth Scope 详情

        :param db: 异步数据库会话
        :param scope_code: Scope 编码
        :return: ScopeModel 详情
        :raises OAuthClientManagementError: Scope 不存在时抛出
        """
        scope = await OAuthResourceDao.get_scope(db, scope_code)
        if scope is None:
            raise OAuthClientManagementError('scope not found')
        resource_id = None
        if scope.resource_pk is not None:
            resource_id = await OAuthResourceDao.resource_id_for_scope(db, scope.resource_pk)
        return cls._scope_view(scope, resource_id)

    @classmethod
    async def list_scopes(cls, db: AsyncSession, query: ScopePageQueryModel | None = None) -> list[ScopeModel]:
        """
        分页查询 OAuth Scope

        :param db: 异步数据库会话
        :param query: Scope 分页查询参数
        :return: ScopeModel 列表
        """
        page = query or ScopePageQueryModel()
        rows = await OAuthResourceDao.list_scopes_page(db, page)
        return [await cls.detail_scope(db, row.scope_code) for row in rows]

    @classmethod
    async def count_scopes(cls, db: AsyncSession, query: ScopePageQueryModel | None = None) -> int:
        """
        统计 OAuth Scope 数量

        :param db: 异步数据库会话
        :param query: Scope 分页统计参数
        :return: Scope 数量
        """
        page = query or ScopePageQueryModel()
        return await OAuthResourceDao.count_scopes(db, page)

    @classmethod
    async def _change_scope_status(
        cls, db: AsyncSession, payload: ScopeStatusModel, *, actor: str, now: datetime | None = None
    ) -> ScopeModel:
        """
        在事务中变更 Scope 状态

        :param db: 异步数据库会话
        :param payload: Scope 状态变更参数
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ScopeModel 详情
        :raises OAuthClientManagementError: Scope 不存在或状态值不合法时抛出
        """
        actor_value, current = cls._actor(actor), cls._now(now)
        scope = await OAuthResourceDao.get_scope(db, payload.scope_code, for_update=True)
        if scope is None:
            raise OAuthClientManagementError('scope not found')
        if scope.scope_code == 'openid' and payload.status != '0':
            raise OAuthClientManagementError('openid scope cannot be disabled')
        if scope.status != payload.status:
            clients = await cls._lock_scope_clients(db, scope.scope_pk)
            scope.status = payload.status
            scope.update_by, scope.update_time = actor_value, current
            cls._bump_clients(clients, actor_value, current)
            await OAuthResourceDao.persist_scope_change(db, scope)
            await cls._record_audit(
                db, OidcAuditEvent.SCOPE_POLICY_CHANGED, actor_value, detail={'action': 'scope_status_changed'}
            )
        return await cls.detail_scope(db, scope.scope_code)

    @classmethod
    async def _soft_disable_scope(
        cls, db: AsyncSession, scope_code: str, *, actor: str, now: datetime | None = None
    ) -> ScopeModel:
        """
        在事务中禁用 Scope 并失效关联授权

        :param db: 异步数据库会话
        :param scope_code: Scope 编码
        :param actor: 操作人标识
        :param now: 当前时间
        :return: ScopeModel 详情
        """
        return await cls._change_scope_status(
            db, ScopeStatusModel(scope_code=scope_code, status='1'), actor=actor, now=now
        )

    @classmethod
    async def collect_resource_invalidation_targets(
        cls, db: AsyncSession, resource_id: str
    ) -> ResourceInvalidationTargets:
        """
        收集 Resource 变更后需撤销的授权记录

        :param db: 异步数据库会话
        :param resource_id: 资源标识
        :return: Resource 失效目标集合
        :raises OAuthClientManagementError: Resource 不存在时抛出
        """
        resource = await OAuthResourceDao.get_resource(db, resource_id)
        if resource is None:
            raise OAuthClientManagementError('resource not found')
        client_rows = [
            *await OAuthResourceDao.client_ids_for_resource(db, resource.resource_pk),
            *await OAuthResourceDao.client_ids_for_resource_scope(db, resource.resource_pk),
        ]
        client_pks = {row[0] for row in client_rows}
        client_ids = tuple(sorted({row[1] for row in client_rows}))
        if not client_pks:
            return ResourceInvalidationTargets(resource.resource_id, (), (), ())
        grants = await OAuthResourceDao.active_grants(db, list(client_pks))
        grant_ids = tuple(
            grant.grant_id
            for grant in grants
            if resource.resource_id in (grant.granted_resources or [])
            or resource.audience in (grant.granted_resources or [])
        )
        refresh_tokens = await OAuthResourceDao.active_refresh_tokens(db, list(client_pks))
        refresh_ids = tuple(
            token.token_id
            for token in refresh_tokens
            if resource.resource_id in (token.resources or []) or resource.audience in (token.resources or [])
        )
        return ResourceInvalidationTargets(resource.resource_id, client_ids, grant_ids, refresh_ids)
