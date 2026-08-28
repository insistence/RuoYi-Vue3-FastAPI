import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, field_validator, model_validator


class ProtocolModel(BaseModel):
    """
    标准协议模型基类。

    标准端点字段保持 snake_case，并拒绝未定义参数。
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True, str_strip_whitespace=True)


class AuthorizeRequest(ProtocolModel):
    """
    Authorization Endpoint 请求参数。

    OIDC 请求必须携带 nonce，并固定使用 PKCE S256。
    """

    response_type: str = Field(min_length=1, max_length=100)
    client_id: str = Field(min_length=1, max_length=64)
    redirect_uri: str = Field(min_length=1, max_length=1000)
    scope: str = Field(min_length=1, max_length=2000)
    resource: str | None = Field(default=None, min_length=1, max_length=500)
    state: str | None = Field(default=None, max_length=1024)
    nonce: str | None = Field(default=None, max_length=1024)
    code_challenge: str = Field(min_length=43, max_length=128)
    code_challenge_method: str = Field(min_length=1, max_length=20)
    prompt: str | None = Field(default=None, max_length=100)
    max_age: NonNegativeInt | None = None
    login_hint: str | None = Field(default=None, max_length=512)

    @field_validator('code_challenge')
    @classmethod
    def validate_code_challenge(cls, value: str) -> str:
        """
        校验未填充的 base64url SHA-256 challenge。

        :param value: 客户端提交的 code_challenge
        :return: 已校验 challenge
        """

        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', value):
            raise ValueError('code_challenge must be an unpadded base64url SHA-256 value')
        return value

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, value: str | None) -> str | None:
        """
        只接受规范支持的 prompt 值，且 none 不能和其他值混用。

        :param value: 空格分隔的 prompt 列表
        :return: 规范化后的 prompt 或 None
        """

        if value is None:
            return value
        prompts = value.split()
        allowed = {'login', 'consent', 'none'}
        if not prompts or any(item not in allowed for item in prompts) or len(set(prompts)) != len(prompts):
            raise ValueError('prompt must contain only supported values; none cannot be combined')
        if 'none' in prompts and len(prompts) != 1:
            raise ValueError('prompt must contain only supported values; none cannot be combined')
        return ' '.join(prompts)

    @model_validator(mode='after')
    def validate_oidc_nonce(self) -> 'AuthorizeRequest':
        """
        校验 OIDC 授权请求必须绑定 nonce。

        :return: 当前已校验请求
        """

        if 'openid' in self.scope.split() and not self.nonce:
            raise ValueError('nonce is required when openid scope is requested')
        return self


class TokenRequest(ProtocolModel):
    """
    Token Endpoint 表单参数。

    不同 grant_type 只允许携带其对应凭据。
    """

    grant_type: str = Field(min_length=1, max_length=50)
    code: str | None = Field(default=None, min_length=1, max_length=4096)
    redirect_uri: str | None = Field(default=None, min_length=1, max_length=1000)
    client_id: str | None = Field(default=None, min_length=1, max_length=64)
    code_verifier: str | None = Field(default=None, min_length=43, max_length=128)
    refresh_token: str | None = Field(default=None, min_length=1, max_length=4096)
    scope: str | None = Field(default=None, min_length=1, max_length=2000)
    resource: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode='after')
    def check_grant_fields(self) -> 'TokenRequest':
        """
        拒绝与 grant type 不相符的凭据，避免跨流程混用。

        :return: 当前已校验请求
        """

        if self.grant_type == 'authorization_code':
            if not self.code or not self.code_verifier or not self.redirect_uri:
                raise ValueError('authorization_code requires code, redirect_uri and code_verifier')
            if self.refresh_token or self.scope is not None or self.resource is not None:
                raise ValueError('authorization_code contains incompatible fields')
        elif self.grant_type == 'refresh_token':
            if not self.refresh_token:
                raise ValueError('refresh_token grant requires refresh_token')
            if self.code or self.code_verifier or self.redirect_uri:
                raise ValueError('refresh_token contains incompatible fields')
        elif self.grant_type == 'client_credentials' and any(
            (self.code, self.code_verifier, self.refresh_token, self.redirect_uri)
        ):
            raise ValueError('client_credentials contains incompatible fields')
        return self


class TokenResponse(ProtocolModel):
    """
    Token Endpoint 成功响应。

    字段直接对应 OAuth 2.0 标准 JSON 响应。
    """

    access_token: str
    token_type: Literal['Bearer'] = 'Bearer'
    expires_in: NonNegativeInt
    refresh_token: str | None = None
    scope: str | None = None
    id_token: str | None = None


class ErrorResponse(ProtocolModel):
    """
    OAuth/OIDC 标准错误响应。

    不包含项目业务响应包装字段。
    """

    error: str
    error_description: str | None = None
    error_uri: str | None = None

    def as_dict(self) -> dict[str, str]:
        """
        返回可直接作为标准 JSON 响应的非空字段。

        :return: 排除 None 字段的标准错误字典
        """

        return self.model_dump(exclude_none=True)


class Jwk(ProtocolModel):
    """
    公开 RSA JWK。

    模型严格拒绝 d、p、q 等私钥参数。
    """

    kty: Literal['RSA'] = 'RSA'
    use: Literal['sig'] = 'sig'
    kid: str = Field(min_length=1, max_length=100)
    alg: Literal['RS256'] = 'RS256'
    n: str = Field(min_length=1)
    e: str = Field(min_length=1)


class JwksResponse(ProtocolModel):
    """
    JWKS 响应。

    keys 仅包含公开签名 JWK。
    """

    keys: list[Jwk]


class DiscoveryResponse(ProtocolModel):
    """
    OIDC Discovery 响应。

    元数据只宣称当前实现确实支持的端点和算法。
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    jwks_uri: str
    revocation_endpoint: str
    introspection_endpoint: str
    end_session_endpoint: str
    scopes_supported: list[str] = Field(default_factory=list)
    response_types_supported: list[Literal['code']] = Field(default_factory=lambda: ['code'])
    response_modes_supported: list[Literal['query']] = Field(default_factory=lambda: ['query'])
    grant_types_supported: list[str] = Field(default_factory=lambda: ['authorization_code', 'refresh_token'])
    subject_types_supported: list[Literal['public']] = Field(default_factory=lambda: ['public'])
    id_token_signing_alg_values_supported: list[Literal['RS256']] = Field(default_factory=lambda: ['RS256'])
    token_endpoint_auth_methods_supported: list[Literal['none', 'client_secret_basic']] = Field(
        default_factory=lambda: ['none', 'client_secret_basic']
    )
    code_challenge_methods_supported: list[Literal['S256']] = Field(default_factory=lambda: ['S256'])
    claims_supported: list[str] = Field(default_factory=list)
    authorization_response_iss_parameter_supported: bool = True
    backchannel_logout_supported: bool = False
    backchannel_logout_session_supported: bool = False


class OAuthServerMetadata(ProtocolModel):
    """
    RFC 8414 OAuth Authorization Server Metadata 子集。

    不继承要求 OIDC 专属 userinfo_endpoint 和 end_session_endpoint 的模型。
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    revocation_endpoint: str | None = None
    introspection_endpoint: str | None = None
    scopes_supported: list[str] = Field(default_factory=list)
    response_types_supported: list[Literal['code']] = Field(default_factory=lambda: ['code'])
    grant_types_supported: list[str] = Field(default_factory=lambda: ['authorization_code', 'refresh_token'])
    token_endpoint_auth_methods_supported: list[Literal['none', 'client_secret_basic']] = Field(
        default_factory=lambda: ['none', 'client_secret_basic']
    )
    code_challenge_methods_supported: list[Literal['S256']] = Field(default_factory=lambda: ['S256'])


class UserInfoResponse(ProtocolModel):
    """
    UserInfo 基础响应。

    允许的扩展字段对应已授权的标准身份声明。
    """

    sub: str
    name: str | None = None
    preferred_username: str | None = None
    picture: str | None = None
    updated_at: int | None = None
    email: str | None = None
    email_verified: bool | None = None
    phone_number: str | None = None
    phone_number_verified: bool | None = None
    dept_id: str | int | None = None
    dept_name: str | None = None
    roles: list[str] | None = None


class RevocationRequest(ProtocolModel):
    """
    Token Revocation 请求。

    token_type_hint 只用于减少服务端查找歧义，不作为安全依据。
    """

    token: str = Field(min_length=1)
    token_type_hint: Literal['access_token', 'refresh_token'] | None = None


class IntrospectionRequest(ProtocolModel):
    """
    Token Introspection 请求。

    请求方权限和 audience 绑定由服务层继续校验。
    """

    token: str = Field(min_length=1)
    token_type_hint: Literal['access_token', 'refresh_token'] | None = None


class IntrospectionResponse(ProtocolModel):
    """
    Token Introspection 响应。

    inactive Token 只应返回 active=false。
    """

    active: bool
    scope: str | None = None
    client_id: str | None = None
    username: str | None = None
    token_type: str | None = None
    exp: int | None = None
    iat: int | None = None
    nbf: int | None = None
    sub: str | None = None
    aud: str | list[str] | None = None
    iss: str | None = None
    jti: str | None = None
    sid: str | None = None


class LogoutRequest(ProtocolModel):
    """
    RP-Initiated Logout 请求。

    post_logout_redirect_uri 必须由服务端按 Client 注册值精确匹配。
    """

    id_token_hint: str | None = None
    logout_hint: str | None = None
    client_id: str | None = None
    post_logout_redirect_uri: str | None = None
    state: str | None = None
