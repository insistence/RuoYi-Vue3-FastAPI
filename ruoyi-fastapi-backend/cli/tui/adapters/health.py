from dataclasses import dataclass, field
from typing import Any

from cli.tui.copy import TUI_COPY
from cli.tui.diagnostics import TUI_DIAGNOSTIC_SERVICE
from cli.tui.keymaps import TUI_KEYMAP_REGISTRY
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER

DEPENDENCY_CHECK_TOTAL = 3
DASHBOARD_PANEL_MAX_LINES = 8
DASHBOARD_PANEL_LINE_MAX_LENGTH = 38
DASHBOARD_PANEL_MORE_HINT = TUI_COPY.build_more_detail_hint()


@dataclass(frozen=True)
class DashboardPanelSnapshot:
    """
    TUI 首页单个面板快照。

    :param title: 面板标题
    :param status: 面板状态
    :param lines: 面板正文文本行
    """

    title: str
    status: str
    lines: list[str]


@dataclass(frozen=True)
class DashboardMetricSnapshot:
    """
    TUI 首页单个指标卡快照。

    :param title: 指标标题
    :param value: 指标主值
    :param status: 指标状态
    :param hint: 指标补充说明
    """

    title: str
    value: str
    status: str
    hint: str


@dataclass(frozen=True)
class DashboardSnapshot:
    """
    TUI 首页聚合快照。

    :param env: 当前运行环境
    :param panels: 面板列表
    """

    env: str
    panels: list[DashboardPanelSnapshot]
    metrics: list[DashboardMetricSnapshot] = field(default_factory=list)


@dataclass(frozen=True)
class DashboardSourcePayloads:
    """
    TUI 首页聚合数据源快照。

    :param app_env_payload: 应用环境结果
    :param app_routes_payload: 应用路由结果
    :param doctor_payload: 应用检查结果
    :param database_payload: 数据库版本结果
    :param cache_payload: 缓存统计结果
    :param deps_payload: 依赖检查结果
    :param server_payload: 服务器摘要结果
    """

    app_env_payload: dict[str, Any] | None
    app_routes_payload: dict[str, Any] | None
    doctor_payload: dict[str, Any] | None
    database_payload: dict[str, Any] | None
    cache_payload: dict[str, Any] | None
    deps_payload: dict[str, Any] | None
    server_payload: dict[str, Any] | None


class DashboardSnapshotCollector:
    """
    TUI 首页聚合数据采集器。

    该对象负责从多路 CLI 命令收集 dashboard 所需原始结果，
    让 `DashboardAdapter` 保持首页装配职责，而不继续承载所有采集细节。
    """

    def collect(self, env: str) -> DashboardSourcePayloads:
        """
        采集首页聚合所需的多路原始结果。

        :param env: 当前运行环境
        :return: 首页聚合数据源快照
        """
        return DashboardSourcePayloads(
            app_env_payload=NESTED_CLI_SUPPORT.run(
                'app',
                'env',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            app_routes_payload=NESTED_CLI_SUPPORT.run(
                'app',
                'routes',
                f'--env={env}',
                '--group-by=tag',
                '--output=json',
                parse_json=True,
            ).payload,
            doctor_payload=NESTED_CLI_SUPPORT.run(
                'app',
                'doctor',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            database_payload=NESTED_CLI_SUPPORT.run(
                'db',
                'current',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            cache_payload=NESTED_CLI_SUPPORT.run(
                'cache',
                'stats',
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


class DashboardFormattingSupport:
    """
    首页仪表盘格式化支持对象。

    该对象负责统一处理摘要消息提取、状态优先级、布尔文本、信号条和
    面板空态/失败态文案，供面板与指标构建对象共享。
    """

    @staticmethod
    def truncate_dashboard_line(line: str) -> str:
        """
        截断首页面板单行文本，并保留结构化前缀。

        :param line: 原始文本行
        :return: 截断后的文本行
        """
        stripped = str(line).strip()
        if not stripped:
            return ''
        if stripped.startswith('## '):
            return f'## {SHELL_TEXT_FORMATTER.truncate_text(stripped[3:].strip(), DASHBOARD_PANEL_LINE_MAX_LENGTH - 3)}'
        if stripped.startswith('> '):
            return f'> {SHELL_TEXT_FORMATTER.truncate_text(stripped[2:].strip(), DASHBOARD_PANEL_LINE_MAX_LENGTH - 2)}'
        return SHELL_TEXT_FORMATTER.truncate_text(stripped, DASHBOARD_PANEL_LINE_MAX_LENGTH)

    @staticmethod
    def resolve_status_priority(status: str) -> int:
        """
        解析状态优先级，值越小越需要优先关注。

        :param status: 状态文本
        :return: 优先级
        """
        return {
            'fail': 0,
            'warn': 1,
            'ok': 2,
            'info': 3,
        }.get(str(status).strip().lower(), 9)

    @staticmethod
    def render_bool_flag(value: object) -> str:
        """
        将布尔语义值标准化为文本。

        :param value: 原始值
        :return: 规范化后的文本
        """
        return '是' if bool(value) else '否'

    @staticmethod
    def render_signal_bar(
        passed: int,
        total: int,
        *,
        width: int = 8,
        on: str = '#',
        off: str = '-',
    ) -> str:
        """
        将通过数量渲染为 ASCII 信号条。

        :param passed: 已通过数量
        :param total: 总数量
        :param width: 信号条宽度
        :param on: 点亮字符
        :param off: 熄灭字符
        :return: ASCII 信号条
        """
        if total <= 0:
            return f'[{off * width}]'
        safe_passed = max(0, min(passed, total))
        filled = round((safe_passed / total) * width)
        return f'[{on * filled}{off * max(0, width - filled)}]'

    @staticmethod
    def extract_payload_message(payload: dict[str, Any] | None) -> str:
        """
        提取结果负载中的摘要消息。

        :param payload: 标准结果负载
        :return: 摘要文本
        """
        if not isinstance(payload, dict):
            return '-'
        if payload.get('message'):
            return str(payload.get('message'))
        if payload.get('error'):
            return SHELL_TEXT_FORMATTER.truncate_text(payload.get('error'), 120)
        return '-'

    def build_failure_lines(
        self,
        payload: dict[str, Any] | None,
        *,
        summary_label: str,
        summary_value: str,
        suggestion: str = TUI_COPY.build_dashboard_failure_suggestion(),
    ) -> list[str]:
        """
        构建首页面板统一失败态摘要。

        :param payload: 标准结果负载
        :param summary_label: 主字段名称
        :param summary_value: 主字段值
        :param suggestion: 建议操作
        :return: 面板正文
        """
        return [
            '## 当前状态',
            f'{summary_label}: {summary_value}',
            '',
            '## 错误摘要',
            f'> {self.extract_payload_message(payload)}',
            '',
            '## 建议操作',
            suggestion,
        ]

    @staticmethod
    def build_empty_lines(
        *,
        summary_label: str,
        summary_value: str,
        detail: str,
        suggestion: str = TUI_COPY.build_dashboard_empty_suggestion(),
    ) -> list[str]:
        """
        构建首页面板统一空态摘要。

        :param summary_label: 主字段名称
        :param summary_value: 主字段值
        :param detail: 空态说明
        :param suggestion: 建议操作
        :return: 面板正文
        """
        return [
            '## 当前状态',
            f'{summary_label}: {summary_value}',
            '',
            '## 说明',
            detail,
            '',
            '## 建议操作',
            suggestion,
        ]


class DashboardPanelCompressor:
    """
    首页面板压缩器。

    该对象负责将原始多行面板压缩为适合首页展示的统一密度摘要卡。

    :param formatting: 首页仪表盘格式化支持对象
    """

    def __init__(self, formatting: DashboardFormattingSupport) -> None:
        """
        初始化首页面板压缩器。

        :param formatting: 首页仪表盘格式化支持对象
        :return: None
        """
        self.formatting = formatting

    def compact_panel_lines(self, lines: list[str]) -> list[str]:
        """
        将首页面板正文压缩为统一长度的摘要卡内容。

        :param lines: 原始正文文本行
        :return: 压缩后的摘要行列表
        """
        compact_lines: list[str] = []
        for raw_line in lines:
            compact_line = self.formatting.truncate_dashboard_line(raw_line)
            if not compact_line:
                if compact_lines and compact_lines[-1] != '':
                    compact_lines.append('')
                continue
            compact_lines.append(compact_line)

        while compact_lines and compact_lines[0] == '':
            compact_lines.pop(0)
        while compact_lines and compact_lines[-1] == '':
            compact_lines.pop()

        if len(compact_lines) <= DASHBOARD_PANEL_MAX_LINES:
            return compact_lines

        summarized_lines = compact_lines[: DASHBOARD_PANEL_MAX_LINES - 1]
        while summarized_lines and summarized_lines[-1] == '':
            summarized_lines.pop()
        summarized_lines.append(DASHBOARD_PANEL_MORE_HINT)
        return summarized_lines

    def compact_panels(self, panels: list[DashboardPanelSnapshot]) -> list[DashboardPanelSnapshot]:
        """
        将首页所有面板压缩为统一密度的摘要卡。

        :param panels: 原始面板列表
        :return: 压缩后的面板列表
        """
        return [
            DashboardPanelSnapshot(
                title=panel.title,
                status=panel.status,
                lines=self.compact_panel_lines(panel.lines),
            )
            for panel in panels
        ]


class DashboardPanelBuilder:
    """
    首页面板构建器。

    该对象负责根据各个 CLI 结果负载构建首页展示面板，并统一风险热区与
    建议入口逻辑。

    :param formatting: 首页仪表盘格式化支持对象
    """

    def __init__(self, formatting: DashboardFormattingSupport) -> None:
        """
        初始化首页面板构建器。

        :param formatting: 首页仪表盘格式化支持对象
        :return: None
        """
        self.formatting = formatting

    def build_app_env_panel(
        self,
        env: str,
        env_payload: dict[str, Any] | None,
        routes_payload: dict[str, Any] | None,
    ) -> DashboardPanelSnapshot:
        """
        构建应用环境总览面板。

        :param env: 当前运行环境
        :param env_payload: `app env` JSON 负载
        :param routes_payload: `app routes` JSON 负载
        :return: 面板快照
        """
        runtime = env_payload.get('runtime') if isinstance(env_payload, dict) else None
        route_count = routes_payload.get('count', 0) if isinstance(routes_payload, dict) else 0
        grouped_routes = routes_payload.get('groupedRoutes') if isinstance(routes_payload, dict) else None
        group_count = len(grouped_routes) if isinstance(grouped_routes, dict) else 0
        if not isinstance(runtime, dict):
            return DashboardPanelSnapshot(
                title='应用摘要',
                status='fail',
                lines=self.formatting.build_failure_lines(
                    env_payload,
                    summary_label='环境',
                    summary_value=env,
                    suggestion=TUI_COPY.build_dashboard_page_suggestion('应用', '检查环境解析结果'),
                ),
            )
        return DashboardPanelSnapshot(
            title='应用摘要',
            status='ok' if env_payload.get('ok', False) else 'fail',
            lines=[
                '## 环境映射',
                f'当前环境: {env} | CLI 目标环境: {runtime.get("cliEnv", "-")}',
                f'配置文件环境: {runtime.get("configEnv", "-")}',
                '## 路由摘要',
                f'注册路由: {route_count} 条 | 标签分组: {group_count} 个',
                '## 环境文件',
                f'已加载环境文件: {runtime.get("envFile", "-")}',
                f'环境文件存在: {self.formatting.render_bool_flag(runtime.get("envFileExists", False))}',
            ],
        )

    def build_health_panel(self, payload: dict[str, Any] | None) -> DashboardPanelSnapshot:
        """
        构建健康检查面板。

        :param payload: `app doctor` JSON 负载
        :return: 面板快照
        """
        if not isinstance(payload, dict):
            return DashboardPanelSnapshot(
                title='系统摘要',
                status='fail',
                lines=self.formatting.build_failure_lines(
                    payload,
                    summary_label='巡检结果',
                    summary_value='不可用',
                    suggestion=TUI_COPY.build_dashboard_page_suggestion('运维/健康检查', '查看原因'),
                ),
            )

        database = payload.get('database') if isinstance(payload.get('database'), dict) else {}
        redis = payload.get('redis') if isinstance(payload.get('redis'), dict) else {}
        crypto = payload.get('crypto') if isinstance(payload.get('crypto'), dict) else {}
        return DashboardPanelSnapshot(
            title='系统摘要',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 总体态势',
                f'整体结果: {"通过" if payload.get("ok", False) else "异常"}',
                '',
                '## 依赖检查',
                f'数据库: {"正常" if database.get("ok", False) else "异常"}',
                f'> {self.formatting.extract_payload_message(database)}',
                f'Redis: {"正常" if redis.get("ok", False) else "异常"}',
                f'> {self.formatting.extract_payload_message(redis)}',
                f'加密组件: {"正常" if crypto.get("ok", False) else "异常"}',
                f'> {self.formatting.extract_payload_message(crypto)}',
            ],
        )

    def build_recommended_entry_panel(
        self,
        doctor_payload: dict[str, Any] | None,
        database_payload: dict[str, Any] | None,
        cache_payload: dict[str, Any] | None,
    ) -> DashboardPanelSnapshot:
        """
        构建首页建议入口面板。

        :param doctor_payload: 健康检查负载
        :param database_payload: 数据库状态负载
        :param cache_payload: 缓存状态负载
        :return: 面板快照
        """
        database_ok = (
            bool(doctor_payload.get('database', {}).get('ok', False)) if isinstance(doctor_payload, dict) else False
        )
        redis_ok = bool(doctor_payload.get('redis', {}).get('ok', False)) if isinstance(doctor_payload, dict) else False
        crypto_ok = (
            bool(doctor_payload.get('crypto', {}).get('ok', False)) if isinstance(doctor_payload, dict) else False
        )
        db_revision = str(database_payload.get('currentRevision', '-') if isinstance(database_payload, dict) else '-')
        cache_size = cache_payload.get('dbSize', '-') if isinstance(cache_payload, dict) else '-'

        if not database_ok:
            status = 'fail'
            lines = [
                '## 首选入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("database").upper()}] 数据库',
                f'> {TUI_DIAGNOSTIC_SERVICE.build_database_focus_hint()}',
                '',
                '## 次级入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("ops").upper()}] 运维',
                f'> {TUI_DIAGNOSTIC_SERVICE.build_ops_focus_hint()}',
                '',
                '## 当前判断',
                f'迁移版本: {db_revision}',
                '> 数据库异常会优先阻断后续业务巡检',
            ]
        elif not redis_ok:
            status = 'fail'
            lines = [
                '## 首选入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("cache").upper()}] 缓存',
                f'> {TUI_DIAGNOSTIC_SERVICE.build_cache_focus_hint()}',
                '',
                '## 次级入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("ops").upper()}] 运维',
                f'> {TUI_DIAGNOSTIC_SERVICE.build_ops_focus_hint()}',
                '',
                '## 当前判断',
                f'Redis 键数: {cache_size}',
                '> 缓存异常通常会影响配置读取和任务运行',
            ]
        elif not crypto_ok:
            status = 'warn'
            lines = [
                '## 首选入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("crypto").upper()}] 加密',
                '> 先检查运行校验、公钥身份和兼容版本',
                '',
                '## 次级入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("ops").upper()}] 运维',
                '> 对照依赖版本，确认是否缺少加密相关运行依赖',
                '',
                '## 当前判断',
                '> 加密异常不会立即阻断全部能力，但会影响安全链路',
            ]
        else:
            status = 'ok'
            lines = [
                '## 首选入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("jobs").upper()}] 任务 · {TUI_DIAGNOSTIC_SERVICE.build_jobs_focus_hint()}',
                '## 次级入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("configs").upper()}] 参数配置 · {TUI_DIAGNOSTIC_SERVICE.build_configs_focus_hint()}',
                '## 扩展入口',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("gen").upper()}] 代码生成 · {TUI_DIAGNOSTIC_SERVICE.build_gen_focus_hint()}',
                f'[{TUI_KEYMAP_REGISTRY.get_navigation_shortcut("app").upper()}] 应用 · 配置摘要 / 路由状态',
            ]

        return DashboardPanelSnapshot(
            title='建议摘要',
            status=status,
            lines=lines,
        )

    def build_inspection_conclusion_panel(
        self,
        doctor_payload: dict[str, Any] | None,
        database_payload: dict[str, Any] | None,
        cache_payload: dict[str, Any] | None,
    ) -> DashboardPanelSnapshot:
        """
        构建首页巡检结论面板。

        :param doctor_payload: 健康检查负载
        :param database_payload: 数据库状态负载
        :param cache_payload: 缓存状态负载
        :return: 面板快照
        """
        database_ok = (
            bool(doctor_payload.get('database', {}).get('ok', False)) if isinstance(doctor_payload, dict) else False
        )
        redis_ok = bool(doctor_payload.get('redis', {}).get('ok', False)) if isinstance(doctor_payload, dict) else False
        crypto_ok = (
            bool(doctor_payload.get('crypto', {}).get('ok', False)) if isinstance(doctor_payload, dict) else False
        )
        db_revision = database_payload.get('currentRevision', '-') if isinstance(database_payload, dict) else '-'
        cache_size = cache_payload.get('dbSize', '-') if isinstance(cache_payload, dict) else '-'

        if not database_ok:
            status = 'fail'
            conclusion = '数据库存在异常，建议优先处理连接或迁移问题'
            next_step = '优先进入数据库页面，确认迁移版本和连接配置'
        elif not redis_ok:
            status = 'fail'
            conclusion = '缓存服务存在异常，建议优先检查 Redis 可用性'
            next_step = '优先进入缓存页面，确认连接数、键数量和状态说明'
        elif not crypto_ok:
            status = 'warn'
            conclusion = '加密组件状态异常，建议尽快核对运行依赖'
            next_step = '先查看系统摘要面板，再排查加密组件依赖'
        else:
            status = 'ok'
            conclusion = '当前核心依赖状态正常，可继续查看业务分区'
            next_step = '优先查看任务与参数配置页面，确认业务侧是否有风险'

        return DashboardPanelSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 建议操作',
                next_step,
                '',
                '## 当前快照',
                f'迁移版本: {db_revision}',
                f'Redis 键数: {cache_size}',
            ],
        )

    def build_database_panel(self, payload: dict[str, Any] | None) -> DashboardPanelSnapshot:
        """
        构建数据库状态面板。

        :param payload: `db current` JSON 负载
        :return: 面板快照
        """
        current_revision = payload.get('currentRevision', '-') if isinstance(payload, dict) else '-'
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DashboardPanelSnapshot(
                title='数据库摘要',
                status='fail',
                lines=self.formatting.build_failure_lines(
                    payload,
                    summary_label='迁移版本',
                    summary_value=str(current_revision or '-'),
                    suggestion=TUI_COPY.build_dashboard_page_suggestion('数据库', '确认迁移版本与连接状态'),
                ),
            )
        return DashboardPanelSnapshot(
            title='数据库摘要',
            status='ok',
            lines=[
                '## 迁移信息',
                f'迁移版本: {current_revision}',
                '',
                '## 状态说明',
                f'> {self.formatting.extract_payload_message(payload)}',
            ],
        )

    def build_cache_panel(self, payload: dict[str, Any] | None) -> DashboardPanelSnapshot:
        """
        构建缓存状态面板。

        :param payload: `cache stats` JSON 负载
        :return: 面板快照
        """
        if not isinstance(payload, dict):
            return DashboardPanelSnapshot(
                title='缓存摘要',
                status='fail',
                lines=self.formatting.build_failure_lines(
                    payload,
                    summary_label='缓存状态',
                    summary_value='不可用',
                    suggestion=TUI_COPY.build_dashboard_page_suggestion('缓存', '查看 Redis 状态'),
                ),
            )
        info = payload.get('info') if isinstance(payload.get('info'), dict) else {}
        cache_names = payload.get('cacheNames') if isinstance(payload.get('cacheNames'), list) else []
        return DashboardPanelSnapshot(
            title='缓存摘要',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## Redis 概况',
                f'当前键数: {payload.get("dbSize", "-")}',
                f'Redis 版本: {info.get("redis_version", "-")}',
                f'客户端连接数: {info.get("connected_clients", "-")}',
                '',
                '## 缓存资源',
                f'已登记缓存名: {len(cache_names)} 个',
            ],
        )

    def build_dependency_panel(self, payload: dict[str, Any] | None) -> DashboardPanelSnapshot:
        """
        构建首页依赖版本摘要面板。

        :param payload: `ops deps` JSON 负载
        :return: 面板快照
        """
        if not isinstance(payload, dict):
            return DashboardPanelSnapshot(
                title='依赖版本',
                status='fail',
                lines=self.formatting.build_failure_lines(
                    payload,
                    summary_label='依赖检查',
                    summary_value='不可用',
                    suggestion=TUI_COPY.build_dashboard_page_suggestion('运维', '检查依赖详情'),
                ),
            )
        packages = payload.get('packages') if isinstance(payload.get('packages'), dict) else {}
        missing_required = payload.get('missingRequired') if isinstance(payload.get('missingRequired'), list) else []
        lines = [
            '## 依赖结论',
            f'检查结果: {"通过" if payload.get("ok", False) else "异常"}',
            f'缺失核心依赖: {len(missing_required)} 个',
            '',
            '## 关键版本',
        ]
        for package_name in ('python', 'fastapi', 'sqlalchemy', 'redis'):
            package_payload = packages.get(package_name)
            if not isinstance(package_payload, dict):
                continue
            installed = '已安装' if package_payload.get('installed', False) else '缺失'
            lines.append(f'{package_name}: {installed} · {package_payload.get("version", "-") or "-"}')
        return DashboardPanelSnapshot(
            title='依赖版本',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=lines,
        )

    def build_server_info_panel(self, payload: dict[str, Any] | None) -> DashboardPanelSnapshot:
        """
        构建首页服务器概况面板。

        :param payload: `ops server-info` JSON 负载
        :return: 面板快照
        """
        server = payload.get('server') if isinstance(payload, dict) else None
        if not isinstance(server, dict):
            return DashboardPanelSnapshot(
                title='服务器摘要',
                status='fail',
                lines=self.formatting.build_failure_lines(
                    payload,
                    summary_label='服务器摘要',
                    summary_value='不可用',
                    suggestion=TUI_COPY.build_dashboard_page_suggestion('运维', '重新采集服务器摘要'),
                ),
            )
        sys_info = server.get('sys') if isinstance(server.get('sys'), dict) else {}
        cpu_info = server.get('cpu') if isinstance(server.get('cpu'), dict) else {}
        mem_info = server.get('mem') if isinstance(server.get('mem'), dict) else {}
        return DashboardPanelSnapshot(
            title='服务器摘要',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 主机状态',
                f'主机名: {sys_info.get("computerName", "-")}',
                f'主机 IP: {sys_info.get("computerIp", "-")}',
                '',
                '## 资源概况',
                f'CPU 使用率: {cpu_info.get("used", "-")}%',
                f'内存使用率: {mem_info.get("usage", "-")}%',
            ],
        )

    def build_risk_heatmap_panel(self, panels: list[DashboardPanelSnapshot]) -> DashboardPanelSnapshot:
        """
        构建首页风险热区面板。

        :param panels: 当前已构建的面板列表
        :return: 风险热区面板
        """
        sorted_panels = sorted(
            panels, key=lambda item: (self.formatting.resolve_status_priority(item.status), item.title)
        )
        fail_panels = [panel for panel in sorted_panels if panel.status == 'fail']
        warn_panels = [panel for panel in sorted_panels if panel.status == 'warn']
        primary_targets = fail_panels[:3] or warn_panels[:3] or sorted_panels[:3]

        lines = [
            '## 热区摘要',
            f'失败面板: {len(fail_panels)} 个',
            f'警告面板: {len(warn_panels)} 个',
            '',
            '## 优先关注',
        ]
        if not primary_targets:
            lines.extend(
                self.formatting.build_empty_lines(
                    summary_label='风险热区',
                    summary_value='0 个',
                    detail='当前没有需要优先处理的失败或警告面板',
                    suggestion='可继续浏览任务、缓存、参数配置等业务页面',
                )
            )
        else:
            for index, panel in enumerate(primary_targets, start=1):
                lead_line = SHELL_TEXT_FORMATTER.truncate_text(
                    panel.lines[1] if len(panel.lines) > 1 else panel.lines[0], 56
                )
                lines.extend(
                    [
                        f'> HOT-{index:02d} [{panel.status.upper()}] {panel.title}',
                        f'> {lead_line}',
                    ]
                )

        status = 'fail' if fail_panels else 'warn' if warn_panels else 'ok'
        return DashboardPanelSnapshot(
            title='风险摘要',
            status=status,
            lines=lines,
        )

    def build_panels(
        self,
        *,
        env: str,
        app_env_payload: dict[str, Any] | None,
        app_routes_payload: dict[str, Any] | None,
        doctor_payload: dict[str, Any] | None,
        database_payload: dict[str, Any] | None,
        cache_payload: dict[str, Any] | None,
        deps_payload: dict[str, Any] | None,
        server_payload: dict[str, Any] | None,
    ) -> list[DashboardPanelSnapshot]:
        """
        构建首页全部原始面板。

        :param env: 当前运行环境
        :param app_env_payload: 应用环境负载
        :param app_routes_payload: 应用路由负载
        :param doctor_payload: 健康检查负载
        :param database_payload: 数据库状态负载
        :param cache_payload: 缓存状态负载
        :param deps_payload: 运维依赖负载
        :param server_payload: 服务器摘要负载
        :return: 原始面板列表
        """
        panels = [
            self.build_app_env_panel(env, app_env_payload, app_routes_payload),
            self.build_health_panel(doctor_payload),
            self.build_inspection_conclusion_panel(doctor_payload, database_payload, cache_payload),
            self.build_recommended_entry_panel(doctor_payload, database_payload, cache_payload),
            self.build_database_panel(database_payload),
            self.build_cache_panel(cache_payload),
            self.build_dependency_panel(deps_payload),
            self.build_server_info_panel(server_payload),
        ]
        panels.append(self.build_risk_heatmap_panel(panels))
        return panels


class DashboardMetricBuilder:
    """
    首页指标卡构建器。

    该对象负责根据健康检查、数据库和缓存状态构建首页驾驶舱指标卡。

    :param formatting: 首页仪表盘格式化支持对象
    """

    def __init__(self, formatting: DashboardFormattingSupport) -> None:
        """
        初始化首页指标卡构建器。

        :param formatting: 首页仪表盘格式化支持对象
        :return: None
        """
        self.formatting = formatting

    def build_metrics(
        self,
        doctor_payload: dict[str, Any] | None,
        database_payload: dict[str, Any] | None,
        cache_payload: dict[str, Any] | None,
    ) -> list[DashboardMetricSnapshot]:
        """
        构建首页驾驶舱指标卡。

        :param doctor_payload: 健康检查负载
        :param database_payload: 数据库状态负载
        :param cache_payload: 缓存状态负载
        :return: 指标卡列表
        """
        database = doctor_payload.get('database') if isinstance(doctor_payload, dict) else None
        redis = doctor_payload.get('redis') if isinstance(doctor_payload, dict) else None
        crypto = doctor_payload.get('crypto') if isinstance(doctor_payload, dict) else None

        dependency_results = [
            bool(database.get('ok', False)) if isinstance(database, dict) else False,
            bool(redis.get('ok', False)) if isinstance(redis, dict) else False,
            bool(crypto.get('ok', False)) if isinstance(crypto, dict) else False,
        ]
        passed_dependencies = sum(1 for item in dependency_results if item)
        posture = '风险' if isinstance(doctor_payload, dict) and not doctor_payload.get('ok', False) else '稳定'
        posture_status = 'fail' if posture == '风险' else 'ok'
        current_revision = database_payload.get('currentRevision', '-') if isinstance(database_payload, dict) else '-'
        cache_size = cache_payload.get('dbSize', '-') if isinstance(cache_payload, dict) else '-'

        metrics = [
            DashboardMetricSnapshot(
                title='当前态势',
                value=f'{self.formatting.render_signal_bar(passed_dependencies, DEPENDENCY_CHECK_TOTAL)} {posture}',
                status=posture_status,
                hint=f'依赖通过 {passed_dependencies}/{DEPENDENCY_CHECK_TOTAL}，健康检查自动判定',
            ),
            DashboardMetricSnapshot(
                title='依赖通过率',
                value=(
                    f'{self.formatting.render_signal_bar(passed_dependencies, DEPENDENCY_CHECK_TOTAL)} '
                    f'{passed_dependencies}/{DEPENDENCY_CHECK_TOTAL}'
                ),
                status=(
                    'ok'
                    if passed_dependencies == DEPENDENCY_CHECK_TOTAL
                    else 'warn'
                    if passed_dependencies > 0
                    else 'fail'
                ),
                hint='数据库、Redis、加密组件',
            ),
            DashboardMetricSnapshot(
                title='迁移版本',
                value=f'[{SHELL_TEXT_FORMATTER.truncate_text(current_revision, 16)}]',
                status='ok' if current_revision != '-' else 'warn',
                hint='当前数据库 revision 基线',
            ),
            DashboardMetricSnapshot(
                title='Redis 键数',
                value=f'[KEYS] {cache_size}',
                status='info',
                hint='当前缓存库 key 数量观测值',
            ),
        ]
        return sorted(
            metrics,
            key=lambda item: self.formatting.resolve_status_priority(item.status),
        )


class DashboardAdapter:
    """
    TUI 首页巡检聚合适配器。

    该适配器负责采集应用、健康检查、数据库、缓存与运维只读快照，
    并委托面板构建器、指标构建器和压缩器组装首页结果。
    """

    def __init__(
        self,
        formatting: DashboardFormattingSupport | None = None,
        panel_builder: DashboardPanelBuilder | None = None,
        metric_builder: DashboardMetricBuilder | None = None,
        panel_compressor: DashboardPanelCompressor | None = None,
        snapshot_collector: DashboardSnapshotCollector | None = None,
    ) -> None:
        """
        初始化首页巡检聚合适配器。

        :param formatting: 首页仪表盘格式化支持对象
        :param panel_builder: 首页面板构建器
        :param metric_builder: 首页指标卡构建器
        :param panel_compressor: 首页面板压缩器
        :param snapshot_collector: 首页聚合数据采集器
        :return: None
        """
        self.formatting = formatting or DashboardFormattingSupport()
        self.panel_builder = panel_builder or DashboardPanelBuilder(self.formatting)
        self.metric_builder = metric_builder or DashboardMetricBuilder(self.formatting)
        self.panel_compressor = panel_compressor or DashboardPanelCompressor(self.formatting)
        self.snapshot_collector = snapshot_collector or DashboardSnapshotCollector()

    def collect_snapshot(self, env: str) -> DashboardSnapshot:
        """
        采集 TUI 首页只读巡检快照。

        :param env: 当前运行环境
        :return: 首页聚合快照
        """
        source_payloads = self.snapshot_collector.collect(env)
        panels = self.panel_builder.build_panels(
            env=env,
            app_env_payload=source_payloads.app_env_payload,
            app_routes_payload=source_payloads.app_routes_payload,
            doctor_payload=source_payloads.doctor_payload,
            database_payload=source_payloads.database_payload,
            cache_payload=source_payloads.cache_payload,
            deps_payload=source_payloads.deps_payload,
            server_payload=source_payloads.server_payload,
        )
        return DashboardSnapshot(
            env=env,
            metrics=self.metric_builder.build_metrics(
                source_payloads.doctor_payload,
                source_payloads.database_payload,
                source_payloads.cache_payload,
            ),
            panels=self.panel_compressor.compact_panels(panels),
        )


DASHBOARD_ADAPTER = DashboardAdapter()
