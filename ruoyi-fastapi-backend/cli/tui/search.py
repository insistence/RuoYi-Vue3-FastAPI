from collections.abc import Callable
from dataclasses import dataclass, field

from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY, CompletionProviderGateway

CompletionProviderCallable = Callable[[object, list[str] | None, str], list[str]]


@dataclass(frozen=True)
class PageFilterOption:
    """
    浏览页筛选项定义。

    :param key: 筛选键
    :param label: 展示名称
    :param shortcut: 快捷键
    """

    key: str
    label: str
    shortcut: str


@dataclass(frozen=True)
class PageSearchContext:
    """
    浏览页搜索上下文定义。

    :param placeholder: 搜索输入提示
    :param query: 当前搜索词
    :param suggestions: 候选建议列表
    """

    placeholder: str
    query: str = ''
    suggestions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchSuggestionProviderSpec:
    """
    页面搜索建议提供者定义。

    :param placeholder: 搜索输入提示
    :param suggestion_provider: 候选建议提供函数
    """

    placeholder: str
    suggestion_provider: Callable[[str], list[str]] | None = None


JOB_FILTER_OPTIONS: tuple[PageFilterOption, ...] = (
    PageFilterOption('all', '全部', '1'),
    PageFilterOption('failed', '失败', '2'),
    PageFilterOption('paused', '暂停', '3'),
    PageFilterOption('ok', '正常', '4'),
)

CONFIG_FILTER_OPTIONS: tuple[PageFilterOption, ...] = (
    PageFilterOption('all', '全部', '1'),
    PageFilterOption('risky', '高风险', '2'),
    PageFilterOption('mismatch', '值不一致', '3'),
    PageFilterOption('cache-drift', '缓存异常', '4'),
)


class TuiSearchSuggestionProviderRegistry:
    """
    TUI 搜索建议提供者注册表。

    该对象负责管理页面搜索提示文案及其候选建议提供函数，避免搜索服务
    继续通过字符串反射隐式定位 completion provider。

    :param providers: 页面搜索提供者映射
    """

    def __init__(self, providers: dict[str, SearchSuggestionProviderSpec]) -> None:
        """
        初始化搜索建议提供者注册表。

        :param providers: 页面搜索提供者映射
        :return: None
        """
        self.providers = {self.normalize_view_key(key): value for key, value in providers.items()}

    @staticmethod
    def normalize_view_key(view_key: str) -> str:
        """
        规范化页面视图标识。

        :param view_key: 原始页面视图标识
        :return: 规范化后的页面视图标识
        """
        return str(view_key or '').strip().lower()

    def get_provider(self, view_key: str) -> SearchSuggestionProviderSpec | None:
        """
        获取指定页面的搜索建议提供者。

        :param view_key: 页面视图标识
        :return: 搜索建议提供者定义
        """
        return self.providers.get(self.normalize_view_key(view_key))


class CompletionSuggestionProviderFactory:
    """
    基于 completion 注册表构建 TUI 搜索建议提供函数。

    :param completion_provider_gateway: completion 提供器对外网关
    """

    def __init__(self, completion_provider_gateway: CompletionProviderGateway) -> None:
        """
        初始化 completion 搜索建议工厂。

        :param completion_provider_gateway: completion 提供器对外网关
        :return: None
        """
        self.completion_provider_gateway = completion_provider_gateway

    def build(self, provider: CompletionProviderCallable) -> Callable[[str], list[str]]:
        """
        根据显式 completion provider 构建建议提供函数。

        :param provider: completion provider 可调用对象
        :return: 搜索建议提供函数
        """

        def provide(query: str) -> list[str]:
            """
            调用 completion provider 生成候选建议。

            :param query: 当前搜索词
            :return: 候选建议列表
            """
            candidates = provider(None, [], str(query or '').strip())
            return [str(candidate).strip() for candidate in candidates if str(candidate).strip()]

        return provide


def build_default_search_provider_registry(
    completion_provider_gateway: CompletionProviderGateway,
) -> TuiSearchSuggestionProviderRegistry:
    """
    构建默认 TUI 搜索建议提供者注册表。

    :param completion_provider_gateway: completion 提供器对外网关
    :return: 搜索建议提供者注册表
    """
    provider_factory = CompletionSuggestionProviderFactory(completion_provider_gateway)
    return TuiSearchSuggestionProviderRegistry(
        providers={
            'jobs': SearchSuggestionProviderSpec(
                '按任务名搜索',
                provider_factory.build(completion_provider_gateway.complete_job_names),
            ),
            'configs': SearchSuggestionProviderSpec(
                '按配置键搜索',
                provider_factory.build(completion_provider_gateway.complete_config_keys),
            ),
            'cache': SearchSuggestionProviderSpec(
                '按缓存名搜索',
                provider_factory.build(completion_provider_gateway.complete_cache_names),
            ),
            'gen': SearchSuggestionProviderSpec(
                '按业务表名搜索',
                provider_factory.build(completion_provider_gateway.complete_gen_table_names),
            ),
            'database': SearchSuggestionProviderSpec(
                '按 revision 搜索',
                provider_factory.build(completion_provider_gateway.complete_alembic_revisions),
            ),
            'app': SearchSuggestionProviderSpec('按分区或内容搜索'),
            'ops': SearchSuggestionProviderSpec('按分区或内容搜索'),
            'crypto': SearchSuggestionProviderSpec('按分区或内容搜索'),
        }
    )


class TuiSearchHighlighter:
    """
    TUI 搜索高亮器。

    该对象负责对终端文本做轻量关键字高亮。
    """

    @staticmethod
    def highlight(text: str, query: str, *, left_tag: str = '【', right_tag: str = '】') -> str:
        """
        对给定文本中的搜索词做轻量高亮。

        :param text: 原始文本
        :param query: 搜索词
        :param left_tag: 左高亮标记
        :param right_tag: 右高亮标记
        :return: 高亮后的文本
        """
        raw_text = str(text or '')
        normalized_query = str(query or '').strip()
        if not raw_text or not normalized_query:
            return raw_text
        lower_text = raw_text.lower()
        lower_query = normalized_query.lower()
        result: list[str] = []
        cursor = 0
        query_length = len(normalized_query)
        while True:
            index = lower_text.find(lower_query, cursor)
            if index < 0:
                result.append(raw_text[cursor:])
                break
            result.append(raw_text[cursor:index])
            result.append(f'{left_tag}{raw_text[index : index + query_length]}{right_tag}')
            cursor = index + query_length
        return ''.join(result)


class TuiSearchService:
    """
    TUI 搜索服务。

    该对象负责筛选项解析、筛选条文案构建、搜索上下文装配和详情分区过滤。
    """

    def __init__(self, provider_registry: TuiSearchSuggestionProviderRegistry) -> None:
        """
        初始化 TUI 搜索服务。

        :param provider_registry: 页面搜索建议提供者注册表
        :return: None
        """
        self.provider_registry = provider_registry

    @staticmethod
    def resolve_filter_option(
        options: list[PageFilterOption] | tuple[PageFilterOption, ...],
        filter_key: str | None,
    ) -> PageFilterOption | None:
        """
        从筛选项列表中解析指定键对应的筛选定义。

        :param options: 筛选项列表
        :param filter_key: 筛选键
        :return: 匹配到的筛选项
        """
        normalized_key = str(filter_key or '').strip().lower()
        if not normalized_key:
            return None
        for option in options:
            if option.key == normalized_key:
                return option
        return None

    def build_filter_bar_text(
        self,
        options: list[PageFilterOption] | tuple[PageFilterOption, ...],
        active_filter_key: str | None,
        *,
        search_query: str | None = None,
        search_placeholder: str | None = None,
        search_suggestions: list[str] | None = None,
    ) -> str:
        """
        构建浏览页顶部筛选条文本。

        :param options: 筛选项列表
        :param active_filter_key: 当前激活筛选键
        :param search_query: 当前搜索词
        :param search_placeholder: 搜索提示文本
        :param search_suggestions: 搜索候选建议
        :return: 筛选条文本
        """
        if not options and not search_placeholder:
            return ''
        lines: list[str] = []
        normalized_active = str(active_filter_key or '').strip().lower()
        if options:
            rendered_items = [
                f'[{option.shortcut}] {option.label}{" *" if option.key == normalized_active else ""}'
                for option in options
            ]
            active_option = self.resolve_filter_option(options, normalized_active)
            active_label = active_option.label if active_option is not None else '未指定'
            lines.extend(
                [
                    f'筛选器 · {"  ".join(rendered_items)}',
                    f'当前筛选 · {active_label}',
                ]
            )
        if search_placeholder:
            normalized_query = str(search_query or '').strip()
            lines.append(f'搜索器 · [/] {search_placeholder}')
            lines.append(f'当前搜索 · {normalized_query or "未指定"}  |  [Backspace] 清空')
            if search_suggestions:
                lines.append(f'候选建议 · {"  ".join(search_suggestions[:4])}')
        return '\n'.join(lines)

    def resolve_search_context(
        self,
        view_key: str,
        query: str = '',
        *,
        default_suggestions: list[str] | None = None,
    ) -> PageSearchContext | None:
        """
        根据页面视图解析搜索上下文，并复用 completion provider 生成候选建议。

        :param view_key: 当前页面视图标识
        :param query: 当前搜索词
        :param default_suggestions: 缺省候选建议
        :return: 搜索上下文
        """
        normalized_view = str(view_key).strip().lower()
        provider_spec = self.provider_registry.get_provider(normalized_view)
        if provider_spec is None:
            return None
        suggestions = self.resolve_search_suggestions(provider_spec, query)
        if not suggestions and default_suggestions:
            normalized_query = str(query or '').strip().lower()
            suggestions = [
                suggestion
                for suggestion in default_suggestions
                if suggestion and (not normalized_query or normalized_query in suggestion.lower())
            ]
        return PageSearchContext(
            placeholder=provider_spec.placeholder,
            query=str(query or '').strip(),
            suggestions=suggestions[:6],
        )

    @staticmethod
    def resolve_search_suggestions(provider_spec: SearchSuggestionProviderSpec, query: str) -> list[str]:
        """
        调用搜索建议提供函数生成当前搜索词的候选建议。

        :param provider_spec: 搜索建议提供者定义
        :param query: 当前搜索词
        :return: 候选建议列表
        """
        normalized_query = str(query or '').strip()
        if not normalized_query or not callable(provider_spec.suggestion_provider):
            return []
        try:
            candidates = provider_spec.suggestion_provider(normalized_query)
        except Exception:
            return []
        return [str(candidate).strip() for candidate in candidates if str(candidate).strip()]

    @staticmethod
    def filter_detail_sections(sections: list[object], query: str) -> list[object]:
        """
        按搜索词过滤详情页分区列表。

        :param sections: 原始分区列表
        :param query: 当前搜索词
        :return: 过滤后的分区列表
        """
        normalized_query = str(query or '').strip().lower()
        if not normalized_query:
            return sections
        filtered_sections: list[object] = []
        for section in sections:
            title = str(getattr(section, 'title', '') or '').strip().lower()
            lines = getattr(section, 'lines', [])
            joined_lines = ' '.join(str(line).strip().lower() for line in lines if str(line).strip())
            if normalized_query in title or normalized_query in joined_lines:
                filtered_sections.append(section)
        return filtered_sections


TUI_SEARCH_HIGHLIGHTER = TuiSearchHighlighter()
TUI_SEARCH_PROVIDER_REGISTRY = build_default_search_provider_registry(COMPLETION_PROVIDER_GATEWAY)
TUI_SEARCH_SERVICE = TuiSearchService(TUI_SEARCH_PROVIDER_REGISTRY)
