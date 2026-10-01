from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from common.types import ApiUtcDateTime
from utils.oidc_util import OidcUtil

_MAX_ROLE_KEY_LENGTH = 100


class ClientModel(BaseModel):
    """
    OAuth Client 管理模型基类
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


class ClientCreateModel(ClientModel):
    """
    创建 OAuth Client 请求
    """

    client_name: str = Field(min_length=1, max_length=100, description='客户端名称')
    client_type: Literal['public', 'confidential'] = Field(
        description='客户端类型（public公开客户端 confidential机密客户端）'
    )
    token_endpoint_auth_method: Literal['none', 'client_secret_basic'] = Field(description='令牌端点的客户端认证方式')
    grant_types: list[str] = Field(default_factory=lambda: ['authorization_code'], description='允许使用的授权类型')
    response_types: list[Literal['code']] = Field(
        default_factory=lambda: ['code'], description='允许使用的授权响应类型'
    )
    require_pkce: bool = Field(default=True, description='是否强制使用PKCE')
    require_consent: bool = Field(default=True, description='是否要求用户确认授权')
    trusted_client: bool = Field(default=False, description='是否为受信任客户端')
    scope_codes: list[str] = Field(default_factory=list, description='客户端允许申请的权限标识列表')
    allowed_role_keys: list[str] = Field(
        default_factory=list, max_length=100, description='允许向客户端发布的角色权限字符，空列表表示不发布角色'
    )
    pre_authorized_scope_codes: list[str] = Field(default_factory=list, description='预先授权的权限标识列表')
    resource_ids: list[str] = Field(default_factory=list, description='允许访问的资源标识列表')
    redirect_uris: list[str] = Field(default_factory=list, description='授权完成后允许跳转的回调地址列表')
    post_logout_redirect_uris: list[str] = Field(default_factory=list, description='退出完成后允许跳转的回调地址列表')
    backchannel_logout_uris: list[str] = Field(default_factory=list, description='后端退出通知地址列表')
    cors_origins: list[str] = Field(default_factory=list, description='允许跨域访问的源地址列表')
    access_token_ttl_seconds: int | None = Field(default=None, gt=0, description='访问令牌有效期，单位为秒')
    refresh_token_idle_seconds: int | None = Field(default=None, gt=0, description='刷新令牌闲置有效期，单位为秒')
    refresh_token_absolute_seconds: int | None = Field(default=None, gt=0, description='刷新令牌绝对有效期，单位为秒')
    logo_uri: str | None = Field(default=None, description='客户端图标地址')
    policy_uri: str | None = Field(default=None, description='隐私政策地址')
    tos_uri: str | None = Field(default=None, description='服务条款地址')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @model_validator(mode='before')
    @classmethod
    def default_non_code_response_types(cls, value: Any) -> Any:
        """
        为不含 authorization_code 的 Client 默认空 response_types

        :param value: 管理端提交的原始字段映射
        :return: 应用默认值后的原始字段映射
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
        校验 Client Authentication、Grant、PKCE 与 URI 注册策略

        :return: 当前已校验 Client 创建模型
        :raises ValueError: 策略、Grant 或注册 URI 不符合规范
        """

        if len(set(self.allowed_role_keys)) != len(self.allowed_role_keys) or any(
            not role or len(role) > _MAX_ROLE_KEY_LENGTH or '*' in role or any(char.isspace() for char in role)
            for role in self.allowed_role_keys
        ):
            raise ValueError('允许发布的角色标识不得重复，也不得包含通配符或空白字符')
        expected = 'none' if self.client_type == 'public' else 'client_secret_basic'
        if self.token_endpoint_auth_method != expected:
            raise ValueError('令牌端点认证方式与客户端类型不匹配')
        if self.client_type == 'public' and not self.require_pkce:
            raise ValueError('公开客户端必须启用 PKCE')
        allowed_grants = {'authorization_code', 'refresh_token', 'client_credentials'}
        if not self.grant_types or any(grant not in allowed_grants for grant in self.grant_types):
            raise ValueError('grant_types 包含不支持的授权类型')
        if len(set(self.grant_types)) != len(self.grant_types):
            raise ValueError('grant_types 不得包含重复的授权类型')
        if 'refresh_token' in self.grant_types and 'authorization_code' not in self.grant_types:
            raise ValueError('启用刷新令牌必须同时启用授权码模式')
        if self.client_type == 'public' and 'client_credentials' in self.grant_types:
            raise ValueError('公开客户端不能使用 client_credentials 授权模式')
        if 'authorization_code' in self.grant_types and not self.require_pkce:
            raise ValueError('授权码客户端必须启用 PKCE')
        if 'authorization_code' in self.grant_types:
            if self.response_types != ['code']:
                raise ValueError('授权码客户端的 response_types 必须为 [code]')
            if not self.redirect_uris:
                raise ValueError('授权码客户端必须配置登录回调地址')
        elif self.response_types:
            raise ValueError('未启用授权码模式的客户端不得配置响应类型')
        for uri_type, uris in (
            ('redirect', self.redirect_uris),
            ('post_logout', self.post_logout_redirect_uris),
            ('backchannel_logout', self.backchannel_logout_uris),
            ('cors_origin', self.cors_origins),
        ):
            for uri in uris:
                OidcUtil.validate_registered_uri(uri_type, uri)
        return self


class ClientUpdateModel(ClientCreateModel):
    """
    更新 OAuth Client 的管理请求

    更新请求必须携带外部 client_id。
    """

    client_id: str = Field(min_length=1, max_length=64, description='客户端标识')


class ClientViewModel(ClientCreateModel):
    """
    OAuth Client 安全字段脱敏后的详情模型

    模型不包含任何明文或哈希 Client Secret。
    """

    client_id: str = Field(description='客户端标识')
    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')
    policy_version: int = Field(default=1, description='客户端策略版本')
    create_time: ApiUtcDateTime | None = Field(default=None, description='创建时间')
    update_time: ApiUtcDateTime | None = Field(default=None, description='更新时间')


class ClientSecretResponseModel(ClientModel):
    """
    Client Secret 一次性展示响应

    调用方必须在本次响应后立即安全保存明文 Secret。
    """

    client_id: str = Field(description='客户端标识')
    secret_id: str = Field(description='客户端密钥标识')
    client_secret: str = Field(description='仅在创建或轮换时返回的客户端密钥明文')
    secret_hint: str = Field(description='客户端密钥展示提示')
    not_before: ApiUtcDateTime = Field(description='密钥生效时间')
    expires_at: ApiUtcDateTime | None = Field(default=None, description='过期时间')


class SecretRotationModel(ClientModel):
    """
    Client Secret 轮换的时间策略
    """

    not_before: ApiUtcDateTime | None = Field(default=None, description='密钥生效时间')
    expires_at: ApiUtcDateTime | None = Field(default=None, description='过期时间')
    retirement_seconds: int | None = Field(default=None, gt=0, description='旧客户端密钥的过渡期，单位为秒')


class ClientUriModel(ClientModel):
    """
    单个注册 URI 的管理模型

    URI 在 DTO 边界执行精确匹配所需的安全校验。
    """

    uri_type: Literal['redirect', 'post_logout', 'backchannel_logout', 'cors_origin'] = Field(
        description='注册地址类型'
    )
    uri: str = Field(min_length=1, max_length=1000, description='完整注册地址')
    is_default: bool = Field(default=False, description='是否为默认地址')
    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')

    @model_validator(mode='after')
    def validate_uri(self) -> 'ClientUriModel':
        """
        校验并规范化单个注册 URI

        :return: 当前已校验 URI 模型
        """

        self.uri = OidcUtil.validate_registered_uri(self.uri_type, self.uri)

        return self


class ClientPageQueryModel(ClientModel):
    """
    Client 分页查询参数

    page_num 与 page_size 使用管理端统一分页约束。
    """

    client_name: str | None = Field(default=None, description='客户端名称')
    client_type: Literal['public', 'confidential'] | None = Field(
        default=None, description='客户端类型（public公开客户端 confidential机密客户端）'
    )
    status: Literal['0', '1'] | None = Field(default=None, description='状态（0正常 1停用）')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=200, description='每页记录数')


class ClientStatusModel(ClientModel):
    """
    Client 启停状态变更请求

    status 只允许项目约定的 0（正常）或 1（停用）。
    """

    client_id: str = Field(description='客户端标识')
    status: Literal['0', '1'] = Field(description='状态（0正常 1停用）')
