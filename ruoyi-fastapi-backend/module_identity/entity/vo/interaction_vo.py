from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

_MAX_INTERACTION_SCOPE_LENGTH = 100


class InteractionModel(BaseModel):
    """
    认证交互 API 模型基类

    交互字段使用 camelCase，并拒绝未定义字段。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra='forbid')


class InteractionLoginModel(InteractionModel):
    """
    认证中心登录提交模型
    """

    user_name: str = Field(min_length=1, max_length=64, description='用户账号')
    password: str = Field(min_length=1, max_length=256, description='登录密码')
    code: str | None = Field(default=None, max_length=32, description='验证码')
    uuid: str | None = Field(default=None, max_length=128, description='验证码唯一标识')
    remember_me: bool = Field(default=False, description='是否保持长期登录')


class InteractionConsentModel(InteractionModel):
    """
    认证中心授权同意提交模型
    """

    approved: bool = Field(description='是否同意本次授权')
    scopes: list[str] = Field(default_factory=list, max_length=100, description='本次同意的权限范围')
    remember_consent: bool = Field(default=False, description='是否记住本次选择以便后续免确认')

    @model_validator(mode='after')
    def validate_scopes(self) -> 'InteractionConsentModel':
        """
        拒绝空 Scope、超长 Scope 和重复提交
        """

        if any(
            not isinstance(scope, str) or not scope or len(scope) > _MAX_INTERACTION_SCOPE_LENGTH
            for scope in self.scopes
        ):
            raise ValueError('权限范围标识不能为空，且每项不得超过 100 个字符')
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError('权限范围不得重复')
        return self


class ChangePasswordModel(InteractionModel):
    """
    初始密码或过期密码修改模型
    """

    old_password: str = Field(min_length=1, max_length=256, description='当前密码')
    new_password: str = Field(min_length=1, max_length=256, description='新密码')
    confirm_password: str = Field(min_length=1, max_length=256, description='确认新密码')

    @model_validator(mode='after')
    def validate_confirmation(self) -> 'ChangePasswordModel':
        """
        确保新密码与确认密码完全一致

        :return: 当前已校验的改密请求
        """

        if self.new_password != self.confirm_password:
            raise ValueError('新密码与确认密码必须一致')
        return self


class CaptchaResponseModel(InteractionModel):
    """
    认证交互验证码响应模型
    """

    captcha_enabled: bool = Field(description='是否启用验证码')
    uuid: str | None = Field(default=None, description='验证码唯一标识')
    img: str | None = Field(default=None, description='验证码图片Base64内容')


class InteractionClientModel(InteractionModel):
    """
    授权交互页面展示的 Client 摘要
    """

    client_id: str = Field(description='客户端标识')
    client_name: str = Field(description='客户端名称')
    logo_uri: str | None = Field(default=None, description='客户端图标地址')
    policy_uri: str | None = Field(default=None, description='隐私政策地址')
    tos_uri: str | None = Field(default=None, description='服务条款地址')


class RequestedScopeModel(InteractionModel):
    """
    授权交互页面展示的 Scope 摘要
    """

    scope: str = Field(description='权限标识')
    name: str = Field(description='权限名称')
    description: str | None = Field(default=None, description='权限说明')
    sensitive: bool = Field(default=False, description='是否为敏感权限')
    required: bool = Field(default=False, description='是否为必选权限')


class InteractionViewModel(InteractionModel):
    """
    Interaction 页面视图模型
    """

    interaction_id: str = Field(description='认证交互标识')
    client: InteractionClientModel = Field(description='发起认证的客户端摘要')
    requested_scopes: list[RequestedScopeModel] = Field(default_factory=list, description='客户端请求的权限列表')
    next_action: Literal['login', 'consent', 'redirect', 'changePassword'] = Field(description='认证交互的下一步动作')
    captcha_enabled: bool = Field(default=False, description='是否启用验证码')
    expires_in: int = Field(description='剩余有效时间，单位为秒')


class InteractionResultModel(InteractionModel):
    """
    登录、同意或改密后的下一步动作模型
    """

    next_action: Literal['login', 'consent', 'redirect', 'changePassword'] = Field(description='认证交互的下一步动作')
    interaction_id: str | None = Field(default=None, description='认证交互标识')
    redirect_url: str | None = Field(default=None, description='服务端返回的下一步跳转地址')
    reason: str | None = Field(default=None, description='下一步动作的原因')
