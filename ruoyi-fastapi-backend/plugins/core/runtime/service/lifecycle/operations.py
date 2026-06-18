from collections.abc import Mapping
from typing import Protocol

from ..context import PluginRuntimeContextService
from ..dependency_container import PluginRuntimeDependencies
from ..responses import PluginDependencyInstallResponse


class PluginLifecycleRuntimeOperations(Protocol):
    """
    生命周期工作流所需的运行时协作能力。
    """

    dependencies: PluginRuntimeDependencies
    context: PluginRuntimeContextService

    async def record_plugin_operation_log(
        self,
        payload: Mapping[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """
        记录插件操作审计日志。

        :param payload: 插件操作结果负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续
        :return: None
        """

    async def record_plugin_failure_state(self, payload: Mapping[str, object], default_message: str) -> None:
        """
        记录插件操作失败状态。

        :param payload: 插件操作返回负载
        :param default_message: 缺省失败信息
        :return: None
        """

    def install_plugin_dependencies_from_result(
        self,
        plugin_id: str,
        dependency_result: object,
        *,
        dry_run: bool = False,
        discovered_plugin: object | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        根据既有依赖检查结果生成计划并执行依赖安装。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param dry_run: 是否仅预演
        :param discovered_plugin: 已发现插件
        :return: 插件依赖安装负载
        """

    async def install_plugin_dependencies_from_result_async(
        self,
        plugin_id: str,
        dependency_result: object,
        *,
        dry_run: bool = False,
        discovered_plugin: object | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        根据既有依赖检查结果异步生成计划并执行依赖安装。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param dry_run: 是否仅预演
        :param discovered_plugin: 已发现插件
        :return: 插件依赖安装负载
        """

    def refresh_dependency_checker(self) -> None:
        """
        刷新插件 Python/npm 依赖检查器。

        :return: None
        """
