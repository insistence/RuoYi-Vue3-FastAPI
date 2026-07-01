from collections.abc import Callable
from typing import Annotated, Any, Literal

import typer

from cli.context import AllowProdOption, EnvOption, OutputOption, YesOption

PluginConfigAction = Literal['get', 'set', 'export', 'import']


def register_configuration_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册插件配置命令。

    :param app: Typer 命令组
    :param get_controller: 插件命令控制器工厂
    :return: None
    """

    @app.command('config', help='查看或设置插件配置')
    def config_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        action: Annotated[PluginConfigAction, typer.Argument(help='操作类型：get、set、export 或 import')],
        pairs: Annotated[list[str] | None, typer.Argument(help='配置键值，例如 provider=openai')] = None,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
        reveal_secret: Annotated[bool, typer.Option('--reveal-secret', help='导出敏感配置明文')] = False,
        output_file: Annotated[str, typer.Option('--output-file', help='配置导出 JSON 文件路径')] = '',
        input_file: Annotated[str, typer.Option('--input-file', help='配置导入 JSON 文件路径')] = '',
    ) -> None:
        """
        查看或设置插件配置。

        :param plugin_id: 插件ID
        :param action: 操作类型
        :param pairs: 配置键值列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param reveal_secret: 是否导出敏感配置明文
        :param output_file: 配置导出 JSON 文件路径
        :param input_file: 配置导入 JSON 文件路径
        :return: None
        """
        get_controller().plugin_config(
            plugin_id,
            action,
            pairs or [],
            env,
            output,
            allow_prod=allow_prod,
            yes=yes,
            reveal_secret=reveal_secret,
            output_file=output_file,
            input_file=input_file,
        )
