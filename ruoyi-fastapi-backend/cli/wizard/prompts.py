import typer

from cli.metadata import ENVIRONMENT_OPTION_SERVICE


class WizardPromptService:
    """
    向导交互输入服务。

    该对象集中封装向导中稳定复用的环境选择、枚举选择、
    文本采集和确认交互逻辑，避免继续扩散模块级散函数入口。
    """

    def prompt_env(self, default_env: str = 'dev') -> str:
        """
        交互采集运行环境名称。

        :param default_env: 默认环境名称
        :return: 用户选择的环境名称
        """
        env_names = ENVIRONMENT_OPTION_SERVICE.discover_env_names()
        prompt_message = f'运行环境（可选值: {", ".join(env_names)}）'
        while True:
            env_value = typer.prompt(prompt_message, default=default_env).strip()
            if env_value in env_names:
                return env_value
            typer.echo(f'不支持的环境名称：{env_value}，请重新输入。')

    @staticmethod
    def prompt_choice(prompt_text: str, choices: list[str], default_value: str) -> str:
        """
        交互采集枚举型文本输入。

        :param prompt_text: 提示文案
        :param choices: 可选值列表
        :param default_value: 默认值
        :return: 用户选择的枚举值
        """
        while True:
            value = typer.prompt(
                f'{prompt_text}（可选值: {", ".join(choices)}）',
                default=default_value,
            ).strip()
            if value in choices:
                return value
            typer.echo(f'不支持的选项：{value}，请重新输入。')

    @staticmethod
    def prompt_required_text(prompt_text: str, default_value: str = '') -> str:
        """
        交互采集必填文本输入。

        :param prompt_text: 提示文案
        :param default_value: 默认值
        :return: 用户输入文本
        """
        while True:
            value = typer.prompt(prompt_text, default=default_value).strip()
            if value:
                return value
            typer.echo('该字段不能为空，请重新输入。')

    @staticmethod
    def prompt_optional_text(prompt_text: str, default_value: str = '') -> str:
        """
        交互采集可选文本输入。

        :param prompt_text: 提示文案
        :param default_value: 默认值
        :return: 用户输入文本
        """
        return typer.prompt(prompt_text, default=default_value).strip()

    @staticmethod
    def prompt_confirm(prompt_text: str, default_value: bool = False) -> bool:
        """
        交互采集确认型输入。

        :param prompt_text: 提示文案
        :param default_value: 默认值
        :return: 用户确认结果
        """
        return typer.confirm(prompt_text, default=default_value)


WIZARD_PROMPT_SERVICE = WizardPromptService()
