from collections.abc import Awaitable, Callable, Mapping
from typing import cast

from plugins.core.environment import PLUGIN_RUNTIME_ENVIRONMENT, PluginRuntimeEnvironmentService
from plugins.core.runtime.support import PluginRuntimePayloadBuilder
from plugins.core.types import PluginConfigValue
from plugins.core.validation.dependencies import NpmDependencyInspector, PluginDependencyChecker

from .audit import PluginAuditUseCase
from .batch import PluginBatchUseCase
from .config import PluginConfigUseCase
from .context import PluginRuntimeContextService
from .dependencies import PluginDependencyUseCase
from .dependency_container import PluginRuntimeDependencies
from .gateway import (
    DefaultPluginCommandRunnerGateway,
    PluginCommandRunnerGateway,
    PluginManagementModelGateway,
    PluginStateGateway,
    UnavailablePluginManagementModelGateway,
    UnavailablePluginStateGateway,
)
from .lifecycle import PluginEnableUseCase, PluginInstallUseCase, PluginPurgeUseCase, PluginUpgradeUseCase
from .lifecycle_lock import NoopPluginLifecycleLock, PluginLifecycleLock
from .precheck import PluginPrecheckUseCase
from .query import PluginQueryUseCase
from .responses import (
    PluginBatchItemExecutionResponse,
    PluginBatchResponse,
    PluginCatalogInfoResponse,
    PluginCatalogListResponse,
    PluginCheckResponse,
    PluginConfigExportResponse,
    PluginConfigImportResponse,
    PluginConfigStateResponse,
    PluginDependencyCheckResponse,
    PluginDependencyInstallResponse,
    PluginDiagnoseResponse,
    PluginDocumentationResponse,
    PluginHealthResponse,
    PluginLifecycleResponse,
    PluginPlanResponse,
    PluginPrecheckResponse,
)
from .tools import PluginToolUseCase


class PluginRuntimeService:
    """
    插件应用运行时服务。

    使用 Facade + 组合式 use case 管理插件查询、检查、生命周期、配置、测试和模板等核心能力。
    数据库状态、管理模型和命令执行等外部依赖通过显式端口注入。
    """

    def __init__(
        self,
        *,
        runtime_environment: PluginRuntimeEnvironmentService | None = None,
        dependency_checker: PluginDependencyChecker | None = None,
        state_gateway: PluginStateGateway | None = None,
        model_gateway: PluginManagementModelGateway | None = None,
        command_gateway: PluginCommandRunnerGateway | None = None,
        lifecycle_lock: PluginLifecycleLock | None = None,
    ) -> None:
        """
        初始化插件应用运行时服务。

        :param runtime_environment: 插件运行时环境服务
        :param dependency_checker: 插件依赖检查器
        :param state_gateway: 插件管理状态网关
        :param model_gateway: 插件管理模型工厂网关
        :param command_gateway: 插件命令执行网关
        :param lifecycle_lock: 插件生命周期操作锁
        :return: None
        """
        resolved_environment = runtime_environment or PLUGIN_RUNTIME_ENVIRONMENT
        resolved_dependency_checker = dependency_checker or PluginDependencyChecker(
            npm_inspector=NpmDependencyInspector(frontend_root=resolved_environment.get_frontend_dir()),
            frontend_mode=resolved_environment.get_frontend_mode(),
        )
        self._replace_dependencies(
            PluginRuntimeDependencies(
                runtime_environment=resolved_environment,
                dependency_checker=resolved_dependency_checker,
                state_gateway=state_gateway or UnavailablePluginStateGateway(),
                model_gateway=model_gateway or UnavailablePluginManagementModelGateway(),
                command_gateway=command_gateway or DefaultPluginCommandRunnerGateway(),
            )
        )
        self.lifecycle_lock = lifecycle_lock or NoopPluginLifecycleLock()

    def _replace_dependencies(self, dependencies: PluginRuntimeDependencies) -> None:
        """
        替换插件运行时依赖容器并刷新组合 use case。

        :param dependencies: 新的插件运行时依赖容器
        :return: None
        """
        self.dependencies = dependencies
        self.context = PluginRuntimeContextService(dependencies)
        self.audit = PluginAuditUseCase(dependencies)
        self.batch = PluginBatchUseCase(dependencies, runtime_operations=self, context=self.context)
        self.config = PluginConfigUseCase(dependencies, context=self.context)
        self.dependency = PluginDependencyUseCase(dependencies, context=self.context)
        self.enable = PluginEnableUseCase(dependencies, runtime_operations=self, context=self.context)
        self.install = PluginInstallUseCase(dependencies, runtime_operations=self, context=self.context)
        self.precheck = PluginPrecheckUseCase(dependencies, context=self.context)
        self.purge = PluginPurgeUseCase(dependencies, runtime_operations=self, context=self.context)
        self.query = PluginQueryUseCase(dependencies, runtime_operations=self, context=self.context)
        self.tools = PluginToolUseCase(dependencies, context=self.context)
        self.upgrade = PluginUpgradeUseCase(dependencies, runtime_operations=self, context=self.context)

    def set_dependency_checker(self, dependency_checker: PluginDependencyChecker) -> None:
        """
        替换插件依赖检查器。

        :param dependency_checker: 新的依赖检查器
        :return: None
        """
        self.dependencies.dependency_checker = dependency_checker

    def refresh_dependency_checker(self) -> None:
        """
        刷新插件 Python/npm 依赖检查器。

        :return: None
        """
        self.set_dependency_checker(
            PluginDependencyChecker(
                npm_inspector=NpmDependencyInspector(
                    frontend_root=self.dependencies.runtime_environment.get_frontend_dir(),
                ),
                frontend_mode=self.dependencies.runtime_environment.get_frontend_mode(),
            )
        )

    def list_plugins(self) -> PluginCatalogListResponse:
        """
        获取本地插件列表。

        :return: 插件列表负载
        """
        return cast('PluginCatalogListResponse', self.query.list_plugins())

    def get_plugin_info(self, plugin_id: str) -> PluginCatalogInfoResponse:
        """
        获取插件详情。

        :param plugin_id: 插件ID
        :return: 插件详情负载
        """
        return cast('PluginCatalogInfoResponse', self.query.get_plugin_info(plugin_id))

    async def get_plugin_info_with_state(self, plugin_id: str) -> PluginCatalogInfoResponse:
        """
        获取包含数据库状态的插件详情。

        :param plugin_id: 插件ID
        :return: 插件详情负载
        """
        return cast('PluginCatalogInfoResponse', await self.query.get_plugin_info_with_state(plugin_id))

    def check_plugin(self, plugin_id: str | None = None) -> PluginCheckResponse:
        """
        检查插件依赖状态。

        :param plugin_id: 插件ID，未传入时检查全部插件
        :return: 插件检查负载
        """
        return cast('PluginCheckResponse', self.query.check_plugin(plugin_id))

    async def check_plugin_async(self, plugin_id: str | None = None) -> PluginCheckResponse:
        """
        异步检查插件依赖状态。

        :param plugin_id: 插件ID，未传入时检查全部插件
        :return: 插件检查负载
        """
        return cast('PluginCheckResponse', await self.query.check_plugin_async(plugin_id))

    def check_plugin_dependencies(self, plugin_id: str) -> PluginDependencyCheckResponse:
        """
        检查插件依赖状态。

        :param plugin_id: 插件ID
        :return: 插件依赖检查负载
        """
        return cast('PluginDependencyCheckResponse', self.query.check_plugin_dependencies(plugin_id))

    async def health_plugin(self, plugin_id: str) -> PluginHealthResponse:
        """
        执行插件健康检查。

        :param plugin_id: 插件ID
        :return: 插件健康检查负载
        """
        return cast('PluginHealthResponse', await self.query.health_plugin(plugin_id))

    async def diagnose_plugin(self, plugin_id: str) -> PluginDiagnoseResponse:
        """
        生成插件诊断包。

        :param plugin_id: 插件ID
        :return: 插件诊断包负载
        """
        return cast('PluginDiagnoseResponse', await self.query.diagnose_plugin(plugin_id))

    async def get_plugin_config(self, plugin_id: str, *, reveal_secret: bool = False) -> PluginConfigStateResponse:
        """
        获取插件配置。

        :param plugin_id: 插件ID
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置负载
        """
        return cast(
            'PluginConfigStateResponse', await self.config.get_plugin_config(plugin_id, reveal_secret=reveal_secret)
        )

    async def export_plugin_config(self, plugin_id: str, *, reveal_secret: bool = False) -> PluginConfigExportResponse:
        """
        导出插件配置快照。

        :param plugin_id: 插件ID
        :param reveal_secret: 是否导出敏感配置明文
        :return: 插件配置导出负载
        """
        return cast(
            'PluginConfigExportResponse', await self.config.export_plugin_config(plugin_id, reveal_secret=reveal_secret)
        )

    async def set_plugin_config(
        self,
        plugin_id: str,
        values: dict[str, PluginConfigValue],
        *,
        audit_operation: str = 'config_set',
        success_message: str = '插件配置已更新',
    ) -> PluginConfigStateResponse:
        """
        更新插件配置。

        :param plugin_id: 插件ID
        :param values: 配置键值
        :param audit_operation: 审计操作类型
        :param success_message: 操作成功提示
        :return: 插件配置更新负载
        """
        return cast(
            'PluginConfigStateResponse',
            await self.config.set_plugin_config(
                plugin_id,
                values,
                audit_operation=audit_operation,
                success_message=success_message,
            ),
        )

    async def import_plugin_config(
        self, plugin_id: str, values: dict[str, PluginConfigValue]
    ) -> PluginConfigImportResponse:
        """
        导入插件配置。

        :param plugin_id: 插件ID
        :param values: 待导入配置键值
        :return: 插件配置导入负载
        """
        return cast('PluginConfigImportResponse', await self.config.import_plugin_config(plugin_id, values))

    async def precheck_plugin_operation(self, plugin_id: str, operation: str) -> PluginPrecheckResponse:
        """
        执行插件操作预检。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :return: 插件操作预检负载
        """
        return cast('PluginPrecheckResponse', await self.precheck.precheck_plugin_operation(plugin_id, operation))

    def plan_plugins(self, operation: str, plugin_ids: list[str] | None = None) -> PluginPlanResponse:
        """
        生成插件批量操作拓扑计划。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :return: 插件批量操作拓扑计划负载
        """
        return cast('PluginPlanResponse', self.batch.plan_plugins(operation, plugin_ids))

    async def plan_plugins_async(self, operation: str, plugin_ids: list[str] | None = None) -> PluginPlanResponse:
        """
        异步生成插件批量操作拓扑计划。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :return: 插件批量操作拓扑计划负载
        """
        return cast('PluginPlanResponse', await self.batch.plan_plugins_async(operation, plugin_ids))

    async def batch_plugins(
        self,
        operation: str,
        plugin_ids: list[str] | None = None,
        *,
        dry_run: bool = False,
        continue_on_error: bool = False,
    ) -> PluginBatchResponse:
        """
        批量执行插件安装、启用或升级。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :param dry_run: 是否仅预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量执行结果负载
        """
        return cast(
            'PluginBatchResponse',
            await self.batch.batch_plugins(
                operation,
                plugin_ids,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            ),
        )

    async def execute_batch_plugin_item(self, operation: str, plugin_id: str) -> PluginBatchItemExecutionResponse:
        """
        执行单个批量插件操作项。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 单插件操作结果负载
        """
        return cast(
            'PluginBatchItemExecutionResponse', await self.batch.execute_batch_plugin_item(operation, plugin_id)
        )

    def install_plugin_dependencies(self, plugin_id: str, *, dry_run: bool = False) -> PluginDependencyInstallResponse:
        """
        安装插件依赖。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件依赖安装负载
        """
        return cast(
            'PluginDependencyInstallResponse', self.dependency.install_plugin_dependencies(plugin_id, dry_run=dry_run)
        )

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
        return cast(
            'PluginDependencyInstallResponse',
            self.dependency.install_plugin_dependencies_from_result(
                plugin_id,
                dependency_result,
                dry_run=dry_run,
                discovered_plugin=discovered_plugin,
            ),
        )

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
        return cast(
            'PluginDependencyInstallResponse',
            await self.dependency.install_plugin_dependencies_from_result_async(
                plugin_id,
                dependency_result,
                dry_run=dry_run,
                discovered_plugin=discovered_plugin,
            ),
        )

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
        await self.audit.record_plugin_operation_log(
            cast('dict[str, object]', payload),
            dry_run=dry_run,
            continue_on_error=continue_on_error,
        )

    async def record_plugin_failure_state(self, payload: Mapping[str, object], default_message: str) -> None:
        """
        记录插件操作失败状态。

        :param payload: 插件操作返回负载
        :param default_message: 缺省失败信息
        :return: None
        """
        await self.audit.record_plugin_failure_state(cast('dict[str, object]', payload), default_message)

    async def install_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        安装插件并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件安装结果负载
        """
        return await self._run_with_lifecycle_lock(
            plugin_id,
            'install',
            dry_run=dry_run,
            operation=lambda: self.install.install_plugin(
                plugin_id,
                dry_run=dry_run,
                record_operation_log=record_operation_log,
            ),
        )

    async def set_plugin_enabled(
        self,
        plugin_id: str,
        *,
        enabled: bool,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        更新插件启停状态并按需记录审计日志。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件启停结果负载
        """
        operation = 'enable' if enabled else 'disable'
        return await self._run_with_lifecycle_lock(
            plugin_id,
            operation,
            dry_run=dry_run,
            operation=lambda: self.enable.set_plugin_enabled(
                plugin_id,
                enabled=enabled,
                dry_run=dry_run,
                record_operation_log=record_operation_log,
            ),
        )

    async def uninstall_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        安全卸载插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件卸载结果负载
        """
        return await self._run_with_lifecycle_lock(
            plugin_id,
            'uninstall',
            dry_run=dry_run,
            operation=lambda: self.enable.uninstall_plugin(
                plugin_id,
                dry_run=dry_run,
                record_operation_log=record_operation_log,
            ),
        )

    async def purge_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        物理清理插件平台元数据并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件物理清理结果负载
        """
        return await self._run_with_lifecycle_lock(
            plugin_id,
            'purge',
            dry_run=dry_run,
            operation=lambda: self.purge.purge_plugin(
                plugin_id,
                dry_run=dry_run,
                record_operation_log=record_operation_log,
            ),
        )

    async def upgrade_plugin(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        record_operation_log: bool = True,
    ) -> PluginLifecycleResponse:
        """
        升级插件并按需记录审计日志。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param record_operation_log: 是否记录插件操作审计日志
        :return: 插件升级结果负载
        """
        return await self._run_with_lifecycle_lock(
            plugin_id,
            'upgrade',
            dry_run=dry_run,
            operation=lambda: self.upgrade.upgrade_plugin(
                plugin_id,
                dry_run=dry_run,
                record_operation_log=record_operation_log,
            ),
        )

    async def _run_with_lifecycle_lock(
        self,
        plugin_id: str,
        lock_operation: str,
        *,
        dry_run: bool,
        operation: Callable[[], Awaitable[PluginLifecycleResponse]],
    ) -> PluginLifecycleResponse:
        """
        在插件生命周期分布式锁内执行写操作。

        :param plugin_id: 插件ID
        :param lock_operation: 锁定的操作类型
        :param dry_run: 是否仅预演
        :param operation: 实际操作
        :return: 插件生命周期操作结果
        """
        if dry_run:
            return await operation()
        async with self.lifecycle_lock.lock(plugin_id, lock_operation) as lock_result:
            if not lock_result.acquired:
                return cast(
                    'PluginLifecycleResponse',
                    PluginRuntimePayloadBuilder.build_invalid_operation_payload(
                        plugin_id,
                        lock_operation,
                        message=lock_result.message,
                    ),
                )
            return await operation()

    def generate_plugin_docs(self, plugin_id: str) -> PluginDocumentationResponse:
        """
        生成插件 Markdown 文档片段。

        :param plugin_id: 插件ID
        :return: 插件文档生成负载
        """
        return self.tools.generate_plugin_docs(plugin_id)
