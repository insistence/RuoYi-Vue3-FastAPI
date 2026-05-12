from typing import Annotated

import typer

from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY
from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

from .controller import DbCommandController

app = typer.Typer(
    help='数据库相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_DB_COMMAND_CONTROLLER = DbCommandController()


@app.command('check', help='检查数据库连接状态')
def check(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    检查数据库连接状态。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _DB_COMMAND_CONTROLLER.check(env, output)


@app.command('current', help='查看当前数据库迁移版本')
def current(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看数据库当前迁移版本。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _DB_COMMAND_CONTROLLER.current(env, output)


@app.command('upgrade', help='执行数据库升级')
def upgrade(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    revision: Annotated[
        str,
        typer.Option(
            '--revision',
            help='目标迁移版本',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_alembic_revisions,
        ),
    ] = 'head',
) -> None:
    """
    执行数据库升级。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param revision: 目标迁移版本
    :return: None
    """
    _DB_COMMAND_CONTROLLER.upgrade(env, output, allow_prod, yes, dry_run, revision=revision)


@app.command('init', help='初始化数据库到最新迁移版本')
def init(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    初始化数据库到最新迁移版本。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :return: None
    """
    _DB_COMMAND_CONTROLLER.init(env, output, allow_prod, yes, dry_run)


@app.command('downgrade', help='执行数据库回退')
def downgrade(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    revision: Annotated[
        str,
        typer.Option(
            '--revision',
            help='目标回退版本',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_alembic_revisions,
        ),
    ] = '-1',
) -> None:
    """
    执行数据库回退。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param revision: 目标回退版本
    :return: None
    """
    _DB_COMMAND_CONTROLLER.downgrade(env, output, allow_prod, yes, dry_run, revision=revision)


@app.command('revision', help='创建新的数据库迁移版本文件')
def revision(
    message: Annotated[str, typer.Option('--message', '-m', help='迁移说明')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    autogenerate: bool = typer.Option(False, '--autogenerate/--no-autogenerate', help='是否自动生成迁移内容'),
) -> None:
    """
    创建新的数据库迁移版本文件。

    :param message: 迁移说明
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param autogenerate: 是否自动生成迁移内容
    :return: None
    """
    _DB_COMMAND_CONTROLLER.revision(
        message,
        env,
        output,
        allow_prod,
        yes,
        dry_run,
        autogenerate=autogenerate,
    )


@app.command('heads', help='查看当前代码仓库中的 Alembic heads')
def heads(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看当前代码仓库中的 Alembic heads。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _DB_COMMAND_CONTROLLER.heads(env, output)


@app.command('history', help='查看当前代码仓库中的 Alembic 历史版本')
def history(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    limit: Annotated[int, typer.Option('--limit', min=1, help='输出的最大历史记录数量')] = 20,
) -> None:
    """
    查看当前代码仓库中的 Alembic 历史版本。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param limit: 输出的最大历史记录数量
    :return: None
    """
    _DB_COMMAND_CONTROLLER.history(env, output, limit=limit)
