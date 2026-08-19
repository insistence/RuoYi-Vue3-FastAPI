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
from plugins.core.validation.dependency_policy import (
    DependencyInstallPolicyConfig,
    DependencyInstallPolicyEvaluator,
)

from .context import PluginRuntimeContextService
from .dependency_container import PluginRuntimeDependencies
from .gateway import PluginCommandOutputCallback
from .responses import PluginDependencyInstallResponse, PluginRuntimeBlockedPayloadDict

PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS = 600


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

    @staticmethod
    def _with_dependency_install_metadata(
        payload: dict[str, object],
        *,
        confirmed: bool,
    ) -> dict[str, object]:
        """
        为 standalone 依赖安装审计补充稳定操作元数据。

        :param payload: 依赖安装负载
        :param confirmed: 是否已显式确认
        :return: 补充元数据后的负载
        """
        payload['operation'] = 'dependency_install'
        payload['confirmed'] = confirmed
        return payload

    def install_plugin_dependencies(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        policy_config: DependencyInstallPolicyConfig | None = None,
        confirmed: bool = False,
        output_callback: PluginCommandOutputCallback | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        从 Web/应用运行时入口安装插件依赖。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param policy_config: 依赖安装策略配置
        :param confirmed: 是否已显式确认
        :param output_callback: 依赖安装实时输出回调
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
            return self._install_discovered_plugin_dependencies(
                plugin_id,
                discovered_plugin,
                dry_run=dry_run,
                policy_config=policy_config,
                confirmed=confirmed,
                output_callback=output_callback,
            )
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('安装插件依赖失败', exc)

    def install_plugin_dependencies_from_cli(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        policy_config: DependencyInstallPolicyConfig | None = None,
        confirmed: bool = False,
        output_callback: PluginCommandOutputCallback | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        从 CLI 入口安装插件依赖。

        CLI 不受 Web 运行时能力限制，但仍与 Web 共用同一套依赖检查、
        安装计划和策略判定。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param policy_config: 依赖安装策略配置
        :param confirmed: 是否已显式确认
        :param output_callback: 依赖安装实时输出回调
        :return: 插件依赖安装负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id, dry_run=dry_run)
            payload = self._install_discovered_plugin_dependencies(
                plugin_id,
                discovered_plugin,
                dry_run=dry_run,
                policy_config=policy_config,
                confirmed=confirmed,
                output_callback=output_callback,
            )
            cast('dict[str, object]', payload).pop('capability', None)
            return payload
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('安装插件依赖失败', exc)

    def _install_discovered_plugin_dependencies(
        self,
        plugin_id: str,
        discovered_plugin: DiscoveredPlugin,
        *,
        dry_run: bool,
        policy_config: DependencyInstallPolicyConfig | None,
        confirmed: bool,
        output_callback: PluginCommandOutputCallback | None,
    ) -> PluginDependencyInstallResponse:
        """
        对已发现插件执行共用的依赖检查、计划、策略判定和安装流程。

        :param plugin_id: 插件ID
        :param discovered_plugin: 已发现插件
        :param dry_run: 是否仅预演
        :param policy_config: 依赖安装策略配置
        :param confirmed: 是否已显式确认
        :param output_callback: 依赖安装实时输出回调
        :return: 插件依赖安装负载
        """
        dependency_result = self.dependencies.dependency_checker.check_manifest(discovered_plugin.manifest)
        return self.install_plugin_dependencies_from_result(
            plugin_id,
            dependency_result,
            dry_run=dry_run,
            discovered_plugin=discovered_plugin,
            policy_config=policy_config,
            confirmed=confirmed,
            output_callback=output_callback,
        )

    def install_plugin_dependencies_from_result(
        self,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
        *,
        dry_run: bool = False,
        discovered_plugin: DiscoveredPlugin | None = None,
        policy_config: DependencyInstallPolicyConfig | None = None,
        confirmed: bool = False,
        output_callback: PluginCommandOutputCallback | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        根据既有依赖检查结果生成计划并执行依赖安装。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param dry_run: 是否仅预演
        :param discovered_plugin: 已发现插件，传入后避免重复扫描插件目录
        :param policy_config: 依赖安装策略配置
        :param confirmed: 是否已显式确认
        :param output_callback: 依赖安装实时输出回调
        :return: 插件依赖安装负载
        """
        discovered_plugin = discovered_plugin or self._get_discovered_plugin(plugin_id)
        install_plan = PluginDependencyInstallPlanner(
            frontend_root=Path(self.dependencies.runtime_environment.get_frontend_dir())
        ).build_plan(dependency_result)
        resolved_policy_config = policy_config or DependencyInstallPolicyConfig.from_environment()
        policy_decision = DependencyInstallPolicyEvaluator(resolved_policy_config).evaluate(
            install_plan,
            confirmed=confirmed,
        )
        install_plan_items = policy_decision.install_plan_items
        if dry_run:
            payload = PluginDependencyInstallPayloadBuilder.build_dry_run_payload(
                plugin_id,
                dependency_result,
                install_plan_items,
                policy_decision,
            )
            payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )
        if not install_plan.has_actions:
            payload = PluginDependencyInstallPayloadBuilder.build_satisfied_payload(
                plugin_id,
                dependency_result,
                install_plan_items,
                policy_decision,
            )
            payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )
        if not policy_decision.allowed:
            payload = PluginDependencyInstallPayloadBuilder.build_payload(
                plugin_id=plugin_id,
                dependency_result=dependency_result,
                install_plan_items=install_plan_items,
                dry_run=False,
                ok=False,
                message='插件依赖安装被策略阻断',
                policy_decision=policy_decision,
            )
            payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )

        install_results = []
        total = len(install_plan_items)
        for index, item in enumerate(install_plan_items, start=1):
            self._emit_install_status(output_callback, index, total, item.requirement, '开始安装')
            try:
                completed = self.dependencies.command_gateway.run_command(
                    item.command,
                    item.workdir,
                    timeout=resolved_policy_config.install_timeout_seconds,
                    output_callback=output_callback,
                )
            except Exception:
                self._emit_install_status(output_callback, index, total, item.requirement, '安装中断')
                raise
            install_results.append(PluginPayloadBuilder.build_dependency_install_result(item, completed))
            status = '安装完成' if completed.returncode == 0 else f'安装失败（退出码 {completed.returncode}）'
            self._emit_install_status(output_callback, index, total, item.requirement, status)
        PluginNpmPackageJsonSynchronizer.sync_successful_items(install_plan_items, install_results)
        payload = PluginDependencyInstallPayloadBuilder.build_execution_payload(
            plugin_id,
            dependency_result,
            install_plan_items,
            install_results,
            policy_decision,
        )
        payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
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
        policy_config: DependencyInstallPolicyConfig | None = None,
        confirmed: bool = False,
        output_callback: PluginCommandOutputCallback | None = None,
    ) -> PluginDependencyInstallResponse:
        """
        根据既有依赖检查结果异步生成计划并执行依赖安装。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :param dry_run: 是否仅预演
        :param discovered_plugin: 已发现插件，传入后避免重复扫描插件目录
        :param policy_config: 依赖安装策略配置
        :param confirmed: 是否已显式确认
        :param output_callback: 依赖安装实时输出回调
        :return: 插件依赖安装负载
        """
        discovered_plugin = discovered_plugin or self._get_discovered_plugin(plugin_id)
        install_plan = PluginDependencyInstallPlanner(
            frontend_root=Path(self.dependencies.runtime_environment.get_frontend_dir())
        ).build_plan(dependency_result)
        resolved_policy_config = policy_config or DependencyInstallPolicyConfig.from_environment()
        policy_decision = DependencyInstallPolicyEvaluator(resolved_policy_config).evaluate(
            install_plan,
            confirmed=confirmed,
        )
        install_plan_items = policy_decision.install_plan_items
        if dry_run:
            payload = PluginDependencyInstallPayloadBuilder.build_dry_run_payload(
                plugin_id,
                dependency_result,
                install_plan_items,
                policy_decision,
            )
            payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )
        if not install_plan.has_actions:
            payload = PluginDependencyInstallPayloadBuilder.build_satisfied_payload(
                plugin_id,
                dependency_result,
                install_plan_items,
                policy_decision,
            )
            payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )
        if not policy_decision.allowed:
            payload = PluginDependencyInstallPayloadBuilder.build_payload(
                plugin_id=plugin_id,
                dependency_result=dependency_result,
                install_plan_items=install_plan_items,
                dry_run=False,
                ok=False,
                message='插件依赖安装被策略阻断',
                policy_decision=policy_decision,
            )
            payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
            return cast(
                'PluginDependencyInstallResponse',
                self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
            )

        install_results = []
        total = len(install_plan_items)
        for index, item in enumerate(install_plan_items, start=1):
            self._emit_install_status(output_callback, index, total, item.requirement, '开始安装')
            try:
                completed = await asyncio.to_thread(
                    self.dependencies.command_gateway.run_command,
                    item.command,
                    item.workdir,
                    timeout=resolved_policy_config.install_timeout_seconds,
                    output_callback=output_callback,
                )
            except Exception:
                self._emit_install_status(output_callback, index, total, item.requirement, '安装中断')
                raise
            install_results.append(PluginPayloadBuilder.build_dependency_install_result(item, completed))
            status = '安装完成' if completed.returncode == 0 else f'安装失败（退出码 {completed.returncode}）'
            self._emit_install_status(output_callback, index, total, item.requirement, status)
        PluginNpmPackageJsonSynchronizer.sync_successful_items(install_plan_items, install_results)
        payload = PluginDependencyInstallPayloadBuilder.build_execution_payload(
            plugin_id,
            dependency_result,
            install_plan_items,
            install_results,
            policy_decision,
        )
        payload = self._with_dependency_install_metadata(cast('dict[str, object]', payload), confirmed=confirmed)
        return cast(
            'PluginDependencyInstallResponse',
            self._with_plugin_capability(cast('dict[str, object]', payload), discovered_plugin),
        )

    @staticmethod
    def _emit_install_status(
        output_callback: PluginCommandOutputCallback | None,
        index: int,
        total: int,
        requirement: str,
        status: str,
    ) -> None:
        """
        输出单项依赖安装状态。

        :param output_callback: 依赖安装实时输出回调
        :param index: 当前安装项序号
        :param total: 安装项总数
        :param requirement: 依赖声明
        :param status: 当前状态
        :return: None
        """
        if output_callback is not None:
            output_callback('status', f'[{index}/{total}] {status}：{requirement}\n')
