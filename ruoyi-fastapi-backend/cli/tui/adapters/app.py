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

COMPLETION_PREVIEW_LINE_LIMIT = 12


@dataclass(frozen=True)
class AppDetailSourcePayloads:
    """
    应用详情页原始数据源快照。

    :param env_payload: `app env` 结果
    :param config_payload: `app config` 结果
    :param doctor_payload: `app doctor` 结果
    :param routes_payload: `app routes` 结果
    :param completion_payload: `completion doctor` 结果
    :param completion_preview_result: `completion show` 命令结果
    :param preview_shell: 当前补全脚本预览 shell
    """

    env_payload: dict[str, Any] | None
    config_payload: dict[str, Any] | None
    doctor_payload: dict[str, Any] | None
    routes_payload: dict[str, Any] | None
    completion_payload: dict[str, Any] | None
    completion_preview_result: Any
    preview_shell: str


class AppDetailSnapshotCollector:
    """
    应用详情页数据采集器。

    该对象负责拉取应用详情页所需的多路 CLI 原始结果，
    让 `AppDetailAdapter` 保持详情页编排职责。

    :param section_builder: 应用详情分区构建器
    """

    def __init__(self, section_builder: 'AppSectionBuilder') -> None:
        """
        初始化应用详情页数据采集器。

        :param section_builder: 应用详情分区构建器
        :return: None
        """
        self.section_builder = section_builder

    def collect(self, env: str) -> AppDetailSourcePayloads:
        """
        采集应用详情页所需原始结果。

        :param env: 当前运行环境
        :return: 应用详情页原始数据源快照
        """
        env_payload = NESTED_CLI_SUPPORT.run(
            'app',
            'env',
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload
        config_payload = NESTED_CLI_SUPPORT.run(
            'app',
            'config',
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload
        doctor_payload = NESTED_CLI_SUPPORT.run(
            'app',
            'doctor',
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload
        routes_payload = NESTED_CLI_SUPPORT.run(
            'app',
            'routes',
            f'--env={env}',
            '--group-by=tag',
            '--output=json',
            parse_json=True,
        ).payload
        completion_payload = NESTED_CLI_SUPPORT.run(
            'completion',
            'doctor',
            '--output=json',
            parse_json=True,
        ).payload
        preview_shell = self.section_builder.resolve_completion_preview_shell(completion_payload)
        completion_preview_result = NESTED_CLI_SUPPORT.run('completion', 'show', preview_shell)
        return AppDetailSourcePayloads(
            env_payload=env_payload,
            config_payload=config_payload,
            doctor_payload=doctor_payload,
            routes_payload=routes_payload,
            completion_payload=completion_payload,
            completion_preview_result=completion_preview_result,
            preview_shell=preview_shell,
        )


class AppSectionBuilder:
    """
    应用详情分区构建器。

    该构建器负责将应用、补全和路由相关 CLI 结果转换为 TUI 详情页分区，
    使详情页适配器本体只保留采集与编排职责。
    """

    @staticmethod
    def resolve_completion_preview_shell(payload: dict[str, Any] | None) -> str:
        """
        解析补全脚本预览应使用的 shell。

        :param payload: `completion doctor` JSON 负载
        :return: shell 名称
        """
        if not isinstance(payload, dict):
            return 'bash'
        active_shell = str(payload.get('activeShell') or '').strip().lower()
        shells = payload.get('shells') if isinstance(payload.get('shells'), dict) else {}
        if active_shell and isinstance(shells.get(active_shell), dict) and shells[active_shell].get('supported', False):
            return active_shell
        for shell_name in ('bash', 'zsh', 'fish', 'powershell'):
            shell_payload = shells.get(shell_name)
            if isinstance(shell_payload, dict) and shell_payload.get('supported', False):
                return shell_name
        return 'bash'

    @staticmethod
    def build_env_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建应用环境解析分区。

        :param payload: `app env` JSON 负载
        :return: 分区快照
        """
        runtime = payload.get('runtime') if isinstance(payload, dict) else None
        if not isinstance(runtime, dict):
            return DetailSectionSnapshot(
                title='环境解析',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='环境信息', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='环境解析',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 环境映射',
                f'CLI 目标环境: {runtime.get("cliEnv", "-")}',
                f'配置模块环境: {runtime.get("configEnv", "-")}',
                f'进程环境变量: {runtime.get("appEnv", "-") or "-"}',
                '',
                '## 文件与进程',
                f'环境文件: {runtime.get("envFile", "-")}',
                f'环境文件存在: {"是" if runtime.get("envFileExists", False) else "否"}',
                f'后端目录: {SHELL_TEXT_FORMATTER.truncate_text(runtime.get("backendDir", "-"), 64)}',
                f'Python 可执行文件: {SHELL_TEXT_FORMATTER.truncate_text(runtime.get("pythonExecutable", "-"), 64)}',
            ],
        )

    @staticmethod
    def build_config_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建应用基础配置分区。

        :param payload: `app config` JSON 负载
        :return: 分区快照
        """
        config = payload.get('config') if isinstance(payload, dict) else None
        if not isinstance(config, dict):
            return DetailSectionSnapshot(
                title='应用配置',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='应用配置', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='应用配置',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 应用入口',
                f'应用名称: {SHELL_TEXT_FORMATTER.truncate_text(config.get("name", "-"), 40)}',
                f'监听地址: {config.get("host", "-")}:{config.get("port", "-")}',
                f'根路径: {config.get("rootPath", "-") or "/"}',
                f'工作进程: {config.get("workers", "-")}',
                f'热重载: {"开启" if config.get("reload", False) else "关闭"}',
                '',
                '## 文档与日志',
                f'Swagger: {"关闭" if config.get("disableSwagger", False) else "开启"}',
                f'ReDoc: {"关闭" if config.get("disableRedoc", False) else "开启"}',
                f'日志级别: {config.get("logLevel", "-")}',
            ],
        )

    @staticmethod
    def build_dependency_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建应用依赖配置分区。

        :param payload: `app config` JSON 负载
        :return: 分区快照
        """
        config = payload.get('config') if isinstance(payload, dict) else None
        if not isinstance(config, dict):
            return DetailSectionSnapshot(
                title='依赖配置',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='依赖配置', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='依赖配置',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 数据库',
                f'类型: {config.get("dbType", "-")}',
                f'地址: {config.get("dbHost", "-")}:{config.get("dbPort", "-")}',
                f'数据库名: {config.get("dbDatabase", "-")}',
                '',
                '## Redis 与加密',
                f'Redis 地址: {config.get("redisHost", "-")}:{config.get("redisPort", "-")}',
                f'传输加密: {"开启" if config.get("transportCryptoEnabled", False) else "关闭"}',
                f'加密模式: {config.get("transportCryptoMode", "-")}',
            ],
        )

    def build_routes_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建应用路由摘要分区。

        :param payload: `app routes` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='路由摘要',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='路由', empty_value='不可用'),
            )

        count = payload.get('count', 0)
        routes = payload.get('routes') if isinstance(payload.get('routes'), list) else []
        grouped_routes = payload.get('groupedRoutes') if isinstance(payload.get('groupedRoutes'), dict) else {}
        group_items = sorted(
            ((str(tag), len(items) if isinstance(items, list) else 0) for tag, items in grouped_routes.items()),
            key=lambda item: (-item[1], item[0]),
        )

        lines = [
            '## 路由规模',
            f'总路由数: {count}',
            f'标签分组数: {len(group_items)}',
            '',
            '## 主要标签',
        ]
        if group_items:
            lines.extend(f'> {tag} · {size} 条' for tag, size in group_items[:6])
        else:
            lines.append('> 暂无标签分组数据')

        if routes:
            lines.extend(['', '## 路由样本'])
            for route in routes[:6]:
                if not isinstance(route, dict):
                    continue
                methods = '/'.join(route.get('methods', [])) if isinstance(route.get('methods'), list) else '-'
                lines.extend(
                    [
                        f'> [{methods or "-"}] {SHELL_TEXT_FORMATTER.truncate_text(route.get("path", "-"), 48)}',
                        f'> {SHELL_TEXT_FORMATTER.truncate_text(route.get("summary", "-") or "-", 48)}',
                    ]
                )
        else:
            lines.extend(
                [
                    '',
                    *TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                        empty_label='路由样本',
                        empty_value='0 条',
                        detail='当前环境未返回可展示的路由样本',
                        suggestion=TUI_COPY.build_refresh_page_suggestion('应用', '确认当前环境是否已完成路由注册'),
                    ),
                ]
            )

        return DetailSectionSnapshot(
            title='路由摘要',
            status='ok',
            lines=lines,
        )

    @staticmethod
    def build_completion_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建 shell completion 诊断分区。

        :param payload: `completion doctor` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='补全诊断',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='补全诊断', empty_value='不可用'
                ),
            )

        shells = payload.get('shells') if isinstance(payload.get('shells'), dict) else {}
        active_shell = str(payload.get('activeShell') or '-')
        env_choices = payload.get('envChoices') if isinstance(payload.get('envChoices'), list) else []
        active_shell_payload = shells.get(active_shell) if isinstance(shells.get(active_shell), dict) else None
        target_file = active_shell_payload.get('targetFile', '-') if isinstance(active_shell_payload, dict) else '-'
        source_command = (
            active_shell_payload.get('sourceCommand', '-') if isinstance(active_shell_payload, dict) else '-'
        )
        install_command = (
            active_shell_payload.get('recommendedInstallCommand', '-')
            if isinstance(active_shell_payload, dict)
            else payload.get('recommendedInstallCommand', '-')
        )

        lines = [
            '## 当前环境',
            f'活动 Shell: {active_shell}',
            f'项目目录: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("projectDir", "-"), 64)}',
            f'补全环境变量: {payload.get("completeEnvVar", "-")}',
            f'环境候选数: {len(env_choices)}',
            '',
            '## 激活建议',
            f'目标脚本: {SHELL_TEXT_FORMATTER.truncate_text(target_file, 64)}',
            f'加载命令: {SHELL_TEXT_FORMATTER.truncate_text(source_command, 72)}',
            f'推荐安装命令: {SHELL_TEXT_FORMATTER.truncate_text(install_command, 72)}',
        ]

        shell_lines = []
        for shell_name in ('bash', 'zsh', 'fish', 'powershell'):
            shell_payload = shells.get(shell_name)
            if not isinstance(shell_payload, dict):
                continue
            supported = '支持' if shell_payload.get('supported', False) else '不支持'
            detected = '当前 Shell' if shell_payload.get('detected', False) else '候选 Shell'
            shell_lines.append(f'> {shell_name} · {supported} · {detected}')
        if shell_lines:
            lines.extend(['', '## Shell 支持'])
            lines.extend(shell_lines)

        return DetailSectionSnapshot(
            title='补全诊断',
            status='ok',
            lines=lines,
        )

    def build_completion_preview_section(
        self,
        shell: str,
        preview_result: Any,
    ) -> DetailSectionSnapshot:
        """
        构建补全脚本预览分区。

        :param shell: 当前预览 shell
        :param preview_result: `completion show` 调用结果
        :return: 分区快照
        """
        stdout = str(getattr(preview_result, 'stdout', '') or '').strip()
        stderr = str(getattr(preview_result, 'stderr', '') or '').strip()
        returncode = int(getattr(preview_result, 'returncode', 1) or 0)
        if returncode != 0:
            return DetailSectionSnapshot(
                title='补全脚本预览',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    {'ok': False, 'message': stderr or stdout or '补全脚本生成失败'},
                    empty_label='补全脚本',
                    empty_value='不可用',
                ),
            )
        preview_lines = [
            SHELL_TEXT_FORMATTER.truncate_text(line, 88) for line in stdout.splitlines()[:COMPLETION_PREVIEW_LINE_LIMIT]
        ]
        if not preview_lines:
            return DetailSectionSnapshot(
                title='补全脚本预览',
                status='info',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                    empty_label='补全脚本',
                    empty_value='0 行',
                    detail='当前 shell 的补全脚本未返回可预览内容',
                    suggestion=TUI_COPY.build_refresh_page_suggestion('应用', '重新生成补全脚本预览'),
                ),
            )
        return DetailSectionSnapshot(
            title='补全脚本预览',
            status='ok',
            lines=[
                '## 预览目标',
                f'Shell: {shell}',
                f'预览行数: {len(preview_lines)}',
                '',
                '## 脚本片段',
                *preview_lines,
            ],
        )

    @staticmethod
    def build_doctor_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建应用启动前检查分区。

        :param payload: `app doctor` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict):
            return DetailSectionSnapshot(
                title='启动前检查',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='启动前检查', empty_value='不可用'
                ),
            )

        database = payload.get('database') if isinstance(payload.get('database'), dict) else {}
        redis = payload.get('redis') if isinstance(payload.get('redis'), dict) else {}
        crypto = payload.get('crypto') if isinstance(payload.get('crypto'), dict) else {}
        return DetailSectionSnapshot(
            title='启动前检查',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 检查结果',
                f'环境: {payload.get("env", "-")}',
                f'数据库: {"正常" if database.get("ok", False) else "异常"}',
                f'> {SHELL_TEXT_FORMATTER.truncate_text(database.get("message", "-"), 64)}',
                f'Redis: {"正常" if redis.get("ok", False) else "异常"}',
                f'> {SHELL_TEXT_FORMATTER.truncate_text(redis.get("message", "-"), 64)}',
                f'加密组件: {"正常" if crypto.get("ok", False) else "异常"}',
                f'> {SHELL_TEXT_FORMATTER.truncate_text(crypto.get("message", "-"), 64)}',
            ],
        )

    @staticmethod
    def build_run_entry_section() -> DetailSectionSnapshot:
        """
        构建应用启动向导入口分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='启动入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备启动当前环境应用时，可直接启动应用，或先通过向导确认目标环境与启动前检查选项。',
                command=TUI_COPY.build_cli_command_hint('app', 'run', '--env=dev'),
                guide='若需要先做启动前检查或切换环境，建议改用 `wizard app-run` 进入交互式启动流程。',
            ),
        )

    @staticmethod
    def build_completion_install_entry_section() -> DetailSectionSnapshot:
        """
        构建 shell 补全安装入口分区。

        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='补全安装入口',
            status='info',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备为当前 Shell 安装或修复补全脚本时，可直接执行补全安装命令，并按需把激活命令写入 rc 文件。',
                command=TUI_COPY.build_cli_command_hint('completion', 'install', '--activate', '--output=text'),
                guide='当前页面提供补全诊断与安装入口；执行安装后可返回补全诊断分区确认 target file 和 source command 是否更新。',
            ),
        )

    @staticmethod
    def build_overview_section(
        env_payload: dict[str, Any] | None,
        config_payload: dict[str, Any] | None,
        doctor_payload: dict[str, Any] | None,
        routes_payload: dict[str, Any] | None,
        completion_payload: dict[str, Any] | None,
    ) -> DetailSectionSnapshot:
        """
        构建应用页总览判断分区。

        :param env_payload: `app env` JSON 负载
        :param config_payload: `app config` JSON 负载
        :param doctor_payload: `app doctor` JSON 负载
        :param routes_payload: `app routes` JSON 负载
        :param completion_payload: `completion doctor` JSON 负载
        :return: 分区快照
        """
        env_ok = bool(isinstance(env_payload, dict) and env_payload.get('ok', False))
        config_ok = bool(isinstance(config_payload, dict) and config_payload.get('ok', False))
        doctor_ok = bool(isinstance(doctor_payload, dict) and doctor_payload.get('ok', False))
        routes_ok = bool(isinstance(routes_payload, dict) and routes_payload.get('ok', False))
        completion_ok = bool(isinstance(completion_payload, dict) and completion_payload.get('ok', False))
        route_count = routes_payload.get('count', 0) if isinstance(routes_payload, dict) else 0
        runtime = (
            env_payload.get('runtime')
            if isinstance(env_payload, dict) and isinstance(env_payload.get('runtime'), dict)
            else {}
        )
        config = (
            config_payload.get('config')
            if isinstance(config_payload, dict) and isinstance(config_payload.get('config'), dict)
            else {}
        )

        status = 'ok'
        conclusion = '应用基线正常，可继续查看环境映射、配置摘要与路由状态'
        if not env_ok or not config_ok:
            status = 'fail'
            conclusion = '应用基础信息读取异常，优先确认环境映射与应用配置是否可用'
        elif not doctor_ok:
            status = 'fail'
            conclusion = '启动前检查异常，优先确认数据库、Redis 和加密组件状态'
        elif not completion_ok:
            status = 'warn'
            conclusion = '补全诊断读取异常，建议优先确认项目目录、Shell 类型和补全脚本状态'
        elif not routes_ok:
            status = 'warn'
            conclusion = '路由摘要读取异常，建议先确认当前环境是否完成应用初始化'
        elif int(route_count or 0) <= 0:
            status = 'info'
            conclusion = '当前未返回注册路由，建议检查路由注册流程与运行上下文'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'CLI 环境: {runtime.get("cliEnv", "-")}',
                f'配置环境: {runtime.get("configEnv", "-")}',
                f'监听地址: {config.get("host", "-")}:{config.get("port", "-")}',
                f'注册路由: {route_count} 条',
                f'启动前检查: {"正常" if doctor_ok else "异常"}',
                f'传输加密: {"开启" if config.get("transportCryptoEnabled", False) else "关闭"}',
                f'补全诊断: {"正常" if completion_ok else "异常"}',
                '',
                '## 建议入口',
                '优先关注：环境解析 / 应用配置 / 启动前检查 / 补全诊断 / 路由摘要 / 启动入口',
            ],
        )

    def build_sections(
        self,
        *,
        env_payload: dict[str, Any] | None,
        config_payload: dict[str, Any] | None,
        doctor_payload: dict[str, Any] | None,
        routes_payload: dict[str, Any] | None,
        completion_payload: dict[str, Any] | None,
        completion_preview_result: Any,
        preview_shell: str,
    ) -> list[DetailSectionSnapshot]:
        """
        构建应用页全部详情分区。

        :param env_payload: `app env` 结果负载
        :param config_payload: `app config` 结果负载
        :param doctor_payload: `app doctor` 结果负载
        :param routes_payload: `app routes` 结果负载
        :param completion_payload: `completion doctor` 结果负载
        :param completion_preview_result: `completion show` 命令结果
        :param preview_shell: 当前预览 shell
        :return: 详情分区列表
        """
        return [
            self.build_overview_section(
                env_payload,
                config_payload,
                doctor_payload,
                routes_payload,
                completion_payload,
            ),
            self.build_env_section(env_payload),
            self.build_config_section(config_payload),
            self.build_dependency_section(config_payload),
            self.build_doctor_section(doctor_payload),
            self.build_completion_section(completion_payload),
            self.build_completion_preview_section(preview_shell, completion_preview_result),
            self.build_completion_install_entry_section(),
            self.build_routes_section(routes_payload),
            self.build_run_entry_section(),
        ]


class AppDetailAdapter(BaseDetailAdapter):
    """
    应用详情页适配器。

    该适配器负责采集应用相关 CLI 结果，并委托分区构建器组装为
    TUI 详情页快照。
    """

    def __init__(
        self,
        section_builder: AppSectionBuilder | None = None,
        snapshot_collector: AppDetailSnapshotCollector | None = None,
    ) -> None:
        """
        初始化应用详情页适配器。

        :param section_builder: 应用详情分区构建器
        :param snapshot_collector: 应用详情页数据采集器
        :return: None
        """
        super().__init__(
            page_title='应用',
            search_view_key='app',
            default_suggestions=[
                '总览判断',
                '环境解析',
                '应用配置',
                '依赖配置',
                '启动前检查',
                '补全诊断',
                '补全脚本预览',
                '补全安装入口',
                '路由摘要',
                '启动入口',
            ],
        )
        self.section_builder = section_builder or AppSectionBuilder()
        self.snapshot_collector = snapshot_collector or AppDetailSnapshotCollector(self.section_builder)

    def collect_snapshot(self, env: str, query: str = '') -> DetailPageSnapshot:
        """
        采集应用状态页只读快照。

        :param env: 当前运行环境
        :param query: 当前搜索词
        :return: 页面快照
        """
        source_payloads = self.snapshot_collector.collect(env)
        sections = self.section_builder.build_sections(
            env_payload=source_payloads.env_payload,
            config_payload=source_payloads.config_payload,
            doctor_payload=source_payloads.doctor_payload,
            routes_payload=source_payloads.routes_payload,
            completion_payload=source_payloads.completion_payload,
            completion_preview_result=source_payloads.completion_preview_result,
            preview_shell=source_payloads.preview_shell,
        )
        return DetailPageSnapshot(
            title='应用',
            subtitle=TUI_DIAGNOSTIC_SERVICE.build_app_diagnostic_subtitle(
                source_payloads.env_payload,
                source_payloads.config_payload,
                source_payloads.doctor_payload,
                source_payloads.routes_payload,
                source_payloads.completion_payload,
            ),
            sections=self.filter_sections(sections, query),
            search=self.resolve_search_context(query),
        )


APP_DETAIL_ADAPTER = AppDetailAdapter()
