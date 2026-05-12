from dataclasses import dataclass

import typer

from cli.context import CliContext, OutputOption
from cli.wizard.base import BaseCliWizardFlow


@dataclass(frozen=True)
class GenExportWizardSelection:
    """
    `wizard gen-export` 向导采集结果。

    :param env: 运行环境
    :param table_names: 业务表名称列表
    :param mode: 导出模式
    :param output_file: zip 导出目标文件路径
    :param dry_run: 是否演练执行
    :param allow_prod: 是否允许生产环境执行
    """

    env: str
    table_names: list[str]
    mode: str
    output_file: str
    dry_run: bool
    allow_prod: bool


class GenExportWizardFlow(BaseCliWizardFlow[GenExportWizardSelection]):
    """
    `wizard gen-export` 向导流程。

    :param default_env: 默认环境
    :param default_table_names: 默认业务表名称列表文本
    :param default_mode: 默认导出模式
    :param default_output_file: 默认 zip 导出目标文件路径
    :param default_dry_run: 默认是否先执行 dry-run
    """

    wizard_name = 'wizard gen-export'
    preview_title = 'wizard gen-export preview'
    failure_message = '代码导出向导执行失败'

    def __init__(
        self,
        *,
        default_env: str = 'dev',
        default_table_names: str = '',
        default_mode: str = 'zip',
        default_output_file: str = '',
        default_dry_run: bool = True,
    ) -> None:
        """
        初始化代码导出向导流程。

        :param default_env: 默认环境
        :param default_table_names: 默认业务表名称列表文本
        :param default_mode: 默认导出模式
        :param default_output_file: 默认 zip 导出目标文件路径
        :param default_dry_run: 默认是否先执行 dry-run
        :return: None
        """
        self.default_env = default_env
        self.default_table_names = default_table_names
        self.default_mode = default_mode
        self.default_output_file = default_output_file
        self.default_dry_run = default_dry_run

    def collect_selection(self) -> GenExportWizardSelection:
        """
        采集代码导出向导参数。

        :return: 向导采集结果
        """
        env = self.prompt_service.prompt_env(self.default_env)
        raw_table_names = self.prompt_service.prompt_required_text(
            '业务表名称列表（多个表请使用逗号分隔）',
            self.default_table_names,
        )
        table_names = self.parse_table_names(raw_table_names)
        while not table_names:
            typer.echo('至少需要输入一个业务表名称，请重新输入。')
            raw_table_names = self.prompt_service.prompt_required_text(
                '业务表名称列表（多个表请使用逗号分隔）',
                self.default_table_names,
            )
            table_names = self.parse_table_names(raw_table_names)

        mode = self.prompt_service.prompt_choice('导出模式', ['zip', 'local'], self.default_mode)
        output_file = ''
        if mode == 'zip':
            output_file = self.prompt_service.prompt_optional_text(
                'zip 导出目标文件路径（留空则使用默认文件名）',
                self.default_output_file,
            )
        dry_run = self.prompt_service.prompt_confirm('是否先执行 dry-run 预演', default_value=self.default_dry_run)
        allow_prod = (
            self.prompt_service.prompt_confirm('当前为 prod 环境，是否允许继续执行', default_value=False)
            if env == 'prod'
            else False
        )
        return GenExportWizardSelection(
            env=env,
            table_names=table_names,
            mode=mode,
            output_file=output_file,
            dry_run=dry_run,
            allow_prod=allow_prod,
        )

    def prepare_context(self, selection: GenExportWizardSelection, output: OutputOption) -> CliContext:
        """
        构建代码导出向导上下文。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: CLI 上下文
        """
        return self.build_regular_context(
            selection.env,
            output,
            allow_prod=selection.allow_prod,
            yes=True,
            dry_run=selection.dry_run,
        )

    def build_preview_summary(self, selection: GenExportWizardSelection) -> dict[str, str]:
        """
        构建代码导出预览摘要。

        :param selection: 向导采集结果
        :return: 预览摘要
        """
        return {
            'env': selection.env,
            'table_names': ','.join(selection.table_names),
            'mode': selection.mode,
            'output_file': selection.output_file or '-',
            'dry_run': str(selection.dry_run).lower(),
            'allow_prod': str(selection.allow_prod).lower(),
        }

    def build_preview_command(self, selection: GenExportWizardSelection) -> list[str]:
        """
        构建代码导出预览命令。

        :param selection: 向导采集结果
        :return: 用户视角命令参数
        """
        command = [
            'ruoyi',
            'gen',
            'export',
            *selection.table_names,
            f'--env={selection.env}',
            f'--mode={selection.mode}',
        ]
        if selection.output_file:
            command.append(f'--output-file={selection.output_file}')
        if selection.dry_run:
            command.append('--dry-run')
        if selection.allow_prod:
            command.append('--allow-prod')
        return command

    def confirm_prompt(self, selection: GenExportWizardSelection) -> str:
        """
        返回代码导出最终确认提示。

        :param selection: 向导采集结果
        :return: 确认提示
        """
        del selection
        return '确认执行代码导出向导吗'

    def build_execute_arguments(self, selection: GenExportWizardSelection, output: OutputOption) -> list[str]:
        """
        构建代码导出内部 CLI 参数。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 参数
        """
        arguments = [
            'gen',
            'export',
            *selection.table_names,
            f'--env={selection.env}',
            f'--output={output}',
            f'--mode={selection.mode}',
            '--yes',
        ]
        if selection.output_file:
            arguments.append(f'--output-file={selection.output_file}')
        if selection.dry_run:
            arguments.append('--dry-run')
        if selection.allow_prod:
            arguments.append('--allow-prod')
        return arguments

    @staticmethod
    def parse_table_names(raw_value: str) -> list[str]:
        """
        将逗号分隔的业务表名称文本解析为列表。

        :param raw_value: 原始输入文本
        :return: 去空白后的业务表名称列表
        """
        return [table_name.strip() for table_name in raw_value.split(',') if table_name.strip()]


def run_gen_export_wizard(
    output: OutputOption = 'text',
    *,
    default_env: str = 'dev',
    default_table_names: str = '',
    default_mode: str = 'zip',
    default_output_file: str = '',
    default_dry_run: bool = True,
) -> None:
    """
    执行 `wizard gen-export` 向导。

    :param output: 输出格式
    :param default_env: 默认环境
    :param default_table_names: 默认业务表名称列表文本
    :param default_mode: 默认导出模式
    :param default_output_file: 默认 zip 导出目标文件路径
    :param default_dry_run: 默认是否先 dry-run
    :return: None
    """
    GenExportWizardFlow(
        default_env=default_env,
        default_table_names=default_table_names,
        default_mode=default_mode,
        default_output_file=default_output_file,
        default_dry_run=default_dry_run,
    ).run(output)
