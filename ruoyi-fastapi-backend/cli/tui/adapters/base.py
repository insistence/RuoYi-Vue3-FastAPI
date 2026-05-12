from collections.abc import Sequence
from typing import Any

from cli.tui.adapters.models import (
    TUI_ADAPTER_MODEL_RENDERER,
    BrowserRecordSnapshot,
    DetailSectionSnapshot,
)
from cli.tui.copy import TUI_COPY
from cli.tui.search import TUI_SEARCH_SERVICE, PageFilterOption, PageSearchContext
from cli.utils import SHELL_TEXT_FORMATTER


class BaseBrowserAdapter:
    """
    TUI 浏览页适配基类。

    :param page_title: 浏览页标题
    :param search_view_key: 搜索上下文对应的页面键
    :param filter_options: 页面支持的筛选项
    """

    def __init__(
        self,
        *,
        page_title: str,
        search_view_key: str,
        filter_options: Sequence[PageFilterOption],
    ) -> None:
        """
        初始化浏览页适配基类。

        :param page_title: 浏览页标题
        :param search_view_key: 搜索上下文对应的页面键
        :param filter_options: 页面支持的筛选项
        :return: None
        """
        self.page_title = page_title
        self.search_view_key = search_view_key
        self.filter_options = tuple(filter_options)

    @staticmethod
    def extract_page_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        """
        从标准分页 JSON 负载中提取行数据。

        :param payload: 标准分页结果负载
        :return: 行数据列表
        """
        page_payload = payload.get('page') if isinstance(payload, dict) else None
        rows = page_payload.get('rows') if isinstance(page_payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def resolve_active_filter(self, filter_key: str) -> PageFilterOption:
        """
        解析当前激活筛选项。

        :param filter_key: 筛选键
        :return: 已解析的筛选项
        """
        return TUI_SEARCH_SERVICE.resolve_filter_option(self.filter_options, filter_key) or self.filter_options[0]

    def resolve_search_context(self, query: str) -> PageSearchContext:
        """
        解析当前页面搜索上下文。

        :param query: 搜索词
        :return: 搜索上下文
        """
        return TUI_SEARCH_SERVICE.resolve_search_context(self.search_view_key, query)

    def build_failure_record(
        self,
        *,
        key: str,
        subject: str,
        section_subject: str,
        payload: dict[str, Any] | None,
    ) -> BrowserRecordSnapshot:
        """
        构建底层命令失败时的兜底记录。

        :param key: 记录键
        :param subject: 页面主体名称
        :param section_subject: 失败分区名称
        :param payload: 失败结果负载
        :return: 浏览记录快照
        """
        return BrowserRecordSnapshot(
            key=key,
            title=TUI_COPY.build_unavailable_record_title(subject),
            status='fail',
            summary=SHELL_TEXT_FORMATTER.truncate_text(self.extract_payload_message(payload), 64),
            metadata_lines=[],
            detail_sections=[
                DetailSectionSnapshot(
                    title=TUI_COPY.build_load_failure_section_title(section_subject),
                    status='fail',
                    lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                        payload, empty_label=section_subject, empty_value='不可用'
                    ),
                )
            ],
        )

    def build_empty_record(
        self,
        *,
        key: str,
        subject: str,
        empty_label: str,
        has_source_rows: bool,
        filtered_summary: str,
        empty_summary: str,
        filtered_empty_value: str,
        empty_empty_value: str,
        filtered_detail: str,
        empty_detail: str,
    ) -> BrowserRecordSnapshot:
        """
        构建当前页面没有可浏览记录时的空态记录。

        :param key: 记录键
        :param subject: 记录主体名称
        :param empty_label: 空态主字段名称
        :param has_source_rows: 是否存在未筛选前的源数据
        :param filtered_summary: 有源数据但当前筛选无结果时的摘要
        :param empty_summary: 源数据本身为空时的摘要
        :param filtered_empty_value: 有源数据但当前筛选无结果时的空态值
        :param empty_empty_value: 源数据本身为空时的空态值
        :param filtered_detail: 有源数据但当前筛选无结果时的说明
        :param empty_detail: 源数据本身为空时的说明
        :return: 浏览记录快照
        """
        summary = filtered_summary if has_source_rows else empty_summary
        empty_value = filtered_empty_value if has_source_rows else empty_empty_value
        detail = filtered_detail if has_source_rows else empty_detail
        return BrowserRecordSnapshot(
            key=key,
            title=TUI_COPY.build_empty_record_title(subject),
            status='info',
            summary=TUI_COPY.build_empty_record_summary(summary),
            metadata_lines=[],
            detail_sections=[
                DetailSectionSnapshot(
                    title=TUI_COPY.build_empty_record_title(subject),
                    status='info',
                    lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                        empty_label=empty_label,
                        empty_value=empty_value,
                        detail=detail,
                    ),
                )
            ],
        )

    @staticmethod
    def extract_payload_message(payload: dict[str, object] | None) -> str:
        """
        提取结果负载中的可读消息。

        :param payload: 标准结果负载
        :return: 摘要消息文本
        """
        return TUI_ADAPTER_MODEL_RENDERER.extract_payload_message(payload)


class BaseDetailAdapter:
    """
    TUI 详情页适配基类。

    :param page_title: 详情页标题
    :param search_view_key: 搜索上下文对应的页面键
    :param default_suggestions: 默认搜索建议
    """

    def __init__(
        self,
        *,
        page_title: str,
        search_view_key: str,
        default_suggestions: Sequence[str],
    ) -> None:
        """
        初始化详情页适配基类。

        :param page_title: 详情页标题
        :param search_view_key: 搜索上下文对应的页面键
        :param default_suggestions: 默认搜索建议
        :return: None
        """
        self.page_title = page_title
        self.search_view_key = search_view_key
        self.default_suggestions = tuple(default_suggestions)

    def filter_sections(self, sections: Sequence[DetailSectionSnapshot], query: str) -> list[DetailSectionSnapshot]:
        """
        按搜索词过滤详情分区列表。

        :param sections: 原始详情分区列表
        :param query: 搜索词
        :return: 过滤后的分区列表
        """
        return TUI_SEARCH_SERVICE.filter_detail_sections(list(sections), query)  # type: ignore[arg-type]

    def resolve_search_context(self, query: str) -> PageSearchContext:
        """
        解析当前详情页搜索上下文。

        :param query: 搜索词
        :return: 搜索上下文
        """
        return TUI_SEARCH_SERVICE.resolve_search_context(
            self.search_view_key,
            query,
            default_suggestions=list(self.default_suggestions),
        )
