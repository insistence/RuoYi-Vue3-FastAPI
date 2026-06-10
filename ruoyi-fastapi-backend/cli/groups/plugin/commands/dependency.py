from collections.abc import Callable
from typing import Annotated, Any

import typer

from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption


def register_dependency_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册插件依赖、预检和计划命令。

    :param app: Typer 命令组
    :param get_controller: 插件命令控制器工厂
    :return: None
    """

    @app.command('check-deps', help='检查插件依赖')
    def check_deps_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        检查插件依赖。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().check_plugin_dependencies(plugin_id, env, output)

    @app.command('precheck', help='执行插件操作预检')
    def precheck_command(
        operation: Annotated[str, typer.Argument(help='预检操作类型：install、enable、upgrade、uninstall 或 purge')],
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        执行插件操作预检。

        :param operation: 预检操作类型
        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().precheck_plugin(operation, plugin_id, env, output)

    @app.command('plan', help='生成插件批量操作拓扑计划')
    def plan_command(
        operation: Annotated[str, typer.Argument(help='计划操作类型：install、enable 或 upgrade')],
        plugin_ids: Annotated[list[str] | None, typer.Argument(help='插件ID列表，不传则计划全部插件')] = None,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        生成插件批量操作拓扑计划。

        :param operation: 计划操作类型
        :param plugin_ids: 插件ID列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().plan_plugins(operation, plugin_ids or [], env, output)

    @app.command('install-deps', help='安装插件依赖')
    def install_deps_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
        dry_run: DryRunOption = False,
    ) -> None:
        """
        安装插件依赖。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :return: None
        """
        get_controller().install_plugin_dependencies(
            plugin_id,
            env,
            output,
            allow_prod=allow_prod,
            yes=yes,
            dry_run=dry_run,
        )
