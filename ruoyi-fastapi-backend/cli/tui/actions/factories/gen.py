from dataclasses import dataclass

from cli.tui.actions.builders import TuiActionTemplate, TuiActionTemplateSupport
from cli.tui.adapters.models import BrowserRecordSnapshot
from cli.tui.copy import TUI_COPY


@dataclass(frozen=True)
class GenActionTemplateFactory:
    """
    代码生成页动作模板工厂。

    该对象负责生成代码生成浏览页相关动作模板，统一记录标题提取、
    导出导入向导和表结构同步动作的构建逻辑。

    :param support: 动作模板共享构建支持
    """

    support: TuiActionTemplateSupport

    def build_export_wizard_command(self, record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...] | None:
        """
        构建代码生成导出向导命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        table_name = self.support.require_record_title(record)
        if table_name is None:
            return None
        return (
            'wizard',
            'gen-export',
            '--output=text',
            f'--default-env={env}',
            f'--default-table-names={table_name}',
            '--default-mode=zip',
            '--default-dry-run',
        )

    def build_import_wizard_command(self, record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...] | None:
        """
        构建代码生成导入向导命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        table_name = self.support.require_record_title(record)
        if table_name is None:
            return None
        return (
            'wizard',
            'gen-import',
            '--output=text',
            f'--default-env={env}',
            f'--default-table-names={table_name}',
            '--default-dry-run',
        )

    def build_export_dry_run_command(self, record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...] | None:
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
        return ('gen', 'export', table_name, '--dry-run', '--mode=zip')

    def build_sync_db_command(self, record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...] | None:
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
        return ('gen', 'sync-db', table_name)

    @staticmethod
    def build_export_wizard_summary(record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建代码生成导出向导摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del env
        if record is None:
            return []
        return [
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('scope'), f'当前业务表 {record.title}'
            ),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('current_status'),
                record.summary,
            ),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('purpose'),
                '进入向导后选择业务表、输出目录和覆盖策略',
            ),
        ]

    @staticmethod
    def build_import_wizard_summary(record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建代码生成导入向导摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del env
        if record is None:
            return []
        return [
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('scope'), f'当前物理表 {record.title}'
            ),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('current_status'),
                record.summary,
            ),
            TUI_COPY.build_labeled_value_line(
                TUI_COPY.build_action_preview_field_label('purpose'),
                '进入向导后确认物理表列表，并先执行 dry-run 导入预演',
            ),
        ]

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

    def create_export_wizard_template(self) -> TuiActionTemplate:
        """
        创建代码生成导出向导动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='wizard-gen-export',
            label=TUI_COPY.build_action_label('gen_export_wizard'),
            command_builder=self.build_export_wizard_command,
            summary_builder=self.build_export_wizard_summary,
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
            refresh_view=False,
        )

    def create_import_wizard_template(self) -> TuiActionTemplate:
        """
        创建代码生成导入向导动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='wizard-gen-import',
            label=TUI_COPY.build_action_label('gen_import_wizard'),
            command_builder=self.build_import_wizard_command,
            summary_builder=self.build_import_wizard_summary,
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
            refresh_view=False,
        )

    def create_export_dry_run_template(self) -> TuiActionTemplate:
        """
        创建代码生成导出预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='gen-export-dry-run',
            label=TUI_COPY.build_action_label('gen_export_dry_run'),
            command_builder=self.build_export_dry_run_command,
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
            command_builder=self.build_sync_db_command,
            summary_builder=self.build_sync_db_summary,
        )
