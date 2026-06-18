import asyncio
from pathlib import Path
from typing import cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.support import (
    PluginDependencyInstallPayloadBuilder,
    PluginNpmPackageJsonSynchronizer,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)
from plugins.core.validation.dependencies import (
    DependencyCheckResult,
    PluginDependencyInstallPlanner,
)

from .context import PluginRuntimeContextService
from .dependency_container import PluginRuntimeDependencies
from .responses import PluginDependencyInstallResponse, PluginRuntimeBlockedPayloadDict


class PluginDependencyUseCase:
    """
    插件 Python/npm 依赖检查和安装 use case。
    """

    def __init__(self, dependencies: PluginRuntimeDependencies, context: PluginRuntimeContextService) -> None:
        """
        初始化插件依赖 use case。

        :param dependencies: 插件运行时依赖容器
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.context = context

    def _get_discovered_plugin(self, plugin_id: str) -> DiscoveredPlugin | None:
        """
        根据插件 ID 获取已发现插件。

        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin(plugin_id)

    def _build_operation_blocked_payload(
        self,
        discovered_plugin: DiscoveredPlugin,
        operation: str,
        *,
        dry_run: bool | None = None,
    ) -> PluginRuntimeBlockedPayloadDict | None:
        """
        构建运行模式阻断负载。

        :param discovered_plugin: 已发现插件
        :param operation: 操作类型
        :param dry_run: 是否预演
        :return: 阻断负载，不阻断时返回 None
        """
        return cast(
            'PluginRuntimeBlockedPayloadDict | None',
            self.context.build_operation_blocked_payload(discovered_plugin, operation, dry_run=dry_run),
        )

    def _with_plugin_capability(
        self,
        payload: dict[str, object],
        discovered_plugin: DiscoveredPlugin | None,
    ) -> dict[str, object]:
        """
        为运行时响应负载附加插件操作能力。

        :param payload: 运行时响应负载
        :param discovered_plugin: 已发现插件
        :return: 附加能力后的响应负载
        """
        return cast('dict[str, object]', self.context.with_plugin_capability(payload, discovered_plugin))

    def install_plugin_dependencies(self, plugin_id: str, *, dry_run: bool = False) -> PluginDependencyInstallResponse:
        """
        安装插件依赖。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件依赖安装负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id, dry_run=dry_run)
            blocked_payload = self._build_operation_blocked_payload(
                discovered_plugin,
                'dependency_install',
                dry_run=dry_run,
            )
            if blocked_payload:
                return blocked_payload

            dependency_result = self.dependencies.dependency_checker.check_manifest(discovered_plugin.manifest)
            return self.install_plugin_dependencies_from_result(
                plugin_id,
                dependency_result,
                dry_run=dry_run,
                discovered_plugin=discovered_plugin,
            )
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('安装插件依赖失败', exc)

    def install_plugin_dependencies_from_result(
        self,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        *,
        dry_run: bool = False,
        discovered_plugin: DiscoveredPlugin | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        根据既有依赖检查结果生成计划并执行依赖安装。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param dry_run: 是否仅预演
        :param discovered_plugin: 已发现插件，传入后避免重复扫描插件目录
        :return: 插件依赖安装负载
        """
        discovered_plugin = discovered_plugin or self._get_discovered_plugin(plugin_id)
        install_plan = PluginDependencyInstallPlanner(
            frontend_root=Path(self.dependencies.runtime_environment.get_backend_dir()).parent
            / 'ruoyi-fastapi-frontend'
        ).build_plan(dependency_result)
        if dry_run:
            payload = PluginDependencyInstallPayloadBuilder.build_dry_run_payload(
                plugin_id,
                dependency_result,
                install_plan.items,
            )
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )
        if not install_plan.has_actions:
            payload = PluginDependencyInstallPayloadBuilder.build_satisfied_payload(
                plugin_id,
                dependency_result,
                install_plan.items,
            )
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )

        install_results = [
            PluginPayloadBuilder.build_dependency_install_result(
                item,
                self.dependencies.command_gateway.run_command(item.command, item.workdir),
            )
            for item in install_plan.items
        ]
        PluginNpmPackageJsonSynchronizer.sync_successful_items(install_plan.items, install_results)
        payload = PluginDependencyInstallPayloadBuilder.build_execution_payload(
            plugin_id,
            dependency_result,
            install_plan.items,
            install_results,
        )
        return cast(
            'PluginDependencyInstallResponse',
            self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
        )

    async def install_plugin_dependencies_from_result_async(
        self,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        *,
        dry_run: bool = False,
        discovered_plugin: DiscoveredPlugin | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        根据既有依赖检查结果异步生成计划并执行依赖安装。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param dry_run: 是否仅预演
        :param discovered_plugin: 已发现插件，传入后避免重复扫描插件目录
        :return: 插件依赖安装负载
        """
        discovered_plugin = discovered_plugin or self._get_discovered_plugin(plugin_id)
        install_plan = PluginDependencyInstallPlanner(
            frontend_root=Path(self.dependencies.runtime_environment.get_backend_dir()).parent
            / 'ruoyi-fastapi-frontend'
        ).build_plan(dependency_result)
        if dry_run:
            payload = PluginDependencyInstallPayloadBuilder.build_dry_run_payload(
                plugin_id,
                dependency_result,
                install_plan.items,
            )
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )
        if not install_plan.has_actions:
            payload = PluginDependencyInstallPayloadBuilder.build_satisfied_payload(
                plugin_id,
                dependency_result,
                install_plan.items,
            )
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )

        install_results = [
            PluginPayloadBuilder.build_dependency_install_result(
                item,
                await asyncio.to_thread(self.dependencies.command_gateway.run_command, item.command, item.workdir),
            )
            for item in install_plan.items
        ]
        PluginNpmPackageJsonSynchronizer.sync_successful_items(install_plan.items, install_results)
        payload = PluginDependencyInstallPayloadBuilder.build_execution_payload(
            plugin_id,
            dependency_result,
            install_plan.items,
            install_results,
        )
        return cast(
            'PluginDependencyInstallResponse',
            self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
        )
