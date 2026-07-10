from dataclasses import dataclass

from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.validation.dependencies import PluginDependencyChecker

from .gateway import (
    PluginAuditGateway,
    PluginCommandRunnerGateway,
    PluginConfigGateway,
    PluginLifecycleStateGateway,
    PluginLifecycleUnitOfWorkGateway,
    PluginManagementModelGateway,
    PluginMigrationExecutionGateway,
    PluginMigrationHistoryGateway,
    PluginPurgePlanGateway,
    PluginStateQueryGateway,
)


@dataclass
class PluginRuntimeGatewayOverrides:
    """
    插件运行时窄端口覆盖项。

    该对象用于测试或特殊组合根显式覆盖某个窄端口，避免 facade 构造器随着端口拆分持续膨胀。
    """

    config_gateway: PluginConfigGateway | None = None
    audit_gateway: PluginAuditGateway | None = None
    state_query_gateway: PluginStateQueryGateway | None = None
    migration_history_gateway: PluginMigrationHistoryGateway | None = None
    purge_plan_gateway: PluginPurgePlanGateway | None = None
    lifecycle_state_gateway: PluginLifecycleStateGateway | None = None
    lifecycle_uow_gateway: PluginLifecycleUnitOfWorkGateway | None = None
    migration_execution_gateway: PluginMigrationExecutionGateway | None = None


@dataclass
class PluginRuntimeDependencies:
    """
    插件运行时基础依赖集合。
    """

    runtime_environment: PluginRuntimeEnvironmentService
    dependency_checker: PluginDependencyChecker
    config_gateway: PluginConfigGateway
    audit_gateway: PluginAuditGateway
    state_query_gateway: PluginStateQueryGateway
    migration_history_gateway: PluginMigrationHistoryGateway
    purge_plan_gateway: PluginPurgePlanGateway
    lifecycle_state_gateway: PluginLifecycleStateGateway
    lifecycle_uow_gateway: PluginLifecycleUnitOfWorkGateway
    migration_execution_gateway: PluginMigrationExecutionGateway
    model_gateway: PluginManagementModelGateway
    command_gateway: PluginCommandRunnerGateway
