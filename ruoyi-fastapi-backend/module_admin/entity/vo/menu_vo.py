from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from datetime import datetime
from typing import Union, Optional, List
from module_admin.annotation.pydantic_annotation import as_query


class MenuModel(BaseModel):
    """
    菜单表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    menu_id: Optional[int] = None
    menu_name: Optional[str] = None
    parent_id: Optional[int] = None
    order_num: Optional[int] = None
    path: Optional[str] = None
    component: Optional[str] = None
    query: Optional[str] = None
    is_frame: Optional[int] = None
    is_cache: Optional[int] = None
    menu_type: Optional[str] = None
    visible: Optional[str] = None
    status: Optional[str] = None
    perms: Optional[str] = None
    icon: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None


@as_query
class MenuQueryModel(MenuModel):
    """
    菜单管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


class DeleteMenuModel(BaseModel):
    """
    删除菜单模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    menu_ids: str
