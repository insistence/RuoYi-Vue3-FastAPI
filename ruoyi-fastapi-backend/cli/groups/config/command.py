from typing import Annotated, Literal

import typer

from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY
from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

from .controller import ConfigCommandController

app = typer.Typer(
    help='参数配置相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_CONFIG_COMMAND_CONTROLLER = ConfigCommandController()


@app.command('list', help='查看参数配置列表')
def list_command(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    config_name: Annotated[str, typer.Option('--config-name', help='按参数名称过滤')] = '',
    config_key: Annotated[
        str,
        typer.Option(
            '--config-key',
            help='按参数键名过滤',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_config_keys,
        ),
    ] = '',
    config_type: Annotated[Literal['Y', 'N'] | None, typer.Option('--config-type', help='按系统内置标记过滤')] = None,
    begin_date: Annotated[str, typer.Option('--begin-date', help='按创建时间开始日期过滤，格式 YYYY-MM-DD')] = '',
    end_date: Annotated[str, typer.Option('--end-date', help='按创建时间结束日期过滤，格式 YYYY-MM-DD')] = '',
    paged: Annotated[bool, typer.Option('--paged/--no-paged', help='是否启用分页结果')] = False,
    page_num: Annotated[int, typer.Option('--page-num', min=1, help='分页页码')] = 1,
    page_size: Annotated[int, typer.Option('--page-size', min=1, help='分页每页数量')] = 20,
) -> None:
    """
    查看参数配置列表。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param config_name: 参数名称过滤条件
    :param config_key: 参数键名过滤条件
    :param config_type: 参数类型过滤条件
    :param begin_date: 查询开始日期
    :param end_date: 查询结束日期
    :param paged: 是否启用分页
    :param page_num: 页码
    :param page_size: 每页数量
    :return: None
    """
    _CONFIG_COMMAND_CONTROLLER.list_configs(
        env,
        output,
        config_name=config_name,
        config_key=config_key,
        config_type=config_type,
        begin_date=begin_date,
        end_date=end_date,
        paged=paged,
        page_num=page_num,
        page_size=page_size,
    )


@app.command('get', help='查看单个参数配置详情')
def get_command(
    config_key: Annotated[
        str,
        typer.Argument(
            help='需要查询的参数键名',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_config_keys,
        ),
    ],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    source: Annotated[Literal['db', 'cache', 'both'], typer.Option('--source', help='读取来源')] = 'both',
) -> None:
    """
    查看单个参数配置详情。

    :param config_key: 需要查询的参数键名
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param source: 配置读取来源
    :return: None
    """
    _CONFIG_COMMAND_CONTROLLER.get_config(config_key, env, output, source=source)


@app.command('set', help='新增或更新单个参数配置')
def set_command(
    config_key: Annotated[
        str,
        typer.Argument(
            help='需要写入的参数键名',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_config_keys,
        ),
    ],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    value: Annotated[str, typer.Option('--value', help='参数键值')] = ...,
    name: Annotated[str | None, typer.Option('--name', help='参数名称，新增时必填')] = None,
    config_type: Annotated[Literal['Y', 'N'] | None, typer.Option('--config-type', help='系统内置标记')] = None,
    remark: Annotated[str | None, typer.Option('--remark', help='参数备注')] = None,
) -> None:
    """
    新增或更新单个参数配置。

    :param config_key: 需要写入的参数键名
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param value: 参数键值
    :param name: 参数名称
    :param config_type: 参数类型
    :param remark: 参数备注
    :return: None
    """
    _CONFIG_COMMAND_CONTROLLER.set_config(
        config_key,
        env,
        output,
        allow_prod,
        yes,
        dry_run,
        value=value,
        name=name,
        config_type=config_type,
        remark=remark,
    )


@app.command('sync-cache', help='刷新参数配置缓存')
def sync_cache(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
) -> None:
    """
    刷新参数配置缓存。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :return: None
    """
    _CONFIG_COMMAND_CONTROLLER.sync_cache(env, output, allow_prod, yes)


@app.command('doctor', help='诊断参数配置数据库与缓存是否一致')
def doctor(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    sample_limit: Annotated[int, typer.Option('--sample-limit', min=1, help='问题示例键名输出上限')] = 10,
) -> None:
    """
    诊断参数配置数据库与缓存是否一致。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param sample_limit: 问题示例键名输出上限
    :return: None
    """
    _CONFIG_COMMAND_CONTROLLER.doctor(env, output, sample_limit=sample_limit)
