from __future__ import annotations

from typing import Any, Protocol, TypeAlias

from pydantic import JsonValue as PydanticJsonValue

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = PydanticJsonValue
JSONObject: TypeAlias = dict[str, JSONValue]
Payload: TypeAlias = dict[str, JSONValue]
PluginConfigValue: TypeAlias = JSONValue


class SupportsModelDump(Protocol):
    """
    支持 Pydantic 风格序列化的对象协议。
    """

    def model_dump(self, *, by_alias: bool = False) -> dict[str, Any]:
        """
        序列化模型。

        :param by_alias: 是否使用字段别名
        :return: 序列化后的字典
        """
        ...


class SupportsToPayload(Protocol):
    """
    支持运行时 payload 序列化的对象协议。
    """

    def to_payload(self) -> dict[str, object]:
        """
        序列化为 payload 字典。

        :return: payload 字典
        """
        ...


class PluginStateRecord(Protocol):
    """
    插件数据库状态记录协议。
    """

    plugin_id: str
    installed_version: str | None
    enabled: str | None
    status: str | None
    last_error: str | None
    source: str | None
    backend_path: str | None
    frontend_path: str | None
