from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query


class DeptModel(BaseModel):
    """
    部门表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    dept_id: Optional[int] = None
    parent_id: Optional[int] = None
    ancestors: Optional[str] = None
    dept_name: Optional[str] = None
    order_num: Optional[int] = None
    leader: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    del_flag: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None


@as_query
class DeptQueryModel(DeptModel):
    """
    部门管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


class DeleteDeptModel(BaseModel):
    """
    删除部门模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    dept_ids: str
    update_by: Optional[str] = None
    update_time: Optional[str] = None
