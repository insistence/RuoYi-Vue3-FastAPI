from typing import Any

from cli.tui.adapters.base import BaseBrowserAdapter
from cli.tui.adapters.models import (
    TUI_ADAPTER_MODEL_RENDERER,
    BrowserPageSnapshot,
    BrowserRecordSnapshot,
    DetailSectionSnapshot,
)
from cli.tui.copy import TUI_COPY
from cli.tui.diagnostics import TUI_DIAGNOSTIC_SERVICE
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER


class CacheRowExtractor:
    """
    缓存浏览行提取器。

    该对象负责从缓存统计结果中提取缓存名称列表，供共享分区和记录构建
    逻辑复用。
    """

    @staticmethod
    def extract_cache_name_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        """
        从缓存统计结果中提取缓存名称列表。

        :param payload: `cache stats` JSON 负载
        :return: 缓存名称行列表
        """
        if not isinstance(payload, dict):
            return []
        cache_names = payload.get('cacheNames')
        if not isinstance(cache_names, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in cache_names:
            if isinstance(item, dict):
                rows.append(item)
                continue
            if isinstance(item, str):
                rows.append({'cacheName': item, 'remark': ''})
        return rows


class CacheSectionBuilder:
    """
    缓存浏览页分区构建器。

    该构建器负责构建缓存浏览页共享分区，以及单个缓存名前缀下的键摘要、
    键列表和键详情分区。

    :param page_adapter: 缓存浏览页适配器
    :param row_extractor: 缓存浏览行提取器
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        row_extractor: CacheRowExtractor | None = None,
    ) -> None:
        """
        初始化缓存浏览页分区构建器。

        :param page_adapter: 缓存浏览页适配器
        :param row_extractor: 缓存浏览行提取器
        :return: None
        """
        self.page_adapter = page_adapter
        self.row_extractor = row_extractor or CacheRowExtractor()

    def build_overview_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建缓存总览共享分区。

        :param payload: `cache stats` JSON 负载
        :return: 分区快照
        """
        info = payload.get('info') if isinstance(payload, dict) and isinstance(payload.get('info'), dict) else {}
        cache_rows = self.row_extractor.extract_cache_name_rows(payload)
        return DetailSectionSnapshot(
            title='Redis 摘要',
            status='ok' if isinstance(payload, dict) and payload.get('ok', False) else 'fail',
            lines=[
                '## 容量状态',
                f'当前键数: {payload.get("dbSize", "-") if isinstance(payload, dict) else "-"}',
                f'已登记缓存名: {len(cache_rows)} 个',
                '',
                '## 运行指标',
                f'Redis 版本: {info.get("redis_version", "-")}',
                f'客户端连接数: {info.get("connected_clients", "-")}',
                f'内存占用: {info.get("used_memory_human", info.get("used_memory", "-"))}',
            ],
        )

    def build_overview_judgement_section(
        self,
        payload: dict[str, Any] | None,
        filtered_rows: list[dict[str, Any]],
    ) -> DetailSectionSnapshot:
        """
        构建缓存页总览判断共享分区。

        :param payload: `cache stats` JSON 负载
        :param filtered_rows: 当前筛选后的缓存名列表
        :return: 分区快照
        """
        info = payload.get('info') if isinstance(payload, dict) and isinstance(payload.get('info'), dict) else {}
        cache_rows = self.row_extractor.extract_cache_name_rows(payload)
        db_size = payload.get('dbSize', '-') if isinstance(payload, dict) else '-'
        client_count = info.get('connected_clients', '-')
        command_stats = payload.get('commandStats') if isinstance(payload, dict) else None
        command_count = len(command_stats) if isinstance(command_stats, list) else 0

        status = 'ok'
        conclusion = '缓存基线正常，可继续查看键列表、键值样本与 TTL'
        if not isinstance(payload, dict) or not payload.get('ok', False):
            status = 'fail'
            conclusion = '缓存状态读取失败，优先确认 Redis 连通性与运行环境'
        elif not cache_rows:
            status = 'info'
            conclusion = '当前没有登记的缓存名前缀，可先核对缓存配置与实际键空间'
        elif not filtered_rows:
            status = 'info'
            conclusion = '当前搜索条件没有命中缓存名前缀，可调整关键字后继续排查'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'已登记缓存名: {len(cache_rows)} 个',
                f'当前匹配: {len(filtered_rows)} 个',
                f'Redis 键数: {db_size}',
                f'客户端连接数: {client_count}',
                f'命令统计样本: {command_count} 组',
                '',
                '## 建议入口',
                '优先关注：Redis 摘要 / 命令统计 / 键值样本 / TTL',
            ],
        )

    def build_top_commands_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建缓存命令统计共享分区。

        :param payload: `cache stats` JSON 负载
        :return: 分区快照
        """
        command_stats = payload.get('commandStats') if isinstance(payload, dict) else None
        lines = TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
            empty_label='命令统计',
            empty_value='暂无数据',
            detail='当前 Redis 运行快照中未返回命令统计样本',
        )
        section_status = 'info'
        if isinstance(command_stats, list) and command_stats:
            section_status = 'ok'
            lines = [
                f'{item.get("name", "-")} · {item.get("value", 0)} 次'
                for item in command_stats[:8]
                if isinstance(item, dict)
            ]
        return DetailSectionSnapshot(
            title='命令统计',
            status=section_status if isinstance(payload, dict) and payload.get('ok', False) else 'fail',
            lines=lines,
        )

    @staticmethod
    def build_cache_clear_entry_section() -> DetailSectionSnapshot:
        """
        构建缓存清理向导入口分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='缓存清理入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='当缓存命中异常、键数量失控，或需要按缓存名和前缀清理时，应先通过向导确认影响范围。',
                command=TUI_COPY.build_cli_command_hint('wizard', 'cache-clear', '--output=text'),
                guide='向导会继续询问环境、缓存名、键前缀和 dry-run 选项，确认后再执行实际清理。',
            ),
        )

    def build_keys_summary_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建缓存键摘要分区。

        :param payload: `cache keys` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='键摘要',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='键摘要', empty_value='不可用'
                ),
            )
        keys = payload.get('keys') if isinstance(payload.get('keys'), list) else []
        rendered_keys = [str(item).strip() for item in keys if str(item).strip()]
        lines = [
            '## 统计',
            f'缓存名: {payload.get("cacheName", "-")}',
            f'键数量: {payload.get("count", len(rendered_keys))}',
        ]
        if rendered_keys:
            lines.extend(
                ['', '## 键样本', *[f'> {SHELL_TEXT_FORMATTER.truncate_text(item, 64)}' for item in rendered_keys[:5]]]
            )
        else:
            lines.extend(['', '## 键样本', '> 当前缓存名前缀下没有键'])
        return DetailSectionSnapshot(
            title='键摘要',
            status='ok',
            lines=lines,
        )

    def build_keys_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建缓存键列表分区。

        :param payload: `cache keys` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='键列表',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='键列表', empty_value='不可用'
                ),
            )
        keys = payload.get('keys') if isinstance(payload.get('keys'), list) else []
        lines = [
            SHELL_TEXT_FORMATTER.truncate_text(item, 88) for item in keys[:12] if str(item).strip()
        ] or TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
            empty_label='缓存键',
            empty_value='0 个',
            detail='当前缓存名前缀下没有可展示的缓存键',
        )
        return DetailSectionSnapshot(
            title='键列表',
            status='ok',
            lines=lines,
        )

    def render_ttl_text(self, payload: dict[str, Any] | None) -> str:
        """
        渲染缓存 TTL 文本。

        :param payload: `cache ttl` JSON 负载
        :return: TTL 文本
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return SHELL_TEXT_FORMATTER.truncate_text(self.page_adapter.extract_payload_message(payload), 56)
        ttl_seconds = payload.get('ttlSeconds', '-')
        if payload.get('persistent', False):
            return '永久'
        if payload.get('expires', False):
            return f'{ttl_seconds} 秒'
        return str(ttl_seconds)

    def build_key_detail_sections(
        self,
        cache_name: str,
        key_items: list[str],
        env: str,
    ) -> list[DetailSectionSnapshot]:
        """
        构建按缓存键展开的详情分区。

        :param cache_name: 缓存名称
        :param key_items: 缓存键列表
        :param env: 当前运行环境
        :return: 分区快照列表
        """
        if not key_items:
            return []

        sections: list[DetailSectionSnapshot] = []
        for cache_key in key_items[:5]:
            value_payload = NESTED_CLI_SUPPORT.run(
                'cache',
                'get',
                cache_name,
                cache_key,
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload
            ttl_payload = NESTED_CLI_SUPPORT.run(
                'cache',
                'ttl',
                cache_name,
                cache_key,
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload

            value_ok = isinstance(value_payload, dict) and value_payload.get('ok', False)
            ttl_ok = isinstance(ttl_payload, dict) and ttl_payload.get('ok', False)
            if value_ok and ttl_ok:
                section_status = 'ok'
            elif value_ok or ttl_ok:
                section_status = 'warn'
            else:
                section_status = 'fail'

            cache_value = (
                '' if not value_ok or value_payload.get('cacheValue') is None else str(value_payload.get('cacheValue'))
            )
            preview_lines = cache_value.splitlines()[:6]
            ttl_text = self.render_ttl_text(ttl_payload)
            lines = [
                '## 键信息',
                f'缓存名: {cache_name}',
                f'缓存键: {SHELL_TEXT_FORMATTER.truncate_text(cache_key, 72)}',
                f'TTL: {ttl_text}',
                '',
                '## 值预览',
            ]
            if value_ok:
                lines.extend(
                    [f'> {SHELL_TEXT_FORMATTER.truncate_text(line, 72)}' for line in preview_lines]
                    if preview_lines
                    else ['> -']
                )
            else:
                lines.append(
                    f'> {SHELL_TEXT_FORMATTER.truncate_text(self.page_adapter.extract_payload_message(value_payload), 72)}'
                )
            if not ttl_ok:
                lines.extend(
                    [
                        '',
                        '## TTL 结果',
                        f'> {SHELL_TEXT_FORMATTER.truncate_text(self.page_adapter.extract_payload_message(ttl_payload), 72)}',
                    ]
                )
            sections.append(
                DetailSectionSnapshot(
                    title=f'键详情 · {SHELL_TEXT_FORMATTER.truncate_text(cache_key, 28)}',
                    status=section_status,
                    lines=lines,
                )
            )
        return sections

    def load_cache_detail_sections(
        self,
        cache_row: dict[str, Any],
        env: str,
    ) -> list[DetailSectionSnapshot]:
        """
        按需加载单个缓存名称的详情分区。

        :param cache_row: 缓存名称行数据
        :param env: 当前运行环境
        :return: 详情分区列表
        """
        cache_name = str(cache_row.get('cacheName', '-') or '-')
        keys_payload = NESTED_CLI_SUPPORT.run(
            'cache',
            'keys',
            cache_name,
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload
        key_items: list[str] = []
        if isinstance(keys_payload, dict) and keys_payload.get('ok', False):
            raw_keys = keys_payload.get('keys') if isinstance(keys_payload.get('keys'), list) else []
            key_items = [str(item).strip() for item in raw_keys if str(item).strip()]
        return [
            self.build_keys_summary_section(keys_payload),
            self.build_keys_section(keys_payload),
            *self.build_key_detail_sections(cache_name, key_items, env),
        ]

    def build_shared_sections(
        self,
        payload: dict[str, Any] | None,
        filtered_rows: list[dict[str, Any]],
    ) -> list[DetailSectionSnapshot]:
        """
        构建缓存浏览页共享分区。

        :param payload: `cache stats` 结果负载
        :param filtered_rows: 当前筛选后的缓存名列表
        :return: 共享分区列表
        """
        return [
            self.build_overview_judgement_section(payload, filtered_rows),
            self.build_overview_section(payload),
            self.build_top_commands_section(payload),
            self.build_cache_clear_entry_section(),
        ]


class CacheRecordBuilder:
    """
    缓存浏览记录构建器。

    该对象负责构建缓存页单条浏览记录与失败兜底记录。

    :param page_adapter: 缓存浏览页适配器
    :param section_builder: 缓存浏览页分区构建器
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        section_builder: CacheSectionBuilder,
    ) -> None:
        """
        初始化缓存浏览记录构建器。

        :param page_adapter: 缓存浏览页适配器
        :param section_builder: 缓存浏览页分区构建器
        :return: None
        """
        self.page_adapter = page_adapter
        self.section_builder = section_builder

    def build_record(self, cache_row: dict[str, Any], env: str) -> BrowserRecordSnapshot:
        """
        构建单条缓存浏览记录。

        :param cache_row: 缓存名称行数据
        :param env: 当前运行环境
        :return: 浏览记录快照
        """
        cache_name = str(cache_row.get('cacheName', '-') or '-')
        remark = str(cache_row.get('remark', '') or '').strip()
        return BrowserRecordSnapshot(
            key=f'cache:{cache_name}',
            title=SHELL_TEXT_FORMATTER.truncate_text(cache_name, 40),
            status='ok',
            summary=SHELL_TEXT_FORMATTER.truncate_text(remark or '查看当前缓存名前缀下的键、值样本和过期时间', 64),
            metadata_lines=[
                '## 缓存身份',
                f'缓存名称: {cache_name}',
                f'用途说明: {SHELL_TEXT_FORMATTER.truncate_text(remark or "-", 64)}',
            ],
            detail_sections=[],
            detail_loader=lambda cache_row=cache_row, env=env: self.section_builder.load_cache_detail_sections(
                cache_row, env
            ),
        )

    def build_failure_record(self, payload: dict[str, Any] | None) -> BrowserRecordSnapshot:
        """
        构建缓存页失败兜底记录。

        :param payload: 失败结果负载
        :return: 浏览记录快照
        """
        return self.page_adapter.build_failure_record(
            key='cache:unavailable',
            subject='缓存',
            section_subject='缓存状态',
            payload=payload,
        )


class CacheBrowserAdapter(BaseBrowserAdapter):
    """
    缓存浏览页适配器。

    该适配器负责采集 Redis 统计和缓存名前缀列表，并委托协作对象构建
    共享分区、单条记录与键详情分区。
    """

    def __init__(
        self,
        row_extractor: CacheRowExtractor | None = None,
        section_builder: CacheSectionBuilder | None = None,
        record_builder: CacheRecordBuilder | None = None,
    ) -> None:
        """
        初始化缓存浏览页适配器。

        :param row_extractor: 缓存浏览行提取器
        :param section_builder: 缓存浏览页分区构建器
        :param record_builder: 缓存浏览记录构建器
        :return: None
        """
        super().__init__(
            page_title='缓存',
            search_view_key='cache',
            filter_options=(),
        )
        self.row_extractor = row_extractor or CacheRowExtractor()
        self.section_builder = section_builder or CacheSectionBuilder(self, self.row_extractor)
        self.record_builder = record_builder or CacheRecordBuilder(self, self.section_builder)

    @staticmethod
    def apply_cache_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        """
        按缓存名或备注查询词过滤缓存行数据。

        :param rows: 原始缓存行列表
        :param query: 当前搜索词
        :return: 过滤后的缓存行列表
        """
        normalized_query = str(query).strip().lower()
        if not normalized_query:
            return rows
        return [
            row
            for row in rows
            if normalized_query in str(row.get('cacheName', '') or '').strip().lower()
            or normalized_query in str(row.get('remark', '') or '').strip().lower()
        ]

    def collect_snapshot(self, env: str, query: str = '') -> BrowserPageSnapshot:
        """
        采集缓存浏览页只读快照。

        :param env: 当前运行环境
        :param query: 当前搜索词
        :return: 浏览页快照
        """
        search_context = self.resolve_search_context(query)
        payload = NESTED_CLI_SUPPORT.run(
            'cache',
            'stats',
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload
        cache_rows = self.row_extractor.extract_cache_name_rows(payload)
        filtered_rows = self.apply_cache_query(cache_rows, query)
        shared_sections = self.section_builder.build_shared_sections(payload, filtered_rows)
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return BrowserPageSnapshot(
                title='缓存',
                subtitle=TUI_COPY.build_unavailable_subtitle(
                    '缓存状态',
                    SHELL_TEXT_FORMATTER.truncate_text(self.extract_payload_message(payload), 72),
                ),
                records=[self.record_builder.build_failure_record(payload)],
                shared_sections=shared_sections,
                search=search_context,
            )

        records = [self.record_builder.build_record(cache_row, env) for cache_row in filtered_rows[:12]]
        if not records:
            records = [
                self.build_empty_record(
                    key='cache:none',
                    subject='缓存名',
                    empty_label='缓存名前缀',
                    has_source_rows=bool(cache_rows),
                    filtered_summary='当前搜索条件下没有匹配缓存名前缀',
                    empty_summary='当前运行环境没有登记可浏览的缓存名前缀',
                    filtered_empty_value='暂无匹配',
                    empty_empty_value='暂无登记',
                    filtered_detail='当前搜索条件下没有匹配缓存名前缀',
                    empty_detail='当前运行环境没有登记可浏览的缓存名前缀',
                )
            ]
        return BrowserPageSnapshot(
            title='缓存',
            subtitle=TUI_DIAGNOSTIC_SERVICE.build_cache_diagnostic_subtitle(payload, len(filtered_rows)),
            records=records,
            shared_sections=shared_sections,
            search=search_context,
        )


CACHE_BROWSER_ADAPTER = CacheBrowserAdapter()
