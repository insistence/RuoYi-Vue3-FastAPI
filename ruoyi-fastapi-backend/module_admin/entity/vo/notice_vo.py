from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size, Xss


class NoticeModel(BaseModel):
    """
    通知公告表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    notice_id: int | None = Field(default=None, description='公告ID')
    notice_title: str | None = Field(default=None, description='公告标题')
    notice_type: Literal['1', '2'] | None = Field(default=None, description='公告类型（1通知 2公告）')
    notice_content: bytes | None = Field(default=None, description='公告内容')
    status: Literal['0', '1'] | None = Field(default=None, description='公告状态（0正常 1关闭）')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')
    remark: str | None = Field(default=None, description='备注')

    @Xss(field_name='notice_title', message='公告标题不能包含脚本字符')
    @NotBlank(field_name='notice_title', message='公告标题不能为空')
    @Size(field_name='notice_title', min_length=0, max_length=50, message='公告标题不能超过50个字符')
    def get_notice_title(self) -> str | None:
        return self.notice_title

    def validate_fields(self) -> None:
        self.get_notice_title()


class NoticeQueryModel(NoticeModel):
    """
    通知公告管理不分页查询模型
    """

    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


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
