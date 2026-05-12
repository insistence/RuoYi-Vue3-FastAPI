import typer

from cli.context import EnvOption, OutputOption

from .controller import OpsCommandController

app = typer.Typer(
    help='运维相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_OPS_COMMAND_CONTROLLER = OpsCommandController()


@app.command('ping-db', help='检查数据库连接')
def ping_db(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    检查数据库连接。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _OPS_COMMAND_CONTROLLER.ping_db(env, output)


@app.command('ping-redis', help='检查 Redis 连接')
def ping_redis_command(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    检查 Redis 连接。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _OPS_COMMAND_CONTROLLER.ping_redis(env, output)


@app.command('health', help='查看基础健康检查结果')
def health(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    输出基础健康检查结果。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _OPS_COMMAND_CONTROLLER.health(env, output)


@app.command('deps', help='查看当前 CLI 和后端运行依赖版本')
def deps(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    include_dev: bool = typer.Option(False, '--include-dev', help='附带输出开发依赖'),
) -> None:
    """
    检查当前 CLI 和后端运行依赖版本。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param include_dev: 是否附带输出开发依赖
    :return: None
    """
    _OPS_COMMAND_CONTROLLER.deps(env, output, include_dev=include_dev)


@app.command('server-info', help='查看服务器运行时信息')
def server_info(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    输出服务器运行时信息。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _OPS_COMMAND_CONTROLLER.server_info(env, output)
