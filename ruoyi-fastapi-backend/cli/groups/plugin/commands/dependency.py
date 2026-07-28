from collections.abc import Callable
from typing import Annotated, Any, Literal

import typer

from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption
from cli.groups.plugin.options import (
    PluginDependencyAllowlistExampleCommandOptions,
    PluginDependencyInstallCommandOptions,
    PluginDependencyLockCommandOptions,
)

PluginPrecheckOperation = Literal['install', 'enable', 'upgrade', 'uninstall', 'purge']
PluginPlanOperation = Literal['install', 'enable', 'upgrade']


def register_dependency_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册插件依赖、预检和计划命令。

    :param app: Typer 命令组
    :param get_controller: 插件命令控制器工厂
    :return: None
    """

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
        get_controller().check_plugin_dependencies(plugin_id, env, output)

    @app.command('precheck', help='执行插件操作预检')
    def precheck_command(
        operation: Annotated[
            PluginPrecheckOperation,
            typer.Argument(help='预检操作类型：install、enable、upgrade、uninstall 或 purge'),
        ],
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
        get_controller().precheck_plugin(operation, plugin_id, env, output)

    @app.command('plan', help='生成插件批量操作拓扑计划')
    def plan_command(
        operation: Annotated[PluginPlanOperation, typer.Argument(help='计划操作类型：install、enable 或 upgrade')],
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
        get_controller().plan_plugins(operation, plugin_ids or [], env, output)

    @app.command('install-deps', help='安装插件依赖')
    def install_deps_command(  # noqa: PLR0913
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        *,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
        dry_run: DryRunOption = False,
        policy_mode: Annotated[
            Literal['disabled', 'plan_only', 'explicit', 'locked', 'offline'] | None,
            typer.Option('--policy-mode', help='临时覆盖插件依赖安装策略模式'),
        ] = None,
        allow_unlisted: Annotated[
            bool,
            typer.Option('--allow-unlisted', help='dev 环境允许未命中 allowlist 的依赖仅告警'),
        ] = False,
        lockfile: Annotated[str, typer.Option('--lockfile', help='指定插件依赖锁文件路径')] = '',
        offline_dir: Annotated[str, typer.Option('--offline-dir', help='指定插件离线依赖制品目录')] = '',
        require_lockfile: Annotated[
            bool | None,
            typer.Option('--require-lockfile/--no-require-lockfile', help='临时切换锁文件要求'),
        ] = None,
    ) -> None:
        """
        安装插件依赖。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :param policy_mode: 临时覆盖策略模式
        :param allow_unlisted: dev 环境是否允许未命中 allowlist 的依赖仅告警
        :param lockfile: 锁文件路径
        :param offline_dir: 离线制品目录
        :param require_lockfile: 是否要求锁文件
        :return: None
        """
        get_controller().install_plugin_dependencies(
            plugin_id,
            env,
            output,
            options=PluginDependencyInstallCommandOptions(
                allow_prod=allow_prod,
                yes=yes,
                dry_run=dry_run,
                policy_mode=policy_mode,
                allow_unlisted=allow_unlisted,
                lockfile=lockfile,
                offline_dir=offline_dir,
                require_lockfile=require_lockfile,
            ),
        )

    @app.command('lock-deps', help='生成插件依赖锁文件模板')
    def lock_deps_command(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        dry_run: DryRunOption = False,
        output_path: Annotated[
            str,
            typer.Option('--output-path', help='输出锁文件路径，默认写入插件目录 plugin.lock.yaml'),
        ] = '',
        offline_dir: Annotated[
            str, typer.Option('--offline-dir', help='从本地离线制品目录反填版本和 hash/integrity')
        ] = '',
        overwrite: Annotated[bool, typer.Option('--overwrite', help='覆盖已有锁文件')] = False,
    ) -> None:
        """
        生成插件依赖锁文件模板。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param dry_run: 是否仅预演
        :param output_path: 输出锁文件路径
        :param offline_dir: 离线制品目录
        :param overwrite: 是否覆盖已有锁文件
        :return: None
        """
        get_controller().lock_plugin_dependencies(
            plugin_id,
            env,
            output,
            options=PluginDependencyLockCommandOptions(
                output_path=output_path,
                offline_dir=offline_dir,
                dry_run=dry_run,
                overwrite=overwrite,
            ),
        )

    @app.command('allowlist-example', help='生成插件依赖允许列表示例')
    def allowlist_example_command(
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        dry_run: DryRunOption = False,
        output_path: Annotated[
            str,
            typer.Option('--output-path', help='输出允许列表路径，默认写入 config/plugin_dependency_allowlist.yaml'),
        ] = '',
        overwrite: Annotated[bool, typer.Option('--overwrite', help='覆盖已有允许列表文件')] = False,
    ) -> None:
        """
        生成插件依赖允许列表示例。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param dry_run: 是否仅预演
        :param output_path: 输出允许列表路径
        :param overwrite: 是否覆盖已有允许列表文件
        :return: None
        """
        get_controller().generate_plugin_dependency_allowlist_example(
            env,
            output,
            options=PluginDependencyAllowlistExampleCommandOptions(
                output_path=output_path,
                dry_run=dry_run,
                overwrite=overwrite,
            ),
        )
