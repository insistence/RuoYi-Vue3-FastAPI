from dataclasses import dataclass

from cli.tui.actions.builders import TuiActionTemplate, TuiActionTemplateSupport
from cli.tui.adapters.models import BrowserRecordSnapshot
from cli.tui.copy import TUI_COPY


@dataclass(frozen=True)
class JobActionTemplateFactory:
    """
    任务页动作模板工厂。

    该对象负责生成任务浏览页相关动作模板，收口任务 ID 解析、
    暂停/恢复切换和摘要拼装逻辑。

    :param support: 动作模板共享构建支持
    """

    support: TuiActionTemplateSupport

    def build_run_once_command(self, record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...] | None:
        """
        构建任务执行一次命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del env
        job_id = self.support.extract_job_id(record)
        if job_id is None:
            return None
        return ('job', 'run-once', job_id)

    def build_run_once_summary(self, record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建任务执行一次动作摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del env
        if record is None:
            return []
        job_id = self.support.extract_job_id(record) or ''
        return [
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('job'), record.title),
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('job_id'), job_id),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('current_status'),
                record.summary,
            ),
        ]

    def build_toggle_command(self, record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...] | None:
        """
        构建任务暂停或恢复命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del env
        if record is None:
            return None
        job_id = self.support.extract_job_id(record)
        if job_id is None:
            return None
        if record.status == 'warn':
            return ('job', 'resume', job_id)
        return ('job', 'pause', job_id)

    def build_toggle_summary(self, record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建任务暂停或恢复动作摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del env
        if record is None:
            return []
        job_id = self.support.extract_job_id(record) or ''
        label = (
            TUI_COPY.build_action_label('job_resume')
            if record.status == 'warn'
            else TUI_COPY.build_action_label('job_pause')
        )
        return [
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('job'), record.title),
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('job_id'), job_id),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('current_status'),
                record.summary,
            ),
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('target_action'), label),
        ]

    @staticmethod
    def build_toggle_action_id(record: BrowserRecordSnapshot | None, env: str) -> str:
        """
        构建任务暂停或恢复动作标识。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 动作标识
        """
        del env
        if record is not None and record.status == 'warn':
            return 'job-resume'
        return 'job-pause'

    @staticmethod
    def build_toggle_label(record: BrowserRecordSnapshot | None, env: str) -> str:
        """
        构建任务暂停或恢复动作标题。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 动作标题
        """
        del env
        if record is not None and record.status == 'warn':
            return TUI_COPY.build_action_label('job_resume')
        return TUI_COPY.build_action_label('job_pause')

    def create_run_once_template(self) -> TuiActionTemplate:
        """
        创建任务执行一次动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='job-run-once',
            label=TUI_COPY.build_action_label('job_run_once'),
            command_builder=self.build_run_once_command,
            summary_builder=self.build_run_once_summary,
        )

    def create_toggle_template(self) -> TuiActionTemplate:
        """
        创建任务暂停或恢复动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='job-toggle',
            label=TUI_COPY.build_action_label('job_pause'),
            command_builder=self.build_toggle_command,
            summary_builder=self.build_toggle_summary,
            action_id_builder=self.build_toggle_action_id,
            label_builder=self.build_toggle_label,
        )

    def create_sync_template(self) -> TuiActionTemplate:
        """
        创建任务同步动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='job-sync',
            label=TUI_COPY.build_action_label('job_sync'),
            command_builder=lambda record, env: ('job', 'sync'),
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('job_sync'),
                TUI_COPY.build_action_purpose_label('job_sync'),
            ),
        )
