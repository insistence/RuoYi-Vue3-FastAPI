from cli.utils import SHELL_TEXT_FORMATTER


class JobCommandPresenter:
    """
    定时任务命令文本渲染器。

    该渲染器负责将 `job` 命令组产生的结构化 payload 转换为稳定的文本摘要，
    同时保持 JSON 输出仍由控制器直接返回，不在此处做契约变形。
    """

    def build_job_list_text(self, payload: dict[str, object]) -> str:
        """
        将任务列表结果渲染为文本摘要。

        :param payload: 任务列表结果字典
        :return: 文本摘要
        """
        lines = [f'ok: {str(payload.get("ok", False)).lower()}']

        filters = payload.get('filters')
        if isinstance(filters, dict):
            lines.extend(self._build_job_filter_lines(filters))

        page_payload = payload.get('page')
        if isinstance(page_payload, dict):
            rows = page_payload.get('rows', [])
            lines.append(
                'page: '
                f'{page_payload.get("pageNum", "-")}/{page_payload.get("pages", "-")} '
                f'(page_size={page_payload.get("pageSize", "-")}, total={page_payload.get("total", "-")})'
            )
            lines.append(f'count: {len(rows) if isinstance(rows, list) else 0}')
            if not isinstance(rows, list) or not rows:
                lines.append('jobs: none')
                return '\n'.join(lines)
            lines.append('jobs:')
            for row in rows:
                if isinstance(row, dict):
                    lines.extend([f'  {item}' for item in self._build_job_item_lines(row)])
            return '\n'.join(lines)

        items = payload.get('items')
        lines.append(f'count: {payload.get("count", 0)}')
        if not isinstance(items, list) or not items:
            lines.append('jobs: none')
            return '\n'.join(lines)

        lines.append('jobs:')
        for item in items:
            if isinstance(item, dict):
                lines.extend([f'  {line}' for line in self._build_job_item_lines(item)])
        return '\n'.join(lines)

    def build_job_detail_text(self, payload: dict[str, object]) -> str:
        """
        将单个定时任务详情渲染为文本摘要。

        :param payload: 定时任务详情结果字典
        :return: 文本摘要
        """
        job = payload.get('job')
        if not isinstance(job, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    f'job_id: {payload.get("jobId", "-")}',
                    'job: none',
                ]
            )

        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'job_id: {job.get("jobId", "-")}',
                f'job_name: {job.get("jobName", "-")}',
                f'job_group: {job.get("jobGroup", "-")}',
                f'job_executor: {job.get("jobExecutor", "-")}',
                f'status: {job.get("status", "-")}',
                f'cron_expression: {job.get("cronExpression", "-")}',
                f'invoke_target: {SHELL_TEXT_FORMATTER.truncate_text(job.get("invokeTarget", ""), 160) or "-"}',
                f'job_args: {SHELL_TEXT_FORMATTER.truncate_text(job.get("jobArgs", ""), 120) or "-"}',
                f'job_kwargs: {SHELL_TEXT_FORMATTER.truncate_text(job.get("jobKwargs", ""), 120) or "-"}',
                f'misfire_policy: {job.get("misfirePolicy", "-")}',
                f'concurrent: {job.get("concurrent", "-")}',
                f'remark: {SHELL_TEXT_FORMATTER.truncate_text(job.get("remark", ""), 160) or "-"}',
                f'create_by: {job.get("createBy", "-")}',
                f'create_time: {job.get("createTime", "-")}',
                f'update_by: {job.get("updateBy", "-")}',
                f'update_time: {job.get("updateTime", "-")}',
            ]
        )

    def build_job_logs_text(self, payload: dict[str, object]) -> str:
        """
        将定时任务日志列表结果渲染为文本摘要。

        :param payload: 定时任务日志列表结果字典
        :return: 文本摘要
        """
        lines = [f'ok: {str(payload.get("ok", False)).lower()}']

        filters = payload.get('filters')
        if isinstance(filters, dict):
            lines.extend(self._build_job_filter_lines(filters))

        page_payload = payload.get('page')
        if isinstance(page_payload, dict):
            rows = page_payload.get('rows', [])
            lines.append(
                'page: '
                f'{page_payload.get("pageNum", "-")}/{page_payload.get("pages", "-")} '
                f'(page_size={page_payload.get("pageSize", "-")}, total={page_payload.get("total", "-")})'
            )
            lines.append(f'count: {len(rows) if isinstance(rows, list) else 0}')
            if not isinstance(rows, list) or not rows:
                lines.append('logs: none')
                return '\n'.join(lines)
            lines.append('logs:')
            for row in rows:
                if isinstance(row, dict):
                    lines.extend([f'  {item}' for item in self._build_job_log_item_lines(row)])
            return '\n'.join(lines)

        items = payload.get('items')
        lines.append(f'count: {payload.get("count", 0)}')
        if not isinstance(items, list) or not items:
            lines.append('logs: none')
            return '\n'.join(lines)

        lines.append('logs:')
        for item in items:
            if isinstance(item, dict):
                lines.extend([f'  {line}' for line in self._build_job_log_item_lines(item)])
        return '\n'.join(lines)

    @staticmethod
    def _build_job_filter_lines(filters: dict[str, object]) -> list[str]:
        """
        构建任务列表过滤条件文本行。

        :param filters: 过滤条件字典
        :return: 过滤条件文本行列表
        """
        active_filters = []
        for key, value in filters.items():
            if value in (None, '', False):
                continue
            active_filters.append(f'{SHELL_TEXT_FORMATTER.to_snake_case(key)}={value}')
        if not active_filters:
            return ['filters: none']
        return ['filters:', *[f'  - {item}' for item in active_filters]]

    @staticmethod
    def _build_job_item_lines(job_item: dict[str, object]) -> list[str]:
        """
        构建单条任务记录的文本行。

        :param job_item: 单条任务记录
        :return: 任务记录文本行列表
        """
        job_id = job_item.get('jobId', '-')
        job_name = SHELL_TEXT_FORMATTER.truncate_text(job_item.get('jobName', ''), 30)
        job_group = SHELL_TEXT_FORMATTER.truncate_text(job_item.get('jobGroup', ''), 16)
        status = job_item.get('status', '-')
        cron_expression = SHELL_TEXT_FORMATTER.truncate_text(job_item.get('cronExpression', ''), 40)
        invoke_target = SHELL_TEXT_FORMATTER.truncate_text(job_item.get('invokeTarget', ''), 80)
        executor = SHELL_TEXT_FORMATTER.truncate_text(job_item.get('jobExecutor', ''), 24)
        return [
            f'- [{job_id}] {job_name} | 组: {job_group} | 状态: {status}',
            f'  cron: {cron_expression or "-"}',
            f'  invoke: {invoke_target or "-"}',
            f'  executor: {executor or "-"}',
        ]

    @staticmethod
    def _build_job_log_item_lines(job_log_item: dict[str, object]) -> list[str]:
        """
        构建单条定时任务日志记录的文本行。

        :param job_log_item: 单条定时任务日志记录
        :return: 文本行列表
        """
        job_log_id = job_log_item.get('jobLogId', '-')
        job_name = SHELL_TEXT_FORMATTER.truncate_text(job_log_item.get('jobName', ''), 30)
        job_group = SHELL_TEXT_FORMATTER.truncate_text(job_log_item.get('jobGroup', ''), 16)
        status = job_log_item.get('status', '-')
        job_trigger = SHELL_TEXT_FORMATTER.truncate_text(job_log_item.get('jobTrigger', ''), 40)
        job_message = SHELL_TEXT_FORMATTER.truncate_text(job_log_item.get('jobMessage', ''), 80)
        exception_info = SHELL_TEXT_FORMATTER.truncate_text(job_log_item.get('exceptionInfo', ''), 120)
        return [
            f'- [{job_log_id}] {job_name} | 组: {job_group} | 状态: {status}',
            f'  trigger: {job_trigger or "-"}',
            f'  message: {job_message or "-"}',
            f'  exception: {exception_info or "-"}',
            f'  create_time: {job_log_item.get("createTime", "-")}',
        ]
