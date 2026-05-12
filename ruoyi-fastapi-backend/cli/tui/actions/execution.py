from dataclasses import dataclass

from cli.tui.actions.models import TuiActionResult, TuiActionSpec
from cli.tui.copy import TUI_COPY
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER


@dataclass(frozen=True)
class TuiActionExecutionService:
    """
    TUI 动作执行服务。

    该对象负责统一封装 nested JSON 动作、外部交互动作
    与结果文本行的收口逻辑。
    """

    def execute(self, spec: TuiActionSpec, env: str) -> TuiActionResult:
        """
        执行指定 TUI 动作。

        :param spec: 动作定义
        :param env: 当前运行环境
        :return: 动作执行结果
        """
        command_arguments = [
            *spec.command_args,
            f'--env={env}',
            '--output=json',
        ]
        if spec.append_yes:
            command_arguments.append('--yes')
        payload = NESTED_CLI_SUPPORT.run(*command_arguments, parse_json=True).payload
        return TuiActionResult(spec=spec, payload=payload)

    def execute_external(self, spec: TuiActionSpec) -> TuiActionResult:
        """
        在当前终端中执行交互式 TUI 动作。

        :param spec: 动作定义
        :return: 动作执行结果
        """
        completed = NESTED_CLI_SUPPORT.run_live(*spec.command_args)
        if completed.returncode == 0:
            message = '外部交互命令已执行完成'
        else:
            message = f'外部交互命令执行失败，退出码 {completed.returncode}'
        return TuiActionResult(
            spec=spec,
            external_exit_code=completed.returncode,
            external_message=message,
        )

    def build_result_lines(self, result: TuiActionResult) -> list[str]:
        """
        构建动作结果详情文本。

        :param result: 动作执行结果
        :return: 结果文本行
        """
        payload = result.payload if isinstance(result.payload, dict) else {}
        lines = [
            TUI_COPY.build_action_result_message_line(
                TUI_COPY.build_action_result_field_label('name'),
                result.spec.label,
            ),
            TUI_COPY.build_action_result_message_line(
                TUI_COPY.build_action_result_field_label('outcome'),
                TUI_COPY.build_action_result_field_label('success')
                if result.ok
                else TUI_COPY.build_action_result_field_label('fail'),
            ),
            TUI_COPY.build_action_result_message_line(
                TUI_COPY.build_action_result_field_label('summary'),
                SHELL_TEXT_FORMATTER.truncate_text(result.message, 88),
            ),
        ]
        service_message = str(payload.get('serviceMessage', '') or '').strip()
        if service_message:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('service'),
                    SHELL_TEXT_FORMATTER.truncate_text(service_message, 88),
                )
            )
        if payload.get('hint'):
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('hint'),
                    SHELL_TEXT_FORMATTER.truncate_text(str(payload.get('hint', '') or ''), 88),
                )
            )
        if payload.get('count') is not None:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('count'),
                    str(payload.get('count')),
                )
            )
        if payload.get('jobId') is not None:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('job_id'),
                    str(payload.get('jobId')),
                )
            )
        if result.external_exit_code is not None:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('exit_code'),
                    str(result.external_exit_code),
                )
            )
        operation_label = str(payload.get('operationLabel', '') or '').strip()
        if operation_label and operation_label != result.spec.label:
            lines.append(
                TUI_COPY.build_action_result_message_line(
                    TUI_COPY.build_action_result_field_label('operation'),
                    SHELL_TEXT_FORMATTER.truncate_text(operation_label, 64),
                )
            )
        return lines
