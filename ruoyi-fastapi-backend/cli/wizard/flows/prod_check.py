from dataclasses import dataclass
from typing import Any

from cli.context import CliContext, OutputOption
from cli.wizard.aggregators import ProdCheckAggregator
from cli.wizard.base import BaseCliWizardFlow
from cli.wizard.presenters import ProdCheckPresenter


@dataclass(frozen=True)
class ProdCheckWizardSelection:
    """
    `wizard prod-check` 向导采集结果。

    :param env: 运行环境
    :param include_config: 是否附带配置快照
    """

    env: str
    include_config: bool


class ProdCheckWizardFlow(BaseCliWizardFlow[ProdCheckWizardSelection]):
    """
    `wizard prod-check` 向导流程。

    :param default_env: 默认环境
    :param default_include_config: 默认是否附带配置快照
    """

    wizard_name = 'wizard prod-check'
    preview_title = 'wizard prod-check preview'
    failure_message = '生产巡检向导执行失败'

    def __init__(
        self,
        *,
        default_env: str = 'prod',
        default_include_config: bool = True,
    ) -> None:
        """
        初始化生产巡检向导流程。

        :param default_env: 默认环境
        :param default_include_config: 默认是否附带配置快照
        :return: None
        """
        super().__init__()
        self.default_env = default_env
        self.default_include_config = default_include_config
        self.aggregator = ProdCheckAggregator()
        self.presenter = ProdCheckPresenter()

    def collect_selection(self) -> ProdCheckWizardSelection:
        """
        采集生产巡检向导参数。

        :return: 向导采集结果
        """
        env = self.prompt_service.prompt_env(self.default_env)
        include_config = self.prompt_service.prompt_confirm(
            '是否附带应用配置快照',
            default_value=self.default_include_config,
        )
        return ProdCheckWizardSelection(env=env, include_config=include_config)

    def prepare_context(self, selection: ProdCheckWizardSelection, output: OutputOption) -> CliContext:
        """
        构建生产巡检向导上下文。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: CLI 上下文
        """
        return self.build_readonly_context(selection.env, output)

    def build_preview_summary(self, selection: ProdCheckWizardSelection) -> dict[str, str]:
        """
        构建生产巡检预览摘要。

        :param selection: 向导采集结果
        :return: 预览摘要
        """
        return {
            'env': selection.env,
            'include_config': str(selection.include_config).lower(),
        }

    def build_preview_command(self, selection: ProdCheckWizardSelection) -> list[str]:
        """
        构建生产巡检预览命令。

        :param selection: 向导采集结果
        :return: 用户视角命令参数
        """
        return ['ruoyi', 'app', 'doctor', f'--env={selection.env}']

    def confirm_prompt(self, selection: ProdCheckWizardSelection) -> str:
        """
        返回生产巡检最终确认提示。

        :param selection: 向导采集结果
        :return: 确认提示
        """
        del selection
        return '确认执行生产巡检向导吗'

    def confirm_default_value(self, selection: ProdCheckWizardSelection) -> bool:
        """
        返回生产巡检确认默认值。

        :param selection: 向导采集结果
        :return: 默认确认值
        """
        del selection
        return True

    def build_execute_arguments(self, selection: ProdCheckWizardSelection, output: OutputOption) -> list[str]:
        """
        返回生产巡检占位执行参数。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 参数
        """
        del selection, output
        return []

    def execute(self, selection: ProdCheckWizardSelection, output: OutputOption) -> dict[str, Any]:
        """
        执行生产巡检聚合逻辑。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 聚合后的巡检结果
        """
        del output
        runtime_result = self.run_nested_command(
            'app', 'env', f'--env={selection.env}', '--output=json', parse_json=True
        )
        doctor_result = self.run_nested_command(
            'app',
            'doctor',
            f'--env={selection.env}',
            '--output=json',
            parse_json=True,
        )
        config_payload = None
        if selection.include_config:
            config_result = self.run_nested_command(
                'app',
                'config',
                f'--env={selection.env}',
                '--output=json',
                parse_json=True,
            )
            config_payload = config_result.payload
        return self.aggregator.build_payload(
            env=selection.env,
            runtime_payload=runtime_result.payload if isinstance(runtime_result.payload, dict) else None,
            doctor_payload=doctor_result.payload if isinstance(doctor_result.payload, dict) else None,
            config_payload=config_payload,
        )

    def complete_payload(
        self,
        ctx: CliContext,
        payload: dict[str, Any],
        *,
        default_exit_code: int = 0,
    ) -> None:
        """
        以聚合结果展示器收口生产巡检结果。

        :param ctx: CLI 上下文
        :param payload: 聚合结果负载
        :param default_exit_code: 默认退出码
        :return: None
        """
        self.complete_payload_result(
            ctx,
            payload,
            text_builder=self.presenter.build_text,
            default_exit_code=default_exit_code,
        )

    def extract_payload(self, nested_result: Any) -> dict[str, Any] | None:
        """
        提取生产巡检聚合结果负载。

        :param nested_result: 聚合执行结果
        :return: 结构化结果负载
        """
        return nested_result if isinstance(nested_result, dict) else None

    def extract_returncode(self, nested_result: Any) -> int:
        """
        提取生产巡检聚合结果退出码。

        :param nested_result: 聚合执行结果
        :return: 退出码
        """
        del nested_result
        return 0


def run_prod_check_wizard(
    output: OutputOption = 'text',
    *,
    default_env: str = 'prod',
    default_include_config: bool = True,
) -> None:
    """
    执行 `wizard prod-check` 向导。

    :param output: 输出格式
    :param default_env: 默认环境
    :param default_include_config: 默认是否附带配置快照
    :return: None
    """
    ProdCheckWizardFlow(
        default_env=default_env,
        default_include_config=default_include_config,
    ).run(output)
