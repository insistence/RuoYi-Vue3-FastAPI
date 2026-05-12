import typer

from cli.completion.providers import COMPLETION_PROVIDER_GATEWAY
from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

from .controller import CacheCommandController

app = typer.Typer(
    help='缓存相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_CACHE_COMMAND_CONTROLLER = CacheCommandController()


@app.command('stats', help='查看缓存统计信息')
def stats(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看缓存统计信息。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _CACHE_COMMAND_CONTROLLER.stats(env, output)


@app.command('keys', help='查看指定缓存名称下的键名列表')
def keys(
    cache_name: str = typer.Argument(
        ...,
        help='缓存名称',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_cache_names,
    ),
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看指定缓存名称下的键名列表。

    :param cache_name: 缓存名称
    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _CACHE_COMMAND_CONTROLLER.keys(cache_name, env, output)


@app.command('get', help='查看指定缓存内容')
def get(
    cache_name: str = typer.Argument(
        ...,
        help='缓存名称',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_cache_names,
    ),
    cache_key: str = typer.Argument(
        ...,
        help='缓存键名',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_cache_keys,
    ),
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看指定缓存内容。

    :param cache_name: 缓存名称
    :param cache_key: 缓存键名
    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _CACHE_COMMAND_CONTROLLER.get(cache_name, cache_key, env, output)


@app.command('clear', help='执行缓存清理')
def clear(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    cache_name: str = typer.Option(
        '',
        '--cache-name',
        help='按缓存名称前缀清理',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_cache_names,
    ),
    cache_key: str = typer.Option('', '--cache-key', help='按缓存键名模糊清理'),
    clear_all: bool = typer.Option(False, '--all', help='清理全部缓存并重建系统基础缓存'),
) -> None:
    """
    清理缓存。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param cache_name: 缓存名称前缀
    :param cache_key: 缓存键名
    :param clear_all: 是否清理全部缓存
    :return: None
    """
    _CACHE_COMMAND_CONTROLLER.clear(
        env,
        output,
        allow_prod,
        yes,
        dry_run,
        cache_name=cache_name,
        cache_key=cache_key,
        clear_all=clear_all,
    )


@app.command('ttl', help='查看指定缓存键的剩余过期时间')
def ttl(
    cache_name: str = typer.Argument(
        ...,
        help='缓存名称',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_cache_names,
    ),
    cache_key: str = typer.Argument(
        ...,
        help='缓存键名',
        autocompletion=COMPLETION_PROVIDER_GATEWAY.complete_cache_keys,
    ),
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    查看指定缓存键的剩余过期时间。

    :param cache_name: 缓存名称
    :param cache_key: 缓存键名
    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _CACHE_COMMAND_CONTROLLER.ttl(cache_name, cache_key, env, output)


@app.command('warmup', help='执行系统缓存预热')
def warmup(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
) -> None:
    """
    执行系统缓存预热。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :return: None
    """
    _CACHE_COMMAND_CONTROLLER.warmup(env, output, allow_prod, yes)
