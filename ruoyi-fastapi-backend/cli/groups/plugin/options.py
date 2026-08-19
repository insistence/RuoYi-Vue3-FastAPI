from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PluginCreateCommandOptions:
    """
    插件创建命令选项。

    :param backend_only: 是否只创建后端插件模板
    :param frontend_only: 是否只创建前端插件模板
    :param template: 插件模板名称
    :param frontend_version: 前端 Vue 版本，支持 auto、vue2、vue3
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
    frontend_version: Literal['auto', 'vue2', 'vue3'] = 'auto'
    no_migration: bool = False
    no_seed: bool = False
    no_job: bool = False
    no_config: bool = False
    no_test: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class PluginDependencyInstallCommandOptions:
    """
    插件依赖安装命令选项。

    :param allow_prod: 是否允许生产环境危险命令
    :param yes: 是否跳过确认
    :param dry_run: 是否仅预演
    :param policy_mode: 临时覆盖策略模式
    :param allow_unlisted: 是否允许未命中 allowlist 的依赖仅告警
    :param lockfile: 锁文件路径
    :param allowlist: 依赖允许列表路径
    :param offline_dir: 离线制品目录
    :param require_lockfile: 是否要求锁文件
    """

    allow_prod: bool = False
    yes: bool = False
    dry_run: bool = False
    policy_mode: str | None = None
    allow_unlisted: bool = False
    lockfile: str = ''
    allowlist: str = ''
    offline_dir: str = ''
    require_lockfile: bool | None = None


@dataclass(frozen=True)
class PluginDependencyLockCommandOptions:
    """
    插件依赖锁文件模板命令选项。

    :param output_path: 输出锁文件路径
    :param offline_dir: 离线制品目录
    :param dry_run: 是否仅预演
    :param overwrite: 是否覆盖已有锁文件
    """

    output_path: str = ''
    offline_dir: str = ''
    dry_run: bool = False
    overwrite: bool = False


@dataclass(frozen=True)
class PluginDependencyAllowlistExampleCommandOptions:
    """
    插件依赖允许列表示例命令选项。

    :param output_path: 输出允许列表路径
    :param dry_run: 是否仅预演
    :param overwrite: 是否覆盖已有文件
    """

    output_path: str = ''
    dry_run: bool = False
    overwrite: bool = False
