from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PluginOperationResult:
    """
    插件操作结果视图。
    """

    payload: Mapping[str, object]
    ok: bool
    message: str

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
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

    def exit_code(self, *, success_exit_code: int, failure_exit_code: int) -> int:
        """
        根据插件操作结果选择退出码。

        :param success_exit_code: 成功退出码
        :param failure_exit_code: 失败退出码
        :return: 退出码
        """
        return success_exit_code if self.ok else failure_exit_code
