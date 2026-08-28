from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class ResourceModel(BaseModel):
    """
    Resource 与 Scope 管理模型基类。
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


def _validate_path_identifier(value: str, field_name: str) -> str:
    """
    校验可安全放入单一路径段的管理标识。
    """
    if (
        not isinstance(value, str)
        or not value
        or not value[0].isalnum()
        or any(not (char.isascii() and (char.isalnum() or char in '._:-')) for char in value)
    ):
        raise ValueError(f'{field_name} must be a safe path identifier')
    return value


class ScopeModel(ResourceModel):
    """
    OAuth Scope 管理模型。
    """

    scope_code: str = Field(min_length=1, max_length=100)
    scope_name: str = Field(min_length=1, max_length=100)
    scope_type: Literal['identity', 'resource']
    resource_id: str | None = None
    claims: list[str] = Field(default_factory=list)
    consent_required: bool = True
    sensitive: bool = False
    status: Literal['0', '1'] = '0'
    remark: str | None = Field(default=None, max_length=500)

    _validate_code = field_validator('scope_code')(lambda value: _validate_path_identifier(value, 'scope_code'))

    @model_validator(mode='after')
    def validate_scope_resource(self) -> 'ScopeModel':
        """
        校验 Resource Scope 与 Resource ID 的绑定关系。

        :return: 当前已校验 Scope
        """
        if self.scope_type == 'resource' and not self.resource_id:
            raise ValueError('resource scope requires resource_id')
        if self.scope_type == 'identity' and self.resource_id:
            raise ValueError('identity scope cannot be bound to a resource')
        return self


class ResourceCreateModel(ResourceModel):
    """
    Resource Server 创建模型。
    """

    resource_id: str = Field(min_length=1, max_length=64)
    resource_name: str = Field(min_length=1, max_length=100)
    audience: str = Field(min_length=1, max_length=500)
    token_format: Literal['jwt'] = 'jwt'
    signing_alg: Literal['RS256'] = 'RS256'
    access_token_ttl_seconds: int | None = Field(default=None, gt=0)
    introspection_client_id: str | None = None
    allowed_claims: list[str] = Field(default_factory=list)
    remark: str | None = Field(default=None, max_length=500)

    _validate_resource_id = field_validator('resource_id')(
        lambda value: _validate_path_identifier(value, 'resource_id')
    )


class ResourceUpdateModel(ResourceCreateModel):
    """
    Resource Server 更新模型。
    """

    status: Literal['0', '1'] = '0'


class ResourceViewModel(ResourceCreateModel):
    """
    Resource Server 管理详情模型。
    """

    status: Literal['0', '1'] = '0'


class ClaimPolicyModel(ResourceModel):
    """
    Client/Resource Claim 允许列表模型。
    """

    client_id: str | None = None
    resource_id: str | None = None
    allowed_claims: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)


class ResourcePageQueryModel(ResourceModel):
    """
    Resource Server 分页查询模型。
    """

    resource_name: str | None = None
    status: Literal['0', '1'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)


class ScopePageQueryModel(ResourceModel):
    """
    Scope 分页查询模型。
    """

    scope_name: str | None = None
    scope_type: Literal['identity', 'resource'] | None = None
    status: Literal['0', '1'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)


class ResourceStatusModel(ResourceModel):
    """
    Resource Server 启停状态模型。
    """

    resource_id: str
    status: Literal['0', '1']

    _validate_resource_id = field_validator('resource_id')(
        lambda value: _validate_path_identifier(value, 'resource_id')
    )


class ScopeStatusModel(ResourceModel):
    """
    Scope 启停状态模型。
    """

    scope_code: str
    status: Literal['0', '1']

    _validate_scope_code = field_validator('scope_code')(lambda value: _validate_path_identifier(value, 'scope_code'))
