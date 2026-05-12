import importlib


def test_cli_main_runner_reuses_single_project_runtime_locator() -> None:
    """
    校验 CLI 根运行器与导入期参数作用域共享同一个项目定位器实例。

    :return: None
    """
    cli_main = importlib.import_module('cli.main')

    assert cli_main.CLI_MAIN_RUNNER.project_runtime_locator is cli_main.PROJECT_RUNTIME_LOCATOR
    assert cli_main.CLI_MAIN_RUNNER.import_argv_scope.project_runtime_locator is cli_main.PROJECT_RUNTIME_LOCATOR
