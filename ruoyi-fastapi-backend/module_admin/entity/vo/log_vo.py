from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query, as_form


class OperLogModel(BaseModel):
    """
    操作日志表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    oper_id: Optional[int] = None
    title: Optional[str] = None
    business_type: Optional[int] = None
    method: Optional[str] = None
    request_method: Optional[str] = None
    operator_type: Optional[int] = None
    oper_name: Optional[str] = None
    dept_name: Optional[str] = None
    oper_url: Optional[str] = None
    oper_ip: Optional[str] = None
    oper_location: Optional[str] = None
    oper_param: Optional[str] = None
    json_result: Optional[str] = None
    status: Optional[int] = None
    error_msg: Optional[str] = None
    oper_time: Optional[datetime] = None
    cost_time: Optional[int] = None


class LogininforModel(BaseModel):
    """
    登录日志表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    info_id: Optional[int] = None
    user_name: Optional[str] = None
    ipaddr: Optional[str] = None
    login_location: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    status: Optional[str] = None
    msg: Optional[str] = None
    login_time: Optional[datetime] = None


class OperLogQueryModel(OperLogModel):
    """
    操作日志管理不分页查询模型
    """
    order_by_column: Optional[str] = None
    is_asc: Optional[str] = None
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class OperLogPageQueryModel(OperLogQueryModel):
    """
    操作日志管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeleteOperLogModel(BaseModel):
    """
    删除操作日志模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    oper_ids: str


class LoginLogQueryModel(LogininforModel):
    """
    登录日志管理不分页查询模型
    """
    order_by_column: Optional[str] = None
    is_asc: Optional[str] = None
    begin_time: Optional[str] = None
    end_time: Optional[str] = None



@as_query
@as_form
class LoginLogPageQueryModel(LoginLogQueryModel):
    """
    登录日志管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeleteLoginLogModel(BaseModel):
    """
    删除登录日志模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    info_ids: str


class UnlockUser(BaseModel):
    """
    解锁用户模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    user_name: str
