import typer

from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

from .controller import CryptoCommandController

app = typer.Typer(
    help='传输加密相关命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
_CRYPTO_COMMAND_CONTROLLER = CryptoCommandController()


@app.command('validate', help='校验传输加密配置')
def validate(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    校验传输加密配置。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _CRYPTO_COMMAND_CONTROLLER.validate(env, output)


@app.command('keygen', help='生成新的传输加密密钥对')
def keygen(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    kid: str = typer.Option('default', '--kid', help='生成的密钥版本标识'),
    key_size: int = typer.Option(2048, '--key-size', help='RSA 密钥长度'),
) -> None:
    """
    生成新的传输加密密钥对。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param kid: 生成的密钥版本标识
    :param key_size: RSA 密钥长度
    :return: None
    """
    _CRYPTO_COMMAND_CONTROLLER.keygen(env, output, kid=kid, key_size=key_size)


@app.command('rotate', help='生成传输加密密钥轮换辅助结果')
def rotate(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    next_kid: str = typer.Option('rotated', '--next-kid', help='轮换后的新密钥版本标识'),
    key_size: int = typer.Option(2048, '--key-size', help='新密钥的 RSA 长度'),
) -> None:
    """
    生成传输加密密钥轮换辅助结果。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否演练执行
    :param next_kid: 轮换后的新密钥版本标识
    :param key_size: 新密钥的 RSA 长度
    :return: None
    """
    _CRYPTO_COMMAND_CONTROLLER.rotate(
        env,
        output,
        allow_prod,
        yes,
        dry_run,
        next_kid=next_kid,
        key_size=key_size,
    )


@app.command('export-public', help='查看当前运行环境的公钥信息')
def export_public(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
) -> None:
    """
    导出当前运行环境的公钥信息。

    :param env: 当前命令运行环境
    :param output: 输出格式
    :return: None
    """
    _CRYPTO_COMMAND_CONTROLLER.export_public(env, output)
