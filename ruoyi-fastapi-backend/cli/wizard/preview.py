from typing import Any

from cli.exit_codes import GUARD_REJECTED
from cli.output import CommandResult
from cli.utils import SHELL_TEXT_FORMATTER


class WizardPreviewRenderer:
    """
    向导预览渲染器。

    该对象负责统一构建向导预览文本和取消结果，
    为各个 flow 提供稳定的类式渲染入口。
    """

    @staticmethod
    def render_preview(
        title: str,
        *,
        summary: dict[str, Any],
        command: list[str],
        notes: list[str] | None = None,
    ) -> str:
        """
        渲染向导执行预览文本。

        :param title: 预览标题
        :param summary: 关键参数摘要
        :param command: 用户视角命令参数列表
        :param notes: 额外提示列表
        :return: 可直接输出的预览文本
        """
        lines = [title, 'summary:']
        for key, value in summary.items():
            lines.append(f'  {key}: {value}')
        lines.extend(
            [
                'command:',
                f'  {SHELL_TEXT_FORMATTER.format_shell_command(command)}',
            ]
        )
        if notes:
            lines.append('notes:')
            lines.extend(f'  - {note}' for note in notes if note)
        return '\n'.join(lines)

    @staticmethod
    def build_cancel_result(wizard_name: str) -> CommandResult:
        """
        构建向导取消结果。

        :param wizard_name: 向导名称
        :return: 命令结果对象
        """
        return CommandResult(
            data={
                'ok': False,
                'message': f'已取消向导执行：{wizard_name}',
                'hint': '可重新运行向导并调整参数后再次执行',
            },
            exit_code=GUARD_REJECTED,
        )


WIZARD_PREVIEW_RENDERER = WizardPreviewRenderer()
