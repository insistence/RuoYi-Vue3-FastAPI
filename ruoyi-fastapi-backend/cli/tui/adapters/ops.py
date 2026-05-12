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
class OpsDetailSourcePayloads:
    """
    运维详情页原始数据源快照。

    :param health_payload: `ops health` 结果
    :param ping_db_payload: `ops ping-db` 结果
    :param ping_redis_payload: `ops ping-redis` 结果
    :param deps_payload: `ops deps` 结果
    :param server_payload: `ops server-info` 结果
    """

    health_payload: dict[str, Any] | None
    ping_db_payload: dict[str, Any] | None
    ping_redis_payload: dict[str, Any] | None
    deps_payload: dict[str, Any] | None
    server_payload: dict[str, Any] | None


class OpsDetailSnapshotCollector:
    """
    运维详情页数据采集器。

    该对象负责拉取运维详情页所需的多路 CLI 原始结果，
    让 `OpsDetailAdapter` 保持详情页编排职责。
    """

    def collect(self, env: str) -> OpsDetailSourcePayloads:
        """
        采集运维详情页所需原始结果。

        :param env: 当前运行环境
        :return: 运维详情页原始数据源快照
        """
        return OpsDetailSourcePayloads(
            health_payload=NESTED_CLI_SUPPORT.run(
                'ops',
                'health',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            ping_db_payload=NESTED_CLI_SUPPORT.run(
                'ops',
                'ping-db',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            ping_redis_payload=NESTED_CLI_SUPPORT.run(
                'ops',
                'ping-redis',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            deps_payload=NESTED_CLI_SUPPORT.run(
                'ops',
                'deps',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            server_payload=NESTED_CLI_SUPPORT.run(
                'ops',
                'server-info',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
        )


class OpsSectionBuilder:
    """
    运维详情分区构建器。

    该构建器负责将运维相关 CLI 结果负载转换为 TUI 详情页分区，
    使详情页适配器本体只保留采集与编排职责。
    """

    @staticmethod
    def build_health_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建运维健康检查分区。

        :param payload: `ops health` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict):
            return DetailSectionSnapshot(
                title='健康检查',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='健康检查', empty_value='不可用'
                ),
            )
        database = payload.get('database') if isinstance(payload.get('database'), dict) else {}
        redis = payload.get('redis') if isinstance(payload.get('redis'), dict) else {}
        return DetailSectionSnapshot(
            title='健康检查',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 基础连通性',
                f'环境: {payload.get("env", "-")}',
                f'数据库: {"正常" if database.get("ok", False) else "异常"}',
                f'> {SHELL_TEXT_FORMATTER.truncate_text(database.get("message", "-"), 64)}',
                f'Redis: {"正常" if redis.get("ok", False) else "异常"}',
                f'> {SHELL_TEXT_FORMATTER.truncate_text(redis.get("message", "-"), 64)}',
            ],
        )

    @staticmethod
    def build_ping_db_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建数据库探活结果分区。

        :param payload: `ops ping-db` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict):
            return DetailSectionSnapshot(
                title='数据库探活',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='数据库探活', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='数据库探活',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 探活结果',
                f'数据库连接: {"正常" if payload.get("ok", False) else "异常"}',
                f'结果摘要: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("message", "-"), 72)}',
            ],
        )

    @staticmethod
    def build_ping_redis_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建 Redis 探活结果分区。

        :param payload: `ops ping-redis` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict):
            return DetailSectionSnapshot(
                title='Redis 探活',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='Redis 探活', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='Redis 探活',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 探活结果',
                f'Redis 连接: {"正常" if payload.get("ok", False) else "异常"}',
                f'结果摘要: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("message", "-"), 72)}',
            ],
        )

    @staticmethod
    def build_dependency_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建运维依赖版本分区。

        :param payload: `ops deps` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict):
            return DetailSectionSnapshot(
                title='依赖版本',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='依赖', empty_value='不可用'),
            )
        packages = payload.get('packages') if isinstance(payload.get('packages'), dict) else {}
        missing_required = payload.get('missingRequired') if isinstance(payload.get('missingRequired'), list) else []
        lines = [
            '## 总体结论',
            f'检查结果: {"通过" if payload.get("ok", False) else "异常"}',
            f'缺失核心依赖: {len(missing_required)} 个',
            f'> {SHELL_TEXT_FORMATTER.truncate_text(payload.get("message", "-"), 72)}',
            '',
            '## 关键版本',
        ]
        for package_name in ('python', 'fastapi', 'sqlalchemy', 'redis', 'typer', 'alembic'):
            package_payload = packages.get(package_name)
            if not isinstance(package_payload, dict):
                continue
            installed = '已安装' if package_payload.get('installed', False) else '缺失'
            lines.append(f'> {package_name} · {installed} · {package_payload.get("version", "-") or "-"}')
        if missing_required:
            lines.extend(['', '## 缺失项'])
            lines.extend(f'> {item}' for item in missing_required[:8])
        return DetailSectionSnapshot(
            title='依赖版本',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=lines,
        )

    @staticmethod
    def build_server_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建服务器运行概况分区。

        :param payload: `ops server-info` JSON 负载
        :return: 分区快照
        """
        server = payload.get('server') if isinstance(payload, dict) else None
        if not isinstance(server, dict):
            return DetailSectionSnapshot(
                title='服务器摘要',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='服务器信息', empty_value='不可用'
                ),
            )

        sys_info = server.get('sys') if isinstance(server.get('sys'), dict) else {}
        cpu_info = server.get('cpu') if isinstance(server.get('cpu'), dict) else {}
        mem_info = server.get('mem') if isinstance(server.get('mem'), dict) else {}
        py_info = server.get('py') if isinstance(server.get('py'), dict) else {}
        return DetailSectionSnapshot(
            title='服务器摘要',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 主机信息',
                f'主机名: {sys_info.get("computerName", "-")}',
                f'主机 IP: {sys_info.get("computerIp", "-")}',
                f'操作系统: {SHELL_TEXT_FORMATTER.truncate_text(sys_info.get("osName", "-"), 56)}',
                f'系统架构: {sys_info.get("osArch", "-")}',
                '',
                '## 资源负载',
                f'CPU 核心: {cpu_info.get("cpuNum", "-")}',
                f'CPU 使用率: {cpu_info.get("used", "-")}%',
                f'内存总量: {mem_info.get("total", "-")}',
                f'内存使用率: {mem_info.get("usage", "-")}%',
                '',
                '## Python 进程',
                f'版本: {py_info.get("version", "-")}',
                f'运行时长: {py_info.get("runTime", "-")}',
                f'进程内存: {py_info.get("used", "-")} / {py_info.get("total", "-")}',
            ],
        )

    def build_disk_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建服务器磁盘样本分区。

        :param payload: `ops server-info` JSON 负载
        :return: 分区快照
        """
        server = payload.get('server') if isinstance(payload, dict) else None
        if not isinstance(server, dict):
            return DetailSectionSnapshot(
                title='磁盘样本',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='磁盘样本', empty_value='不可用'
                ),
            )
        sys_files = server.get('sysFiles') if isinstance(server.get('sysFiles'), list) else []
        lines = TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
            empty_label='磁盘样本',
            empty_value='0 个',
            detail='当前服务器信息中没有返回磁盘分区样本',
            suggestion=TUI_COPY.build_refresh_page_suggestion('运维', '重新采集服务器信息'),
        )
        section_status = 'info'
        if sys_files:
            section_status = 'ok'
            lines = []
            for item in sys_files[:8]:
                if not isinstance(item, dict):
                    continue
                lines.extend(
                    [
                        f'## {SHELL_TEXT_FORMATTER.truncate_text(item.get("dirName", "-"), 36)}',
                        (
                            f'> 已用 {item.get("used", "-")} / 总量 {item.get("total", "-")} '
                            f'| 使用率 {item.get("usage", "-")}'
                        ),
                        f'> 可用 {item.get("free", "-")}',
                        '',
                    ]
                )
            if lines and lines[-1] == '':
                lines.pop()
        return DetailSectionSnapshot(
            title='磁盘样本',
            status=section_status,
            lines=lines,
        )

    @staticmethod
    def build_prod_check_entry_section() -> DetailSectionSnapshot:
        """
        构建生产巡检向导入口分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='生产巡检入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备做生产环境巡检或上线前复核时，应先通过向导统一检查数据库、缓存和运行配置。',
                command=TUI_COPY.build_cli_command_hint('wizard', 'prod-check', '--output=text'),
                guide='向导会继续询问目标环境并输出预览结果，确认后再执行完整巡检。',
            ),
        )

    @staticmethod
    def build_overview_section(
        health_payload: dict[str, Any] | None,
        deps_payload: dict[str, Any] | None,
        server_payload: dict[str, Any] | None,
    ) -> DetailSectionSnapshot:
        """
        构建运维页总览判断分区。

        :param health_payload: `ops health` JSON 负载
        :param deps_payload: `ops deps` JSON 负载
        :param server_payload: `ops server-info` JSON 负载
        :return: 分区快照
        """
        health_ok = bool(isinstance(health_payload, dict) and health_payload.get('ok', False))
        deps_ok = bool(isinstance(deps_payload, dict) and deps_payload.get('ok', False))
        server_ok = bool(isinstance(server_payload, dict) and server_payload.get('ok', False))
        missing_required = deps_payload.get('missingRequired') if isinstance(deps_payload, dict) else None
        missing_count = len(missing_required) if isinstance(missing_required, list) else 0
        server = (
            server_payload.get('server')
            if isinstance(server_payload, dict) and isinstance(server_payload.get('server'), dict)
            else {}
        )
        cpu_info = server.get('cpu') if isinstance(server.get('cpu'), dict) else {}
        mem_info = server.get('mem') if isinstance(server.get('mem'), dict) else {}

        status = 'ok'
        conclusion = '基础探活与运行依赖正常，可继续查看服务器资源与磁盘样本'
        if not health_ok:
            status = 'fail'
            conclusion = '运维探活存在异常，优先处理数据库或 Redis 连通性问题'
        elif not deps_ok or missing_count > 0:
            status = 'warn'
            conclusion = '运行依赖存在缺口，建议优先补齐核心依赖并确认版本兼容性'
        elif not server_ok:
            status = 'warn'
            conclusion = '服务器信息采集异常，建议重新采集资源与磁盘状态'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'探活状态: {"正常" if health_ok else "异常"}',
                f'缺失核心依赖: {missing_count} 个',
                f'CPU 使用率: {cpu_info.get("used", "-")}%',
                f'内存使用率: {mem_info.get("usage", "-")}%',
                '',
                '## 建议入口',
                '优先关注：健康检查 / 依赖版本 / 服务器摘要 / 生产巡检入口',
            ],
        )

    def build_sections(
        self,
        *,
        health_payload: dict[str, Any] | None,
        ping_db_payload: dict[str, Any] | None,
        ping_redis_payload: dict[str, Any] | None,
        deps_payload: dict[str, Any] | None,
        server_payload: dict[str, Any] | None,
    ) -> list[DetailSectionSnapshot]:
        """
        构建运维页全部详情分区。

        :param health_payload: `ops health` 结果负载
        :param ping_db_payload: `ops ping-db` 结果负载
        :param ping_redis_payload: `ops ping-redis` 结果负载
        :param deps_payload: `ops deps` 结果负载
        :param server_payload: `ops server-info` 结果负载
        :return: 详情分区列表
        """
        return [
            self.build_overview_section(health_payload, deps_payload, server_payload),
            self.build_health_section(health_payload),
            self.build_ping_db_section(ping_db_payload),
            self.build_ping_redis_section(ping_redis_payload),
            self.build_dependency_section(deps_payload),
            self.build_server_section(server_payload),
            self.build_disk_section(server_payload),
            self.build_prod_check_entry_section(),
        ]


class OpsDetailAdapter(BaseDetailAdapter):
    """
    运维详情页适配器。

    该适配器负责采集运维相关 CLI 结果，并委托分区构建器组装为
    TUI 详情页快照。
    """

    def __init__(
        self,
        section_builder: OpsSectionBuilder | None = None,
        snapshot_collector: OpsDetailSnapshotCollector | None = None,
    ) -> None:
        """
        初始化运维详情页适配器。

        :param section_builder: 运维详情分区构建器
        :param snapshot_collector: 运维详情页数据采集器
        :return: None
        """
        super().__init__(
            page_title='运维',
            search_view_key='ops',
            default_suggestions=[
                '总览判断',
                '健康检查',
                '数据库探活',
                'Redis 探活',
                '依赖版本',
                '服务器摘要',
                '磁盘样本',
                '生产巡检入口',
            ],
        )
        self.section_builder = section_builder or OpsSectionBuilder()
        self.snapshot_collector = snapshot_collector or OpsDetailSnapshotCollector()

    def collect_snapshot(self, env: str, query: str = '') -> DetailPageSnapshot:
        """
        采集运维状态页只读快照。

        :param env: 当前运行环境
        :param query: 当前搜索词
        :return: 页面快照
        """
        source_payloads = self.snapshot_collector.collect(env)
        sections = self.section_builder.build_sections(
            health_payload=source_payloads.health_payload,
            ping_db_payload=source_payloads.ping_db_payload,
            ping_redis_payload=source_payloads.ping_redis_payload,
            deps_payload=source_payloads.deps_payload,
            server_payload=source_payloads.server_payload,
        )
        return DetailPageSnapshot(
            title='运维',
            subtitle=TUI_DIAGNOSTIC_SERVICE.build_ops_diagnostic_subtitle(
                source_payloads.health_payload,
                source_payloads.deps_payload,
                source_payloads.server_payload,
            ),
            sections=self.filter_sections(sections, query),
            search=self.resolve_search_context(query),
        )


OPS_DETAIL_ADAPTER = OpsDetailAdapter()
