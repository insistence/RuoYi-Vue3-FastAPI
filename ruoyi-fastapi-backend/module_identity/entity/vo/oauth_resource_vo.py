from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class ResourceModel(BaseModel):
    """
    Resource 与 Scope 管理模型基类
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra='forbid')


def _validate_path_identifier(value: str, field_name: str) -> str:
    """
    校验可安全放入单一路径段的管理标识

    :param value: 待校验的资源或权限标识
    :param field_name: 校验失败时展示的字段名称
    :return: 校验通过的管理标识
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
    OAuth Scope 管理模型
    """

    scope_code: str = Field(min_length=1, max_length=100, description='权限标识')
    scope_name: str = Field(min_length=1, max_length=100, description='权限名称')
    scope_type: Literal['identity', 'resource'] = Field(description='权限类型（identity身份权限 resource资源权限）')
    resource_id: str | None = Field(default=None, description='资源标识')
    claims: list[str] = Field(default_factory=list, description='权限关联的声明字段列表')
    consent_required: bool = Field(default=True, description='是否要求用户确认该权限')
    sensitive: bool = Field(default=False, description='是否为敏感权限')
    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    _validate_code = field_validator('scope_code')(lambda value: _validate_path_identifier(value, 'scope_code'))

    @model_validator(mode='after')
    def validate_scope_resource(self) -> 'ScopeModel':
        """
        校验 Resource Scope 与 Resource ID 的绑定关系

        :return: 当前已校验 Scope
        """

        if self.scope_type == 'resource' and not self.resource_id:
            raise ValueError('resource scope requires resource_id')
        if self.scope_type == 'identity' and self.resource_id:
            raise ValueError('identity scope cannot be bound to a resource')
        return self


class ResourceCreateModel(ResourceModel):
    """
    Resource Server 创建模型
    """

    resource_id: str = Field(min_length=1, max_length=64, description='资源标识')
    resource_name: str = Field(min_length=1, max_length=100, description='资源名称')
    audience: str = Field(min_length=1, max_length=500, description='资源服务器的令牌受众标识')
    token_format: Literal['jwt'] = Field(default='jwt', description='访问令牌格式')
    signing_alg: Literal['RS256'] = Field(default='RS256', description='令牌签名算法')
    access_token_ttl_seconds: int | None = Field(default=None, gt=0, description='访问令牌有效期，单位为秒')
    introspection_client_id: str | None = Field(default=None, description='允许调用令牌内省的客户端标识')
    allowed_claims: list[str] = Field(default_factory=list, description='允许发布的声明字段列表')
    remark: str | None = Field(default=None, max_length=500, description='备注')

    _validate_resource_id = field_validator('resource_id')(
        lambda value: _validate_path_identifier(value, 'resource_id')
    )


class ResourceUpdateModel(ResourceCreateModel):
    """
    Resource Server 更新模型
    """

    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')


class ResourceViewModel(ResourceCreateModel):
    """
    Resource Server 管理详情模型
    """

    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')


class ClaimPolicyModel(ResourceModel):
    """
    Client/Resource Claim 允许列表模型
    """

    client_id: str | None = Field(default=None, description='客户端标识')
    resource_id: str | None = Field(default=None, description='资源标识')
    allowed_claims: list[str] = Field(default_factory=list, description='允许发布的声明字段列表')
    required_scopes: list[str] = Field(default_factory=list, description='发布声明所需的权限列表')


class ResourcePageQueryModel(ResourceModel):
    """
    Resource Server 分页查询模型
    """

    resource_name: str | None = Field(default=None, description='资源名称')
    status: Literal['0', '1'] | None = Field(default=None, description='状态（0正常 1停用）')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=200, description='每页记录数')


class ScopePageQueryModel(ResourceModel):
    """
    Scope 分页查询模型
    """

    scope_name: str | None = Field(default=None, description='权限名称')
    scope_type: Literal['identity', 'resource'] | None = Field(
        default=None, description='权限类型（identity身份权限 resource资源权限）'
    )
    status: Literal['0', '1'] | None = Field(default=None, description='状态（0正常 1停用）')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=200, description='每页记录数')


class ResourceStatusModel(ResourceModel):
    """
    Resource Server 启停状态模型
    """

    resource_id: str = Field(description='资源标识')
    status: Literal['0', '1'] = Field(description='状态（0正常 1停用）')

    _validate_resource_id = field_validator('resource_id')(
        lambda value: _validate_path_identifier(value, 'resource_id')
    )


class ScopeStatusModel(ResourceModel):
    """
    Scope 启停状态模型
    """

    scope_code: str = Field(description='权限标识')
    status: Literal['0', '1'] = Field(description='状态（0正常 1停用）')

    _validate_scope_code = field_validator('scope_code')(lambda value: _validate_path_identifier(value, 'scope_code'))
