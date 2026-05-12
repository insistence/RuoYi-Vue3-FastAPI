from dataclasses import dataclass
from typing import Any

from cli.context import CliContext
from cli.wizard.base import BaseLiveExecCliWizardFlow


@dataclass(frozen=True)
class AppRunWizardSelection:
    """
    `wizard app-run` 向导采集结果。

    :param env: 运行环境
    :param run_doctor: 启动前是否先执行应用检查
    """

    env: str
    run_doctor: bool


class AppRunWizardFlow(BaseLiveExecCliWizardFlow[AppRunWizardSelection]):
    """
    `wizard app-run` 向导流程。

    :param doctor_payload: 启动前检查结果缓存
    """

    wizard_name = 'wizard app-run'
    preview_title = 'wizard app-run preview'
    failure_message = '应用启动向导执行失败'

    def collect_selection(self) -> AppRunWizardSelection:
        """
        采集应用启动向导参数。

        :return: 向导采集结果
        """
        env = self.prompt_service.prompt_env('dev')
        run_doctor = self.prompt_service.prompt_confirm('启动前是否先执行应用检查', default_value=True)
        return AppRunWizardSelection(env=env, run_doctor=run_doctor)

    def prepare_context(self, selection: AppRunWizardSelection, output: str) -> CliContext:
        """
        构建应用启动向导上下文。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: CLI 上下文
        """
        del output
        return self.build_readonly_context(selection.env, 'text')

    def build_preview_summary(self, selection: AppRunWizardSelection) -> dict[str, Any]:
        """
        构建应用启动预览摘要。

        :param selection: 向导采集结果
        :return: 预览摘要
        """
        return {
            'env': selection.env,
            'run_doctor': str(selection.run_doctor).lower(),
            'doctor_ok': '-' if self.doctor_payload is None else str(self.doctor_payload.get('ok', False)).lower(),
        }

    def build_preview_command(self, selection: AppRunWizardSelection) -> list[str]:
        """
        构建应用启动预览命令。

        :param selection: 向导采集结果
        :return: 用户视角命令参数
        """
        return ['ruoyi', 'app', 'run', f'--env={selection.env}']

    def build_preview_notes(self, selection: AppRunWizardSelection) -> list[str] | None:
        """
        构建应用启动预览附加说明。

        :param selection: 向导采集结果
        :return: 预览附加说明
        """
        del selection
        notes: list[str] = []
        if isinstance(self.doctor_payload, dict) and not self.doctor_payload.get('ok', False):
            notes.append(self.doctor_payload.get('message', '启动前检查未通过'))
        return notes or None

    def confirm_prompt(self, selection: AppRunWizardSelection) -> str:
        """
        返回应用启动最终确认提示。

        :param selection: 向导采集结果
        :return: 确认提示
        """
        del selection
        return '确认启动应用吗'

    def confirm_default_value(self, selection: AppRunWizardSelection) -> bool:
        """
        返回应用启动确认默认值。

        :param selection: 向导采集结果
        :return: 默认确认值
        """
        del selection
        return bool(self.doctor_payload is None or self.doctor_payload.get('ok', False))

    def build_execute_arguments(self, selection: AppRunWizardSelection, output: str) -> list[str]:
        """
        构建应用启动内部 CLI 参数。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 参数
        """
        del output
        return ['app', 'run', f'--env={selection.env}']

    def __init__(self) -> None:
        """
        初始化应用启动向导流程。

        :return: None
        """
        super().__init__()
        self.doctor_payload: dict[str, Any] | None = None

    def prepare_execution_state(self, selection: AppRunWizardSelection, output: str) -> None:
        """
        在预览与确认前准备启动前检查结果。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: None
        """
        del output
        self.doctor_payload = None
        if selection.run_doctor:
            doctor_result = self.run_nested_command(
                'app', 'doctor', f'--env={selection.env}', '--output=json', parse_json=True
            )
            payload = getattr(doctor_result, 'payload', None)
            self.doctor_payload = payload if isinstance(payload, dict) else None


def run_app_run_wizard() -> None:
    """
    执行 `wizard app-run` 向导。

    :return: None
    """
    AppRunWizardFlow().run('text')
