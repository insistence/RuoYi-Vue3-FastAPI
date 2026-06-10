from collections.abc import Callable
from typing import Annotated, Any

import typer

from cli.context import EnvOption, OutputOption


def register_discovery_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册插件发现与诊断命令。

    :param app: Typer 命令组
    :param get_controller: 插件命令控制器工厂
    :return: None
    """

    @app.command('list', help='查看本地插件列表')
    def list_command(
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        查看本地插件列表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().list_plugins(env, output)

    @app.command('info', help='查看插件详情')
    def info_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        查看插件详情。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().plugin_info(plugin_id, env, output)

    @app.command('check', help='检查插件依赖状态')
    def check_command(
        plugin_id: Annotated[str | None, typer.Argument(help='插件ID，不传则检查全部插件')] = None,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        检查插件依赖状态。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().check_plugin(plugin_id, env, output)

    @app.command('health', help='执行插件健康检查')
    def health_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        执行插件健康检查。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().health_plugin(plugin_id, env, output)

    @app.command('diagnose', help='生成插件诊断包')
    def diagnose_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        output_file: Annotated[str, typer.Option('--output-file', help='诊断包 JSON 导出文件路径')] = '',
    ) -> None:
        """
        生成插件诊断包。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param output_file: 诊断包 JSON 导出文件路径
        :return: None
        """
        get_controller().diagnose_plugin(plugin_id, env, output, output_file=output_file)

    @app.command('docs', help='生成插件 Markdown 文档片段')
    def docs_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        output_file: Annotated[str, typer.Option('--output-file', help='Markdown 文档导出文件路径')] = '',
    ) -> None:
        """
        生成插件 Markdown 文档片段。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param output_file: Markdown 文档导出文件路径
        :return: None
        """
        get_controller().generate_plugin_docs(plugin_id, env, output, output_file=output_file)
