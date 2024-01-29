from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query, as_form


class DictTypeModel(BaseModel):
    """
    字典类型表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    dict_id: Optional[int] = None
    dict_name: Optional[str] = None
    dict_type: Optional[str] = None
    status: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None


class DictDataModel(BaseModel):
    """
    字典数据表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    dict_code: Optional[int] = None
    dict_sort: Optional[int] = None
    dict_label: Optional[str] = None
    dict_value: Optional[str] = None
    dict_type: Optional[str] = None
    css_class: Optional[str] = None
    list_class: Optional[str] = None
    is_default: Optional[str] = None
    status: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None


class DictTypeQueryModel(DictTypeModel):
    """
    字典类型管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class DictTypePageQueryModel(DictTypeQueryModel):
    """
    字典类型管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeleteDictTypeModel(BaseModel):
    """
    删除字典类型模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    dict_ids: str


class DictDataQueryModel(DictDataModel):
    """
    字典数据管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class DictDataPageQueryModel(DictDataQueryModel):
    """
    字典数据管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeleteDictDataModel(BaseModel):
    """
    删除字典数据模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    dict_codes: str
