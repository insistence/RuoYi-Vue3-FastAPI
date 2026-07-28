from typing import Any

from pydantic import BaseModel, ConfigDict


class PluginPayloadModel(BaseModel):
    """
    插件运行时 payload 模型基类。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    def to_payload(self, *, exclude_none: bool = False) -> dict[str, Any]:
        """
        序列化为现有运行时 dict payload 契约。

        :param exclude_none: 是否排除 None 字段
        :return: payload 字典
        """
        return self.model_dump(by_alias=True, exclude_none=exclude_none)


__all__ = ['PluginPayloadModel']
