from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from common.types import ApiUtcDateTime
from module_identity.entity.vo.protocol_vo import Jwk
from utils.oidc_util import OidcUtil


class OidcKeyModel(BaseModel):
    """
    OIDC 签名密钥管理模型基类
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


class OidcKeyRotateModel(OidcKeyModel):
    """
    OIDC 签名密钥轮换请求模型
    """

    alg: Literal['RS256'] = Field(default='RS256', description='签名算法')
    kid: str = Field(min_length=1, max_length=100, description='签名密钥标识')
    publish_at: ApiUtcDateTime = Field(description='计划发布到JWKS的时间')
    activate_at: ApiUtcDateTime | None = Field(default=None, description='计划启用签名的时间，为空时需手动激活')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    @field_validator('kid')
    @classmethod
    def validate_kid(cls, value: str) -> str:
        """
        拒绝无法安全放入密钥路径的 kid

        :param value: 待校验的签名密钥标识
        :return: 校验通过的签名密钥标识
        """

        return OidcUtil.validate_path_identifier(value, '签名密钥标识 kid')


class OidcKeyViewModel(OidcKeyModel):
    """
    仅包含公开 JWK 的签名密钥详情模型
    """

    kid: str = Field(description='签名密钥标识')
    key_use: Literal['sig'] = Field(default='sig', description='密钥用途')
    alg: Literal['RS256'] = Field(default='RS256', description='签名算法')
    public_jwk: Jwk = Field(description='签名公钥的JWK表示')
    status: Literal['pending', 'active', 'retiring', 'retired', 'compromised'] = Field(
        description='密钥状态（pending待启用 active签名中 retiring退役中 retired已退役 compromised已泄露）'
    )
    publish_at: ApiUtcDateTime = Field(description='计划发布到JWKS的时间')
    signing_start_at: ApiUtcDateTime | None = Field(default=None, description='开始签名的时间')
    signing_stop_at: ApiUtcDateTime | None = Field(default=None, description='停止签名的时间')
    remove_from_jwks_at: ApiUtcDateTime | None = Field(default=None, description='从JWKS移除的时间')
    create_time: ApiUtcDateTime | None = Field(default=None, description='创建时间')
