import sys
from dataclasses import dataclass

from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliApplicationBuilder,
    CompletionDispatcher,
    ProjectRuntimeLocator,
)


@dataclass(frozen=True)
class CliImportArgvScope:
    """
    CLI 导入期参数作用域。

    该对象负责在根应用构建阶段暂时切换 `sys.argv`，只保留导入期
    需要的最小参数集，避免该过程继续以内联 `try/finally` 形式散落
    在入口运行器中。

    :param project_runtime_locator: CLI 项目运行时定位器
    """

    project_runtime_locator: ProjectRuntimeLocator

    def run(self, callback: object) -> object:
        """
        在导入期参数作用域内执行回调。

        :param callback: 待执行回调
        :return: 回调执行结果
        """
        original_argv = list(sys.argv)
        try:
            sys.argv = self.project_runtime_locator.extract_import_argv(original_argv)
            return callback()
        finally:
            sys.argv = original_argv


@dataclass(frozen=True)
class CliMainRunner:
    """
    CLI 根入口运行器。

    该运行器负责串联项目目录定位、导入期参数裁剪、根应用构建、
    completion 分发与 Typer 应用启动，避免 `main.py` 继续停留在
    模块级散乱编排状态。

    :param project_runtime_locator: CLI 项目运行时定位器
    :param completion_dispatcher: shell completion 分发器
    :param application_builder: 根应用构建器
    """

    project_runtime_locator: ProjectRuntimeLocator
    completion_dispatcher: CompletionDispatcher
    application_builder: CliApplicationBuilder
    import_argv_scope: CliImportArgvScope

    def build_cli(self) -> object:
        """
        构建 CLI 根应用，并在导入期仅保留最小化参数集。

        :return: Typer 根应用
        """
        self.project_runtime_locator.ensure_backend_dir_on_sys_path()
        return self.import_argv_scope.run(self.application_builder.build)

    def run(self) -> None:
        """
        执行 Typer CLI 根应用。

        :return: None
        """
        cli = self.build_cli()
        self.completion_dispatcher.dispatch(cli)
        cli(prog_name='ruoyi')


CLI_APPLICATION_BUILDER = CliApplicationBuilder(output_renderer=DEFAULT_CORE_SERVICES.output_renderer)
PROJECT_RUNTIME_LOCATOR = ProjectRuntimeLocator()
CLI_MAIN_RUNNER = CliMainRunner(
    project_runtime_locator=PROJECT_RUNTIME_LOCATOR,
    completion_dispatcher=CompletionDispatcher(),
    application_builder=CLI_APPLICATION_BUILDER,
    import_argv_scope=CliImportArgvScope(project_runtime_locator=PROJECT_RUNTIME_LOCATOR),
)


def main() -> None:
    """
    执行 CLI 根入口运行器。

    :return: None
    """
    CLI_MAIN_RUNNER.run()


if __name__ == '__main__':
    main()
