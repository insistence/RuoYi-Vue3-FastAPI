from typing import Annotated

import typer

from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

from .controller import OidcCommandController

app = typer.Typer(
    help='OIDC 认证中心部署与运维命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
key_app = typer.Typer(
    help='OIDC 签名密钥命令',
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']},
)
app.add_typer(key_app, name='key')
_OIDC_COMMAND_CONTROLLER = OidcCommandController()


@key_app.command('bootstrap', help='幂等创建并激活首把 OIDC 签名密钥')
def bootstrap_key(
    env: EnvOption = 'dev',
    output: OutputOption = 'text',
    allow_prod: AllowProdOption = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
    kid: Annotated[str, typer.Option('--kid', help='签名密钥公开编号')] = 'bootstrap-primary',
    actor: Annotated[str, typer.Option('--actor', help='写入审计记录的部署操作者')] = 'system:deployment',
) -> None:
    """
    初始化首把 OIDC 签名密钥

    :param env: 当前命令运行环境
    :param output: 输出格式
    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否只执行预演
    :param kid: 首把签名密钥标识
    :param actor: 部署操作人标识
    :return: None
    """
    _OIDC_COMMAND_CONTROLLER.bootstrap_key(
        env,
        output,
        allow_prod,
        yes,
        dry_run,
        kid=kid,
        actor=actor,
    )
