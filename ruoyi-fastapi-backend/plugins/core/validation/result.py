from dataclasses import dataclass
from typing import Literal

ValidationLevel = Literal['error', 'warning', 'info']


@dataclass(frozen=True)
class PluginValidationIssue:
    """
    插件校验问题项。

    :param level: 校验等级
    :param category: 校验分类
    :param kind: 校验项类型
    :param path: 问题路径或目标
    :param message: 问题说明
    :param suggestion: 修复建议
    :param ok: 当前校验项是否通过
    """

    level: ValidationLevel
    category: str
    kind: str
    path: str
    message: str
    suggestion: str = ''
    ok: bool = False


class PluginValidationLevelResolver:
    """
    插件校验等级解析器。

    使用 Strategy 模式集中约定校验项等级，避免 CLI、API 和前端分别推断。
    """

    @staticmethod
    def from_ok(ok: bool) -> ValidationLevel:
        """
        根据通过状态解析校验等级。

        :param ok: 校验项是否通过
        :return: 校验等级
        """
        return 'info' if ok else 'error'
