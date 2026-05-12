from dataclasses import dataclass

from cli.context import CliContext, OutputOption
from cli.wizard.base import BaseCliWizardFlow


@dataclass(frozen=True)
class CacheClearWizardSelection:
    """
    `wizard cache-clear` 向导采集结果。

    :param env: 运行环境
    :param mode: 清理模式
    :param cache_name: 缓存名称前缀
    :param cache_key: 缓存键名关键字
    :param dry_run: 是否演练执行
    :param allow_prod: 是否允许生产环境执行
    """

    env: str
    mode: str
    cache_name: str
    cache_key: str
    dry_run: bool
    allow_prod: bool


class CacheClearWizardFlow(BaseCliWizardFlow[CacheClearWizardSelection]):
    """
    `wizard cache-clear` 向导流程。

    :param default_env: 默认环境
    :param default_mode: 默认清理模式
    :param default_cache_name: 默认缓存名称前缀
    :param default_cache_key: 默认缓存键名关键字
    :param default_dry_run: 默认是否先执行 dry-run
    """

    wizard_name = 'wizard cache-clear'
    preview_title = 'wizard cache-clear preview'
    failure_message = '缓存清理向导执行失败'

    def __init__(
        self,
        *,
        default_env: str = 'dev',
        default_mode: str = 'cache-name',
        default_cache_name: str = '',
        default_cache_key: str = '',
        default_dry_run: bool = True,
    ) -> None:
        """
        初始化缓存清理向导流程。

        :param default_env: 默认环境
        :param default_mode: 默认清理模式
        :param default_cache_name: 默认缓存名称前缀
        :param default_cache_key: 默认缓存键名关键字
        :param default_dry_run: 默认是否先执行 dry-run
        :return: None
        """
        self.default_env = default_env
        self.default_mode = default_mode
        self.default_cache_name = default_cache_name
        self.default_cache_key = default_cache_key
        self.default_dry_run = default_dry_run

    def collect_selection(self) -> CacheClearWizardSelection:
        """
        采集缓存清理向导参数。

        :return: 向导采集结果
        """
        env = self.prompt_service.prompt_env(self.default_env)
        mode = self.prompt_service.prompt_choice(
            '清理模式',
            ['cache-name', 'cache-key', 'all'],
            self.default_mode,
        )
        cache_name = ''
        cache_key = ''
        if mode == 'cache-name':
            cache_name = self.prompt_service.prompt_required_text('缓存名称前缀', self.default_cache_name)
        elif mode == 'cache-key':
            cache_key = self.prompt_service.prompt_required_text('缓存键名关键字', self.default_cache_key)
        else:
            self.prompt_service.prompt_optional_text('当前将清理全部缓存，按回车继续', '')
        dry_run = self.prompt_service.prompt_confirm('是否先执行 dry-run 预演', default_value=self.default_dry_run)
        allow_prod = (
            self.prompt_service.prompt_confirm('当前为 prod 环境，是否允许继续执行', default_value=False)
            if env == 'prod'
            else False
        )
        return CacheClearWizardSelection(
            env=env,
            mode=mode,
            cache_name=cache_name,
            cache_key=cache_key,
            dry_run=dry_run,
            allow_prod=allow_prod,
        )

    def prepare_context(self, selection: CacheClearWizardSelection, output: OutputOption) -> CliContext:
        """
        构建缓存清理向导上下文。

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

    def build_preview_summary(self, selection: CacheClearWizardSelection) -> dict[str, str]:
        """
        构建缓存清理预览摘要。

        :param selection: 向导采集结果
        :return: 预览摘要
        """
        return {
            'env': selection.env,
            'mode': selection.mode,
            'cache_name': selection.cache_name or '-',
            'cache_key': selection.cache_key or '-',
            'dry_run': str(selection.dry_run).lower(),
            'allow_prod': str(selection.allow_prod).lower(),
        }

    def build_preview_command(self, selection: CacheClearWizardSelection) -> list[str]:
        """
        构建缓存清理预览命令。

        :param selection: 向导采集结果
        :return: 用户视角命令参数
        """
        command = ['ruoyi', 'cache', 'clear', f'--env={selection.env}']
        if selection.mode == 'cache-name':
            command.append(f'--cache-name={selection.cache_name}')
        elif selection.mode == 'cache-key':
            command.append(f'--cache-key={selection.cache_key}')
        else:
            command.append('--all')
        if selection.dry_run:
            command.append('--dry-run')
        if selection.allow_prod:
            command.append('--allow-prod')
        return command

    def confirm_prompt(self, selection: CacheClearWizardSelection) -> str:
        """
        返回缓存清理最终确认提示。

        :param selection: 向导采集结果
        :return: 确认提示
        """
        del selection
        return '确认执行缓存清理向导吗'

    def build_execute_arguments(self, selection: CacheClearWizardSelection, output: OutputOption) -> list[str]:
        """
        构建缓存清理内部 CLI 参数。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 参数
        """
        arguments = ['cache', 'clear', f'--env={selection.env}', f'--output={output}', '--yes']
        if selection.mode == 'cache-name':
            arguments.append(f'--cache-name={selection.cache_name}')
        elif selection.mode == 'cache-key':
            arguments.append(f'--cache-key={selection.cache_key}')
        else:
            arguments.append('--all')
        if selection.dry_run:
            arguments.append('--dry-run')
        if selection.allow_prod:
            arguments.append('--allow-prod')
        return arguments


def run_cache_clear_wizard(
    output: OutputOption = 'text',
    *,
    default_env: str = 'dev',
    default_mode: str = 'cache-name',
    default_cache_name: str = '',
    default_cache_key: str = '',
    default_dry_run: bool = True,
) -> None:
    """
    执行 `wizard cache-clear` 向导。

    :param output: 输出格式
    :param default_env: 默认环境
    :param default_mode: 默认清理模式
    :param default_cache_name: 默认缓存名称前缀
    :param default_cache_key: 默认缓存键关键字
    :param default_dry_run: 默认是否执行 dry-run
    :return: None
    """
    CacheClearWizardFlow(
        default_env=default_env,
        default_mode=default_mode,
        default_cache_name=default_cache_name,
        default_cache_key=default_cache_key,
        default_dry_run=default_dry_run,
    ).run(output)
