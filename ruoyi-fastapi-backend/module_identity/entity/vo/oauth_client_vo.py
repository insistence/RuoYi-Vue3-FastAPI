from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

_DEVELOPMENT_HTTP_HOSTS = {'localhost', '127.0.0.1', '::1'}


def _validate_registered_uri(uri_type: str, value: str) -> str:
    """
    校验注册 URI。
    """

    if '*' in value:
        raise ValueError('URI must not contain wildcard')
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('URI must use HTTP or HTTPS and contain a host')
    if parsed.username is not None or parsed.password is not None:
        raise ValueError('URI must not contain userinfo')
    if parsed.fragment:
        raise ValueError('URI must not contain fragment')
    if uri_type == 'backchannel_logout' and parsed.query:
        raise ValueError('backchannel_logout URI must not contain query')
    try:
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise ValueError('URI host or port is invalid') from exc
    if not hostname:
        raise ValueError('URI must contain a host')
    if parsed.scheme == 'http' and hostname.lower() not in _DEVELOPMENT_HTTP_HOSTS:
        raise ValueError('HTTP URI is only allowed for localhost development')
    if uri_type == 'cors_origin' and (parsed.path or parsed.query):
        raise ValueError('cors_origin must contain only scheme, host and optional port')
    return value


class ClientModel(BaseModel):
    """
    OAuth Client 管理模型基类。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


class ClientCreateModel(ClientModel):
    """
    创建 OAuth Client 请求。
    """

    client_name: str = Field(min_length=1, max_length=100)
    client_type: Literal['public', 'confidential']
    token_endpoint_auth_method: Literal['none', 'client_secret_basic']
    grant_types: list[str] = Field(default_factory=lambda: ['authorization_code'])
    response_types: list[Literal['code']] = Field(default_factory=lambda: ['code'])
    require_pkce: bool = True
    require_consent: bool = True
    trusted_client: bool = False
    scope_codes: list[str] = Field(default_factory=list)
    pre_authorized_scope_codes: list[str] = Field(default_factory=list)
    resource_ids: list[str] = Field(default_factory=list)
    redirect_uris: list[str] = Field(default_factory=list)
    post_logout_redirect_uris: list[str] = Field(default_factory=list)
    backchannel_logout_uris: list[str] = Field(default_factory=list)
    cors_origins: list[str] = Field(default_factory=list)
    access_token_ttl_seconds: int | None = Field(default=None, gt=0)
    refresh_token_idle_seconds: int | None = Field(default=None, gt=0)
    refresh_token_absolute_seconds: int | None = Field(default=None, gt=0)
    logo_uri: str | None = None
    policy_uri: str | None = None
    tos_uri: str | None = None
    remark: str | None = Field(default=None, max_length=500)

    @model_validator(mode='before')
    @classmethod
    def default_non_code_response_types(cls, value: Any) -> Any:
        """为不含 authorization_code 的 Client 默认空 response_types。

        :param value: 管理端提交的原始字段映射。
        :return: 应用默认值后的原始字段映射。
        """
        if isinstance(value, dict) and 'response_types' not in value and 'responseTypes' not in value:
            grant_key = 'grant_types' if 'grant_types' in value else 'grantTypes'
            response_key = 'response_types' if 'grant_types' in value else 'responseTypes'
            grants = value.get(grant_key, ['authorization_code'])
            if isinstance(grants, list) and 'authorization_code' not in grants:
                value = {**value, response_key: []}
        return value

    @model_validator(mode='after')
    def validate_auth_policy(self) -> 'ClientCreateModel':  # noqa: PLR0912
        """
        校验 Client Authentication、Grant、PKCE 与 URI 注册策略。

        :return: 当前已校验 Client 创建模型
        :raises ValueError: 策略、Grant 或注册 URI 不符合规范
        """

        expected = 'none' if self.client_type == 'public' else 'client_secret_basic'
        if self.token_endpoint_auth_method != expected:
            raise ValueError('token endpoint authentication method does not match client type')
        if self.client_type == 'public' and not self.require_pkce:
            raise ValueError('public clients must require PKCE')
        allowed_grants = {'authorization_code', 'refresh_token', 'client_credentials'}
        if not self.grant_types or any(grant not in allowed_grants for grant in self.grant_types):
            raise ValueError('grant_types contains an unsupported grant')
        if len(set(self.grant_types)) != len(self.grant_types):
            raise ValueError('grant_types must not contain duplicates')
        if 'refresh_token' in self.grant_types and 'authorization_code' not in self.grant_types:
            raise ValueError('refresh_token requires authorization_code')
        if self.client_type == 'public' and 'client_credentials' in self.grant_types:
            raise ValueError('public clients cannot use client_credentials')
        if 'authorization_code' in self.grant_types and not self.require_pkce:
            raise ValueError('authorization_code clients must require PKCE')
        if 'authorization_code' in self.grant_types:
            if self.response_types != ['code']:
                raise ValueError('authorization_code clients require response_types [code]')
            if not self.redirect_uris:
                raise ValueError('authorization_code clients require a redirect URI')
        elif self.response_types:
            raise ValueError('non-authorization-code clients must not declare response types')
        for uri_type, uris in (
            ('redirect', self.redirect_uris),
            ('post_logout', self.post_logout_redirect_uris),
            ('backchannel_logout', self.backchannel_logout_uris),
            ('cors_origin', self.cors_origins),
        ):
            for uri in uris:
                _validate_registered_uri(uri_type, uri)
        return self


class ClientUpdateModel(ClientCreateModel):
    """
    更新 OAuth Client 的管理请求。

    更新请求必须携带外部 client_id。
    """

    client_id: str = Field(min_length=1, max_length=64)


class ClientViewModel(ClientCreateModel):
    """
    OAuth Client 安全字段脱敏后的详情模型。

    模型不包含任何明文或哈希 Client Secret。
    """

    client_id: str
    status: Literal['0', '1'] = '0'
    policy_version: int = 1
    create_time: datetime | None = None
    update_time: datetime | None = None


class ClientSecretResponseModel(ClientModel):
    """
    Client Secret 一次性展示响应。

    调用方必须在本次响应后立即安全保存明文 Secret。
    """

    client_id: str
    secret_id: str
    client_secret: str
    secret_hint: str
    not_before: datetime
    expires_at: datetime | None = None


class SecretRotationModel(ClientModel):
    """
    Client Secret 轮换的时间策略。
    """

    not_before: datetime | None = None
    expires_at: datetime | None = None
    retirement_seconds: int | None = Field(default=None, gt=0)


class ClientUriModel(ClientModel):
    """
    单个注册 URI 的管理模型。

    URI 在 DTO 边界执行精确匹配所需的安全校验。
    """

    uri_type: Literal['redirect', 'post_logout', 'backchannel_logout', 'cors_origin']
    uri: str = Field(min_length=1, max_length=1000)
    is_default: bool = False
    status: Literal['0', '1'] = '0'

    @staticmethod
    def _validate_uri_value(uri_type: str, value: str) -> str:
        """复用 Client 注册 URI 的统一安全校验。

        :param uri_type: URI 类型
        :param value: 待校验 URI
        :return: 原样返回已验证 URI
        """

        return _validate_registered_uri(uri_type, value)

    @model_validator(mode='after')
    def validate_uri(self) -> 'ClientUriModel':
        """
        校验并规范化单个注册 URI。

        :return: 当前已校验 URI 模型
        """

        self.uri = self._validate_uri_value(self.uri_type, self.uri)
        return self


class ClientPageQueryModel(ClientModel):
    """
    Client 分页查询参数。

    page_num 与 page_size 使用管理端统一分页约束。
    """

    client_name: str | None = None
    client_type: Literal['public', 'confidential'] | None = None
    status: Literal['0', '1'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)


class ClientStatusModel(ClientModel):
    """
    Client 启停状态变更请求。

    status 只允许项目约定的 0（正常）或 1（停用）。
    """

    client_id: str
    status: Literal['0', '1']
