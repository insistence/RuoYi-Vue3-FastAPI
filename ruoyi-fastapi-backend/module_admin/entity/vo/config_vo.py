from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query, as_form


class ConfigModel(BaseModel):
    """
    参数配置表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    config_id: Optional[int] = None
    config_name: Optional[str] = None
    config_key: Optional[str] = None
    config_value: Optional[str] = None
    config_type: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None


class ConfigQueryModel(ConfigModel):
    """
    参数配置管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class ConfigPageQueryModel(ConfigQueryModel):
    """
    参数配置管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeleteConfigModel(BaseModel):
    """
    删除参数配置模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    config_ids: str
