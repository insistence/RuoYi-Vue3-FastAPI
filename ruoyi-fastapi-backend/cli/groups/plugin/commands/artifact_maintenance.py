from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from cli.context import AllowProdOption, EnvOption, OutputOption, YesOption

KeepLastOption = Annotated[int, typer.Option('--keep-last', min=0, help='每个插件保留最近导入的制品数')]
MinAgeOption = Annotated[int, typer.Option('--min-age-days', min=0, help='最短保留天数')]
MaintenanceOption = Annotated[bool, typer.Option('--maintenance', help='确认全部宿主进程已停止')]


def register_artifact_maintenance_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册制品只读检查、清理预演、签名轮换及中断恢复命令。

    :param app: 制品命令组
    :param get_controller: 延迟获取命令控制器的工厂
    :return: None
    """

    @app.command('inspect', help='核对存储和索引，列出保护引用、孤儿对象与无效制品')
    def inspect_artifacts(
        keep_last: KeepLastOption = 2,
        min_age_days: MinAgeOption = 7,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        只读检查制品存储。

        :param keep_last: 每个插件保留的最近导入数量
        :param min_age_days: 最短保留天数
        :param env: 当前命令环境
        :param output: 输出格式
        :return: None
        """
        get_controller().maintain_artifacts(
            'inspect',
            env,
            output,
            options={
                'keep_last': keep_last,
                'min_age_days': min_age_days,
            },
        )

    @app.command('prune', help='默认只预演；核对计划后传入 --execute 才执行清理')
    def prune_artifacts(
        keep_last: KeepLastOption = 2,
        min_age_days: MinAgeOption = 7,
        expected_plan: Annotated[str | None, typer.Option('--expected-plan', help='已核对的预演计划 SHA256')] = None,
        execute: Annotated[bool, typer.Option('--execute', help='执行清理，默认不写入')] = False,
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        生成或执行已核对的制品清理计划。

        :param keep_last: 每个插件保留的最近导入数量
        :param min_age_days: 最短保留天数
        :param expected_plan: 已核对的预演计划摘要
        :param execute: 是否真正执行文件和索引清理
        :param maintenance: 是否确认全部宿主进程已停止
        :param env: 当前命令环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境变更
        :param yes: 是否跳过交互确认
        :return: None
        """
        get_controller().maintain_artifacts(
            'prune',
            env,
            output,
            options={
                'keep_last': keep_last,
                'min_age_days': min_age_days,
                'expected_plan': expected_plan,
                'maintenance': maintenance,
            },
            allow_prod=allow_prod,
            yes=yes,
            dry_run=not execute,
        )

    @app.command('rotate-signature', help='用新签名 rpk 轮换同一摘要制品的签名，不更改插件字节')
    def rotate_signature(
        archive: Annotated[Path, typer.Argument(help='使用新可信密钥签名、内容完全一致的 rpk')],
        expected_key_id: Annotated[str, typer.Option('--expected-key-id', help='当前索引中的原签名密钥标识')],
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        维护轮换同一制品的签名密钥。

        :param archive: 新密钥签名的同内容制品
        :param expected_key_id: 原签名密钥标识
        :param maintenance: 是否确认全部宿主进程已停止
        :param env: 当前命令环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境变更
        :param yes: 是否跳过交互确认
        :return: None
        """
        get_controller().maintain_artifacts(
            'rotate-signature',
            env,
            output,
            options={
                'archive': archive,
                'expected_key_id': expected_key_id,
                'maintenance': maintenance,
            },
            allow_prod=allow_prod,
            yes=yes,
        )

    @app.command('reconcile', help='按已提交索引恢复中断的清理或签名轮换')
    def reconcile_artifacts(
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        在停机窗口恢复中断维护。

        :param maintenance: 是否确认全部宿主进程已停止
        :param env: 当前命令环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境变更
        :param yes: 是否跳过交互确认
        :return: None
        """
        get_controller().maintain_artifacts(
            'reconcile',
            env,
            output,
            options={
                'maintenance': maintenance,
            },
            allow_prod=allow_prod,
            yes=yes,
        )
