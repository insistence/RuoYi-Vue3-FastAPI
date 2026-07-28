from collections.abc import Callable
from typing import Annotated, Any, Literal

import typer

from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption

PluginBatchOperation = Literal['install', 'enable', 'upgrade']
PluginMigrationStatus = Literal['running', 'success', 'failed', 'unknown']


def register_lifecycle_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册插件生命周期命令。

    :param app: Typer 命令组
    :param get_controller: 插件命令控制器工厂
    :return: None
    """

    @app.command('batch', help='按拓扑顺序批量执行插件操作')
    def batch_command(
        operation: Annotated[PluginBatchOperation, typer.Argument(help='批量操作类型：install、enable 或 upgrade')],
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
        get_controller().batch_plugins(
            operation,
            plugin_ids or [],
            env,
            output,
            allow_prod=allow_prod,
            yes=yes,
            dry_run=dry_run,
            continue_on_error=continue_on_error,
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
        get_controller().install_plugin(
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
        get_controller().upgrade_plugin(
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
        get_controller().set_plugin_enabled(
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
        get_controller().set_plugin_enabled(
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
        get_controller().uninstall_plugin(
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
        get_controller().purge_plugin(
            plugin_id,
            env,
            output,
            allow_prod=allow_prod,
            yes=yes,
            dry_run=dry_run,
        )

    @app.command('migration-list', help='查看插件 migration 历史')
    def migration_list_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        status: Annotated[PluginMigrationStatus | None, typer.Option('--status', help='按状态过滤')] = None,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        查看插件 migration 历史。

        :param plugin_id: 插件ID
        :param status: 执行状态
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().list_plugin_migrations(plugin_id, status, env, output)

    @app.command('mark-success', help='人工标记插件 migration 为成功')
    def mark_success_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        migration_path: Annotated[str, typer.Argument(help='migration 相对路径')],
        note: Annotated[str, typer.Option('--note', help='人工恢复备注')] = '',
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        人工标记插件 migration 为成功。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param note: 人工恢复备注
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        get_controller().mark_plugin_migration_success(
            plugin_id,
            migration_path,
            env,
            output,
            note=note,
            allow_prod=allow_prod,
            yes=yes,
        )

    @app.command('mark-failed', help='人工标记插件 migration 为失败')
    def mark_failed_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        migration_path: Annotated[str, typer.Argument(help='migration 相对路径')],
        note: Annotated[str, typer.Option('--note', help='人工恢复备注')] = '',
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        人工标记插件 migration 为失败。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param note: 人工恢复备注
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        get_controller().mark_plugin_migration_failed(
            plugin_id,
            migration_path,
            env,
            output,
            note=note,
            allow_prod=allow_prod,
            yes=yes,
        )
