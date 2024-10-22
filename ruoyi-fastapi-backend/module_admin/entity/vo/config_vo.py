from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size
from typing import Literal, Optional
from module_admin.annotation.pydantic_annotation import as_query


class ConfigModel(BaseModel):
    """
    参数配置表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    config_id: Optional[int] = Field(default=None, description='参数主键')
    config_name: Optional[str] = Field(default=None, description='参数名称')
    config_key: Optional[str] = Field(default=None, description='参数键名')
    config_value: Optional[str] = Field(default=None, description='参数键值')
    config_type: Optional[Literal['Y', 'N']] = Field(default=None, description='系统内置（Y是 N否）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')

    @NotBlank(field_name='config_key', message='参数名称不能为空')
    @Size(field_name='config_key', min_length=0, max_length=100, message='参数名称长度不能超过100个字符')
    def get_config_key(self):
        return self.config_key

    @NotBlank(field_name='config_name', message='参数键名不能为空')
    @Size(field_name='config_name', min_length=0, max_length=100, message='参数键名长度不能超过100个字符')
    def get_config_name(self):
        return self.config_name

    @NotBlank(field_name='config_value', message='参数键值不能为空')
    @Size(field_name='config_value', min_length=0, max_length=500, message='参数键值长度不能超过500个字符')
    def get_config_value(self):
        return self.config_value

    def validate_fields(self):
        self.get_config_key()
        self.get_config_name()
        self.get_config_value()


class ConfigQueryModel(ConfigModel):
    """
    参数配置管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class ConfigPageQueryModel(ConfigQueryModel):
    """
    参数配置管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteConfigModel(BaseModel):
    """
    删除参数配置模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    config_ids: str = Field(description='需要删除的参数主键')
