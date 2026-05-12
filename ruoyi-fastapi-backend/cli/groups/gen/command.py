from typing import Annotated, Literal

import typer

from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY
from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

from .controller import GenCommandController

app = typer.Typer(
    help='代码生成相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_GEN_COMMAND_CONTROLLER = GenCommandController()


@app.command('import-table', help='导入数据库表到代码生成业务表')
def import_table(
    table_names: Annotated[
        list[str],
        typer.Argument(
            help='待导入的数据库表名，可传多个',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_gen_db_table_names,
        ),
    ],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    导入数据库表到代码生成业务表。

    :param table_names: 待导入表名列表
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.import_table(
        table_names,
        env,
        output,
        allow_prod,
        yes,
        dry_run,
    )


@app.command('list', help='查看代码生成业务表列表')
def list_command(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    table_name: str = typer.Option(
        '',
        '--table-name',
        help='按表名称过滤',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_gen_table_names,
    ),
    table_comment: str = typer.Option('', '--table-comment', help='按表描述过滤'),
    paged: bool = typer.Option(False, '--paged/--no-paged', help='是否启用分页结果'),
    page_num: int = typer.Option(1, '--page-num', min=1, help='分页页码'),
    page_size: int = typer.Option(20, '--page-size', min=1, help='分页每页数量'),
) -> None:
    """
    查看代码生成业务表列表。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param table_name: 表名称过滤条件
    :param table_comment: 表描述过滤条件
    :param paged: 是否启用分页
    :param page_num: 页码
    :param page_size: 每页数量
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.list_tables(
        env,
        output,
        table_name=table_name,
        table_comment=table_comment,
        paged=paged,
        page_num=page_num,
        page_size=page_size,
    )


@app.command('db-list', help='查看数据库中可导入的物理表列表')
def db_list(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    table_name: str = typer.Option(
        '',
        '--table-name',
        help='按表名称过滤',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_gen_db_table_names,
    ),
    table_comment: str = typer.Option('', '--table-comment', help='按表描述过滤'),
    paged: bool = typer.Option(False, '--paged/--no-paged', help='是否启用分页结果'),
    page_num: int = typer.Option(1, '--page-num', min=1, help='分页页码'),
    page_size: int = typer.Option(20, '--page-size', min=1, help='分页每页数量'),
) -> None:
    """
    查看数据库中可导入的物理表列表。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param table_name: 表名称过滤条件
    :param table_comment: 表描述过滤条件
    :param paged: 是否启用分页
    :param page_num: 页码
    :param page_size: 每页数量
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.list_db_tables(
        env,
        output,
        table_name=table_name,
        table_comment=table_comment,
        paged=paged,
        page_num=page_num,
        page_size=page_size,
    )


@app.command('detail', help='查看单个代码生成业务表详情')
def detail(
    table_id: Annotated[int, typer.Argument(help='业务表 ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看单个代码生成业务表详情。

    :param table_id: 业务表 ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.show_detail(table_id, env, output)


@app.command('create-table', help='根据建表 SQL 创建表结构并导入代码生成业务表')
def create_table(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    sql: str = typer.Option('', '--sql', help='直接传入建表 SQL 文本'),
    sql_file: str = typer.Option(
        '',
        '--sql-file',
        help='从文件读取建表 SQL',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_sql_files,
    ),
) -> None:
    """
    根据建表 SQL 创建表结构并导入代码生成业务表。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param sql: 直接传入的 SQL 文本
    :param sql_file: SQL 文件路径
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.create_table(
        env,
        output,
        allow_prod,
        yes,
        dry_run,
        sql=sql,
        sql_file=sql_file,
    )


@app.command('preview', help='查看指定业务表的代码生成结果预览')
def preview(
    table_id: Annotated[int, typer.Argument(help='业务表 ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    预览指定业务表的代码生成结果。

    :param table_id: 业务表 ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.preview(table_id, env, output)


@app.command('export', help='导出代码生成结果')
def export(
    table_names: Annotated[
        list[str],
        typer.Argument(
            help='待导出的业务表名，可传多个',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_gen_table_names,
        ),
    ],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    mode: Annotated[Literal['zip', 'local'], typer.Option('--mode', help='导出模式')] = 'zip',
    output_file: str = typer.Option(
        '',
        '--output-file',
        help='zip 导出目标文件路径',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_output_paths,
    ),
) -> None:
    """
    导出代码生成结果。

    :param table_names: 业务表名称列表
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param mode: 导出模式
    :param output_file: zip 导出目标文件路径
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.export(
        table_names,
        env,
        output,
        allow_prod,
        yes,
        dry_run,
        mode=mode,
        output_file=output_file,
    )


@app.command('sync-db', help='同步指定业务表的数据库表结构')
def sync_db(
    table_name: Annotated[
        str,
        typer.Argument(
            help='业务表名称',
            autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_gen_table_names,
        ),
    ],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
) -> None:
    """
    同步指定业务表的数据库表结构。

    :param table_name: 业务表名称
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :return: None
    """
    _GEN_COMMAND_CONTROLLER.sync_db(table_name, env, output, allow_prod, yes)
