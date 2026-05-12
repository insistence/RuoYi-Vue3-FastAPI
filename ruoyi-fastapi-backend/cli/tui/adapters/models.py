from collections.abc import Callable
from dataclasses import dataclass, field

from cli.tui.copy import TUI_COPY
from cli.tui.search import PageFilterOption, PageSearchContext
from cli.utils import SHELL_TEXT_FORMATTER


@dataclass(frozen=True)
class DetailSectionSnapshot:
    """
    TUI 详情页单个分区快照。

    :param title: 分区标题
    :param status: 分区状态
    :param lines: 分区正文文本行
    """

    title: str
    status: str
    lines: list[str]


@dataclass(frozen=True)
class DetailPageSnapshot:
    """
    TUI 详情页聚合快照。

    :param title: 页面标题
    :param subtitle: 页面副标题
    :param sections: 页面分区列表
    :param search: 当前页面搜索上下文
    """

    title: str
    subtitle: str
    sections: list[DetailSectionSnapshot]
    search: PageSearchContext | None = None


@dataclass(frozen=True)
class BrowserRecordSnapshot:
    """
    TUI 浏览页单条记录快照。

    :param key: 记录唯一标识
    :param title: 记录标题
    :param status: 记录状态
    :param summary: 记录摘要
    :param metadata_lines: 记录元信息文本行
    :param detail_sections: 记录联动详情分区列表
    """

    key: str
    title: str
    status: str
    summary: str
    metadata_lines: list[str]
    detail_sections: list[DetailSectionSnapshot]
    detail_loader: Callable[[], list[DetailSectionSnapshot]] | None = None
    _cached_detail_sections: tuple[DetailSectionSnapshot, ...] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def resolve_detail_sections(self) -> list[DetailSectionSnapshot]:
        """
        获取当前记录详情分区，必要时按需加载并缓存。

        :return: 详情分区列表
        """
        if self.detail_loader is None:
            return self.detail_sections
        if self._cached_detail_sections is None:
            object.__setattr__(self, '_cached_detail_sections', tuple(self.detail_loader()))
        return list(self._cached_detail_sections)


@dataclass(frozen=True)
class BrowserPageSnapshot:
    """
    TUI 浏览页聚合快照。

    :param title: 页面标题
    :param subtitle: 页面副标题
    :param records: 可浏览记录列表
    :param shared_sections: 全局共享分区列表
    :param filters: 页面可用筛选项
    :param active_filter_key: 当前激活筛选键
    :param search: 当前页面搜索上下文
    """

    title: str
    subtitle: str
    records: list[BrowserRecordSnapshot]
    shared_sections: list[DetailSectionSnapshot]
    filters: list[PageFilterOption] = field(default_factory=list)
    active_filter_key: str | None = None
    search: PageSearchContext | None = None


class TuiAdapterModelRenderService:
    """
    TUI 适配层模型渲染服务。

    该对象集中封装结果负载摘要提取，以及空态、加载态、失败态文本行
    的统一构建逻辑，避免这些模块级辅助函数继续散落扩张。
    """

    @staticmethod
    def extract_payload_message(payload: dict[str, object] | None) -> str:
        """
        提取结果负载中的可读消息。

        :param payload: 标准结果负载
        :return: 摘要消息文本
        """
        if not isinstance(payload, dict):
            return '-'
        if payload.get('message'):
            return SHELL_TEXT_FORMATTER.truncate_text(payload.get('message', '-'), 120)
        if payload.get('error'):
            return SHELL_TEXT_FORMATTER.truncate_text(payload.get('error', '-'), 120)
        return '-'

    @staticmethod
    def build_empty_lines(
        *,
        empty_label: str,
        empty_value: str,
        detail: str,
        suggestion: str = TUI_COPY.build_empty_state_suggestion(),
    ) -> list[str]:
        """
        构建统一的空态文本行。

        :param empty_label: 空态主字段名称
        :param empty_value: 空态主字段值
        :param detail: 空态说明
        :param suggestion: 建议操作
        :return: 空态文本行列表
        """
        return [
            TUI_COPY.build_state_section_title('status'),
            f'{empty_label}: {empty_value}',
            '',
            TUI_COPY.build_state_section_title('detail'),
            detail,
            '',
            TUI_COPY.build_state_section_title('suggestion'),
            suggestion,
        ]

    @staticmethod
    def build_loading_lines(
        *,
        loading_label: str,
        loading_value: str,
        detail: str,
        suggestion: str = TUI_COPY.build_loading_state_suggestion(),
    ) -> list[str]:
        """
        构建统一的加载中文本行。

        :param loading_label: 加载态主字段名称
        :param loading_value: 加载态主字段值
        :param detail: 加载说明
        :param suggestion: 建议操作
        :return: 加载态文本行列表
        """
        return [
            TUI_COPY.build_state_section_title('status'),
            f'{loading_label}: {loading_value}',
            '',
            TUI_COPY.build_state_section_title('detail'),
            detail,
            '',
            TUI_COPY.build_state_section_title('suggestion'),
            suggestion,
        ]

    def build_failure_lines(
        self,
        payload: dict[str, object] | None,
        *,
        empty_label: str,
        empty_value: str,
    ) -> list[str]:
        """
        为失败状态构建统一的可读文本行。

        :param payload: 标准结果负载
        :param empty_label: 主字段标签
        :param empty_value: 主字段兜底值
        :return: 失败状态文本行列表
        """
        lines = [
            TUI_COPY.build_state_section_title('status'),
            f'{empty_label}: {empty_value}',
            '',
            TUI_COPY.build_state_section_title('error'),
        ]
        if not isinstance(payload, dict):
            lines.append('结果消息: -')
            lines.extend(
                ['', TUI_COPY.build_state_section_title('suggestion'), TUI_COPY.build_failure_state_suggestion()]
            )
            return lines
        lines.append(f'结果消息: {self.extract_payload_message(payload)}')
        detail_lines: list[str] = []
        if payload.get('hint'):
            detail_lines.append(f'建议提示: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("hint", "-"), 120)}')
        if payload.get('error'):
            detail_lines.append(f'错误信息: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("error", "-"), 120)}')
        if payload.get('stderr'):
            detail_lines.append(f'标准错误: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("stderr", "-"), 120)}')
        if payload.get('stdout'):
            detail_lines.append(f'标准输出: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("stdout", "-"), 120)}')
        if detail_lines:
            lines.extend(['', TUI_COPY.build_state_section_title('diagnostic'), *detail_lines])
        lines.extend(['', TUI_COPY.build_state_section_title('suggestion'), TUI_COPY.build_failure_state_suggestion()])
        return lines


TUI_ADAPTER_MODEL_RENDERER = TuiAdapterModelRenderService()
