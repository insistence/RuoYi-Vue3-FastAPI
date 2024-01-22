from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query


class OnlineModel(BaseModel):
    """
    在线用户对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    token_id: Optional[str] = None
    user_name: Optional[str] = None
    dept_name: Optional[str] = None
    ipaddr: Optional[str] = None
    login_location: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    login_time: Optional[datetime] = None


@as_query
class OnlineQueryModel(OnlineModel):
    """
    岗位管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


class DeleteOnlineModel(BaseModel):
    """
    强退在线用户模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    token_ids: str
