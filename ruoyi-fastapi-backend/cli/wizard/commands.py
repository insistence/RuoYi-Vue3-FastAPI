from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module

import typer

from cli.context import OutputOption

WizardCommandRegistrar = Callable[[typer.Typer, 'WizardCommandRegistration'], None]


@dataclass(frozen=True)
class WizardCommandRegistration:
    """
    wizard 子命令注册元数据。

    :param name: 子命令名称
    :param help_text: 子命令帮助文案
    :param registrar: 对应的注册器函数
    """

    name: str
    help_text: str


class WizardFlowLoader:
    """
    wizard flow 惰性加载器。

    该对象负责在命令真正执行时导入对应 flow，
    避免 `wizard` 入口在模块导入阶段提前拉起全部向导依赖。
    """

    def load_runner(self, module_name: str, function_name: str) -> Callable[..., None]:
        """
        按模块名和函数名加载向导执行入口。

        :param module_name: flow 模块名
        :param function_name: flow 执行函数名
        :return: 可调用的向导执行函数
        """
        flow_module = import_module(module_name)
        return getattr(flow_module, function_name)


@dataclass
class WizardCommandBuilder:
    """
    wizard 子命令构建器。

    :param flow_loader: wizard flow 惰性加载器
    """

    flow_loader: WizardFlowLoader = field(default_factory=WizardFlowLoader)

    def build(self) -> typer.Typer:
        """
        构建 wizard 命令组。

        :return: wizard 子应用
        """
        app = typer.Typer(
            help='交互式向导命令',
            no_args_is_help=True,
            context_settings={'help_option_names': ['-h', '--help']},
        )
        self.register_commands(app)
        return app

    def register_commands(self, app: typer.Typer) -> None:
        """
        向 Typer 子应用注册全部 wizard 子命令。

        :param app: wizard 子应用
        :return: None
        """
        for registration, registrar in self.iter_command_registrars():
            registrar(app, registration)

    def iter_command_registrars(self) -> tuple[tuple[WizardCommandRegistration, WizardCommandRegistrar], ...]:
        """
        返回向导命令注册元数据与显式注册器映射。

        该方法将命令声明与注册函数绑定关系显式化，避免继续依赖
        `registrar_name -> getattr(self, ...)` 的字符串分发。

        :return: 注册元数据与注册器映射列表
        """
        return (
            (
                WizardCommandRegistration('app-run', '通过交互方式启动应用'),
                self._register_app_run_command,
            ),
            (
                WizardCommandRegistration('db-upgrade', '通过交互方式执行数据库升级'),
                self._register_db_upgrade_command,
            ),
            (
                WizardCommandRegistration('cache-clear', '通过交互方式执行缓存清理'),
                self._register_cache_clear_command,
            ),
            (
                WizardCommandRegistration('gen-export', '通过交互方式执行代码导出'),
                self._register_gen_export_command,
            ),
            (
                WizardCommandRegistration('gen-import', '通过交互方式执行物理表导入'),
                self._register_gen_import_command,
            ),
            (
                WizardCommandRegistration('prod-check', '通过交互方式执行生产巡检'),
                self._register_prod_check_command,
            ),
        )

    def _register_app_run_command(self, app: typer.Typer, registration: WizardCommandRegistration) -> None:
        """
        注册 `app-run` 子命令。

        :param app: wizard 子应用
        :param registration: 子命令注册元数据
        :return: None
        """

        @app.command(registration.name, help=registration.help_text)
        def app_run() -> None:
            """
            通过交互方式启动应用。

            :return: None
            """
            self.flow_loader.load_runner('cli.wizard.flows.app_run', 'run_app_run_wizard')()

    def _register_db_upgrade_command(self, app: typer.Typer, registration: WizardCommandRegistration) -> None:
        """
        注册 `db-upgrade` 子命令。

        :param app: wizard 子应用
        :param registration: 子命令注册元数据
        :return: None
        """

        @app.command(registration.name, help=registration.help_text)
        def db_upgrade(
            output: OutputOption = 'text',
            default_env: str = typer.Option('dev', '--default-env', help='向导默认环境'),
            default_revision: str = typer.Option('head', '--default-revision', help='向导默认目标 revision'),
            default_dry_run: bool = typer.Option(
                True, '--default-dry-run/--no-default-dry-run', help='向导默认 dry-run 选项'
            ),
        ) -> None:
            """
            通过交互方式执行数据库升级。

            :param output: 输出格式
            :param default_env: 向导默认环境
            :param default_revision: 向导默认目标 revision
            :param default_dry_run: 向导默认 dry-run 选项
            :return: None
            """
            self.flow_loader.load_runner('cli.wizard.flows.db_upgrade', 'run_db_upgrade_wizard')(
                output,
                default_env=default_env,
                default_revision=default_revision,
                default_dry_run=default_dry_run,
            )

    def _register_cache_clear_command(self, app: typer.Typer, registration: WizardCommandRegistration) -> None:
        """
        注册 `cache-clear` 子命令。

        :param app: wizard 子应用
        :param registration: 子命令注册元数据
        :return: None
        """

        @app.command(registration.name, help=registration.help_text)
        def cache_clear(
            output: OutputOption = 'text',
            default_env: str = typer.Option('dev', '--default-env', help='向导默认环境'),
            default_mode: str = typer.Option('cache-name', '--default-mode', help='向导默认清理模式'),
            default_cache_name: str = typer.Option('', '--default-cache-name', help='向导默认缓存名称前缀'),
            default_cache_key: str = typer.Option('', '--default-cache-key', help='向导默认缓存键关键字'),
            default_dry_run: bool = typer.Option(
                True, '--default-dry-run/--no-default-dry-run', help='向导默认 dry-run 选项'
            ),
        ) -> None:
            """
            通过交互方式执行缓存清理。

            :param output: 输出格式
            :param default_env: 向导默认环境
            :param default_mode: 向导默认清理模式
            :param default_cache_name: 向导默认缓存名称前缀
            :param default_cache_key: 向导默认缓存键关键字
            :param default_dry_run: 向导默认 dry-run 选项
            :return: None
            """
            self.flow_loader.load_runner('cli.wizard.flows.cache_clear', 'run_cache_clear_wizard')(
                output,
                default_env=default_env,
                default_mode=default_mode,
                default_cache_name=default_cache_name,
                default_cache_key=default_cache_key,
                default_dry_run=default_dry_run,
            )

    def _register_gen_export_command(self, app: typer.Typer, registration: WizardCommandRegistration) -> None:
        """
        注册 `gen-export` 子命令。

        :param app: wizard 子应用
        :param registration: 子命令注册元数据
        :return: None
        """

        @app.command(registration.name, help=registration.help_text)
        def gen_export(
            output: OutputOption = 'text',
            default_env: str = typer.Option('dev', '--default-env', help='向导默认环境'),
            default_table_names: str = typer.Option('', '--default-table-names', help='向导默认业务表名称列表'),
            default_mode: str = typer.Option('zip', '--default-mode', help='向导默认导出模式'),
            default_output_file: str = typer.Option('', '--default-output-file', help='向导默认导出目标文件路径'),
            default_dry_run: bool = typer.Option(
                True, '--default-dry-run/--no-default-dry-run', help='向导默认 dry-run 选项'
            ),
        ) -> None:
            """
            通过交互方式执行代码导出。

            :param output: 输出格式
            :param default_env: 向导默认环境
            :param default_table_names: 向导默认业务表名称列表
            :param default_mode: 向导默认导出模式
            :param default_output_file: 向导默认导出目标文件路径
            :param default_dry_run: 向导默认 dry-run 选项
            :return: None
            """
            self.flow_loader.load_runner('cli.wizard.flows.gen_export', 'run_gen_export_wizard')(
                output,
                default_env=default_env,
                default_table_names=default_table_names,
                default_mode=default_mode,
                default_output_file=default_output_file,
                default_dry_run=default_dry_run,
            )

    def _register_gen_import_command(self, app: typer.Typer, registration: WizardCommandRegistration) -> None:
        """
        注册 `gen-import` 子命令。

        :param app: wizard 子应用
        :param registration: 子命令注册元数据
        :return: None
        """

        @app.command(registration.name, help=registration.help_text)
        def gen_import(
            output: OutputOption = 'text',
            default_env: str = typer.Option('dev', '--default-env', help='向导默认环境'),
            default_table_names: str = typer.Option('', '--default-table-names', help='向导默认物理表名称列表'),
            default_dry_run: bool = typer.Option(
                True, '--default-dry-run/--no-default-dry-run', help='向导默认 dry-run 选项'
            ),
        ) -> None:
            """
            通过交互方式执行物理表导入。

            :param output: 输出格式
            :param default_env: 向导默认环境
            :param default_table_names: 向导默认物理表名称列表
            :param default_dry_run: 向导默认 dry-run 选项
            :return: None
            """
            self.flow_loader.load_runner('cli.wizard.flows.gen_import', 'run_gen_import_wizard')(
                output,
                default_env=default_env,
                default_table_names=default_table_names,
                default_dry_run=default_dry_run,
            )

    def _register_prod_check_command(self, app: typer.Typer, registration: WizardCommandRegistration) -> None:
        """
        注册 `prod-check` 子命令。

        :param app: wizard 子应用
        :param registration: 子命令注册元数据
        :return: None
        """

        @app.command(registration.name, help=registration.help_text)
        def prod_check(
            output: OutputOption = 'text',
            default_env: str = typer.Option('prod', '--default-env', help='向导默认环境'),
            default_include_config: bool = typer.Option(
                True,
                '--default-include-config/--no-default-include-config',
                help='向导默认是否附带配置快照',
            ),
        ) -> None:
            """
            通过交互方式执行生产巡检。

            :param output: 输出格式
            :param default_env: 向导默认环境
            :param default_include_config: 向导默认是否附带配置快照
            :return: None
            """
            self.flow_loader.load_runner('cli.wizard.flows.prod_check', 'run_prod_check_wizard')(
                output,
                default_env=default_env,
                default_include_config=default_include_config,
            )


WIZARD_COMMAND_BUILDER = WizardCommandBuilder()
