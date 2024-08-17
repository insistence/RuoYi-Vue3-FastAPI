from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import Optional
from module_admin.annotation.pydantic_annotation import as_query


class OnlineModel(BaseModel):
    """
    在线用户对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    token_id: Optional[str] = Field(default=None, description='会话编号')
    user_name: Optional[str] = Field(default=None, description='登录名称')
    dept_name: Optional[str] = Field(default=None, description='所属部门')
    ipaddr: Optional[str] = Field(default=None, description='主机')
    login_location: Optional[str] = Field(default=None, description='登录地点')
    browser: Optional[str] = Field(default=None, description='浏览器类型')
    os: Optional[str] = Field(default=None, description='操作系统')
    login_time: Optional[datetime] = Field(default=None, description='登录时间')


@as_query
class OnlineQueryModel(OnlineModel):
    """
    岗位管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


class DeleteOnlineModel(BaseModel):
    """
    强退在线用户模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    token_ids: str = Field(description='需要强退的会话编号')
