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
from cli.tui.search import JOB_FILTER_OPTIONS
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER


class JobRenderingSupport:
    """
    任务浏览页渲染支持对象。

    该对象负责状态文本、时间线标记、成功率信号条和失败任务提取等基础
    逻辑，供筛选、分区和记录构建复用。

    :param page_adapter: 任务浏览页适配器
    """

    def __init__(self, page_adapter: BaseBrowserAdapter) -> None:
        """
        初始化任务浏览页渲染支持对象。

        :param page_adapter: 任务浏览页适配器
        :return: None
        """
        self.page_adapter = page_adapter

    def extract_failed_job_names(self, payload: dict[str, Any] | None) -> set[str]:
        """
        从失败日志结果中提取任务名称集合。

        :param payload: 失败日志负载
        :return: 失败任务名称集合
        """
        rows = self.page_adapter.extract_page_rows(payload)
        failed_job_names: set[str] = set()
        for row in rows:
            job_name = str(row.get('jobName', '') or '').strip()
            if job_name:
                failed_job_names.add(job_name)
        return failed_job_names

    @staticmethod
    def render_job_status(value: object) -> str:
        """
        将任务状态码转换为可读文本。

        :param value: 原始状态值
        :return: 中文状态文本
        """
        normalized = str(value).strip()
        if normalized == '0':
            return '正常'
        if normalized == '1':
            return '暂停'
        return normalized or '-'

    @staticmethod
    def render_job_log_status(value: object) -> str:
        """
        将任务日志状态码转换为可读文本。

        :param value: 原始状态值
        :return: 中文状态文本
        """
        normalized = str(value).strip()
        if normalized == '0':
            return '成功'
        if normalized == '1':
            return '失败'
        return normalized or '-'

    def render_job_log_timeline_title(self, row: dict[str, Any]) -> str:
        """
        渲染单条任务日志时间线标题。

        :param row: 日志行数据
        :return: 时间线标题文本
        """
        created_at = SHELL_TEXT_FORMATTER.truncate_text(row.get('createTime', '-'), 24)
        if created_at and created_at != '-':
            return f'{created_at} · {self.render_job_log_status(row.get("status", "-"))}'
        return f'日志 {row.get("jobLogId", "-")} · {self.render_job_log_status(row.get("status", "-"))}'

    @staticmethod
    def render_timeline_marker(status: object) -> str:
        """
        根据日志状态渲染时间线节点标记。

        :param status: 原始日志状态
        :return: 节点标记
        """
        return 'x' if str(status).strip() == '1' else 'o'

    @staticmethod
    def render_signal_bar(passed: int, total: int, *, width: int = 8) -> str:
        """
        渲染 ASCII 成功率条。

        :param passed: 成功数量
        :param total: 总数量
        :param width: 条形宽度
        :return: ASCII 条形
        """
        if total <= 0:
            return f'[{"-" * width}]'
        safe_passed = max(0, min(passed, total))
        filled = round((safe_passed / total) * width)
        return f'[{"#" * filled}{"-" * max(0, width - filled)}]'

    @staticmethod
    def extract_latest_log_time(rows: list[dict[str, Any]]) -> str:
        """
        提取日志列表中的最近时间。

        :param rows: 日志行数据
        :return: 最近时间文本
        """
        if not rows:
            return '-'
        latest_time = str(rows[0].get('createTime', '-') or '-').strip()
        return latest_time or '-'


class JobRowFilter:
    """
    任务浏览行过滤器。

    该对象负责按筛选键和搜索词过滤任务行数据。
    """

    @staticmethod
    def apply_job_filter(
        rows: list[dict[str, Any]],
        failed_job_names: set[str],
        filter_key: str,
    ) -> list[dict[str, Any]]:
        """
        按筛选键过滤任务行数据。

        :param rows: 原始任务行列表
        :param failed_job_names: 最近失败任务名称集合
        :param filter_key: 当前筛选键
        :return: 过滤后的任务行列表
        """
        normalized_filter = str(filter_key).strip().lower()
        if normalized_filter == 'failed':
            return [row for row in rows if str(row.get('jobName', '') or '').strip() in failed_job_names]
        if normalized_filter == 'paused':
            return [row for row in rows if str(row.get('status', '')).strip() == '1']
        if normalized_filter == 'ok':
            return [
                row
                for row in rows
                if str(row.get('jobName', '') or '').strip() not in failed_job_names
                and str(row.get('status', '')).strip() != '1'
            ]
        return rows

    @staticmethod
    def apply_job_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        """
        按任务名称查询词过滤任务行数据。

        :param rows: 原始任务行列表
        :param query: 当前搜索词
        :return: 过滤后的任务行列表
        """
        normalized_query = str(query).strip().lower()
        if not normalized_query:
            return rows
        return [
            row
            for row in rows
            if normalized_query in str(row.get('jobName', '') or '').strip().lower()
            or normalized_query in str(row.get('jobGroup', '') or '').strip().lower()
        ]


class JobSectionBuilder:
    """
    任务浏览页分区构建器。

    该构建器负责构建任务页共享分区以及单条任务详情分区。

    :param page_adapter: 任务浏览页适配器
    :param rendering: 任务浏览页渲染支持对象
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        rendering: JobRenderingSupport,
    ) -> None:
        """
        初始化任务浏览页分区构建器。

        :param page_adapter: 任务浏览页适配器
        :param rendering: 任务浏览页渲染支持对象
        :return: None
        """
        self.page_adapter = page_adapter
        self.rendering = rendering

    def build_job_failure_aggregate_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建任务失败聚合共享分区。

        :param payload: 失败日志 JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title='失败聚合',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='失败聚合', empty_value='不可用'
                ),
            )

        rows = self.page_adapter.extract_page_rows(payload)
        if not rows:
            return DetailSectionSnapshot(
                title='失败聚合',
                status='ok',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                    empty_label='失败日志',
                    empty_value='0 条',
                    detail='当前失败日志池为空，最近没有采集到失败执行记录',
                ),
            )

        grouped_rows: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            job_name = str(row.get('jobName', '-') or '-').strip() or '-'
            grouped_rows.setdefault(job_name, []).append(row)

        sorted_groups = sorted(
            grouped_rows.items(),
            key=lambda item: (-len(item[1]), self.rendering.extract_latest_log_time(item[1]), item[0]),
            reverse=False,
        )
        lines = [
            '## 失败池',
            f'失败日志: {len(rows)} 条',
            f'涉及任务: {len(grouped_rows)} 个',
            f'最近失败: {self.rendering.extract_latest_log_time(rows)}',
            '',
            '## 高频失败任务',
        ]
        for index, (job_name, job_rows) in enumerate(sorted_groups[:6], start=1):
            latest_row = job_rows[0]
            latest_time = self.rendering.extract_latest_log_time(job_rows)
            latest_message = SHELL_TEXT_FORMATTER.truncate_text(latest_row.get('jobMessage', '-'), 48)
            lines.extend(
                [
                    f'[{index}] {SHELL_TEXT_FORMATTER.truncate_text(job_name, 28)} · {len(job_rows)} 次',
                    f'> 最近失败: {latest_time}',
                    f'> 最近结果: {latest_message}',
                ]
            )
            exception_info = SHELL_TEXT_FORMATTER.truncate_text(latest_row.get('exceptionInfo', ''), 48)
            if exception_info:
                lines.append(f'> 异常摘要: {exception_info}')
            lines.append('')

        if lines[-1] == '':
            lines.pop()
        return DetailSectionSnapshot(
            title='失败聚合',
            status='warn',
            lines=lines,
        )

    def build_jobs_overview_section(
        self,
        rows: list[dict[str, Any]],
        filtered_rows: list[dict[str, Any]],
        failed_job_names: set[str],
        paused_count: int,
        failed_logs_payload: dict[str, Any] | None,
        filter_label: str,
    ) -> DetailSectionSnapshot:
        """
        构建任务页总览判断共享分区。

        :param rows: 原始任务行列表
        :param filtered_rows: 当前筛选后的任务行列表
        :param failed_job_names: 最近失败任务名称集合
        :param paused_count: 暂停任务数量
        :param failed_logs_payload: 失败日志负载
        :param filter_label: 当前筛选标签
        :return: 分区快照
        """
        failed_rows = self.page_adapter.extract_page_rows(failed_logs_payload)
        latest_failure = self.rendering.extract_latest_log_time(failed_rows)
        status = 'ok'
        conclusion = '当前任务基线正常，可继续查看执行轨迹与最近执行记录'
        if failed_job_names:
            status = 'warn'
            conclusion = '存在失败任务，优先查看失败聚合与失败执行记录'
        elif paused_count > 0:
            status = 'warn'
            conclusion = '存在暂停任务，建议确认停用原因与恢复窗口'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'当前筛选: {filter_label}',
                f'已加载任务: {len(rows)} 条',
                f'当前匹配: {len(filtered_rows)} 条',
                f'失败任务: {len(failed_job_names)} 个',
                f'暂停任务: {paused_count} 个',
                f'最近失败: {latest_failure}',
                '',
                '## 建议入口',
                '优先关注：失败聚合 / 暂停任务 / 执行轨迹',
            ],
        )

    def build_job_focus_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建任务概览分区。

        :param payload: `job detail` JSON 负载
        :return: 分区快照
        """
        job = payload.get('job') if isinstance(payload, dict) else None
        if not isinstance(job, dict):
            return DetailSectionSnapshot(
                title='任务摘要',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='任务', empty_value='无'),
            )
        return DetailSectionSnapshot(
            title='任务摘要',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 任务身份',
                f'任务 ID: {job.get("jobId", "-")}',
                f'任务名称: {SHELL_TEXT_FORMATTER.truncate_text(job.get("jobName", "-"), 40)}',
                f'任务分组: {SHELL_TEXT_FORMATTER.truncate_text(job.get("jobGroup", "-"), 24)}',
                f'运行状态: {self.rendering.render_job_status(job.get("status", "-"))}',
            ],
        )

    @staticmethod
    def build_job_schedule_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建任务调度配置分区。

        :param payload: `job detail` JSON 负载
        :return: 分区快照
        """
        job = payload.get('job') if isinstance(payload, dict) else None
        if not isinstance(job, dict):
            return DetailSectionSnapshot(
                title='调度配置',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='调度配置', empty_value='不可用'
                ),
            )
        return DetailSectionSnapshot(
            title='调度配置',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 调度表达式',
                f'Cron 表达式: {SHELL_TEXT_FORMATTER.truncate_text(job.get("cronExpression", "-"), 48)}',
                '',
                '## 执行入口',
                f'调用目标: {SHELL_TEXT_FORMATTER.truncate_text(job.get("invokeTarget", "-"), 72)}',
            ],
        )

    def build_job_logs_section(self, payload: dict[str, Any] | None, *, title: str) -> DetailSectionSnapshot:
        """
        构建任务日志分区。

        :param payload: `job logs` JSON 负载
        :param title: 分区标题
        :return: 分区快照
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return DetailSectionSnapshot(
                title=title,
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='日志', empty_value='不可用'),
            )
        rows = self.page_adapter.extract_page_rows(payload)
        lines = TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
            empty_label='日志记录',
            empty_value='0 条',
            detail='当前筛选条件下没有相关日志',
        )
        section_status = 'ok'
        if rows:
            lines = []
            if any(str(row.get('status', '')).strip() == '1' for row in rows):
                section_status = 'warn'
            for row in rows[:8]:
                exception_info = SHELL_TEXT_FORMATTER.truncate_text(row.get('exceptionInfo', '-'), 56)
                timeline_marker = self.rendering.render_timeline_marker(row.get('status', '-'))
                rendered_status = self.rendering.render_job_log_status(row.get('status', '-'))
                lines.extend(
                    [
                        f'## 节点 {row.get("jobLogId", "-")} · {self.rendering.render_job_log_timeline_title(row)}',
                        f'> {timeline_marker} 状态: {rendered_status}',
                        f'> 时间: {SHELL_TEXT_FORMATTER.truncate_text(row.get("createTime", "-"), 24)}',
                        f'> 任务: {SHELL_TEXT_FORMATTER.truncate_text(row.get("jobName", "-"), 24)}',
                        f'> 结果: {SHELL_TEXT_FORMATTER.truncate_text(row.get("jobMessage", "-"), 56)}',
                        *([f'> 异常: {exception_info}'] if exception_info and exception_info != '-' else []),
                        '> 轨道: ├─采集  ├─执行  └─落盘',
                        f'> 轨迹: {"●" if timeline_marker == "o" else "▲"}─{"●" if timeline_marker == "o" else "▲"}─◎',
                        '',
                    ]
                )
        return DetailSectionSnapshot(
            title=title,
            status=section_status,
            lines=lines[:-1] if len(lines) > 1 and lines[-1] == '' else lines,
        )

    def build_job_log_summary_section(
        self,
        recent_logs_payload: dict[str, Any] | None,
        failed_logs_payload: dict[str, Any] | None,
    ) -> DetailSectionSnapshot:
        """
        构建任务日志摘要分区。

        :param recent_logs_payload: 最近日志 JSON 负载
        :param failed_logs_payload: 失败日志 JSON 负载
        :return: 分区快照
        """
        if not isinstance(recent_logs_payload, dict) or not recent_logs_payload.get('ok', False):
            return DetailSectionSnapshot(
                title='执行摘要',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    recent_logs_payload, empty_label='日志摘要', empty_value='不可用'
                ),
            )
        recent_rows = self.page_adapter.extract_page_rows(recent_logs_payload)
        failed_rows = self.page_adapter.extract_page_rows(failed_logs_payload)
        success_count = sum(1 for row in recent_rows if str(row.get('status', '')).strip() == '0')
        failed_count = sum(1 for row in recent_rows if str(row.get('status', '')).strip() not in {'', '0'})
        status = 'warn' if failed_count > 0 or failed_rows else 'ok'
        total_count = len(recent_rows)
        latest_run = self.rendering.extract_latest_log_time(recent_rows)
        latest_failure = self.rendering.extract_latest_log_time(failed_rows)
        return DetailSectionSnapshot(
            title='执行摘要',
            status=status,
            lines=[
                '## 执行统计',
                f'最近采样日志: {total_count} 条',
                f'执行成功: {success_count} 条',
                f'执行失败: {failed_count} 条',
                f'成功率信号: {self.rendering.render_signal_bar(success_count, total_count)} {success_count}/{total_count or 0}',
                '',
                '## 时间线锚点',
                f'最近一次执行: {latest_run}',
                f'最近一次失败: {latest_failure}',
                '',
                '## 轨道视图',
                f'执行轨道: {"─".join("●" if str(row.get("status", "")).strip() == "0" else "▲" for row in recent_rows[:6]) or "-"}',
                f'失败轨道: {"─".join("▲" for _ in failed_rows[:6]) or "-"}',
                f'轨道窗口: {"[执行流]" if recent_rows else "-"} {"[失败流]" if failed_rows else ""}'.strip(),
                '',
                '## 风险信号',
                f'失败记录池: {len(failed_rows)} 条',
            ],
        )

    def load_job_detail_sections(self, job_row: dict[str, Any], env: str) -> list[DetailSectionSnapshot]:
        """
        按需加载单条任务详情与日志分区。

        :param job_row: 任务列表行数据
        :param env: 当前运行环境
        :return: 详情分区列表
        """
        job_id = job_row.get('jobId', '-')
        job_name = str(job_row.get('jobName', '-') or '-')

        detail_payload = NESTED_CLI_SUPPORT.run(
            'job',
            'detail',
            str(job_id),
            f'--env={env}',
            '--output=json',
            parse_json=True,
        ).payload

        log_arguments = ['job', 'logs', f'--env={env}', '--paged', '--page-size=8', '--output=json']
        if job_name.strip() and job_name != '-':
            log_arguments.append(f'--job-name={job_name}')
        recent_logs_payload = NESTED_CLI_SUPPORT.run(*log_arguments, parse_json=True).payload
        failed_logs_payload = NESTED_CLI_SUPPORT.run(*[*log_arguments, '--status=1'], parse_json=True).payload

        return [
            self.build_job_focus_section(detail_payload),
            self.build_job_schedule_section(detail_payload),
            self.build_job_log_summary_section(recent_logs_payload, failed_logs_payload),
            self.build_job_logs_section(recent_logs_payload, title='最近执行记录'),
            self.build_job_logs_section(failed_logs_payload, title='失败执行记录'),
        ]


class JobRecordBuilder:
    """
    任务浏览记录构建器。

    该对象负责构建任务页单条浏览记录与失败兜底记录。

    :param page_adapter: 任务浏览页适配器
    :param rendering: 任务浏览页渲染支持对象
    :param section_builder: 任务浏览页分区构建器
    """

    def __init__(
        self,
        page_adapter: BaseBrowserAdapter,
        rendering: JobRenderingSupport,
        section_builder: JobSectionBuilder,
    ) -> None:
        """
        初始化任务浏览记录构建器。

        :param page_adapter: 任务浏览页适配器
        :param rendering: 任务浏览页渲染支持对象
        :param section_builder: 任务浏览页分区构建器
        :return: None
        """
        self.page_adapter = page_adapter
        self.rendering = rendering
        self.section_builder = section_builder

    def build_job_record(self, job_row: dict[str, Any], env: str) -> BrowserRecordSnapshot:
        """
        构建单条任务浏览记录。

        :param job_row: 任务列表行数据
        :param env: 当前运行环境
        :return: 浏览记录快照
        """
        job_id = job_row.get('jobId', '-')
        job_name = str(job_row.get('jobName', '-') or '-')
        job_status = str(job_row.get('status', '-') or '-')
        job_group = str(job_row.get('jobGroup', '-') or '-')
        cron_expression = str(job_row.get('cronExpression', '-') or '-')
        rendered_status = self.rendering.render_job_status(job_status)

        return BrowserRecordSnapshot(
            key=f'job:{job_id}',
            title=SHELL_TEXT_FORMATTER.truncate_text(job_name, 40),
            status='warn' if str(job_status).strip() == '1' else 'ok',
            summary=f'{rendered_status} · Cron {SHELL_TEXT_FORMATTER.truncate_text(cron_expression, 32)}',
            metadata_lines=[
                '## 任务标识',
                f'任务 ID: {job_id}',
                f'任务分组: {SHELL_TEXT_FORMATTER.truncate_text(job_group, 24)}',
                f'运行状态: {rendered_status}',
                '',
                '## 调度信息',
                f'Cron 表达式: {SHELL_TEXT_FORMATTER.truncate_text(cron_expression, 48)}',
            ],
            detail_sections=[],
            detail_loader=lambda job_row=job_row, env=env: self.section_builder.load_job_detail_sections(job_row, env),
        )

    def build_failure_record(self, payload: dict[str, Any] | None) -> BrowserRecordSnapshot:
        """
        构建任务页失败兜底记录。

        :param payload: 失败结果负载
        :return: 浏览记录快照
        """
        return self.page_adapter.build_failure_record(
            key='job:unavailable',
            subject='任务',
            section_subject='任务列表',
            payload=payload,
        )


class JobsBrowserAdapter(BaseBrowserAdapter):
    """
    任务浏览页适配器。

    该适配器负责采集任务列表、失败日志和单条任务详情，并委托协作对象
    完成过滤、共享分区、详情分区和记录构建。
    """

    def __init__(
        self,
        rendering: JobRenderingSupport | None = None,
        row_filter: JobRowFilter | None = None,
        section_builder: JobSectionBuilder | None = None,
        record_builder: JobRecordBuilder | None = None,
    ) -> None:
        """
        初始化任务浏览页适配器。

        :param rendering: 任务浏览页渲染支持对象
        :param row_filter: 任务浏览行过滤器
        :param section_builder: 任务浏览页分区构建器
        :param record_builder: 任务浏览记录构建器
        :return: None
        """
        super().__init__(
            page_title='任务',
            search_view_key='jobs',
            filter_options=JOB_FILTER_OPTIONS,
        )
        self.rendering = rendering or JobRenderingSupport(self)
        self.row_filter = row_filter or JobRowFilter()
        self.section_builder = section_builder or JobSectionBuilder(self, self.rendering)
        self.record_builder = record_builder or JobRecordBuilder(self, self.rendering, self.section_builder)

    def collect_snapshot(self, env: str, filter_key: str = 'all', query: str = '') -> BrowserPageSnapshot:
        """
        采集定时任务浏览页只读快照。

        :param env: 当前运行环境
        :param filter_key: 当前筛选键
        :param query: 当前搜索词
        :return: 浏览页快照
        """
        active_filter_option = self.resolve_active_filter(filter_key)
        active_filter = active_filter_option.key
        active_filter_label = active_filter_option.label
        search_context = self.resolve_search_context(query)
        jobs_payload = NESTED_CLI_SUPPORT.run(
            'job',
            'list',
            f'--env={env}',
            '--paged',
            '--page-size=8',
            '--output=json',
            parse_json=True,
        ).payload
        failed_logs_payload = NESTED_CLI_SUPPORT.run(
            'job',
            'logs',
            f'--env={env}',
            '--paged',
            '--page-size=20',
            '--status=1',
            '--output=json',
            parse_json=True,
        ).payload
        failed_job_names = self.rendering.extract_failed_job_names(failed_logs_payload)

        if not isinstance(jobs_payload, dict) or not jobs_payload.get('ok', False):
            return BrowserPageSnapshot(
                title='任务',
                subtitle=TUI_COPY.build_unavailable_subtitle(
                    '任务',
                    SHELL_TEXT_FORMATTER.truncate_text(self.extract_payload_message(jobs_payload), 72),
                ),
                records=[self.record_builder.build_failure_record(jobs_payload)],
                shared_sections=[
                    self.section_builder.build_jobs_overview_section(
                        [], [], failed_job_names, 0, failed_logs_payload, active_filter_label
                    ),
                    self.section_builder.build_job_failure_aggregate_section(failed_logs_payload),
                ],
                filters=list(self.filter_options),
                active_filter_key=active_filter,
                search=search_context,
            )

        rows = self.extract_page_rows(jobs_payload)
        sorted_rows = sorted(
            rows,
            key=lambda row: (
                0
                if str(row.get('jobName', '') or '').strip() in failed_job_names
                else 1
                if str(row.get('status', '')).strip() == '1'
                else 2,
                str(row.get('jobName', '') or ''),
            ),
        )
        filtered_rows = self.row_filter.apply_job_query(
            self.row_filter.apply_job_filter(sorted_rows, failed_job_names, active_filter),
            query,
        )
        records = [self.record_builder.build_job_record(job_row, env) for job_row in filtered_rows[:8]]
        if not records:
            records = [
                self.build_empty_record(
                    key='job:none',
                    subject='任务',
                    empty_label='任务列表',
                    has_source_rows=bool(sorted_rows),
                    filtered_summary='当前筛选条件下没有匹配任务',
                    empty_summary='当前环境中还没有定时任务',
                    filtered_empty_value='暂无任务',
                    empty_empty_value='暂无任务配置',
                    filtered_detail='当前筛选条件下没有匹配任务',
                    empty_detail='当前环境中尚未配置定时任务',
                )
            ]
        paused_count = sum(1 for row in rows if str(row.get('status', '')).strip() == '1')
        shared_sections = [
            self.section_builder.build_jobs_overview_section(
                rows,
                filtered_rows,
                failed_job_names,
                paused_count,
                failed_logs_payload,
                active_filter_label,
            ),
            self.section_builder.build_job_failure_aggregate_section(failed_logs_payload),
        ]
        return BrowserPageSnapshot(
            title='任务',
            subtitle=TUI_DIAGNOSTIC_SERVICE.build_jobs_diagnostic_subtitle(
                active_filter_label,
                len(filtered_rows),
                failed_job_names,
                paused_count,
            ),
            records=records,
            shared_sections=shared_sections,
            filters=list(self.filter_options),
            active_filter_key=active_filter,
            search=search_context,
        )


JOBS_BROWSER_ADAPTER = JobsBrowserAdapter()
