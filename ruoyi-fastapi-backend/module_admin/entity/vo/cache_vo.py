from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Optional, List, Any


class CacheMonitorModel(BaseModel):
    """
    缓存监控信息对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    command_stats: Optional[List] = []
    db_size: Optional[int] = None
    info: Optional[dict] = {}


class CacheInfoModel(BaseModel):
    """
    缓存监控对象对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    cache_key: Optional[str] = None
    cache_name: Optional[str] = None
    cache_value: Optional[Any] = None
    remark: Optional[str] = None
