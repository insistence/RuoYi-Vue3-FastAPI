import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from middlewares.trace_middleware import TraceCtx


def current_plugin_request_id() -> str:
    """
    复用宿主请求追踪标识；独立挂载或测试环境未设置追踪时生成新标识。

    :return: 当前请求的关联标识
    """
    return TraceCtx.get_request_id() or uuid4().hex


@dataclass(frozen=True)
class PluginHttpRequest:
    """
    提供给 Python 和原生回调的 HTTP 数据快照，不携带 Cookie、令牌或 Request 对象。

    :param method: HTTP 请求方法
    :param path: 当前请求的路径，不包含查询串
    :param path_params: 路由已解析的路径参数，值为可序列化数据
    :param query: 保留同名多值的查询参数
    :param body: 显式开启 JSON 读取后获得的请求体
    """

    method: str
    path: str
    path_params: Mapping[str, Any] = field(default_factory=dict)
    query: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    body: Any = None

    def __post_init__(self) -> None:
        """
        复制路径和查询参数，避免调用方修改原始请求的参数映射。

        :return: None
        """
        object.__setattr__(self, 'path_params', MappingProxyType(dict(self.path_params)))
        object.__setattr__(self, 'query', MappingProxyType({key: tuple(values) for key, values in self.query.items()}))

    def to_payload(self) -> dict[str, Any]:
        """
        返回独立的 JSON 数据副本，供原生回调或序列化边界消费。

        :return: 不包含宿主对象的 HTTP 请求数据
        """
        return json.loads(
            json.dumps(
                {
                    'method': self.method,
                    'path': self.path,
                    'pathParams': dict(self.path_params),
                    'query': dict(self.query),
                    'body': self.body,
                },
                ensure_ascii=False,
                allow_nan=False,
            )
        )
