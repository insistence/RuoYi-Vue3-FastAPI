import typer

from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY
from cli.context import AllowProdOption, EnvOption, OutputOption, YesOption

from .controller import JobCommandController

app = typer.Typer(
    help='定时任务相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_JOB_COMMAND_CONTROLLER = JobCommandController()


@app.command('list', help='查看定时任务列表')
def list_command(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    job_name: str = typer.Option(
        '',
        '--job-name',
        help='按任务名称过滤',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_job_names,
    ),
    job_group: str = typer.Option('', '--job-group', help='按任务组过滤'),
    status: str | None = typer.Option(None, '--status', help='按任务状态过滤，0正常 1暂停'),
    paged: bool = typer.Option(False, '--paged/--no-paged', help='是否启用分页结果'),
    page_num: int = typer.Option(1, '--page-num', min=1, help='分页页码'),
    page_size: int = typer.Option(20, '--page-size', min=1, help='分页每页数量'),
) -> None:
    """
    查看定时任务列表。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param job_name: 任务名称过滤条件
    :param job_group: 任务组过滤条件
    :param status: 状态过滤条件
    :param paged: 是否启用分页
    :param page_num: 页码
    :param page_size: 每页数量
    :return: None
    """
    _JOB_COMMAND_CONTROLLER.list(
        env,
        output,
        job_name=job_name,
        job_group=job_group,
        status=status,
        paged=paged,
        page_num=page_num,
        page_size=page_size,
    )


@app.command('run-once', help='执行一次定时任务')
def run_once(
    job_id: int = typer.Argument(
        ...,
        help='任务ID',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_job_ids,
    ),
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
) -> None:
    """
    执行一次定时任务。

    :param job_id: 任务ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :return: None
    """
    _JOB_COMMAND_CONTROLLER.run_once(job_id, env, output, allow_prod, yes)


@app.command('detail', help='查看单个定时任务详情')
def detail(
    job_id: int = typer.Argument(
        ...,
        help='任务ID',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_job_ids,
    ),
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看单个定时任务详情。

    :param job_id: 任务ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _JOB_COMMAND_CONTROLLER.detail(job_id, env, output)


@app.command('logs', help='查看定时任务执行日志列表')
def logs(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    job_name: str = typer.Option(
        '',
        '--job-name',
        help='按任务名称过滤',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_job_names,
    ),
    job_group: str = typer.Option('', '--job-group', help='按任务组过滤'),
    status: str | None = typer.Option(None, '--status', help='按执行状态过滤，0成功 1失败'),
    begin_date: str = typer.Option('', '--begin-date', help='按创建时间开始日期过滤，格式 YYYY-MM-DD'),
    end_date: str = typer.Option('', '--end-date', help='按创建时间结束日期过滤，格式 YYYY-MM-DD'),
    paged: bool = typer.Option(False, '--paged/--no-paged', help='是否启用分页结果'),
    page_num: int = typer.Option(1, '--page-num', min=1, help='分页页码'),
    page_size: int = typer.Option(20, '--page-size', min=1, help='分页每页数量'),
) -> None:
    """
    查看定时任务执行日志列表。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param job_name: 任务名称过滤条件
    :param job_group: 任务组过滤条件
    :param status: 执行状态过滤条件
    :param begin_date: 查询开始日期
    :param end_date: 查询结束日期
    :param paged: 是否启用分页
    :param page_num: 页码
    :param page_size: 每页数量
    :return: None
    """
    _JOB_COMMAND_CONTROLLER.logs(
        env,
        output,
        job_name=job_name,
        job_group=job_group,
        status=status,
        begin_date=begin_date,
        end_date=end_date,
        paged=paged,
        page_num=page_num,
        page_size=page_size,
    )


@app.command('pause', help='暂停定时任务')
def pause(
    job_id: int = typer.Argument(
        ...,
        help='任务ID',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_job_ids,
    ),
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
) -> None:
    """
    暂停定时任务。

    :param job_id: 任务ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :return: None
    """
    _JOB_COMMAND_CONTROLLER.pause(job_id, env, output, allow_prod, yes)


@app.command('resume', help='恢复定时任务')
def resume(
    job_id: int = typer.Argument(
        ...,
        help='任务ID',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_job_ids,
    ),
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
) -> None:
    """
    恢复定时任务。

    :param job_id: 任务ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :return: None
    """
    _JOB_COMMAND_CONTROLLER.resume(job_id, env, output, allow_prod, yes)


@app.command('sync', help='同步调度任务配置')
def sync(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
) -> None:
    """
    同步调度任务配置。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :return: None
    """
    _JOB_COMMAND_CONTROLLER.sync(env, output, allow_prod, yes)
