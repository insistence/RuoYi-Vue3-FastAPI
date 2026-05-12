from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


class StatusCarrier(Protocol):
    """
    状态载体协议。

    该协议用于描述首页面板、详情分区和浏览记录这类具备 `status`
    属性的摘要统计对象。
    """

    status: str


@dataclass(frozen=True)
class StatusSummary:
    """
    状态摘要统计结果。

    :param total_count: 总数量
    :param ok_count: 正常数量
    :param warn_count: 警告数量
    :param fail_count: 失败数量
    """

    total_count: int
    ok_count: int
    warn_count: int
    fail_count: int


class StatusSummaryBuilder:
    """
    状态摘要构建器。

    该对象负责对带 `status` 属性的集合做统一计数，供 dashboard、
    detail、browser 三类 screen support 复用。
    """

    @staticmethod
    def build(items: Iterable[StatusCarrier]) -> StatusSummary:
        """
        统计状态摘要。

        :param items: 待统计对象集合
        :return: 状态摘要
        """
        materialized = list(items)
        return StatusSummary(
            total_count=len(materialized),
            ok_count=sum(1 for item in materialized if item.status == 'ok'),
            warn_count=sum(1 for item in materialized if item.status == 'warn'),
            fail_count=sum(1 for item in materialized if item.status == 'fail'),
        )


STATUS_SUMMARY_BUILDER = StatusSummaryBuilder()
