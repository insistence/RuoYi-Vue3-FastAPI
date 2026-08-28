from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class SessionModel(BaseModel):
    """
    Session、Grant 和 Audit 管理模型基类。

    管理端字段接受 camelCase 别名并拒绝额外字段。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


class GrantModel(SessionModel):
    """
    用户对 OAuth Client 的持久授权详情模型。
    """

    grant_id: str
    user_id: int | None = None
    subject_id: str | None = None
    client_id: str
    client_name: str | None = None
    granted_scopes: list[str] = Field(default_factory=list)
    granted_resources: list[str] = Field(default_factory=list)
    status: Literal['active', 'revoked', 'expired'] = 'active'
    client_policy_version: int | None = None
    consented_at: datetime | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoke_reason: str | None = None


class SsoSessionModel(SessionModel):
    """
    认证中心 SSO Session 脱敏详情模型。
    """

    sid: str
    user_id: int | None = None
    subject_id: str | None = None
    auth_version: int | None = None
    auth_time: datetime | None = None
    last_seen_at: datetime | None = None
    idle_expires_at: datetime | None = None
    absolute_expires_at: datetime | None = None
    acr: str | None = None
    amr: list[str] = Field(default_factory=list)
    remember_me: bool = False
    ip_address: str | None = None
    status: Literal['active', 'revoked', 'expired'] = 'active'
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    create_time: datetime | None = None
    client_ids: list[str] = Field(default_factory=list)


class SessionRevokeModel(SessionModel):
    """
    SSO Session 撤销请求模型。
    """

    reason: str = Field(min_length=1, max_length=200)


class SessionPageQueryModel(SessionModel):
    """
    SSO Session 分页查询模型。
    """

    user_id: int | None = None
    ip_address: str | None = None
    status: Literal['active', 'revoked', 'expired'] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)

    @model_validator(mode='after')
    def validate_time_range(self) -> 'SessionPageQueryModel':
        """
        校验 Session 查询时间范围。
        """
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError('end_time must not be earlier than start_time')
        return self


class GrantPageQueryModel(SessionModel):
    """
    Persistent Grant 分页查询模型。
    """

    user_id: int | None = None
    client_id: str | None = None
    status: Literal['active', 'revoked', 'expired'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)


class AuditPageQueryModel(SessionModel):
    """
    OAuth 审计分页查询模型。

    支持按 Client、用户、事件结果、风险和时间范围过滤。
    """

    event_type: str | None = None
    client_id: str | None = None
    user_id: int | None = None
    result: Literal['success', 'failure'] | None = None
    risk_level: Literal['normal', 'medium', 'high', 'critical'] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)

    @model_validator(mode='after')
    def validate_time_range(self) -> 'AuditPageQueryModel':
        """
        校验审计查询的起止时间顺序。

        :return: 当前已校验查询模型
        :raises ValueError: 结束时间早于开始时间
        """

        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError('end_time must not be earlier than start_time')
        return self


class AuditModel(SessionModel):
    """
    脱敏 OAuth 审计事件详情模型。
    """

    audit_id: int
    event_type: str
    result: Literal['success', 'failure']
    risk_level: Literal['normal', 'medium', 'high', 'critical'] = 'normal'
    trace_id: str | None = None
    client_id: str | None = None
    resource_id: str | None = None
    user_id: int | None = None
    subject_id: str | None = None
    sid: str | None = None
    ip_address: str | None = None
    failure_code: str | None = None
    create_time: datetime
