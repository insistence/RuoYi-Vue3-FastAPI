from pathlib import Path
from typing import Any

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


class PluginDependencyOperationMixin:
    """
    插件 Python/npm 依赖检查和安装操作。
    """

    def install_plugin_dependencies(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
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

            dependency_result = self.dependency_checker.check_manifest(discovered_plugin.manifest)
            return self._install_plugin_dependencies_from_result(
                plugin_id,
                dependency_result,
                dry_run=dry_run,
                discovered_plugin=discovered_plugin,
            )
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('安装插件依赖失败', exc)

    def _install_plugin_dependencies_from_result(
        self,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        *,
        dry_run: bool = False,
        discovered_plugin: DiscoveredPlugin | None = None,
    ) -> dict[str, Any]:
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
            frontend_root=Path(self.runtime_environment.get_backend_dir()).parent / 'ruoyi-fastapi-frontend'
        ).build_plan(dependency_result)
        if dry_run:
            payload = PluginDependencyInstallPayloadBuilder.build_dry_run_payload(
                plugin_id,
                dependency_result,
                install_plan.items,
            )
            return self._with_plugin_capability(payload, discovered_plugin)
        if not install_plan.has_actions:
            payload = PluginDependencyInstallPayloadBuilder.build_satisfied_payload(
                plugin_id,
                dependency_result,
                install_plan.items,
            )
            return self._with_plugin_capability(payload, discovered_plugin)

        install_results = [
            PluginPayloadBuilder.build_dependency_install_result(
                item,
                self.infrastructure_gateway.run_command(item.command, item.workdir),
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
        return self._with_plugin_capability(payload, discovered_plugin)
