from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size, Xss
from typing import Literal, Optional
from module_admin.annotation.pydantic_annotation import as_query


class NoticeModel(BaseModel):
    """
    通知公告表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    notice_id: Optional[int] = Field(default=None, description='公告ID')
    notice_title: Optional[str] = Field(default=None, description='公告标题')
    notice_type: Optional[Literal['1', '2']] = Field(default=None, description='公告类型（1通知 2公告）')
    notice_content: Optional[bytes] = Field(default=None, description='公告内容')
    status: Optional[Literal['0', '1']] = Field(default=None, description='公告状态（0正常 1关闭）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')

    @Xss(field_name='notice_title', message='公告标题不能包含脚本字符')
    @NotBlank(field_name='notice_title', message='公告标题不能为空')
    @Size(field_name='notice_title', min_length=0, max_length=50, message='公告标题不能超过50个字符')
    def get_notice_title(self):
        return self.notice_title

    def validate_fields(self):
        self.get_notice_title()


class NoticeQueryModel(NoticeModel):
    """
    通知公告管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class NoticePageQueryModel(NoticeQueryModel):
    """
    通知公告管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteNoticeModel(BaseModel):
    """
    删除通知公告模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    notice_ids: str = Field(description='需要删除的公告ID')
