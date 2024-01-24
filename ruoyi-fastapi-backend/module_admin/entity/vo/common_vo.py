from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Optional, Any


class CrudResponseModel(BaseModel):
    """
    操作响应模型
    """
    is_success: bool
    message: str
    result: Optional[Any] = None


class UploadResponseModel(BaseModel):
    """
    上传响应模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    file_name: Optional[str] = None
    new_file_name: Optional[str] = None
    original_filename: Optional[str] = None
    url: Optional[str] = None
