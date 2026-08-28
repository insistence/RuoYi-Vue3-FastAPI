from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

_MAX_INTERACTION_SCOPE_LENGTH = 100


class InteractionModel(BaseModel):
    """
    认证交互 API 模型基类。

    交互字段使用 camelCase，并拒绝未定义字段。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra='forbid')


class InteractionLoginModel(InteractionModel):
    """
    认证中心登录提交模型。
    """

    user_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    code: str | None = Field(default=None, max_length=32)
    uuid: str | None = Field(default=None, max_length=128)
    remember_me: bool = False


class InteractionConsentModel(InteractionModel):
    """
    认证中心授权同意提交模型。
    """

    approved: bool
    scopes: list[str] = Field(default_factory=list, max_length=100)
    remember_consent: bool = False

    @model_validator(mode='after')
    def validate_scopes(self) -> 'InteractionConsentModel':
        """
        拒绝空 Scope、超长 Scope 和重复提交。
        """
        if any(
            not isinstance(scope, str) or not scope or len(scope) > _MAX_INTERACTION_SCOPE_LENGTH
            for scope in self.scopes
        ):
            raise ValueError('scopes must contain non-empty values of at most 100 characters')
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError('scopes must not contain duplicates')
        return self


class ChangePasswordModel(InteractionModel):
    """
    初始密码或过期密码修改模型。
    """

    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)

    @model_validator(mode='after')
    def validate_confirmation(self) -> 'ChangePasswordModel':
        """
        确保新密码与确认密码完全一致。

        :return: 当前已校验的改密请求
        """

        if self.new_password != self.confirm_password:
            raise ValueError('new_password and confirm_password must match')
        return self


class CaptchaResponseModel(InteractionModel):
    """
    认证交互验证码响应模型。
    """

    captcha_enabled: bool
    uuid: str | None = None
    img: str | None = None


class InteractionClientModel(InteractionModel):
    """
    授权交互页面展示的 Client 摘要。
    """

    client_id: str
    client_name: str
    logo_uri: str | None = None
    policy_uri: str | None = None
    tos_uri: str | None = None


class RequestedScopeModel(InteractionModel):
    """
    授权交互页面展示的 Scope 摘要。
    """

    scope: str
    name: str
    description: str | None = None
    sensitive: bool = False
    required: bool = False


class InteractionViewModel(InteractionModel):
    """
    Interaction 页面视图模型。
    """

    interaction_id: str
    client: InteractionClientModel
    requested_scopes: list[RequestedScopeModel] = Field(default_factory=list)
    next_action: Literal['login', 'consent', 'redirect', 'changePassword']
    captcha_enabled: bool = False
    expires_in: int


class InteractionResultModel(InteractionModel):
    """
    登录、同意或改密后的下一步动作模型。
    """

    next_action: Literal['login', 'consent', 'redirect', 'changePassword']
    interaction_id: str | None = None
    redirect_url: str | None = None
    reason: str | None = None
