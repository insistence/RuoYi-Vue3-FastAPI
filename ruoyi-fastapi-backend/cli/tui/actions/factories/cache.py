from dataclasses import dataclass

from cli.tui.actions.builders import TuiActionTemplate, TuiActionTemplateSupport
from cli.tui.adapters.models import BrowserRecordSnapshot
from cli.tui.copy import TUI_COPY


@dataclass(frozen=True)
class CacheActionTemplateFactory:
    """
    缓存页动作模板工厂。

    该对象负责生成缓存浏览页相关动作模板，统一缓存清理向导和预热动作
    的命令与预览摘要构建。

    :param support: 动作模板共享构建支持
    """

    support: TuiActionTemplateSupport

    def build_clear_command(self, record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建缓存清理向导命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        cache_name = record.title if record is not None else ''
        return (
            'wizard',
            'cache-clear',
            '--output=text',
            f'--default-env={env}',
            '--default-mode=cache-name',
            f'--default-cache-name={cache_name}',
            '--default-dry-run',
        )

    def build_clear_summary(self, record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建缓存清理向导摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del record, env
        return self.support.build_scope_purpose_summary(
            '当前环境缓存清理流程',
            '进入向导后确认缓存名、键前缀和 dry-run 范围',
        )

    def create_warmup_template(self) -> TuiActionTemplate:
        """
        创建缓存预热动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='cache-warmup',
            label=TUI_COPY.build_action_label('cache_warmup'),
            command_builder=lambda record, env: ('cache', 'warmup'),
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('cache_warmup'),
                TUI_COPY.build_action_purpose_label('cache_warmup'),
            ),
        )

    def create_clear_wizard_template(self) -> TuiActionTemplate:
        """
        创建缓存清理向导动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='wizard-cache-clear',
            label=TUI_COPY.build_action_label('cache_clear_wizard'),
            command_builder=self.build_clear_command,
            summary_builder=self.build_clear_summary,
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
        )
