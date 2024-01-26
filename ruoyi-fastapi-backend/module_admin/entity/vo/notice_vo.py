from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query, as_form


class NoticeModel(BaseModel):
    """
    通知公告表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    notice_id: Optional[int] = None
    notice_title: Optional[str] = None
    notice_type: Optional[str] = None
    notice_content: Optional[bytes] = None
    status: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None


class NoticeQueryModel(NoticeModel):
    """
    通知公告管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class NoticePageQueryModel(NoticeQueryModel):
    """
    通知公告管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeleteNoticeModel(BaseModel):
    """
    删除通知公告模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    notice_ids: str
