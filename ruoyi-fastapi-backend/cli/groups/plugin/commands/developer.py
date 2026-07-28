from collections.abc import Callable
from typing import Annotated, Any, Literal

import typer

from cli.context import DryRunOption, EnvOption, OutputOption

from ..options import PluginCreateCommandOptions


def register_developer_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册插件开发者命令。

    :param app: Typer 命令组
    :param get_controller: 插件命令控制器工厂
    :return: None
    """

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
        get_controller().test_plugin(
            plugin_id,
            env,
            output,
            keyword=keyword,
            maxfail=maxfail,
            quiet=quiet,
            frontend_build=frontend_build,
        )

    @app.command('create', help='创建插件开发模板')
    def create_command(  # noqa: PLR0913
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        *,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        template: Annotated[
            str,
            typer.Option('--template', help='插件模板：minimal、backend-only、full-stack、scheduled-job、crud-page'),
        ] = 'full-stack',
        frontend_version: Annotated[
            Literal['auto', 'vue2', 'vue3'],
            typer.Option('--frontend-version', help='前端 Vue 版本：auto、vue2、vue3；auto 读取 package.json'),
        ] = 'auto',
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
        :param frontend_version: 前端 Vue 版本
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
        get_controller().create_plugin(
            plugin_id,
            env,
            output,
            PluginCreateCommandOptions(
                backend_only=backend_only,
                frontend_only=frontend_only,
                template=template,
                frontend_version=frontend_version,
                no_migration=no_migration,
                no_seed=no_seed,
                no_job=no_job,
                no_config=no_config,
                no_test=no_test,
                dry_run=dry_run,
            ),
        )
