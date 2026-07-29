from dataclasses import dataclass

from cli.tui.actions.builders import TuiActionTemplate, TuiActionTemplateSupport
from cli.tui.adapters.models import BrowserRecordSnapshot
from cli.tui.copy import TUI_COPY


@dataclass(frozen=True)
class GenActionTemplateFactory:
    """
    代码生成页动作模板工厂。

    该对象负责生成代码生成浏览页相关动作模板，统一记录标题提取、
    导出预演和表结构同步动作的构建逻辑。

    :param support: 动作模板共享构建支持
    """

    support: TuiActionTemplateSupport

    def build_export_dry_run_parameters(
        self, record: BrowserRecordSnapshot | None, env: str
    ) -> dict[str, object] | None:
        """
        构建代码生成导出 dry-run 命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del env
        table_name = self.support.require_record_title(record)
        if table_name is None:
            return None
        return {'table_name': table_name, 'mode': 'zip', 'dry_run': True}

    def build_sync_db_parameters(self, record: BrowserRecordSnapshot | None, env: str) -> dict[str, object] | None:
        """
        构建代码生成表结构同步命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del env
        table_name = self.support.require_record_title(record)
        if table_name is None:
            return None
        return {'table_name': table_name}

    @staticmethod
    def build_export_dry_run_summary(record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建代码生成导出预演摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del env
        if record is None:
            return []
        return [
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('scope'),
                TUI_COPY.build_action_scope_label('gen_export_dry_run'),
            ),
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('job'), record.title),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('current_status'),
                record.summary,
            ),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('purpose'),
                TUI_COPY.build_action_purpose_label('gen_export_dry_run'),
            ),
        ]

    @staticmethod
    def build_sync_db_summary(record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建代码生成表结构同步摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del env
        if record is None:
            return []
        return [
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('scope'),
                TUI_COPY.build_action_scope_label('gen_sync_db'),
            ),
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('job'), record.title),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('current_status'),
                record.summary,
            ),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('purpose'),
                TUI_COPY.build_action_purpose_label('gen_sync_db'),
            ),
        ]

    def create_export_dry_run_template(self) -> TuiActionTemplate:
        """
        创建代码生成导出预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='gen-export-dry-run',
            label=TUI_COPY.build_action_label('gen_export_dry_run'),
            parameter_builder=self.build_export_dry_run_parameters,
            summary_builder=self.build_export_dry_run_summary,
        )

    def create_sync_db_template(self) -> TuiActionTemplate:
        """
        创建代码生成表结构同步动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='gen-sync-db',
            label=TUI_COPY.build_action_label('gen_sync_db'),
            parameter_builder=self.build_sync_db_parameters,
            summary_builder=self.build_sync_db_summary,
        )
