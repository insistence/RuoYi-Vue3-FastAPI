from dataclasses import dataclass

from cli.tui.actions.builders import TuiActionTemplate, TuiActionTemplateSupport
from cli.tui.adapters.models import BrowserRecordSnapshot
from cli.tui.copy import TUI_COPY


@dataclass(frozen=True)
class CacheActionTemplateFactory:
    """
    缓存页动作模板工厂。

    该对象负责生成缓存浏览页相关动作模板，统一缓存清理预演和预热动作
    的参数与预览摘要构建。

    :param support: 动作模板共享构建支持
    """

    support: TuiActionTemplateSupport

    def build_clear_parameters(self, record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建缓存清理预演参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del env
        cache_name = record.title if record is not None else ''
        return {'cache_name': cache_name, 'dry_run': True}

    def build_clear_summary(self, record: BrowserRecordSnapshot | None, env: str) -> list[str]:
        """
        构建缓存清理预演摘要。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 预览摘要
        """
        del record, env
        return self.support.build_scope_purpose_summary(
            '当前环境缓存清理范围',
            '预演当前缓存名的匹配范围，不删除缓存键',
        )

    def create_warmup_template(self) -> TuiActionTemplate:
        """
        创建缓存预热动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='cache-warmup',
            label=TUI_COPY.build_action_label('cache_warmup'),
            parameter_builder=lambda record, env: {},
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('cache_warmup'),
                TUI_COPY.build_action_purpose_label('cache_warmup'),
            ),
        )

    def create_clear_dry_run_template(self) -> TuiActionTemplate:
        """
        创建缓存清理预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='cache-clear-dry-run',
            label='缓存清理预演',
            parameter_builder=self.build_clear_parameters,
            summary_builder=self.build_clear_summary,
            consequence_text='仅预演当前缓存名的匹配范围，不删除任何缓存键。',
        )
