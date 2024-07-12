from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import Any, Optional


class CrudResponseModel(BaseModel):
    """
    操作响应模型
    """

    is_success: bool = Field(description='操作是否成功')
    message: str = Field(description='响应信息')
    result: Optional[Any] = Field(default=None, description='响应结果')


class UploadResponseModel(BaseModel):
    """
    上传响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    file_name: Optional[str] = Field(default=None, description='新文件映射路径')
    new_file_name: Optional[str] = Field(default=None, description='新文件名称')
    original_filename: Optional[str] = Field(default=None, description='原文件名称')
    url: Optional[str] = Field(default=None, description='新文件url')
