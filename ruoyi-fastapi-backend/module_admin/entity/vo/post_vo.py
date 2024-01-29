from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query, as_form


class PostModel(BaseModel):
    """
    岗位信息表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    post_id: Optional[int] = None
    post_code: Optional[str] = None
    post_name: Optional[str] = None
    post_sort: Optional[int] = None
    status: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None


class PostQueryModel(PostModel):
    """
    岗位管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class PostPageQueryModel(PostQueryModel):
    """
    岗位管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeletePostModel(BaseModel):
    """
    删除岗位模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    post_ids: str
