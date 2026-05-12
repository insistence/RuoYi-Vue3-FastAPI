from dataclasses import dataclass

import typer

from cli.context import CliContext, OutputOption
from cli.wizard.base import BaseCliWizardFlow


@dataclass(frozen=True)
class GenImportWizardSelection:
    """
    `wizard gen-import` 向导采集结果。

    :param env: 运行环境
    :param table_names: 待导入物理表名称列表
    :param dry_run: 是否演练执行
    :param allow_prod: 是否允许生产环境执行
    """

    env: str
    table_names: list[str]
    dry_run: bool
    allow_prod: bool


class GenImportWizardFlow(BaseCliWizardFlow[GenImportWizardSelection]):
    """
    `wizard gen-import` 向导流程。

    :param default_env: 默认环境
    :param default_table_names: 默认物理表名称列表文本
    :param default_dry_run: 默认是否先执行 dry-run
    """

    wizard_name = 'wizard gen-import'
    preview_title = 'wizard gen-import preview'
    failure_message = '代码生成导入向导执行失败'

    def __init__(
        self,
        *,
        default_env: str = 'dev',
        default_table_names: str = '',
        default_dry_run: bool = True,
    ) -> None:
        """
        初始化代码生成导入向导流程。

        :param default_env: 默认环境
        :param default_table_names: 默认物理表名称列表文本
        :param default_dry_run: 默认是否先执行 dry-run
        :return: None
        """
        self.default_env = default_env
        self.default_table_names = default_table_names
        self.default_dry_run = default_dry_run

    def collect_selection(self) -> GenImportWizardSelection:
        """
        采集代码生成导入向导参数。

        :return: 向导采集结果
        """
        env = self.prompt_service.prompt_env(self.default_env)
        raw_table_names = self.prompt_service.prompt_required_text(
            '物理表名称列表（多个表请使用逗号分隔）',
            self.default_table_names,
        )
        table_names = self.parse_table_names(raw_table_names)
        while not table_names:
            typer.echo('至少需要输入一个物理表名称，请重新输入。')
            raw_table_names = self.prompt_service.prompt_required_text(
                '物理表名称列表（多个表请使用逗号分隔）',
                self.default_table_names,
            )
            table_names = self.parse_table_names(raw_table_names)

        dry_run = self.prompt_service.prompt_confirm('是否先执行 dry-run 预演', default_value=self.default_dry_run)
        allow_prod = (
            self.prompt_service.prompt_confirm('当前为 prod 环境，是否允许继续执行', default_value=False)
            if env == 'prod'
            else False
        )
        return GenImportWizardSelection(
            env=env,
            table_names=table_names,
            dry_run=dry_run,
            allow_prod=allow_prod,
        )

    def prepare_context(self, selection: GenImportWizardSelection, output: OutputOption) -> CliContext:
        """
        构建代码生成导入向导上下文。

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

    def build_preview_summary(self, selection: GenImportWizardSelection) -> dict[str, str]:
        """
        构建代码生成导入预览摘要。

        :param selection: 向导采集结果
        :return: 预览摘要
        """
        return {
            'env': selection.env,
            'table_names': ','.join(selection.table_names),
            'dry_run': str(selection.dry_run).lower(),
            'allow_prod': str(selection.allow_prod).lower(),
        }

    def build_preview_command(self, selection: GenImportWizardSelection) -> list[str]:
        """
        构建代码生成导入预览命令。

        :param selection: 向导采集结果
        :return: 用户视角命令参数
        """
        command = ['ruoyi', 'gen', 'import-table', *selection.table_names, f'--env={selection.env}']
        if selection.dry_run:
            command.append('--dry-run')
        if selection.allow_prod:
            command.append('--allow-prod')
        return command

    def build_preview_notes(self, selection: GenImportWizardSelection) -> list[str] | None:
        """
        构建代码生成导入预览附加说明。

        :param selection: 向导采集结果
        :return: 预览附加说明
        """
        del selection
        return ['建议先确认物理表注释和字段规模，再决定是否执行真实导入。']

    def confirm_prompt(self, selection: GenImportWizardSelection) -> str:
        """
        返回代码生成导入最终确认提示。

        :param selection: 向导采集结果
        :return: 确认提示
        """
        del selection
        return '确认执行代码生成导入向导吗'

    def build_execute_arguments(self, selection: GenImportWizardSelection, output: OutputOption) -> list[str]:
        """
        构建代码生成导入内部 CLI 参数。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 参数
        """
        arguments = [
            'gen',
            'import-table',
            *selection.table_names,
            f'--env={selection.env}',
            f'--output={output}',
            '--yes',
        ]
        if selection.dry_run:
            arguments.append('--dry-run')
        if selection.allow_prod:
            arguments.append('--allow-prod')
        return arguments

    @staticmethod
    def parse_table_names(raw_value: str) -> list[str]:
        """
        将逗号分隔的物理表名称文本解析为列表。

        :param raw_value: 原始输入文本
        :return: 去空白后的物理表名称列表
        """
        return [table_name.strip() for table_name in raw_value.split(',') if table_name.strip()]


def run_gen_import_wizard(
    output: OutputOption = 'text',
    *,
    default_env: str = 'dev',
    default_table_names: str = '',
    default_dry_run: bool = True,
) -> None:
    """
    执行 `wizard gen-import` 向导。

    :param output: 输出格式
    :param default_env: 默认环境
    :param default_table_names: 默认物理表名称列表文本
    :param default_dry_run: 默认是否先 dry-run
    :return: None
    """
    GenImportWizardFlow(
        default_env=default_env,
        default_table_names=default_table_names,
        default_dry_run=default_dry_run,
    ).run(output)
