from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class UploadResponseModel(BaseModel):
    """
    上传响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    file_name: str | None = Field(default=None, description='新文件映射路径')
    new_file_name: str | None = Field(default=None, description='新文件名称')
    original_filename: str | None = Field(default=None, description='原文件名称')
    url: str | None = Field(default=None, description='新文件url')
    file_id: str | None = Field(default=None, description='文件ID')
    access_type: Literal['public', 'private'] | None = Field(default=None, description='访问类型')
    download_url: str | None = Field(default=None, description='鉴权下载地址')
