from typing import Annotated

import typer

from cli.context import EnvOption, OutputOption

from .controller import DevCommandController

app = typer.Typer(
    help='开发相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_DEV_COMMAND_CONTROLLER = DevCommandController()


@app.command('lint', help='执行 Ruff 格式化与静态检查')
def lint(
    targets: Annotated[list[str] | None, typer.Argument(help='待检查路径，可传多个')] = None,
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    check_only: bool = typer.Option(False, '--check-only', help='仅检查，不写回格式化结果'),
    fix: bool = typer.Option(False, '--fix', help='执行 ruff check --fix'),
    unsafe_fixes: bool = typer.Option(False, '--unsafe-fixes', help='允许 Ruff 不安全修复'),
) -> None:
    """
    执行 Ruff 格式化与静态检查。

    :param targets: 待检查路径列表
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param check_only: 是否仅检查不写回
    :param fix: 是否自动修复可修复问题
    :param unsafe_fixes: 是否允许不安全修复
    :return: None
    """
    _DEV_COMMAND_CONTROLLER.lint(
        targets,
        env,
        output,
        check_only=check_only,
        fix=fix,
        unsafe_fixes=unsafe_fixes,
    )


@app.command('test', help='执行项目测试')
def test(
    targets: Annotated[list[str] | None, typer.Argument(help='待执行的测试路径，可传多个')] = None,
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    keyword: str = typer.Option('', '--keyword', '-k', help='pytest -k 过滤表达式'),
    maxfail: int = typer.Option(0, '--maxfail', min=0, help='最大失败数，0 表示不限制'),
    quiet: bool = typer.Option(False, '--quiet', '-q', help='启用简洁输出'),
) -> None:
    """
    执行项目测试。

    :param targets: 测试目标路径列表
    :param env: 当前命令运行环境
    :param output: 输出格式
    :param keyword: pytest 关键字过滤表达式
    :param maxfail: 最大失败数
    :param quiet: 是否启用简洁输出
    :return: None
    """
    _DEV_COMMAND_CONTROLLER.test(
        targets,
        env,
        output,
        keyword=keyword,
        maxfail=maxfail,
        quiet=quiet,
    )
