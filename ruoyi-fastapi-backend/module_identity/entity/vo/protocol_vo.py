from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, field_validator, model_validator

from utils.oidc_util import OidcUtil


class ProtocolModel(BaseModel):
    """
    标准协议模型基类

    标准端点字段保持 snake_case，并拒绝未定义参数。
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True, str_strip_whitespace=True)


class AuthorizeRequest(ProtocolModel):
    """
    Authorization Endpoint 请求参数

    OIDC 请求必须携带 nonce，并固定使用 PKCE S256。
    """

    response_type: str = Field(min_length=1, max_length=100, description='授权响应类型')
    response_mode: Literal['query'] = Field(default='query', description='授权响应参数传递方式')
    client_id: str = Field(min_length=1, max_length=64, description='客户端标识')
    redirect_uri: str = Field(min_length=1, max_length=1000, description='已注册的授权回调地址')
    scope: str = Field(min_length=1, max_length=2000, description='空格分隔的权限范围')
    resource: str | None = Field(default=None, min_length=1, max_length=500, description='请求访问的资源受众')
    state: str | None = Field(default=None, max_length=1024, description='客户端用于关联请求和响应的状态值')
    nonce: str | None = Field(default=None, max_length=1024, description='绑定认证请求与ID Token的随机数')
    code_challenge: str = Field(min_length=43, max_length=128, description='PKCE校验挑战值')
    code_challenge_method: str = Field(min_length=1, max_length=20, description='PKCE挑战方法')
    prompt: str | None = Field(default=None, max_length=100, description='空格分隔的认证交互要求')
    max_age: NonNegativeInt | None = Field(default=None, description='允许的最长认证间隔，单位为秒')
    login_hint: str | None = Field(default=None, max_length=512, description='客户端提供的登录账号提示')

    @field_validator('code_challenge')
    @classmethod
    def validate_code_challenge(cls, value: str) -> str:
        """
        校验未填充的 base64url SHA-256 challenge

        :param value: 客户端提交的 code_challenge
        :return: 已校验 challenge
        """

        if not OidcUtil.is_s256_challenge(value):
            raise ValueError('code_challenge 必须为不带填充的 Base64URL 编码 SHA-256 摘要')
        return value

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, value: str | None) -> str | None:
        """
        只接受规范支持的 prompt 值，且 none 不能和其他值混用

        :param value: 空格分隔的 prompt 列表
        :return: 规范化后的 prompt 或 None
        """

        return OidcUtil.normalize_prompt(value)

    @model_validator(mode='after')
    def validate_oidc_nonce(self) -> 'AuthorizeRequest':
        """
        校验 OIDC 授权请求必须绑定 nonce

        :return: 当前已校验请求
        """

        if 'openid' in self.scope.split() and not self.nonce:
            raise ValueError('申请 openid 权限时必须提供 nonce')
        return self


class TokenRequest(ProtocolModel):
    """
    Token Endpoint 表单参数

    不同 grant_type 只允许携带其对应凭据。
    """

    grant_type: str = Field(min_length=1, max_length=50, description='授权类型')
    code: str | None = Field(default=None, min_length=1, max_length=4096, description='授权码')
    redirect_uri: str | None = Field(default=None, min_length=1, max_length=1000, description='已注册的授权回调地址')
    client_id: str | None = Field(default=None, min_length=1, max_length=64, description='客户端标识')
    code_verifier: str | None = Field(default=None, min_length=43, max_length=128, description='PKCE校验原文')
    refresh_token: str | None = Field(default=None, min_length=1, max_length=4096, description='刷新令牌')
    scope: str | None = Field(default=None, min_length=1, max_length=2000, description='空格分隔的权限范围')
    resource: str | None = Field(default=None, min_length=1, max_length=1000, description='请求访问的资源受众')

    @model_validator(mode='after')
    def check_grant_fields(self) -> 'TokenRequest':
        """
        拒绝与 grant type 不相符的凭据，避免跨流程混用

        :return: 当前已校验请求
        """

        if self.grant_type == 'authorization_code':
            if not self.code or not self.code_verifier or not self.redirect_uri:
                raise ValueError('授权码兑换必须提供 code、redirect_uri 和 code_verifier')
            if self.refresh_token or self.scope is not None or self.resource is not None:
                raise ValueError('授权码兑换请求包含不适用的字段')
        elif self.grant_type == 'refresh_token':
            if not self.refresh_token:
                raise ValueError('刷新令牌请求必须提供 refresh_token')
            if self.code or self.code_verifier or self.redirect_uri:
                raise ValueError('刷新令牌请求包含不适用的字段')
        elif self.grant_type == 'client_credentials' and any(
            (self.code, self.code_verifier, self.refresh_token, self.redirect_uri)
        ):
            raise ValueError('客户端凭据授权请求包含不适用的字段')
        return self


class TokenResponse(ProtocolModel):
    """
    Token Endpoint 成功响应

    字段直接对应 OAuth 2.0 标准 JSON 响应。
    """

    access_token: str = Field(description='访问令牌')
    token_type: Literal['Bearer'] = Field(default='Bearer', description='令牌类型')
    expires_in: NonNegativeInt = Field(description='剩余有效时间，单位为秒')
    refresh_token: str | None = Field(default=None, description='刷新令牌')
    scope: str | None = Field(default=None, description='空格分隔的权限范围')
    id_token: str | None = Field(default=None, description='身份令牌')


class ErrorResponse(ProtocolModel):
    """
    OAuth/OIDC 标准错误响应

    不包含项目业务响应包装字段。
    """

    error: str = Field(description='标准协议错误代码')
    error_description: str | None = Field(default=None, description='标准协议错误说明')
    error_uri: str | None = Field(default=None, description='错误说明页面地址')

    def as_dict(self) -> dict[str, str]:
        """
        返回可直接作为标准 JSON 响应的非空字段

        :return: 排除 None 字段的标准错误字典
        """

        return self.model_dump(exclude_none=True)


class Jwk(ProtocolModel):
    """
    公开 RSA JWK

    模型严格拒绝 d、p、q 等私钥参数。
    """

    kty: Literal['RSA'] = Field(default='RSA', description='公钥类型')
    use: Literal['sig'] = Field(default='sig', description='公钥用途')
    kid: str = Field(min_length=1, max_length=100, description='签名密钥标识')
    alg: Literal['RS256'] = Field(default='RS256', description='签名算法')
    n: str = Field(min_length=1, description='RSA公钥模数的Base64URL编码')
    e: str = Field(min_length=1, description='RSA公钥指数的Base64URL编码')


class JwksResponse(ProtocolModel):
    """
    JWKS 响应

    keys 仅包含公开签名 JWK。
    """

    keys: list[Jwk] = Field(description='公开签名密钥列表')


class DiscoveryResponse(ProtocolModel):
    """
    OIDC Discovery 响应

    元数据只宣称当前实现确实支持的端点和算法。
    """

    issuer: str = Field(description='认证中心签发方地址')
    authorization_endpoint: str = Field(description='授权端点地址')
    token_endpoint: str = Field(description='令牌端点地址')
    userinfo_endpoint: str = Field(description='用户信息端点地址')
    jwks_uri: str = Field(description='公开签名密钥集地址')
    revocation_endpoint: str = Field(description='令牌撤销端点地址')
    introspection_endpoint: str = Field(description='令牌内省端点地址')
    end_session_endpoint: str = Field(description='退出端点地址')
    scopes_supported: list[str] = Field(default_factory=list, description='支持的权限列表')
    response_types_supported: list[Literal['code']] = Field(
        default_factory=lambda: ['code'], description='支持的授权响应类型列表'
    )
    response_modes_supported: list[Literal['query']] = Field(
        default_factory=lambda: ['query'], description='支持的授权响应模式列表'
    )
    grant_types_supported: list[str] = Field(
        default_factory=lambda: ['authorization_code', 'refresh_token'], description='支持的授权类型列表'
    )
    subject_types_supported: list[Literal['public']] = Field(
        default_factory=lambda: ['public'], description='支持的主体标识类型列表'
    )
    id_token_signing_alg_values_supported: list[Literal['RS256']] = Field(
        default_factory=lambda: ['RS256'], description='支持的ID Token签名算法列表'
    )
    token_endpoint_auth_methods_supported: list[Literal['none', 'client_secret_basic']] = Field(
        default_factory=lambda: ['none', 'client_secret_basic'], description='支持的令牌端点认证方式列表'
    )
    code_challenge_methods_supported: list[Literal['S256']] = Field(
        default_factory=lambda: ['S256'], description='支持的PKCE挑战方法列表'
    )
    claims_supported: list[str] = Field(default_factory=list, description='支持的声明字段列表')
    authorization_response_iss_parameter_supported: bool = Field(
        default=True, description='是否支持在授权响应中返回签发方'
    )
    backchannel_logout_supported: bool = Field(default=False, description='是否支持后端退出通知')
    backchannel_logout_session_supported: bool = Field(default=False, description='后端退出通知是否支持会话标识')


class OAuthServerMetadata(ProtocolModel):
    """
    RFC 8414 OAuth Authorization Server Metadata 子集

    不继承要求 OIDC 专属 userinfo_endpoint 和 end_session_endpoint 的模型。
    """

    issuer: str = Field(description='认证中心签发方地址')
    authorization_endpoint: str = Field(description='授权端点地址')
    token_endpoint: str = Field(description='令牌端点地址')
    jwks_uri: str = Field(description='公开签名密钥集地址')
    revocation_endpoint: str | None = Field(default=None, description='令牌撤销端点地址')
    introspection_endpoint: str | None = Field(default=None, description='令牌内省端点地址')
    scopes_supported: list[str] = Field(default_factory=list, description='支持的权限列表')
    response_types_supported: list[Literal['code']] = Field(
        default_factory=lambda: ['code'], description='支持的授权响应类型列表'
    )
    grant_types_supported: list[str] = Field(
        default_factory=lambda: ['authorization_code', 'refresh_token'], description='支持的授权类型列表'
    )
    token_endpoint_auth_methods_supported: list[Literal['none', 'client_secret_basic']] = Field(
        default_factory=lambda: ['none', 'client_secret_basic'], description='支持的令牌端点认证方式列表'
    )
    code_challenge_methods_supported: list[Literal['S256']] = Field(
        default_factory=lambda: ['S256'], description='支持的PKCE挑战方法列表'
    )


class UserInfoResponse(ProtocolModel):
    """
    UserInfo 基础响应

    允许的扩展字段对应已授权的标准身份声明。
    """

    sub: str = Field(description='用户稳定主体标识')
    name: str | None = Field(default=None, description='显示名称')
    preferred_username: str | None = Field(default=None, description='用户首选账号名称')
    picture: str | None = Field(default=None, description='用户头像地址')
    updated_at: int | None = Field(default=None, description='用户资料更新时间，Unix时间戳，单位为秒')
    email: str | None = Field(default=None, description='电子邮箱')
    email_verified: bool | None = Field(default=None, description='电子邮箱是否已验证')
    phone_number: str | None = Field(default=None, description='手机号码')
    phone_number_verified: bool | None = Field(default=None, description='手机号码是否已验证')
    dept_id: str | int | None = Field(default=None, description='部门ID')
    dept_name: str | None = Field(default=None, description='部门名称')
    roles: list[str] | None = Field(default=None, description='当前授权允许发布的角色权限字符列表')


class RevocationRequest(ProtocolModel):
    """
    Token Revocation 请求

    token_type_hint 只用于减少服务端查找歧义，不作为安全依据。
    """

    token: str = Field(min_length=1, description='待撤销或内省的令牌')
    token_type_hint: Literal['access_token', 'refresh_token'] | None = Field(default=None, description='令牌类型提示')


class IntrospectionRequest(ProtocolModel):
    """
    Token Introspection 请求

    请求方权限和 audience 绑定由服务层继续校验。
    """

    token: str = Field(min_length=1, description='待撤销或内省的令牌')
    token_type_hint: Literal['access_token', 'refresh_token'] | None = Field(default=None, description='令牌类型提示')


class IntrospectionResponse(ProtocolModel):
    """
    Token Introspection 响应

    inactive Token 只应返回 active=false。
    """

    active: bool = Field(description='令牌是否有效')
    scope: str | None = Field(default=None, description='空格分隔的权限范围')
    client_id: str | None = Field(default=None, description='客户端标识')
    username: str | None = Field(default=None, description='用户账号')
    token_type: str | None = Field(default=None, description='令牌类型')
    exp: int | None = Field(default=None, description='过期时间，Unix时间戳，单位为秒')
    iat: int | None = Field(default=None, description='签发时间，Unix时间戳，单位为秒')
    nbf: int | None = Field(default=None, description='最早生效时间，Unix时间戳，单位为秒')
    sub: str | None = Field(default=None, description='用户稳定主体标识')
    aud: str | list[str] | None = Field(default=None, description='令牌接收方')
    iss: str | None = Field(default=None, description='令牌签发方')
    jti: str | None = Field(default=None, description='令牌唯一标识')
    sid: str | None = Field(default=None, description='SSO会话标识')


class LogoutRequest(ProtocolModel):
    """
    RP-Initiated Logout 请求

    post_logout_redirect_uri 必须由服务端按 Client 注册值精确匹配。
    """

    id_token_hint: str | None = Field(default=None, description='用于关联退出会话的ID Token提示')
    logout_hint: str | None = Field(default=None, description='退出会话提示')
    client_id: str | None = Field(default=None, description='客户端标识')
    post_logout_redirect_uri: str | None = Field(default=None, description='已注册的退出回调地址')
    state: str | None = Field(default=None, description='客户端用于关联请求和响应的状态值')
