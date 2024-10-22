from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size
from typing import Literal, Optional
from module_admin.annotation.pydantic_annotation import as_query


class PostModel(BaseModel):
    """
    岗位信息表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    post_id: Optional[int] = Field(default=None, description='岗位ID')
    post_code: Optional[str] = Field(default=None, description='岗位编码')
    post_name: Optional[str] = Field(default=None, description='岗位名称')
    post_sort: Optional[int] = Field(default=None, description='显示顺序')
    status: Optional[Literal['0', '1']] = Field(default=None, description='状态（0正常 1停用）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')

    @NotBlank(field_name='post_code', message='岗位编码不能为空')
    @Size(field_name='post_code', min_length=0, max_length=64, message='岗位编码长度不能超过64个字符')
    def get_post_code(self):
        return self.post_code

    @NotBlank(field_name='post_name', message='岗位名称不能为空')
    @Size(field_name='post_name', min_length=0, max_length=50, message='岗位名称长度不能超过50个字符')
    def get_post_name(self):
        return self.post_name

    @NotBlank(field_name='post_sort', message='显示顺序不能为空')
    def get_post_sort(self):
        return self.post_sort

    def validate_fields(self):
        self.get_post_code()
        self.get_post_name()
        self.get_post_sort()


class PostQueryModel(PostModel):
    """
    岗位管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class PostPageQueryModel(PostQueryModel):
    """
    岗位管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeletePostModel(BaseModel):
    """
    删除岗位模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    post_ids: str = Field(description='需要删除的岗位ID')
