from dataclasses import dataclass
from typing import Any

from cli.tui.adapters.base import BaseDetailAdapter
from cli.tui.adapters.models import (
    TUI_ADAPTER_MODEL_RENDERER,
    DetailPageSnapshot,
    DetailSectionSnapshot,
)
from cli.tui.copy import TUI_COPY
from cli.tui.diagnostics import TUI_DIAGNOSTIC_SERVICE
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER


@dataclass(frozen=True)
class DatabaseDetailSourcePayloads:
    """
    数据库详情页原始数据源快照。

    :param revision_payload: `db current` 结果
    :param check_payload: `db check` 结果
    :param heads_payload: `db heads` 结果
    :param history_payload: `db history` 结果
    :param config_payload: `app config` 结果
    """

    revision_payload: dict[str, Any] | None
    check_payload: dict[str, Any] | None
    heads_payload: dict[str, Any] | None
    history_payload: dict[str, Any] | None
    config_payload: dict[str, Any] | None


class DatabaseDetailSnapshotCollector:
    """
    数据库详情页数据采集器。

    该对象负责拉取数据库详情页所需的多路 CLI 原始结果，
    让 `DatabaseDetailAdapter` 保持详情页编排职责。
    """

    def collect(self, env: str) -> DatabaseDetailSourcePayloads:
        """
        采集数据库详情页所需原始结果。

        :param env: 当前运行环境
        :return: 数据库详情页原始数据源快照
        """
        return DatabaseDetailSourcePayloads(
            revision_payload=NESTED_CLI_SUPPORT.run(
                'db',
                'current',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            check_payload=NESTED_CLI_SUPPORT.run(
                'db',
                'check',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            heads_payload=NESTED_CLI_SUPPORT.run(
                'db',
                'heads',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            history_payload=NESTED_CLI_SUPPORT.run(
                'db',
                'history',
                f'--env={env}',
                '--limit=8',
                '--output=json',
                parse_json=True,
            ).payload,
            config_payload=NESTED_CLI_SUPPORT.run(
                'app',
                'config',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
        )


class DatabaseSectionBuilder:
    """
    数据库详情分区构建器。

    该构建器负责将数据库相关 CLI 结果负载转换为 TUI 详情页分区，
    使详情页适配器本体只保留采集与编排职责。
    """

    @staticmethod
    def extract_revision_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        """
        从 Alembic 结果中提取修订版本列表。

        :param payload: `db heads` 或 `db history` JSON 负载
        :return: 修订版本列表
        """
        items = payload.get('items') if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def build_revision_item_lines(item: dict[str, Any], *, index: int, item_label: str) -> list[str]:
        """
        构建单条 Alembic 修订版本详情文本。

        :param item: 修订版本字典
        :param index: 当前索引
        :param item_label: 条目标识名称
        :return: 文本行列表
        """
        down_revisions = item.get('downRevisions')
        branch_labels = item.get('branchLabels')
        depends_on = item.get('dependsOn')
        return [
            f'## {item_label} {index:02d} · {item.get("revision", "-")}',
            f'> 下游版本: {",".join(down_revisions) if isinstance(down_revisions, list) and down_revisions else "-"}',
            f'> 分支标签: {",".join(branch_labels) if isinstance(branch_labels, list) and branch_labels else "-"}',
            f'> 依赖版本: {",".join(depends_on) if isinstance(depends_on, list) and depends_on else "-"}',
            f'> 说明: {SHELL_TEXT_FORMATTER.truncate_text(item.get("doc", "-"), 72)}',
            f'> 文件: {SHELL_TEXT_FORMATTER.truncate_text(item.get("path", "-"), 72)}',
        ]

    @staticmethod
    def build_revision_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建数据库迁移状态分区。

        :param payload: `db current` JSON 负载
        :return: 分区快照
        """
        current_revision = payload.get('currentRevision', '-') if isinstance(payload, dict) else '-'
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='迁移版本',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='迁移版本', empty_value=str(current_revision or '-')
                ),
            )
        return DetailSectionSnapshot(
            title='迁移版本',
            status='ok',
            lines=[
                '## 当前版本',
                f'迁移版本: {current_revision}',
                '',
                '## 状态说明',
                f'结果消息: {TUI_ADAPTER_MODEL_RENDERER.extract_payload_message(payload)}',
            ],
        )

    def build_overview_section(
        self,
        revision_payload: dict[str, Any] | None,
        check_payload: dict[str, Any] | None,
        heads_payload: dict[str, Any] | None,
        history_payload: dict[str, Any] | None,
    ) -> DetailSectionSnapshot:
        """
        构建数据库页总览判断分区。

        :param revision_payload: `db current` JSON 负载
        :param check_payload: `db check` JSON 负载
        :param heads_payload: `db heads` JSON 负载
        :param history_payload: `db history` JSON 负载
        :return: 分区快照
        """
        revision_ok = bool(isinstance(revision_payload, dict) and revision_payload.get('ok', False))
        check_ok = bool(isinstance(check_payload, dict) and check_payload.get('ok', False))
        heads_ok = bool(isinstance(heads_payload, dict) and heads_payload.get('ok', False))
        current_revision = revision_payload.get('currentRevision', '-') if isinstance(revision_payload, dict) else '-'
        head_items = self.extract_revision_items(heads_payload)
        history_items = self.extract_revision_items(history_payload)

        status = 'ok'
        conclusion = '数据库基线正常，可继续查看连接状态、Heads 与版本链路'
        if not revision_ok or not check_ok:
            status = 'fail'
            conclusion = '数据库存在基础异常，优先确认迁移版本与连通性检查结果'
        elif not heads_ok or len(head_items) != 1:
            status = 'warn'
            conclusion = '数据库存在迁移分叉风险，优先确认 Heads 与版本链路是否一致'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'当前 revision: {current_revision}',
                f'连通性检查: {"正常" if check_ok else "异常"}',
                f'Heads 数量: {len(head_items)}',
                f'版本数量: {history_payload.get("totalCount", len(history_items)) if isinstance(history_payload, dict) else len(history_items)}',
                '',
                '## 建议入口',
                '优先关注：迁移版本 / 连通性检查 / Heads 状态 / 升级入口',
            ],
        )

    @staticmethod
    def build_profile_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建数据库连接配置分区。

        :param payload: `app config` JSON 负载
        :return: 分区快照
        """
        config = payload.get('config') if isinstance(payload, dict) else None
        if not isinstance(config, dict):
            return DetailSectionSnapshot(
                title='连接信息',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='连接信息', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='连接信息',
            status='ok',
            lines=[
                '## 数据库连接',
                f'数据库类型: {config.get("dbType", "-")}',
                f'连接地址: {config.get("dbHost", "-")}:{config.get("dbPort", "-")}',
                f'数据库名: {config.get("dbDatabase", "-")}',
            ],
        )

    @staticmethod
    def build_check_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建数据库连通性检查分区。

        :param payload: `db check` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='连通性检查',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='数据库连接', empty_value='异常'
                ),
            )
        return DetailSectionSnapshot(
            title='连通性检查',
            status='ok',
            lines=[
                '## 当前状态',
                '数据库连接: 正常',
                '',
                '## 结果摘要',
                f'结果消息: {TUI_ADAPTER_MODEL_RENDERER.extract_payload_message(payload)}',
            ],
        )

    def build_heads_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建 Alembic heads 分区。

        :param payload: `db heads` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='Heads 状态',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='Heads', empty_value='不可用'
                ),
            )
        items = self.extract_revision_items(payload)
        status = 'ok' if len(items) == 1 else 'warn'
        lines = [
            '## Heads 概况',
            f'Heads 数量: {len(items)}',
            f'结果消息: {TUI_ADAPTER_MODEL_RENDERER.extract_payload_message(payload)}',
        ]
        if not items:
            lines.extend(['', '## Heads 列表', '> 当前仓库未返回可用 heads'])
        else:
            lines.extend(['', '## Heads 列表'])
            for index, item in enumerate(items[:4], start=1):
                lines.extend(self.build_revision_item_lines(item, index=index, item_label='Head'))
                lines.append('')
            if len(lines) > 1 and lines[-1] == '':
                lines.pop()
        return DetailSectionSnapshot(
            title='Heads 状态',
            status=status,
            lines=lines,
        )

    def build_history_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建 Alembic 历史版本分区。

        :param payload: `db history` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='历史版本',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='历史版本', empty_value='不可用'
                ),
            )
        items = self.extract_revision_items(payload)
        lines = [
            '## 历史概况',
            f'返回数量: {payload.get("count", len(items))}',
            f'总版本数: {payload.get("totalCount", len(items))}',
            f'查询上限: {payload.get("limit", len(items))}',
            '',
            '## 历史列表',
        ]
        if not items:
            lines.append('> 当前仓库未返回可展示的历史版本')
        else:
            for index, item in enumerate(items[:6], start=1):
                lines.extend(self.build_revision_item_lines(item, index=index, item_label='版本'))
                lines.append('')
            if lines[-1] == '':
                lines.pop()
        return DetailSectionSnapshot(
            title='历史版本',
            status='ok',
            lines=lines,
        )

    @staticmethod
    def build_upgrade_entry_section() -> DetailSectionSnapshot:
        """
        构建数据库升级向导入口分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='升级入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备执行数据库升级、校验迁移路径或在生产前做升级预演时，应先通过向导确认目标版本与 dry-run 结果。',
                command=TUI_COPY.build_cli_command_hint('wizard', 'db-upgrade', '--output=text'),
                guide='向导会继续询问目标环境和目标 revision，并在真正升级前先展示预览信息。',
            ),
        )

    @staticmethod
    def build_init_entry_section() -> DetailSectionSnapshot:
        """
        构建数据库初始化预演入口分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='初始化预演入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备初始化新库、重建本地环境，或先确认初始化命令会执行到哪些迁移版本时，应先执行 dry-run 预演。',
                command=TUI_COPY.build_cli_command_hint('db', 'init', '--dry-run', '--output=text'),
                guide='预演只返回命令摘要与执行目录；确认无误后，再通过外部终端或向导执行真实初始化流程。',
            ),
        )

    def build_sections(
        self,
        *,
        revision_payload: dict[str, Any] | None,
        check_payload: dict[str, Any] | None,
        heads_payload: dict[str, Any] | None,
        history_payload: dict[str, Any] | None,
        config_payload: dict[str, Any] | None,
    ) -> list[DetailSectionSnapshot]:
        """
        构建数据库页全部详情分区。

        :param revision_payload: `db current` 结果负载
        :param check_payload: `db check` 结果负载
        :param heads_payload: `db heads` 结果负载
        :param history_payload: `db history` 结果负载
        :param config_payload: `app config` 结果负载
        :return: 详情分区列表
        """
        return [
            self.build_overview_section(revision_payload, check_payload, heads_payload, history_payload),
            self.build_revision_section(revision_payload),
            self.build_profile_section(config_payload),
            self.build_check_section(check_payload),
            self.build_heads_section(heads_payload),
            self.build_history_section(history_payload),
            self.build_init_entry_section(),
            self.build_upgrade_entry_section(),
        ]


class DatabaseDetailAdapter(BaseDetailAdapter):
    """
    数据库详情页适配器。

    该适配器负责采集数据库相关 CLI 结果，并组装为 TUI 详情页快照。
    页面私有的解析逻辑、分区构建逻辑和快照采集流程统一收口在该类中。

    :param section_builder: 数据库详情分区构建器
    """

    def __init__(
        self,
        section_builder: DatabaseSectionBuilder | None = None,
        snapshot_collector: DatabaseDetailSnapshotCollector | None = None,
    ) -> None:
        """
        初始化数据库详情页适配器。

        :param section_builder: 数据库详情分区构建器
        :param snapshot_collector: 数据库详情页数据采集器
        :return: None
        """
        super().__init__(
            page_title='数据库',
            search_view_key='database',
            default_suggestions=[
                '总览判断',
                '迁移版本',
                '连接信息',
                '连通性检查',
                'Heads 状态',
                '历史版本',
                '初始化预演入口',
                '升级入口',
            ],
        )
        self.section_builder = section_builder or DatabaseSectionBuilder()
        self.snapshot_collector = snapshot_collector or DatabaseDetailSnapshotCollector()

    def collect_snapshot(self, env: str, query: str = '') -> DetailPageSnapshot:
        """
        采集数据库状态页只读快照。

        :param env: 当前运行环境
        :param query: 当前搜索词
        :return: 页面快照
        """
        source_payloads = self.snapshot_collector.collect(env)
        sections = self.section_builder.build_sections(
            revision_payload=source_payloads.revision_payload,
            check_payload=source_payloads.check_payload,
            heads_payload=source_payloads.heads_payload,
            history_payload=source_payloads.history_payload,
            config_payload=source_payloads.config_payload,
        )
        return DetailPageSnapshot(
            title='数据库',
            subtitle=TUI_DIAGNOSTIC_SERVICE.build_database_diagnostic_subtitle(
                source_payloads.revision_payload,
                source_payloads.check_payload,
                source_payloads.heads_payload,
            ),
            sections=self.filter_sections(sections, query),
            search=self.resolve_search_context(query),
        )


DATABASE_DETAIL_ADAPTER = DatabaseDetailAdapter()
