from cli.tui.copy.fragments import (
    ACTION_CONSEQUENCE_TEXTS,
    ACTION_FEEDBACK_COPY,
    ACTION_HINT_COPY,
    ACTION_LABELS,
    ACTION_NOTIFICATION_COPY,
    ACTION_PREVIEW_FIELD_LABELS,
    ACTION_PREVIEW_TITLES,
    ACTION_PURPOSE_LABELS,
    ACTION_RESULT_FIELD_LABELS,
    ACTION_SCOPE_LABELS,
    CAPABILITY_HINT_LABELS,
    CAPABILITY_LABELS,
    COMMAND_HINT_TITLES,
    GENERAL_COPY,
)
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER


class TuiActionCopyMixin:
    """
    TUI 动作与能力文案混入。
    """

    @staticmethod
    def build_action_confirm_hint() -> str:
        """
        构建动作确认弹窗底部提示文案。

        :return: 确认提示文案
        """
        return GENERAL_COPY['action_confirm_hint']

    @staticmethod
    def build_action_confirm_cancel_label() -> str:
        """
        构建动作确认弹窗取消按钮文案。

        :return: 取消按钮文案
        """
        return GENERAL_COPY['action_confirm_cancel_label']

    @staticmethod
    def build_action_label(action_key: str) -> str:
        """
        根据动作标识构建动作标题文案。

        :param action_key: 动作标识
        :return: 动作标题文案
        """
        normalized_key = str(action_key).strip().lower()
        return ACTION_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_action_scope_label(action_key: str) -> str:
        """
        根据动作标识构建作用范围文案。

        :param action_key: 动作标识
        :return: 作用范围文案
        """
        normalized_key = str(action_key).strip().lower()
        return ACTION_SCOPE_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_action_purpose_label(action_key: str) -> str:
        """
        根据动作标识构建用途文案。

        :param action_key: 动作标识
        :return: 用途文案
        """
        normalized_key = str(action_key).strip().lower()
        return ACTION_PURPOSE_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_action_preview_title(title_key: str) -> str:
        """
        根据预览区块标识构建标题文案。

        :param title_key: 预览区块标识
        :return: 标题文案
        """
        normalized_key = str(title_key).strip().lower()
        return ACTION_PREVIEW_TITLES.get(normalized_key, normalized_key)

    @staticmethod
    def build_action_preview_field_label(field_key: str) -> str:
        """
        根据预览字段标识构建字段文案。

        :param field_key: 预览字段标识
        :return: 字段文案
        """
        normalized_key = str(field_key).strip().lower()
        return ACTION_PREVIEW_FIELD_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_action_result_field_label(field_key: str) -> str:
        """
        根据结果字段标识构建字段文案。

        :param field_key: 结果字段标识
        :return: 字段文案
        """
        normalized_key = str(field_key).strip().lower()
        return ACTION_RESULT_FIELD_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_action_notification_title() -> str:
        """
        构建动作通知标题文案。

        :return: 通知标题文案
        """
        return ACTION_NOTIFICATION_COPY['title']

    @staticmethod
    def build_action_unavailable_message() -> str:
        """
        构建无可执行动作时的提示文案。

        :return: 提示文案
        """
        return ACTION_NOTIFICATION_COPY['unavailable_message']

    @staticmethod
    def build_action_empty_line() -> str:
        """
        构建无可执行动作时的空态占位文案。

        :return: 空态占位文案
        """
        return ACTION_NOTIFICATION_COPY['empty_line']

    @staticmethod
    def build_action_consequence_text(consequence_key: str) -> str:
        """
        根据后果说明标识构建说明文案。

        :param consequence_key: 后果说明标识
        :return: 后果说明文案
        """
        normalized_key = str(consequence_key).strip().lower()
        return ACTION_CONSEQUENCE_TEXTS.get(normalized_key, normalized_key)

    @staticmethod
    def build_capability_label(capability_key: str) -> str:
        """
        根据能力标识构建展示标签文案。

        :param capability_key: 能力标识
        :return: 展示标签文案
        """
        normalized_key = str(capability_key).strip().lower()
        return CAPABILITY_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_capability_hint_label(capability_key: str) -> str:
        """
        根据能力标识构建顶部提示短标签文案。

        :param capability_key: 能力标识
        :return: 短标签文案
        """
        normalized_key = str(capability_key).strip().lower()
        return CAPABILITY_HINT_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_action_running_message(label: str) -> str:
        """
        构建动作执行中的提示文案。

        :param label: 动作标题
        :return: 提示文案
        """
        return f'正在执行：{label}'

    @staticmethod
    def build_browser_action_hint_text(view_key: str, interaction_hint: str) -> str:
        """
        构建浏览页动作提示文本。

        :param view_key: 当前页面视图标识
        :param interaction_hint: 通用浏览提示
        :return: 动作提示文本
        """
        normalized_view = str(view_key).strip().lower()
        template = ACTION_HINT_COPY['browser_templates'].get(normalized_view, ACTION_HINT_COPY['browser_default'])
        return template.format(interaction_hint=interaction_hint)

    @staticmethod
    def build_detail_action_hint_text(view_key: str, interaction_hint: str) -> str:
        """
        构建详情页动作提示文本。

        :param view_key: 当前页面视图标识
        :param interaction_hint: 通用浏览提示
        :return: 动作提示文本
        """
        normalized_view = str(view_key).strip().lower()
        template = ACTION_HINT_COPY['detail_templates'].get(normalized_view, ACTION_HINT_COPY['detail_default'])
        return template.format(interaction_hint=interaction_hint)

    @staticmethod
    def build_action_line(key: str, label: str) -> str:
        """
        构建单条动作快捷键信息。

        :param key: 快捷键
        :param label: 动作标题
        :return: 文本文案
        """
        return f'动作键 [{key}] · {label}'

    @staticmethod
    def build_capability_hint_text(capability_labels: list[str], interaction_hint: str, *, fallback: str) -> str:
        """
        根据能力标签列表构建统一动作提示文本。

        :param capability_labels: 动作标签列表
        :param interaction_hint: 通用浏览提示
        :param fallback: 缺省提示模板
        :return: 动作提示文本
        """
        if not capability_labels:
            return fallback.format(interaction_hint=interaction_hint)
        return f'动作键：{"  ".join(capability_labels)}  |  {interaction_hint}'

    @staticmethod
    def build_action_result_message_line(label: str, value: str) -> str:
        """
        构建动作结果详情的单行文案。

        :param label: 字段标题
        :param value: 字段值
        :return: 文本文案
        """
        return f'{label}: {value}'

    @staticmethod
    def build_cli_command_hint(*command_args: str) -> str:
        """
        构建 TUI 中展示的 CLI 命令提示文本。

        :param command_args: CLI 命令参数
        :return: 可直接复制执行的命令文本
        """
        return SHELL_TEXT_FORMATTER.format_shell_command(NESTED_CLI_SUPPORT.build_nested_cli_command(*command_args))

    @staticmethod
    def build_command_hint_lines(
        *,
        scenario: str,
        command: str,
        guide: str,
    ) -> list[str]:
        """
        构建统一的命令入口提示文本。

        :param scenario: 适用场景说明
        :param command: 推荐命令
        :param guide: 使用说明
        :return: 文本行列表
        """
        return [
            COMMAND_HINT_TITLES['scenario'],
            scenario,
            '',
            COMMAND_HINT_TITLES['command'],
            command,
            '',
            COMMAND_HINT_TITLES['guide'],
            guide,
        ]

    @staticmethod
    def build_labeled_value_line(label: str, value: str) -> str:
        """
        构建通用的“标签: 值”文案。

        :param label: 字段标题
        :param value: 字段值
        :return: 文本文案
        """
        return f'{label}: {value}'

    @staticmethod
    def build_action_result_toast(label: str, outcome: str, message: str) -> str:
        """
        构建动作完成后的通知文案。

        :param label: 动作标题
        :param outcome: 执行结果
        :param message: 结果摘要
        :return: 通知文案
        """
        return f'{ACTION_FEEDBACK_COPY["toast_prefix"]} · {label} · {outcome} · {message}'
