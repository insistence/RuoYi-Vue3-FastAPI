from typing import Annotated, Literal

import typer

from cli.context import EnvOption, OutputOption

from .controller import AppCommandController

app = typer.Typer(
    help='应用相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_APP_COMMAND_CONTROLLER = AppCommandController()


@app.command('run', help='启动当前 FastAPI 应用')
def run_app(
    env: EnvOption = 'dev',
) -> None:
    """
    启动当前 FastAPI 应用。

    :param env: 当前命令运行环境
    :return: None
    """
    _APP_COMMAND_CONTROLLER.run_app(env)


@app.command('doctor', help='执行应用启动前检查')
def doctor(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    执行应用启动前检查。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _APP_COMMAND_CONTROLLER.doctor(env, output)


@app.command('config', help='查看当前应用配置快照')
def app_config(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    输出当前应用配置快照。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _APP_COMMAND_CONTROLLER.show_config(env, output)


@app.command('env', help='查看当前 CLI 解析到的应用环境信息')
def app_env(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    输出当前 CLI 解析到的应用环境信息。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _APP_COMMAND_CONTROLLER.show_env(env, output)


@app.command('routes', help='查看当前应用注册路由清单')
def routes(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    path_prefix: Annotated[str, typer.Option('--path-prefix', help='按路由前缀过滤')] = '',
    method: Annotated[str, typer.Option('--method', help='按请求方法过滤，如 GET、POST')] = '',
    group_by: Annotated[Literal['none', 'tag'], typer.Option('--group-by', help='路由分组方式')] = 'none',
    include_hidden: Annotated[bool, typer.Option('--include-hidden', help='包含未出现在 OpenAPI 中的路由')] = False,
) -> None:
    """
    输出当前应用注册路由清单。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param path_prefix: 路由前缀过滤条件
    :param method: 请求方法过滤条件
    :param group_by: 路由分组方式
    :param include_hidden: 是否包含隐藏路由
    :return: None
    """
    _APP_COMMAND_CONTROLLER.show_routes(
        env,
        output,
        path_prefix=path_prefix,
        method=method,
        group_by=group_by,
        include_hidden=include_hidden,
    )
