from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Pattern, Size
from typing import Literal, Optional
from module_admin.annotation.pydantic_annotation import as_query


class DictTypeModel(BaseModel):
    """
    字典类型表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    dict_id: Optional[int] = Field(default=None, description='字典主键')
    dict_name: Optional[str] = Field(default=None, description='字典名称')
    dict_type: Optional[str] = Field(default=None, description='字典类型')
    status: Optional[Literal['0', '1']] = Field(default=None, description='状态（0正常 1停用）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')

    @NotBlank(field_name='dict_name', message='字典名称不能为空')
    @Size(field_name='dict_name', min_length=0, max_length=100, message='字典类型名称长度不能超过100个字符')
    def get_dict_name(self):
        return self.dict_name

    @NotBlank(field_name='dict_type', message='字典类型不能为空')
    @Size(field_name='dict_type', min_length=0, max_length=100, message='字典类型类型长度不能超过100个字符')
    @Pattern(
        field_name='dict_type',
        regexp='^[a-z][a-z0-9_]*$',
        message='字典类型必须以字母开头，且只能为（小写字母，数字，下滑线）',
    )
    def get_dict_type(self):
        return self.dict_type

    def validate_fields(self):
        self.get_dict_name()
        self.get_dict_type()


class DictDataModel(BaseModel):
    """
    字典数据表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    dict_code: Optional[int] = Field(default=None, description='字典编码')
    dict_sort: Optional[int] = Field(default=None, description='字典排序')
    dict_label: Optional[str] = Field(default=None, description='字典标签')
    dict_value: Optional[str] = Field(default=None, description='字典键值')
    dict_type: Optional[str] = Field(default=None, description='字典类型')
    css_class: Optional[str] = Field(default=None, description='样式属性（其他样式扩展）')
    list_class: Optional[str] = Field(default=None, description='表格回显样式')
    is_default: Optional[Literal['Y', 'N']] = Field(default=None, description='是否默认（Y是 N否）')
    status: Optional[Literal['0', '1']] = Field(default=None, description='状态（0正常 1停用）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')

    @NotBlank(field_name='dict_label', message='字典标签不能为空')
    @Size(field_name='dict_label', min_length=0, max_length=100, message='字典标签长度不能超过100个字符')
    def get_dict_label(self):
        return self.dict_label

    @NotBlank(field_name='dict_value', message='字典键值不能为空')
    @Size(field_name='dict_value', min_length=0, max_length=100, message='字典键值长度不能超过100个字符')
    def get_dict_value(self):
        return self.dict_value

    @NotBlank(field_name='dict_type', message='字典类型不能为空')
    @Size(field_name='dict_type', min_length=0, max_length=100, message='字典类型长度不能超过100个字符')
    def get_dict_type(self):
        return self.dict_type

    @Size(field_name='css_class', min_length=0, max_length=100, message='样式属性长度不能超过100个字符')
    def get_css_class(self):
        return self.css_class

    def validate_fields(self):
        self.get_dict_label()
        self.get_dict_value()
        self.get_dict_type()
        self.get_css_class()


class DictTypeQueryModel(DictTypeModel):
    """
    字典类型管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class DictTypePageQueryModel(DictTypeQueryModel):
    """
    字典类型管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteDictTypeModel(BaseModel):
    """
    删除字典类型模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    dict_ids: str = Field(description='需要删除的字典主键')


class DictDataQueryModel(DictDataModel):
    """
    字典数据管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class DictDataPageQueryModel(DictDataQueryModel):
    """
    字典数据管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteDictDataModel(BaseModel):
    """
    删除字典数据模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    dict_codes: str = Field(description='需要删除的字典编码')
