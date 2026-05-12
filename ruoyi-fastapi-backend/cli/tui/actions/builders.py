from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cli.tui.actions.models import (
    ActionCommandBuilder,
    ActionExecutionMode,
    ActionSummaryBuilder,
    ActionTextBuilder,
    TuiActionSpec,
)
from cli.tui.copy import TUI_COPY
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER

if TYPE_CHECKING:
    from cli.tui.adapters.models import BrowserRecordSnapshot


@dataclass(frozen=True)
class TuiActionSpecFactory:
    """
    TUI 动作规格构建器。

    该对象负责统一构建动作预览文本与 `TuiActionSpec`，
    避免各动作函数继续手工拼接重复的预览和规格对象。
    """

    @staticmethod
    def parse_record_suffix(record: BrowserRecordSnapshot, prefix: str) -> str:
        """
        从记录键中提取指定前缀后的标识。

        :param record: 浏览记录
        :param prefix: 键名前缀
        :return: 后缀标识
        """
        raw_key = str(record.key).strip()
        token_prefix = f'{prefix}:'
        if not raw_key.startswith(token_prefix):
            return ''
        return raw_key[len(token_prefix) :].strip()

    def build_command_preview_lines(
        self,
        *,
        env: str,
        summary_lines: list[str],
        command_args: tuple[str, ...],
        append_yes: bool = True,
        consequence_text: str = TUI_COPY.build_action_consequence_text('preview'),
    ) -> list[str]:
        """
        构建统一的动作预览文本。

        :param env: 当前运行环境
        :param summary_lines: 业务摘要文本
        :param command_args: 对应 CLI 命令参数
        :param consequence_text: 结果影响说明
        :return: 预览文本
        """
        nested_cli_arguments = [
            *command_args,
            f'--env={env}',
            '--output=json',
        ]
        if append_yes:
            nested_cli_arguments.append('--yes')
        command = SHELL_TEXT_FORMATTER.format_shell_command(
            NESTED_CLI_SUPPORT.build_nested_cli_command(*nested_cli_arguments)
        )
        return [
            TUI_COPY.build_action_preview_title('summary'),
            *summary_lines,
            '',
            TUI_COPY.build_action_preview_title('env'),
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('target_env'), env),
            '',
            TUI_COPY.build_action_preview_title('command'),
            command,
            '',
            TUI_COPY.build_action_preview_title('consequence'),
            consequence_text,
        ]

    def build_external_command_preview_lines(
        self,
        *,
        env: str,
        summary_lines: list[str],
        command_args: tuple[str, ...],
        append_yes: bool = True,
        consequence_text: str = TUI_COPY.build_action_consequence_text('wizard'),
    ) -> list[str]:
        """
        构建外部交互命令的预览文本。

        :param env: 当前运行环境
        :param summary_lines: 业务摘要文本
        :param command_args: 对应 CLI 命令参数
        :param consequence_text: 结果影响说明
        :return: 预览文本
        """
        return self.build_command_preview_lines(
            env=env,
            summary_lines=summary_lines,
            command_args=command_args,
            append_yes=append_yes,
            consequence_text=consequence_text,
        )

    def build_nested_json_action(
        self,
        *,
        action_id: str,
        label: str,
        command_args: tuple[str, ...],
        env: str,
        summary_lines: list[str],
        preview_title: str | None = None,
        consequence_text: str = TUI_COPY.build_action_consequence_text('preview'),
        append_yes: bool = True,
        refresh_view: bool = True,
    ) -> TuiActionSpec:
        """
        构建标准 nested JSON 动作。

        :param action_id: 动作唯一标识
        :param label: 动作显示名称
        :param command_args: 对应 CLI 命令参数
        :param env: 当前运行环境
        :param summary_lines: 业务摘要文本
        :param preview_title: 预览标题
        :param consequence_text: 结果影响说明
        :param refresh_view: 执行后是否刷新视图
        :return: 动作定义
        """
        return TuiActionSpec(
            action_id=action_id,
            label=label,
            command_args=command_args,
            preview_title=preview_title or label,
            preview_lines=self.build_command_preview_lines(
                env=env,
                summary_lines=summary_lines,
                command_args=command_args,
                append_yes=append_yes,
                consequence_text=consequence_text,
            ),
            append_yes=append_yes,
            refresh_view=refresh_view,
        )

    def build_external_action(
        self,
        *,
        action_id: str,
        label: str,
        command_args: tuple[str, ...],
        env: str,
        summary_lines: list[str],
        preview_title: str | None = None,
        consequence_text: str = TUI_COPY.build_action_consequence_text('wizard'),
        append_yes: bool = True,
        refresh_view: bool = True,
    ) -> TuiActionSpec:
        """
        构建标准外部交互动作。

        :param action_id: 动作唯一标识
        :param label: 动作显示名称
        :param command_args: 对应 CLI 命令参数
        :param env: 当前运行环境
        :param summary_lines: 业务摘要文本
        :param preview_title: 预览标题
        :param consequence_text: 结果影响说明
        :param refresh_view: 执行后是否刷新视图
        :return: 动作定义
        """
        return TuiActionSpec(
            action_id=action_id,
            label=label,
            command_args=command_args,
            preview_title=preview_title or label,
            preview_lines=self.build_external_command_preview_lines(
                env=env,
                summary_lines=summary_lines,
                command_args=command_args,
                append_yes=append_yes,
                consequence_text=consequence_text,
            ),
            execution_mode='external',
            append_yes=append_yes,
            refresh_view=refresh_view,
        )


@dataclass(frozen=True)
class TuiActionTemplate:
    """
    TUI 动作模板。

    该模板将命令参数构建、摘要构建与执行模式收敛为统一对象，
    使动作注册层可以直接声明“某个槽位对应哪类动作”。

    :param action_id: 动作唯一标识
    :param label: 动作显示名称
    :param command_builder: 命令参数构建器
    :param summary_builder: 预览摘要构建器
    :param action_id_builder: 动态动作标识构建器
    :param label_builder: 动态动作标题构建器
    :param preview_title: 预览标题
    :param consequence_text: 结果影响说明
    :param execution_mode: 执行模式
    :param append_yes: 是否在命令执行与预览中自动追加 `--yes`
    :param refresh_view: 执行后是否刷新视图
    :param preview_env_override: 预览中展示的环境名覆盖值
    """

    action_id: str
    label: str
    command_builder: ActionCommandBuilder
    summary_builder: ActionSummaryBuilder
    action_id_builder: ActionTextBuilder | None = None
    label_builder: ActionTextBuilder | None = None
    preview_title: str | None = None
    consequence_text: str = TUI_COPY.build_action_consequence_text('preview')
    execution_mode: ActionExecutionMode = 'nested_json'
    append_yes: bool = True
    refresh_view: bool = True
    preview_env_override: str | None = None

    def build(
        self,
        *,
        record: BrowserRecordSnapshot | None,
        env: str,
        spec_factory: TuiActionSpecFactory,
    ) -> TuiActionSpec | None:
        """
        根据当前页面上下文构建动作定义。

        :param record: 当前选中记录
        :param env: 当前运行环境
        :param spec_factory: 动作规格构建器
        :return: 动作定义
        """
        command_args = self.command_builder(record, env)
        if command_args is None:
            return None
        preview_env = self.preview_env_override or env
        summary_lines = self.summary_builder(record, env)
        action_id = self.action_id_builder(record, env) if self.action_id_builder is not None else self.action_id
        label = self.label_builder(record, env) if self.label_builder is not None else self.label
        if self.execution_mode == 'external':
            return spec_factory.build_external_action(
                action_id=action_id,
                label=label,
                command_args=command_args,
                env=preview_env,
                summary_lines=summary_lines,
                preview_title=self.preview_title,
                consequence_text=self.consequence_text,
                append_yes=self.append_yes,
                refresh_view=self.refresh_view,
            )
        return spec_factory.build_nested_json_action(
            action_id=action_id,
            label=label,
            command_args=command_args,
            env=preview_env,
            summary_lines=summary_lines,
            preview_title=self.preview_title,
            consequence_text=self.consequence_text,
            append_yes=self.append_yes,
            refresh_view=self.refresh_view,
        )


@dataclass(frozen=True)
class TuiActionTemplateSupport:
    """
    TUI 动作模板共享构建支持。

    该对象集中封装多个动作模板都会复用的记录解析与摘要拼装逻辑，
    避免这些基础能力继续散落在模块级函数中。

    :param spec_factory: 动作规格构建器
    """

    spec_factory: TuiActionSpecFactory

    def build_scope_purpose_summary(self, scope: str, purpose: str) -> list[str]:
        """
        构建通用的作用范围与目的摘要。

        :param scope: 作用范围说明
        :param purpose: 目的说明
        :return: 预览摘要
        """
        return [
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('scope'), scope),
            TUI_COPY.build_labeled_value_line(TUI_COPY.build_action_preview_field_label('purpose'), purpose),
        ]

    def extract_job_id(self, record: BrowserRecordSnapshot | None) -> str | None:
        """
        从任务记录中提取任务 ID。

        :param record: 当前记录
        :return: 任务 ID
        """
        if record is None:
            return None
        job_id = self.spec_factory.parse_record_suffix(record, 'job')
        return job_id if job_id.isdigit() else None

    @staticmethod
    def require_record_title(record: BrowserRecordSnapshot | None) -> str | None:
        """
        提取记录标题作为命令目标。

        :param record: 当前记录
        :return: 标题文本
        """
        if record is None:
            return None
        title = str(record.title).strip()
        return title or None
