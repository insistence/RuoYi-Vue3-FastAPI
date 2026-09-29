from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from common.types import ApiUtcDateTime


class SessionModel(BaseModel):
    """
    Session、Grant 和 Audit 管理模型基类

    管理端字段接受 camelCase 别名并拒绝额外字段。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


class GrantModel(SessionModel):
    """
    用户对 OAuth Client 的授权详情模型
    """

    grant_id: str = Field(description='授权记录标识')
    user_id: int | None = Field(default=None, description='用户ID')
    subject_id: str | None = Field(default=None, description='用户稳定主体标识')
    client_id: str = Field(description='客户端标识')
    client_name: str | None = Field(default=None, description='客户端名称')
    granted_scopes: list[str] = Field(default_factory=list, description='已同意的权限列表')
    granted_resources: list[str] = Field(default_factory=list, description='已同意的资源受众列表')
    remembered_scopes: list[str] = Field(default_factory=list, description='后续可免确认的权限列表')
    remembered_resources: list[str] = Field(default_factory=list, description='后续可免确认的资源列表')
    access_status: Literal['allowed', 'blocked'] = Field(default='allowed', description='用户对应用的访问策略')
    access_reason: str | None = Field(default=None, description='访问策略的操作原因')
    status: Literal['active', 'revoked', 'expired'] = Field(
        default='active', description='状态（active有效 revoked已撤销 expired已过期）'
    )
    client_policy_version: int | None = Field(default=None, description='授权时的客户端策略版本')
    consented_at: ApiUtcDateTime | None = Field(default=None, description='用户同意授权的时间')
    last_used_at: ApiUtcDateTime | None = Field(default=None, description='授权最近使用时间')
    expires_at: ApiUtcDateTime | None = Field(default=None, description='过期时间')
    revoke_reason: str | None = Field(default=None, description='撤销原因')


class SsoSessionModel(SessionModel):
    """
    认证中心 SSO Session 脱敏详情模型
    """

    sid: str = Field(description='SSO会话标识')
    user_id: int | None = Field(default=None, description='用户ID')
    subject_id: str | None = Field(default=None, description='用户稳定主体标识')
    auth_version: int | None = Field(default=None, description='用户认证安全版本')
    auth_time: ApiUtcDateTime | None = Field(default=None, description='用户认证时间')
    last_seen_at: ApiUtcDateTime | None = Field(default=None, description='会话最近活动时间')
    idle_expires_at: ApiUtcDateTime | None = Field(default=None, description='闲置过期时间')
    absolute_expires_at: ApiUtcDateTime | None = Field(default=None, description='绝对过期时间')
    acr: str | None = Field(default=None, description='认证上下文')
    amr: list[str] = Field(default_factory=list, description='认证方式列表')
    remember_me: bool = Field(default=False, description='是否保持长期登录')
    ip_address: str | None = Field(default=None, description='IP地址')
    status: Literal['active', 'revoked', 'expired'] = Field(
        default='active', description='状态（active有效 revoked已撤销 expired已过期）'
    )
    revoked_at: ApiUtcDateTime | None = Field(default=None, description='撤销时间')
    revoke_reason: str | None = Field(default=None, description='撤销原因')
    create_time: ApiUtcDateTime | None = Field(default=None, description='创建时间')
    client_ids: list[str] = Field(default_factory=list, description='会话关联的客户端标识列表')


class SessionRevokeModel(SessionModel):
    """
    SSO Session 撤销请求模型
    """

    reason: str = Field(min_length=1, max_length=200, description='会话或授权的撤销原因')


class GrantAccessModel(SessionRevokeModel):
    """
    用户对应用的访问控制请求模型
    """

    blocked: bool = Field(strict=True, description='是否禁止用户访问应用')


class SessionPageQueryModel(SessionModel):
    """
    SSO Session 分页查询模型
    """

    user_id: int | None = Field(default=None, description='用户ID')
    ip_address: str | None = Field(default=None, description='IP地址')
    status: Literal['active', 'revoked', 'expired'] | None = Field(
        default=None, description='状态（active有效 revoked已撤销 expired已过期）'
    )
    start_time: ApiUtcDateTime | None = Field(default=None, description='查询开始时间')
    end_time: ApiUtcDateTime | None = Field(default=None, description='查询结束时间')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=200, description='每页记录数')

    @model_validator(mode='after')
    def validate_time_range(self) -> 'SessionPageQueryModel':
        """
        校验 Session 查询时间范围
        """

        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError('end_time must not be earlier than start_time')
        return self


class GrantPageQueryModel(SessionModel):
    """
    OAuth Grant 分页查询模型
    """

    user_id: int | None = Field(default=None, description='用户ID')
    client_id: str | None = Field(default=None, description='客户端标识')
    status: Literal['active', 'revoked', 'expired'] | None = Field(
        default=None, description='状态（active有效 revoked已撤销 expired已过期）'
    )
    access_status: Literal['allowed', 'blocked'] | None = Field(default=None, description='用户对应用的访问策略')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=200, description='每页记录数')


class AuditPageQueryModel(SessionModel):
    """
    OAuth 审计分页查询模型

    支持按 Client、用户、事件结果、风险和时间范围过滤。
    """

    event_type: str | None = Field(default=None, description='审计事件类型')
    client_id: str | None = Field(default=None, description='客户端标识')
    user_id: int | None = Field(default=None, description='用户ID')
    result: Literal['success', 'failure'] | None = Field(
        default=None, description='处理结果（success成功 failure失败）'
    )
    risk_level: Literal['normal', 'medium', 'high', 'critical'] | None = Field(
        default=None, description='风险等级（normal普通 medium中等 high高 critical严重）'
    )
    start_time: ApiUtcDateTime | None = Field(default=None, description='查询开始时间')
    end_time: ApiUtcDateTime | None = Field(default=None, description='查询结束时间')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=200, description='每页记录数')

    @model_validator(mode='after')
    def validate_time_range(self) -> 'AuditPageQueryModel':
        """
        校验审计查询的起止时间顺序

        :return: 当前已校验查询模型
        :raises ValueError: 结束时间早于开始时间
        """

        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError('end_time must not be earlier than start_time')
        return self


class AuditModel(SessionModel):
    """
    脱敏 OAuth 审计事件详情模型
    """

    audit_id: int = Field(description='审计记录ID')
    event_type: str = Field(description='审计事件类型')
    result: Literal['success', 'failure'] = Field(description='处理结果（success成功 failure失败）')
    risk_level: Literal['normal', 'medium', 'high', 'critical'] = Field(
        default='normal', description='风险等级（normal普通 medium中等 high高 critical严重）'
    )
    trace_id: str | None = Field(default=None, description='请求跟踪标识')
    client_id: str | None = Field(default=None, description='客户端标识')
    resource_id: str | None = Field(default=None, description='资源标识')
    user_id: int | None = Field(default=None, description='用户ID')
    subject_id: str | None = Field(default=None, description='用户稳定主体标识')
    sid: str | None = Field(default=None, description='SSO会话标识')
    ip_address: str | None = Field(default=None, description='IP地址')
    failure_code: str | None = Field(default=None, description='失败原因代码')
    create_time: ApiUtcDateTime = Field(description='创建时间')
