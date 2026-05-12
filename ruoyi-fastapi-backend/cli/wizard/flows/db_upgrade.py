from dataclasses import dataclass

from cli.context import CliContext, OutputOption
from cli.wizard.base import BaseCliWizardFlow


@dataclass(frozen=True)
class DbUpgradeWizardSelection:
    """
    `wizard db-upgrade` 向导采集结果。

    :param env: 运行环境
    :param revision: 目标迁移版本
    :param dry_run: 是否演练执行
    :param allow_prod: 是否允许生产环境执行
    """

    env: str
    revision: str
    dry_run: bool
    allow_prod: bool


class DbUpgradeWizardFlow(BaseCliWizardFlow[DbUpgradeWizardSelection]):
    """
    `wizard db-upgrade` 向导流程。

    :param default_env: 默认环境
    :param default_revision: 默认目标 revision
    :param default_dry_run: 默认是否先执行 dry-run
    """

    wizard_name = 'wizard db-upgrade'
    preview_title = 'wizard db-upgrade preview'
    failure_message = '数据库升级向导执行失败'

    def __init__(
        self,
        *,
        default_env: str = 'dev',
        default_revision: str = 'head',
        default_dry_run: bool = True,
    ) -> None:
        """
        初始化数据库升级向导流程。

        :param default_env: 默认环境
        :param default_revision: 默认目标 revision
        :param default_dry_run: 默认是否先执行 dry-run
        :return: None
        """
        self.default_env = default_env
        self.default_revision = default_revision
        self.default_dry_run = default_dry_run

    def collect_selection(self) -> DbUpgradeWizardSelection:
        """
        采集数据库升级向导参数。

        :return: 向导采集结果
        """
        env = self.prompt_service.prompt_env(self.default_env)
        revision = self.prompt_service.prompt_required_text('目标迁移版本', self.default_revision)
        dry_run = self.prompt_service.prompt_confirm('是否先执行 dry-run 预演', default_value=self.default_dry_run)
        allow_prod = (
            self.prompt_service.prompt_confirm('当前为 prod 环境，是否允许继续执行', default_value=False)
            if env == 'prod'
            else False
        )
        return DbUpgradeWizardSelection(env=env, revision=revision, dry_run=dry_run, allow_prod=allow_prod)

    def prepare_context(self, selection: DbUpgradeWizardSelection, output: OutputOption) -> CliContext:
        """
        构建数据库升级向导上下文。

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

    def build_preview_summary(self, selection: DbUpgradeWizardSelection) -> dict[str, str]:
        """
        构建数据库升级预览摘要。

        :param selection: 向导采集结果
        :return: 预览摘要
        """
        return {
            'env': selection.env,
            'revision': selection.revision,
            'dry_run': str(selection.dry_run).lower(),
            'allow_prod': str(selection.allow_prod).lower(),
        }

    def build_preview_command(self, selection: DbUpgradeWizardSelection) -> list[str]:
        """
        构建数据库升级预览命令。

        :param selection: 向导采集结果
        :return: 用户视角命令参数
        """
        command = ['ruoyi', 'db', 'upgrade', f'--env={selection.env}', f'--revision={selection.revision}']
        if selection.dry_run:
            command.append('--dry-run')
        if selection.allow_prod:
            command.append('--allow-prod')
        return command

    def confirm_prompt(self, selection: DbUpgradeWizardSelection) -> str:
        """
        返回数据库升级最终确认提示。

        :param selection: 向导采集结果
        :return: 确认提示
        """
        del selection
        return '确认执行数据库升级向导吗'

    def build_execute_arguments(self, selection: DbUpgradeWizardSelection, output: OutputOption) -> list[str]:
        """
        构建数据库升级内部 CLI 参数。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 参数
        """
        arguments = [
            'db',
            'upgrade',
            f'--env={selection.env}',
            f'--output={output}',
            f'--revision={selection.revision}',
            '--yes',
        ]
        if selection.dry_run:
            arguments.append('--dry-run')
        if selection.allow_prod:
            arguments.append('--allow-prod')
        return arguments


def run_db_upgrade_wizard(
    output: OutputOption = 'text',
    *,
    default_env: str = 'dev',
    default_revision: str = 'head',
    default_dry_run: bool = True,
) -> None:
    """
    执行 `wizard db-upgrade` 向导。

    :param output: 输出格式
    :param default_env: 默认环境
    :param default_revision: 默认目标 revision
    :param default_dry_run: 默认是否先 dry-run
    :return: None
    """
    DbUpgradeWizardFlow(
        default_env=default_env,
        default_revision=default_revision,
        default_dry_run=default_dry_run,
    ).run(output)
