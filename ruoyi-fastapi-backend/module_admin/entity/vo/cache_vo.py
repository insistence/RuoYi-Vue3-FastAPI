from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CacheMonitorModel(BaseModel):
    """
    缓存监控信息对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    command_stats: list | None = Field(default=[], description='命令统计')
    db_size: int | None = Field(default=None, description='Key数量')
    info: dict | None = Field(default={}, description='Redis信息')


class CacheInfoModel(BaseModel):
    """
    缓存监控对象对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    cache_key: str | None = Field(default=None, description='缓存键名')
    cache_name: str | None = Field(default=None, description='缓存名称')
    cache_value: Any | None = Field(default=None, description='缓存内容')
    remark: str | None = Field(default=None, description='备注')
