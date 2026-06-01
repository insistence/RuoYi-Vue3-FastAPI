from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PluginOperationResult:
    """
    插件操作结果视图。
    """

    payload: dict[str, Any]
    ok: bool
    message: str

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        default_message: str = '插件操作完成',
    ) -> 'PluginOperationResult':
        """
        从插件运行时 payload 构建结果视图。

        :param payload: 插件运行时负载
        :param default_message: 默认消息
        :return: 插件操作结果视图
        """
        return cls(
            payload=payload,
            ok=bool(payload.get('ok', False)),
            message=str(payload.get('message') or default_message),
        )
