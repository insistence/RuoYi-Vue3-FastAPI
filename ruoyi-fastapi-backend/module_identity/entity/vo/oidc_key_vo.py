from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from module_identity.entity.vo.protocol_vo import Jwk


class OidcKeyModel(BaseModel):
    """
    OIDC 签名密钥管理模型基类。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


class OidcKeyRotateModel(OidcKeyModel):
    """
    OIDC 签名密钥轮换请求模型。
    """

    alg: Literal['RS256'] = 'RS256'
    kid: str = Field(min_length=1, max_length=100)
    publish_at: datetime
    activate_at: datetime | None = None
    remark: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def validate_local_times(self) -> 'OidcKeyRotateModel':
        """
        校验轮换时间使用项目约定的无时区格式

        :return: 已校验的轮换请求
        :raises ValueError: 时间包含时区偏移
        """
        if self.publish_at.tzinfo is not None or (self.activate_at is not None and self.activate_at.tzinfo is not None):
            raise ValueError('publishAt and activateAt must not include a timezone offset')
        return self

    @field_validator('kid')
    @classmethod
    def validate_kid(cls, value: str) -> str:
        """
        拒绝无法安全放入密钥路径的 kid。
        """
        if (
            not value
            or not value[0].isalnum()
            or any(not (char.isascii() and (char.isalnum() or char in '._:-')) for char in value)
        ):
            raise ValueError('kid must be a safe path identifier')
        return value


class OidcKeyViewModel(OidcKeyModel):
    """
    仅包含公开 JWK 的签名密钥详情模型。
    """

    kid: str
    key_use: Literal['sig'] = 'sig'
    alg: Literal['RS256'] = 'RS256'
    public_jwk: Jwk
    status: Literal['pending', 'active', 'retiring', 'retired', 'compromised']
    publish_at: datetime
    signing_start_at: datetime | None = None
    signing_stop_at: datetime | None = None
    remove_from_jwks_at: datetime | None = None
    create_time: datetime | None = None
