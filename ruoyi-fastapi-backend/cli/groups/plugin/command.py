import importlib
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

import typer

from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

from .options import PluginCreateCommandOptions

if TYPE_CHECKING:
    from .controller import PluginCommandController

app = typer.Typer(
    help='插件管理相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)


@lru_cache(maxsize=1)
def _get_plugin_command_controller() -> 'PluginCommandController':
    """
    延迟获取插件命令控制器。

    :return: 插件命令控制器
    """
    controller_class = importlib.import_module('cli.groups.plugin.controller').PluginCommandController
    return controller_class()


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
    _get_plugin_command_controller().list_plugins(env, output)


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
    _get_plugin_command_controller().plugin_info(plugin_id, env, output)


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
    _get_plugin_command_controller().check_plugin(plugin_id, env, output)


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
    _get_plugin_command_controller().check_plugin_dependencies(plugin_id, env, output)


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
    _get_plugin_command_controller().precheck_plugin(operation, plugin_id, env, output)


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
    _get_plugin_command_controller().health_plugin(plugin_id, env, output)


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
    _get_plugin_command_controller().diagnose_plugin(plugin_id, env, output, output_file=output_file)


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
    _get_plugin_command_controller().generate_plugin_docs(plugin_id, env, output, output_file=output_file)


@app.command('test', help='执行插件测试')
def test_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    keyword: Annotated[str, typer.Option('--keyword', '-k', help='pytest -k 过滤表达式')] = '',
    maxfail: Annotated[int, typer.Option('--maxfail', min=0, help='最大失败数，0 表示不限制')] = 0,
    quiet: Annotated[bool, typer.Option('--quiet', '-q', help='启用简洁输出')] = False,
    frontend_build: Annotated[bool, typer.Option('--frontend-build', help='追加执行前端构建验收')] = False,
) -> None:
    """
    执行插件测试。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param keyword: pytest 关键字过滤表达式
    :param maxfail: 最大失败数
    :param quiet: 是否启用简洁输出
    :param frontend_build: 是否追加执行前端构建验收
    :return: None
    """
    _get_plugin_command_controller().test_plugin(
        plugin_id,
        env,
        output,
        keyword=keyword,
        maxfail=maxfail,
        quiet=quiet,
        frontend_build=frontend_build,
    )


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
    _get_plugin_command_controller().plan_plugins(operation, plugin_ids or [], env, output)


@app.command('batch', help='按拓扑顺序批量执行插件操作')
def batch_command(
    operation: Annotated[str, typer.Argument(help='批量操作类型：install、enable 或 upgrade')],
    plugin_ids: Annotated[list[str] | None, typer.Argument(help='插件ID列表，不传则执行全部插件')] = None,
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    continue_on_error: Annotated[bool, typer.Option('--continue-on-error', help='失败后继续执行后续插件')] = False,
) -> None:
    """
    按拓扑顺序批量执行插件操作。

    :param operation: 批量操作类型
    :param plugin_ids: 插件ID列表
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :param continue_on_error: 失败后是否继续执行后续插件
    :return: None
    """
    _get_plugin_command_controller().batch_plugins(
        operation,
        plugin_ids or [],
        env,
        output,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
        continue_on_error=continue_on_error,
    )


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
    _get_plugin_command_controller().install_plugin_dependencies(
        plugin_id,
        env,
        output,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
    )


@app.command('create', help='创建插件开发模板')
def create_command(  # noqa: PLR0913
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    template: Annotated[
        str,
        typer.Option('--template', help='插件模板：minimal、backend-only、full-stack、scheduled-job、crud-page'),
    ] = 'full-stack',
    backend_only: Annotated[bool, typer.Option('--backend-only', help='只创建后端插件模板')] = False,
    frontend_only: Annotated[bool, typer.Option('--frontend-only', help='只创建前端插件模板')] = False,
    no_migration: Annotated[bool, typer.Option('--no-migration', help='不创建 migration 示例')] = False,
    no_seed: Annotated[bool, typer.Option('--no-seed', help='不创建 seed 示例')] = False,
    no_job: Annotated[bool, typer.Option('--no-job', help='不创建定时任务示例')] = False,
    no_config: Annotated[bool, typer.Option('--no-config', help='不创建配置项示例')] = False,
    no_test: Annotated[bool, typer.Option('--no-test', help='不创建测试样例')] = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    创建插件开发模板。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param template: 插件模板名称
    :param backend_only: 是否只创建后端插件模板
    :param frontend_only: 是否只创建前端插件模板
    :param no_migration: 是否不创建 migration 示例
    :param no_seed: 是否不创建 seed 示例
    :param no_job: 是否不创建定时任务示例
    :param no_config: 是否不创建配置项示例
    :param no_test: 是否不创建测试样例
    :param dry_run: 是否仅预演
    :return: None
    """
    _get_plugin_command_controller().create_plugin(
        plugin_id,
        env,
        output,
        PluginCreateCommandOptions(
            backend_only=backend_only,
            frontend_only=frontend_only,
            template=template,
            no_migration=no_migration,
            no_seed=no_seed,
            no_job=no_job,
            no_config=no_config,
            no_test=no_test,
            dry_run=dry_run,
        ),
    )


@app.command('install', help='安装插件')
def install_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    安装插件。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :return: None
    """
    _get_plugin_command_controller().install_plugin(
        plugin_id,
        env,
        output,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
    )


@app.command('upgrade', help='升级插件')
def upgrade_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    升级插件。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :return: None
    """
    _get_plugin_command_controller().upgrade_plugin(
        plugin_id,
        env,
        output,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
    )


@app.command('enable', help='启用插件')
def enable_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    启用插件。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :return: None
    """
    _get_plugin_command_controller().set_plugin_enabled(
        plugin_id,
        env,
        output,
        enabled=True,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
    )


@app.command('disable', help='停用插件')
def disable_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    停用插件。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :return: None
    """
    _get_plugin_command_controller().set_plugin_enabled(
        plugin_id,
        env,
        output,
        enabled=False,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
    )


@app.command('uninstall', help='安全卸载插件（第一阶段等价于停用插件和菜单）')
def uninstall_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    安全卸载插件。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :return: None
    """
    _get_plugin_command_controller().uninstall_plugin(
        plugin_id,
        env,
        output,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
    )


@app.command('purge', help='物理清理插件平台元数据')
def purge_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """
    物理清理插件平台元数据。

    :param plugin_id: 插件ID
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :return: None
    """
    _get_plugin_command_controller().purge_plugin(
        plugin_id,
        env,
        output,
        allow_prod=allow_prod,
        yes=yes,
        dry_run=dry_run,
    )


@app.command('config', help='查看或设置插件配置')
def config_command(
    plugin_id: Annotated[str, typer.Argument(help='插件ID')],
    action: Annotated[str, typer.Argument(help='操作类型：get、set、export 或 import')],
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
    _get_plugin_command_controller().plugin_config(
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
