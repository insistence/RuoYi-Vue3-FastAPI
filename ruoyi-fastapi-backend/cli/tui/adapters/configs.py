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
from cli.tui.search import CONFIG_FILTER_OPTIONS
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER

CONFIG_RISK_PRIORITY = {
    'mismatch': 0,
    'missing-cache': 1,
    'orphan-cache': 2,
    'normal': 3,
}

CONFIG_RISK_LABELS = {
    'mismatch': '值不一致',
    'missing-cache': '缓存缺失',
    'orphan-cache': '缓存孤立',
    'normal': '正常',
}

CONFIG_RISK_STATUSES = {
    'mismatch': 'fail',
    'missing-cache': 'warn',
    'orphan-cache': 'warn',
    'normal': 'ok',
}


class ConfigRiskSupport:
    """
    参数配置风险分类支持对象。

    该对象负责从巡检结果提取风险集合、解析单项风险分类，以及执行
    风险排序和筛选逻辑，供浏览页分区和记录构建复用。
    """

    @staticmethod
    def extract_config_issue_keys(payload: dict[str, Any] | None, field_name: str) -> set[str]:
        """
        从配置巡检结果中提取指定风险字段对应的配置键集合。

        :param payload: `config doctor` JSON 负载
        :param field_name: 风险字段名
        :return: 配置键集合
        """
        items = payload.get(field_name) if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return set()
        return {item.strip() for item in items if isinstance(item, str) and item.strip()}

    def build_config_risk_sets(self, payload: dict[str, Any] | None) -> dict[str, set[str]]:
        """
        构建配置风险分类集合。

        :param payload: `config doctor` JSON 负载
        :return: 按风险分类聚合的配置键集合
        """
        return {
            'mismatch': self.extract_config_issue_keys(payload, 'mismatchKeys'),
            'missing-cache': self.extract_config_issue_keys(payload, 'missingInCache'),
            'orphan-cache': self.extract_config_issue_keys(payload, 'orphanInCache'),
        }

    @staticmethod
    def resolve_config_risk_key(config_key: str, risk_sets: dict[str, set[str]]) -> str:
        """
        解析单个配置项的风险分类。

        :param config_key: 配置键
        :param risk_sets: 风险集合
        :return: 风险分类键
        """
        normalized_key = str(config_key).strip()
        if normalized_key in risk_sets.get('mismatch', set()):
            return 'mismatch'
        if normalized_key in risk_sets.get('missing-cache', set()):
            return 'missing-cache'
        if normalized_key in risk_sets.get('orphan-cache', set()):
            return 'orphan-cache'
        return 'normal'

    def build_config_sort_key(
        self,
        config_row: dict[str, Any],
        risk_sets: dict[str, set[str]],
    ) -> tuple[int, str]:
        """
        构建配置列表排序键。

        :param config_row: 配置项行数据
        :param risk_sets: 风险集合
        :return: 排序键
        """
        config_key = str(config_row.get('configKey', '') or '').strip()
        risk_key = self.resolve_config_risk_key(config_key, risk_sets)
        return (CONFIG_RISK_PRIORITY.get(risk_key, 99), config_key)

    def apply_config_filter(
        self,
        rows: list[dict[str, Any]],
        risk_sets: dict[str, set[str]],
        filter_key: str,
    ) -> list[dict[str, Any]]:
        """
        按筛选键过滤配置行数据。

        :param rows: 原始配置行列表
        :param risk_sets: 风险集合
        :param filter_key: 当前筛选键
        :return: 过滤后的配置行列表
        """
        normalized_filter = str(filter_key).strip().lower()
        if normalized_filter == 'risky':
            return [
                row
                for row in rows
                if self.resolve_config_risk_key(str(row.get('configKey', '') or ''), risk_sets) != 'normal'
            ]
        if normalized_filter == 'mismatch':
            return [
                row
                for row in rows
                if self.resolve_config_risk_key(str(row.get('configKey', '') or ''), risk_sets) == 'mismatch'
            ]
        if normalized_filter == 'cache-drift':
            return [
                row
                for row in rows
                if self.resolve_config_risk_key(str(row.get('configKey', '') or ''), risk_sets)
                in {'missing-cache', 'orphan-cache'}
            ]
        return rows

    @staticmethod
    def apply_config_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        """
        按配置键或配置名称查询词过滤配置行数据。

        :param rows: 原始配置行列表
        :param query: 当前搜索词
        :return: 过滤后的配置行列表
        """
        normalized_query = str(query).strip().lower()
        if not normalized_query:
            return rows
        return [
            row
            for row in rows
            if normalized_query in str(row.get('configKey', '') or '').strip().lower()
            or normalized_query in str(row.get('configName', '') or '').strip().lower()
        ]

    @staticmethod
    def append_orphan_cache_rows(rows: list[dict[str, Any]], orphan_keys: set[str]) -> list[dict[str, Any]]:
        """
        将仅存在于缓存侧的孤立配置补充为可浏览记录。

        :param rows: 原始数据库配置行
        :param orphan_keys: 缓存孤立配置键集合
        :return: 补齐后的配置行列表
        """
        merged_rows = list(rows)
        existing_keys = {str(row.get('configKey', '') or '').strip() for row in rows}
        merged_rows.extend(
            {
                'configId': '-',
                'configKey': orphan_key,
                'configName': '缓存孤立配置',
                'configType': '-',
                'configValue': '缓存侧残留，建议排查来源',
            }
            for orphan_key in sorted(orphan_keys - existing_keys)
        )
        return merged_rows


class ConfigSectionBuilder:
    """
    参数配置浏览页分区构建器。

    该构建器负责构建参数配置页共享分区，以及单个配置项详情分区。

    :param page_adapter: 参数配置浏览页适配器
    :param risk_support: 参数配置风险分类支持对象
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        risk_support: ConfigRiskSupport,
    ) -> None:
        """
        初始化参数配置浏览页分区构建器。

        :param page_adapter: 参数配置浏览页适配器
        :param risk_support: 参数配置风险分类支持对象
        :return: None
        """
        self.page_adapter = page_adapter
        self.risk_support = risk_support

    def build_config_doctor_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建参数配置巡检共享分区。

        :param payload: `config doctor` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='配置巡检',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='巡检结果', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='配置巡检',
            status='ok',
            lines=[
                '## 一致性状态',
                f'数据库配置: {payload.get("databaseCount", "-")} 项',
                f'缓存同步配置: {payload.get("cacheCount", "-")} 项',
                f'缓存缺失: {payload.get("missingInCacheCount", "-")} 项',
                f'缓存孤立: {payload.get("orphanInCacheCount", "-")} 项',
                f'值不一致: {payload.get("mismatchCount", "-")} 项',
            ],
        )

    def build_config_issue_samples_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建参数配置不一致样本共享分区。

        :param payload: `config doctor` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='异常样本',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='样本', empty_value='不可用'),
            )

        lines: list[str] = []
        missing_in_cache = payload.get('missingInCache')
        orphan_in_cache = payload.get('orphanInCache')
        mismatch_keys = payload.get('mismatchKeys')

        if isinstance(missing_in_cache, list) and missing_in_cache:
            lines.extend(
                f'缓存缺失示例：{SHELL_TEXT_FORMATTER.truncate_text(item, 64)}'
                for item in missing_in_cache[:5]
                if isinstance(item, str)
            )
        if isinstance(orphan_in_cache, list) and orphan_in_cache:
            lines.extend(
                f'缓存孤立示例：{SHELL_TEXT_FORMATTER.truncate_text(item, 64)}'
                for item in orphan_in_cache[:5]
                if isinstance(item, str)
            )
        if isinstance(mismatch_keys, list) and mismatch_keys:
            lines.extend(
                f'值不一致示例：{SHELL_TEXT_FORMATTER.truncate_text(item, 64)}'
                for item in mismatch_keys[:5]
                if isinstance(item, str)
            )

        issue_count = (
            int(payload.get('missingInCacheCount', 0))
            + int(payload.get('orphanInCacheCount', 0))
            + int(payload.get('mismatchCount', 0))
        )
        return DetailSectionSnapshot(
            title='异常样本',
            status='fail' if issue_count > 0 else 'ok',
            lines=lines
            if lines
            else TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                empty_label='异常样本',
                empty_value='0 条',
                detail='当前未发现配置异常样本',
            ),
        )

    def build_config_set_entry_section(self, rows: list[dict[str, Any]]) -> DetailSectionSnapshot:
        """
        构建配置变更入口共享分区。

        :param rows: 当前配置行列表
        :return: 分区快照
        """
        sample_key = ''
        sample_value = ''
        for row in rows:
            config_key = str(row.get('configKey', '') or '').strip()
            config_value = str(row.get('configValue', '') or '').strip()
            if config_key:
                sample_key = config_key
                sample_value = config_value or 'new-value'
                break
        if not sample_key:
            sample_key = 'demo.config.key'
            sample_value = 'new-value'
        return DetailSectionSnapshot(
            title='配置变更入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备修复高风险配置、回填缓存缺失项或校正数据库与缓存值不一致时，应先在终端中明确目标键和值，再执行配置变更命令。',
                command=TUI_COPY.build_cli_command_hint('config', 'set', sample_key, sample_value, '--output=text'),
                guide='建议先在当前页面核对配置键、来源和现值；变更完成后再回到工作台执行参数缓存刷新，确认巡检结果恢复正常。',
            ),
        )

    def build_high_risk_config_section(
        self,
        rows: list[dict[str, Any]],
        risk_sets: dict[str, set[str]],
    ) -> DetailSectionSnapshot:
        """
        构建高风险配置共享分区。

        :param rows: 配置行列表
        :param risk_sets: 风险集合
        :return: 分区快照
        """
        risky_rows = [
            row
            for row in sorted(
                rows, key=lambda config_row: self.risk_support.build_config_sort_key(config_row, risk_sets)
            )
            if self.risk_support.resolve_config_risk_key(str(row.get('configKey', '') or ''), risk_sets) != 'normal'
        ]
        if not risky_rows:
            return DetailSectionSnapshot(
                title='高风险配置',
                status='ok',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                    empty_label='高风险配置',
                    empty_value='0 项',
                    detail='当前巡检结果中没有需要优先处理的高风险配置',
                ),
            )
        lines: list[str] = []
        for row in risky_rows[:8]:
            config_key = str(row.get('configKey', '-') or '-')
            config_name = str(row.get('configName', '-') or '-')
            risk_key = self.risk_support.resolve_config_risk_key(config_key, risk_sets)
            lines.append(
                f'[{CONFIG_RISK_LABELS.get(risk_key, "风险")}] '
                f'{SHELL_TEXT_FORMATTER.truncate_text(config_key, 40)} · {SHELL_TEXT_FORMATTER.truncate_text(config_name, 20)}'
            )
        return DetailSectionSnapshot(
            title='高风险配置',
            status='warn' if risky_rows else 'ok',
            lines=lines,
        )

    def build_configs_overview_section(
        self,
        rows: list[dict[str, Any]],
        filtered_rows: list[dict[str, Any]],
        risk_sets: dict[str, set[str]],
        filter_label: str,
    ) -> DetailSectionSnapshot:
        """
        构建参数配置页总览判断共享分区。

        :param rows: 原始配置行列表
        :param filtered_rows: 当前筛选后的配置行列表
        :param risk_sets: 风险集合
        :param filter_label: 当前筛选标签
        :return: 分区快照
        """
        mismatch_count = len(risk_sets.get('mismatch', set()))
        drift_count = len(risk_sets.get('missing-cache', set())) + len(risk_sets.get('orphan-cache', set()))
        risky_count = mismatch_count + drift_count
        status = 'ok'
        conclusion = '当前配置一致性正常，可继续抽查单项详情与同步状态'
        if mismatch_count > 0:
            status = 'warn'
            conclusion = '存在值不一致配置，优先核对数据库与缓存是否同步'
        elif drift_count > 0:
            status = 'warn'
            conclusion = '存在缓存漂移配置，建议优先确认缺失项与孤立项来源'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'当前筛选: {filter_label}',
                f'已加载配置: {len(rows)} 项',
                f'当前匹配: {len(filtered_rows)} 项',
                f'高风险配置: {risky_count} 项',
                f'值不一致: {mismatch_count} 项',
                f'缓存漂移: {drift_count} 项',
                '',
                '## 建议入口',
                '优先关注：高风险配置 / 值不一致 / 缓存漂移',
            ],
        )

    def build_config_consistency_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建单个配置的一致性分区。

        :param payload: `config get` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='同步状态',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='同步状态', empty_value='不可用'
                ),
            )
        lines = [
            '## 当前配置',
            f'键名: {payload.get("key", "-")}',
            f'读取来源: {payload.get("source", "-")}',
        ]
        source = str(payload.get('source', '-') or '-').strip().lower()
        section_status = 'ok'
        if source == 'both':
            lines.append(f'数据库与缓存一致: {"是" if payload.get("inSync", False) else "否"}')
            if not payload.get('inSync', False):
                section_status = 'fail'
        elif source == 'database':
            lines.append('缓存状态: 缺失')
            section_status = 'warn'
        elif source == 'cache':
            lines.append('数据库状态: 缺失')
            section_status = 'warn'
        return DetailSectionSnapshot(
            title='同步状态',
            status=section_status,
            lines=lines,
        )

    def build_config_source_section(
        self,
        title: str,
        config_item: dict[str, Any] | None,
        *,
        missing_text: str,
    ) -> DetailSectionSnapshot:
        """
        构建配置来源详情分区。

        :param title: 分区标题
        :param config_item: 配置来源详情
        :param missing_text: 缺失时提示
        :return: 分区快照
        """
        if not isinstance(config_item, dict):
            return DetailSectionSnapshot(
                title=title,
                status='info',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                    empty_label=title,
                    empty_value='未找到',
                    detail=missing_text,
                ),
            )
        return DetailSectionSnapshot(
            title=title,
            status='ok',
            lines=[
                '## 基础信息',
                f'配置 ID: {config_item.get("configId", "-")}',
                f'键名: {SHELL_TEXT_FORMATTER.truncate_text(config_item.get("configKey", "-"), 48)}',
                f'名称: {SHELL_TEXT_FORMATTER.truncate_text(config_item.get("configName", "-"), 32)}',
                f'键值: {SHELL_TEXT_FORMATTER.truncate_text(config_item.get("configValue", "-"), 72)}',
                f'内置标记: {config_item.get("configType", "-")}',
                '',
                '## 备注',
                SHELL_TEXT_FORMATTER.truncate_text(config_item.get('remark', '-') or '-', 88),
            ],
        )

    def load_config_detail_sections(
        self,
        config_row: dict[str, Any],
        env: str,
    ) -> list[DetailSectionSnapshot]:
        """
        按需加载单个配置项详情分区。

        :param config_row: 配置项行数据
        :param env: 当前运行环境
        :return: 详情分区列表
        """
        config_key = str(config_row.get('configKey', '-') or '-')
        detail_payload = NESTED_CLI_SUPPORT.run(
            'config',
            'get',
            config_key,
            f'--env={env}',
            '--source=both',
            '--output=json',
            parse_json=True,
        ).payload
        database_payload = detail_payload.get('database') if isinstance(detail_payload, dict) else None
        cache_payload = detail_payload.get('cache') if isinstance(detail_payload, dict) else None
        return [
            self.build_config_consistency_section(detail_payload),
            self.build_config_source_section('数据库配置', database_payload, missing_text='数据库中未找到该配置项'),
            self.build_config_source_section('缓存配置', cache_payload, missing_text='缓存中未找到该配置项'),
        ]


class ConfigRecordBuilder:
    """
    参数配置浏览记录构建器。

    该构建器负责构建配置浏览记录与失败兜底记录。

    :param page_adapter: 参数配置浏览页适配器
    :param section_builder: 参数配置浏览页分区构建器
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        section_builder: ConfigSectionBuilder,
    ) -> None:
        """
        初始化参数配置浏览记录构建器。

        :param page_adapter: 参数配置浏览页适配器
        :param section_builder: 参数配置浏览页分区构建器
        :return: None
        """
        self.page_adapter = page_adapter
        self.section_builder = section_builder

    def build_record(
        self,
        config_row: dict[str, Any],
        env: str,
        *,
        risk_key: str,
    ) -> BrowserRecordSnapshot:
        """
        构建单条参数配置浏览记录。

        :param config_row: 配置项行数据
        :param env: 当前运行环境
        :param risk_key: 当前配置项风险键
        :return: 浏览记录快照
        """
        config_id = config_row.get('configId', '-')
        config_key = str(config_row.get('configKey', '-') or '-')
        config_name = str(config_row.get('configName', '-') or '-')
        config_type = str(config_row.get('configType', '-') or '-')
        config_value = str(config_row.get('configValue', '-') or '-')
        risk_label = CONFIG_RISK_LABELS.get(risk_key, '正常')
        return BrowserRecordSnapshot(
            key=f'config:{config_key}',
            title=SHELL_TEXT_FORMATTER.truncate_text(config_key, 44),
            status=CONFIG_RISK_STATUSES.get(risk_key, 'ok'),
            summary=f'{risk_label} · {SHELL_TEXT_FORMATTER.truncate_text(config_name, 18)} · 值 {SHELL_TEXT_FORMATTER.truncate_text(config_value, 24)}',
            metadata_lines=[
                '## 配置身份',
                f'配置 ID: {config_id}',
                f'配置名称: {SHELL_TEXT_FORMATTER.truncate_text(config_name, 40)}',
                f'系统内置: {config_type}',
                f'风险分类: {risk_label}',
                '',
                '## 当前值',
                SHELL_TEXT_FORMATTER.truncate_text(config_value, 88),
            ],
            detail_sections=[],
            detail_loader=lambda config_row=config_row, env=env: self.section_builder.load_config_detail_sections(
                config_row,
                env,
            ),
        )

    def build_failure_record(self, payload: dict[str, Any] | None) -> BrowserRecordSnapshot:
        """
        构建配置页失败兜底记录。

        :param payload: 失败结果负载
        :return: 浏览记录快照
        """
        return self.page_adapter.build_failure_record(
            key='config:unavailable',
            subject='参数配置',
            section_subject='配置列表',
            payload=payload,
        )


class ConfigsBrowserAdapter(BaseBrowserAdapter):
    """
    参数配置浏览页适配器。

    该适配器负责采集配置巡检、配置列表和单项配置详情，并统一完成
    风险分类、筛选排序、共享分区构建与浏览记录装配。

    :param risk_support: 参数配置风险分类支持对象
    :param section_builder: 参数配置浏览页分区构建器
    :param record_builder: 参数配置浏览记录构建器
    """

    def __init__(
        self,
        risk_support: ConfigRiskSupport | None = None,
        section_builder: ConfigSectionBuilder | None = None,
        record_builder: ConfigRecordBuilder | None = None,
    ) -> None:
        """
        初始化参数配置浏览页适配器。

        :param risk_support: 参数配置风险分类支持对象
        :param section_builder: 参数配置浏览页分区构建器
        :param record_builder: 参数配置浏览记录构建器
        :return: None
        """
        super().__init__(
            page_title='参数配置',
            search_view_key='configs',
            filter_options=CONFIG_FILTER_OPTIONS,
        )
        self.risk_support = risk_support or ConfigRiskSupport()
        self.section_builder = section_builder or ConfigSectionBuilder(self, self.risk_support)
        self.record_builder = record_builder or ConfigRecordBuilder(self, self.section_builder)

    def collect_snapshot(self, env: str, filter_key: str = 'all', query: str = '') -> BrowserPageSnapshot:
        """
        采集参数配置浏览页只读快照。

        :param env: 当前运行环境
        :param filter_key: 当前筛选键
        :param query: 当前搜索词
        :return: 浏览页快照
        """
        active_filter_option = self.resolve_active_filter(filter_key)
        active_filter = active_filter_option.key
        active_filter_label = active_filter_option.label
        search_context = self.resolve_search_context(query)
        doctor_payload = NESTED_CLI_SUPPORT.run(
            'config',
            'doctor',
            f'--env={env}',
            '--sample-limit=5',
            '--output=json',
            parse_json=True,
        ).payload
        list_payload = NESTED_CLI_SUPPORT.run(
            'config',
            'list',
            f'--env={env}',
            '--paged',
            '--page-size=8',
            '--output=json',
            parse_json=True,
        ).payload
        risk_sets = self.risk_support.build_config_risk_sets(doctor_payload)

        if not isinstance(list_payload, dict) or not list_payload.get('ok', False):
            return BrowserPageSnapshot(
                title='参数配置',
                subtitle=TUI_COPY.build_unavailable_subtitle(
                    '配置',
                    SHELL_TEXT_FORMATTER.truncate_text(self.extract_payload_message(list_payload), 72),
                ),
                records=[self.record_builder.build_failure_record(list_payload)],
                shared_sections=[
                    self.section_builder.build_configs_overview_section([], [], risk_sets, active_filter_label),
                    self.section_builder.build_config_doctor_section(doctor_payload),
                    self.section_builder.build_high_risk_config_section([], risk_sets),
                    self.section_builder.build_config_issue_samples_section(doctor_payload),
                    self.section_builder.build_config_set_entry_section([]),
                ],
                filters=list(self.filter_options),
                active_filter_key=active_filter,
                search=search_context,
            )

        rows = self.risk_support.append_orphan_cache_rows(
            self.extract_page_rows(list_payload),
            risk_sets.get('orphan-cache', set()),
        )
        sorted_rows = sorted(
            rows, key=lambda config_row: self.risk_support.build_config_sort_key(config_row, risk_sets)
        )
        filtered_rows = self.risk_support.apply_config_query(
            self.risk_support.apply_config_filter(sorted_rows, risk_sets, active_filter),
            query,
        )
        records = [
            self.record_builder.build_record(
                config_row,
                env,
                risk_key=self.risk_support.resolve_config_risk_key(
                    str(config_row.get('configKey', '') or ''),
                    risk_sets,
                ),
            )
            for config_row in filtered_rows[:12]
        ]
        if not records:
            records = [
                self.build_empty_record(
                    key='config:none',
                    subject='配置项',
                    empty_label='配置项',
                    has_source_rows=bool(sorted_rows),
                    filtered_summary='当前筛选条件下没有匹配配置项',
                    empty_summary='当前环境没有可浏览的参数配置项',
                    filtered_empty_value='暂无数据',
                    empty_empty_value='暂无配置',
                    filtered_detail='当前筛选条件下没有匹配配置项',
                    empty_detail='当前环境没有可浏览的参数配置项',
                )
            ]

        subtitle = TUI_DIAGNOSTIC_SERVICE.build_configs_diagnostic_subtitle(
            active_filter_label,
            len(filtered_rows),
            len(risk_sets.get('mismatch', set())),
            len(risk_sets.get('missing-cache', set())) + len(risk_sets.get('orphan-cache', set())),
        )
        if isinstance(doctor_payload, dict) and not doctor_payload.get('ok', False):
            subtitle = (
                f'{subtitle} | {SHELL_TEXT_FORMATTER.truncate_text(self.extract_payload_message(doctor_payload), 72)}'
            )
        shared_sections = [
            self.section_builder.build_configs_overview_section(rows, filtered_rows, risk_sets, active_filter_label),
            self.section_builder.build_config_doctor_section(doctor_payload),
            self.section_builder.build_high_risk_config_section(rows, risk_sets),
            self.section_builder.build_config_issue_samples_section(doctor_payload),
            self.section_builder.build_config_set_entry_section(rows),
        ]
        return BrowserPageSnapshot(
            title='参数配置',
            subtitle=subtitle,
            records=records,
            shared_sections=shared_sections,
            filters=list(self.filter_options),
            active_filter_key=active_filter,
            search=search_context,
        )


CONFIGS_BROWSER_ADAPTER = ConfigsBrowserAdapter()
