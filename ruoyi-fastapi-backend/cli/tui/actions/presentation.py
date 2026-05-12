from dataclasses import dataclass

from cli.tui.actions.models import TuiActionResult
from cli.tui.actions.registry import TuiActionRegistry
from cli.tui.adapters.models import BrowserRecordSnapshot
from cli.tui.capabilities import TuiCapabilityRegistry
from cli.tui.copy import TUI_COPY
from cli.tui.keymaps import TUI_KEYMAP_REGISTRY
from cli.utils import SHELL_TEXT_FORMATTER


@dataclass(frozen=True)
class TuiActionPresentationService:
    """
    TUI 动作展示服务。

    该对象负责动作提示、动作列表和动作结果通知等展示层文本构建，
    避免继续保留模块级桥接函数。
    """

    capability_registry: TuiCapabilityRegistry
    action_registry: TuiActionRegistry

    def build_browser_action_hint(self, view_key: str) -> str:
        """
        构建浏览页动作提示文本。

        :param view_key: 当前页面视图标识
        :return: 动作提示文本
        """
        capability_labels = [
            f'[{capability.key}] {capability.hint_label}'
            for capability in self.capability_registry.get_browser_capabilities(view_key)
        ]
        interaction_text = TUI_COPY.build_browser_action_hint_text(
            view_key, TUI_KEYMAP_REGISTRY.browser_interaction_hint
        )
        return TUI_COPY.build_capability_hint_text(
            capability_labels,
            interaction_text,
            fallback='{interaction_hint}',
        )

    def build_detail_action_hint(self, view_key: str) -> str:
        """
        构建详情页动作提示文本。

        :param view_key: 当前页面视图标识
        :return: 动作提示文本
        """
        capability_labels = [
            f'[{capability.key}] {capability.hint_label}'
            for capability in self.capability_registry.get_detail_capabilities(view_key)
        ]
        interaction_text = TUI_COPY.build_detail_action_hint_text(
            view_key, TUI_KEYMAP_REGISTRY.browser_interaction_hint
        )
        return TUI_COPY.build_capability_hint_text(
            capability_labels,
            interaction_text,
            fallback='{interaction_hint}',
        )

    def build_browser_action_lines(
        self,
        *,
        view_key: str,
        record: BrowserRecordSnapshot | None,
        env: str,
    ) -> list[str]:
        """
        构建当前页面可执行动作列表。

        :param view_key: 当前页面视图标识
        :param record: 当前选中记录
        :param env: 当前运行环境
        :return: 动作文本行
        """
        lines: list[str] = []
        for capability in self.capability_registry.get_browser_capabilities(view_key):
            slot = capability.slot  # type: ignore[assignment]
            action = self.action_registry.resolve_browser_action(
                view_key=view_key,
                slot=slot,
                record=record,
                env=env,
            )
            if action is None:
                continue
            lines.append(TUI_COPY.build_action_line(capability.key, action.label))
        return lines or [TUI_COPY.build_action_empty_line()]

    @staticmethod
    def build_action_result_message(result: TuiActionResult) -> str:
        """
        构建动作执行结果通知文本。

        :param result: 动作执行结果
        :return: 通知文本
        """
        outcome = (
            TUI_COPY.build_action_result_field_label('success')
            if result.ok
            else TUI_COPY.build_action_result_field_label('fail')
        )
        return TUI_COPY.build_action_result_toast(
            result.spec.label,
            outcome,
            SHELL_TEXT_FORMATTER.truncate_text(result.message, 72),
        )
