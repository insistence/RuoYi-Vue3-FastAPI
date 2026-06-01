from dataclasses import dataclass


@dataclass(frozen=True)
class PluginCreateCommandOptions:
    """
    插件创建命令选项。

    :param backend_only: 是否只创建后端插件模板
    :param frontend_only: 是否只创建前端插件模板
    :param template: 插件模板名称
    :param no_migration: 是否不创建 migration 示例
    :param no_seed: 是否不创建 seed 示例
    :param no_job: 是否不创建定时任务示例
    :param no_config: 是否不创建配置项示例
    :param no_test: 是否不创建测试样例
    :param dry_run: 是否仅预演
    """

    backend_only: bool = False
    frontend_only: bool = False
    template: str = 'full-stack'
    no_migration: bool = False
    no_seed: bool = False
    no_job: bool = False
    no_config: bool = False
    no_test: bool = False
    dry_run: bool = False
