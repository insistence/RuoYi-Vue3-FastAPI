from dataclasses import dataclass
from importlib import import_module
from types import ModuleType

import typer

from cli.context import EnvOption
from cli.core import DEFAULT_CORE_SERVICES, CliContextFactory, CliExecutionService
from cli.exit_codes import DEPENDENCY_ERROR
from cli.output import CommandResult
from cli.tui.copy import TUI_COPY


@dataclass(frozen=True)
class TuiDependencyResultFactory:
    """
    TUI 依赖结果构建器。

    该对象负责统一构建 Textual/Rich 缺失时的降级结果，
    避免命令注册层继续直接拼接错误负载。
    """

    def build_missing_dependency_result(self) -> CommandResult:
        """
        构建 TUI 可选依赖缺失时的提示结果。

        :return: 命令结果对象
        """
        return CommandResult(
            data={
                'ok': False,
                'message': TUI_COPY.build_missing_dependency_message(),
                'hint': TUI_COPY.build_missing_dependency_hint(),
            },
            exit_code=DEPENDENCY_ERROR,
        )


@dataclass(frozen=True)
class TuiAppModuleLoader:
    """
    TUI 应用模块加载器。

    该对象负责识别缺失的可选依赖，并在命令执行阶段按需导入
    `cli.tui.app` 模块。
    """

    def is_missing_dependency_error(self, exc: ModuleNotFoundError) -> bool:
        """
        判断模块导入异常是否由 TUI 可选依赖缺失触发。

        :param exc: 模块导入异常
        :return: 是否为 TUI 依赖缺失
        """
        missing_module_name = (exc.name or '').split('.', 1)[0]
        return missing_module_name in {'textual', 'rich'}

    def load(self) -> ModuleType:
        """
        惰性导入 TUI 应用模块。

        :return: `cli.tui.app` 模块对象
        """
        return import_module('cli.tui.app')


@dataclass(frozen=True)
class TuiCommandRegistration:
    """
    TUI 命令注册器。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param dependency_result_factory: TUI 缺失依赖结果构建器
    :param module_loader: TUI 应用模块加载器
    """

    context_factory: CliContextFactory
    execution_service: CliExecutionService
    dependency_result_factory: TuiDependencyResultFactory
    module_loader: TuiAppModuleLoader

    def handle_tui_command(self, env: str) -> None:
        """
        执行 `ruoyi tui` 命令。

        :param env: 当前命令运行环境
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, 'text')
        try:
            tui_app_module = self.module_loader.load()
        except ModuleNotFoundError as exc:
            if self.module_loader.is_missing_dependency_error(exc):
                self.execution_service.complete_result(
                    ctx,
                    self.dependency_result_factory.build_missing_dependency_result(),
                )
                return
            raise
        tui_app_module.TUI_APP_RUNNER.run(env)

    def build(self) -> typer.Typer:
        """
        构建 `tui` 子应用。

        :return: `tui` 子应用
        """
        app = typer.Typer(
            help=TUI_COPY.build_tui_command_help(),
            no_args_is_help=False,
            invoke_without_command=True,
            context_settings={'help_option_names': ['-h', '--help']},
        )

        @app.callback()
        def tui(
            env: EnvOption = 'dev',
        ) -> None:
            """
            进入只读巡检工作台。

            :param env: 当前命令运行环境
            :return: None
            """
            self.handle_tui_command(env)

        return app

    def register(self, root_cli: typer.Typer) -> None:
        """
        向根 Typer 应用注册 `tui` 命令。

        :param root_cli: 根 Typer 应用
        :return: None
        """
        root_cli.add_typer(self.build(), name='tui')


TUI_COMMAND_REGISTRATION = TuiCommandRegistration(
    context_factory=DEFAULT_CORE_SERVICES.context_factory,
    execution_service=DEFAULT_CORE_SERVICES.execution_service,
    dependency_result_factory=TuiDependencyResultFactory(),
    module_loader=TuiAppModuleLoader(),
)
