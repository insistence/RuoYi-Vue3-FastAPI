from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict

from plugins.core.manifest.menu_tree import PluginMenuTree
from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, SUCCESS
from plugins.core.runtime.support.payload.validation import (
    DependencyItemPayload,
    MenuConflictItemPayload,
    PluginDependencyItemPayload,
    PluginValidationPayloadBuilderProtocol,
    StructureItemPayload,
    ValidationIssuePayload,
)
from plugins.core.validation.versioning import PluginVersionComparator

from .validation import PluginValidationPayloadMixin

if TYPE_CHECKING:
    from subprocess import CompletedProcess

    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.lifecycle.purge import PluginPurgePlan, PluginPurgePlanItem
    from plugins.core.validation.dependencies import DependencyCheckResult, DependencyInstallPlanItem
    from plugins.core.validation.plugin_deps import (
        PluginBatchOperation,
        PluginDependencyCheckResult,
        PluginDependencyPlan,
        PluginDependencyPlanBlocker,
        PluginDependencyPlanItem,
    )
    from plugins.core.validation.structure import PluginStructureCheckResult


class SupportsOk(Protocol):
    """
    支持 ok 属性的检查结果协议。
    """

    ok: bool


class PluginPlanBlockerPayload(TypedDict):
    """
    插件批量操作计划阻塞项 payload。
    """

    pluginId: str
    dependencyId: str
    status: str
    message: str


class PluginPlanItemPayload(TypedDict):
    """
    插件批量操作计划项 payload。
    """

    pluginId: str
    name: str
    version: str
    operation: PluginBatchOperation
    order: int
    requested: bool
    dependencies: list[str]
    installedVersion: str | None
    enabled: str | None
    status: str | None
    ready: bool
    blockers: list[PluginPlanBlockerPayload]


class PluginPlanPayloadDict(TypedDict):
    """
    插件批量操作拓扑计划 payload。
    """

    operation: PluginBatchOperation
    ok: bool
    requestedPluginIds: list[str]
    orderedPluginIds: list[str]
    items: list[PluginPlanItemPayload]
    blockers: list[PluginPlanBlockerPayload]
    blockerCount: int


class PluginPlanResponsePayload(TypedDict):
    """
    插件批量操作计划响应 payload。
    """

    ok: bool
    message: str
    operation: PluginBatchOperation
    plan: PluginPlanPayloadDict
    exit_code: int


class DependencyInstallPlanItemPayload(TypedDict):
    """
    依赖安装计划项 payload。
    """

    kind: str
    requirement: str
    name: str
    command: list[str]
    commandText: str
    workdir: str
    reason: str
    status: str


class DependencyInstallResultPayload(TypedDict):
    """
    依赖安装执行结果 payload。
    """

    kind: str
    requirement: str
    name: str
    command: list[str]
    commandText: str
    workdir: str
    returnCode: int
    stdout: str
    stderr: str


class CommandResultPayload(TypedDict):
    """
    系统命令执行结果 payload。
    """

    returnCode: int
    stdout: str
    stderr: str


class PurgePlanItemPayload(TypedDict):
    """
    插件物理清理计划项 payload。
    """

    name: str
    label: str
    enabled: bool
    destructive: bool
    count: int
    target: str


class PurgePlanPayload(TypedDict):
    """
    插件物理清理计划 payload。
    """

    pluginId: str
    removesSource: bool
    requiresHook: bool
    destructiveCount: int
    items: list[PurgePlanItemPayload]


class ActionPayload(TypedDict, total=False):
    """
    插件操作动作项 payload。
    """

    name: str
    label: str
    enabled: bool
    count: int
    ok: bool
    hook: str | None
    targetEnabled: bool
    targetStatus: str


class VersionStatePayload(TypedDict):
    """
    插件升级版本状态 payload。
    """

    installed: bool
    installedVersion: str | None
    currentVersion: str
    needsUpgrade: bool


class UpgradeDryRunPayloadContext(TypedDict):
    """
    插件升级 dry-run payload 上下文。
    """

    versionState: VersionStatePayload
    dependencyResult: DependencyCheckResult
    pluginDependencyResult: PluginDependencyCheckResult
    structureResult: PluginStructureCheckResult
    menuConflictResult: SupportsOk
    manifestOk: bool
    actions: list[ActionPayload]
    manifestIssues: list[ValidationIssuePayload]
    manifestWarnings: list[ValidationIssuePayload]
    pluginDependencyErrors: list[PluginDependencyItemPayload]
    structureErrors: list[StructureItemPayload]
    menuConflicts: list[MenuConflictItemPayload]


class UpgradeDryRunPayloadDict(TypedDict):
    """
    插件升级 dry-run payload。
    """

    ok: bool
    message: str
    pluginId: str
    dryRun: bool
    installed: bool
    installedVersion: str | None
    currentVersion: str
    needsUpgrade: bool
    databaseAvailable: bool
    databaseError: str | None
    dependencyOk: bool
    manifestOk: bool
    pluginDependencyOk: bool
    structureOk: bool
    menuConflictOk: bool
    actions: list[ActionPayload]
    manifestIssues: list[ValidationIssuePayload]
    manifestWarnings: list[ValidationIssuePayload]
    pluginDependencyErrors: list[PluginDependencyItemPayload]
    structureErrors: list[StructureItemPayload]
    menuConflicts: list[MenuConflictItemPayload]
    dependencies: list[DependencyItemPayload]
    pluginDependencies: list[PluginDependencyItemPayload]


class PluginPlanPayloadBuilderProtocol(PluginValidationPayloadBuilderProtocol, Protocol):
    """
    插件批量计划 payload builder 协议。
    """

    @staticmethod
    def build_plugin_plan(plan: PluginDependencyPlan) -> PluginPlanPayloadDict:
        """
        构建插件批量操作拓扑计划负载。
        """
        ...


@dataclass(frozen=True)
class PluginPlanPayload:
    """
    插件批量操作计划结构化负载。
    """

    plan: PluginDependencyPlan
    builder: type[PluginPlanPayloadBuilderProtocol] | None = None

    def to_payload(self) -> PluginPlanResponsePayload:
        """
        序列化为现有插件批量操作计划 payload 契约。

        :return: 插件批量操作计划 payload
        """
        builder = self.builder or _DefaultPlanPayloadBuilder
        return {
            'ok': self.plan.ok,
            'message': '插件批量操作计划生成完成' if self.plan.ok else '插件批量操作计划存在阻塞项',
            'operation': self.plan.operation,
            'plan': builder.build_plugin_plan(self.plan),
            'exit_code': SUCCESS if self.plan.ok else DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginUpgradeDryRunPayload:
    """
    插件升级预演结构化负载。
    """

    plugin_id: str
    payload_context: UpgradeDryRunPayloadContext
    database_error: str | None = None
    builder: type[PluginPlanPayloadBuilderProtocol] | None = None

    def to_payload(self) -> UpgradeDryRunPayloadDict:
        """
        序列化为现有插件升级预演 payload 契约。

        :return: 插件升级预演 payload
        """
        builder = self.builder or _DefaultPlanPayloadBuilder
        version_state = self.payload_context['versionState']
        dependency_result = self.payload_context['dependencyResult']
        plugin_dependency_result = self.payload_context['pluginDependencyResult']
        structure_result = self.payload_context['structureResult']
        menu_conflict_result = self.payload_context['menuConflictResult']
        return {
            'ok': True,
            'message': '插件升级演练完成，未执行实际写入',
            'pluginId': self.plugin_id,
            'dryRun': True,
            **version_state,
            'databaseAvailable': self.database_error is None,
            'databaseError': self.database_error,
            'dependencyOk': dependency_result.ok,
            'manifestOk': self.payload_context['manifestOk'],
            'pluginDependencyOk': plugin_dependency_result.ok,
            'structureOk': structure_result.ok,
            'menuConflictOk': menu_conflict_result.ok,
            'actions': self.payload_context['actions'],
            'manifestIssues': self.payload_context['manifestIssues'],
            'manifestWarnings': self.payload_context['manifestWarnings'],
            'pluginDependencyErrors': self.payload_context['pluginDependencyErrors'],
            'structureErrors': self.payload_context['structureErrors'],
            'menuConflicts': self.payload_context['menuConflicts'],
            'dependencies': [builder.build_dependency_item(item) for item in dependency_result.items],
            'pluginDependencies': [
                builder.build_plugin_dependency_item(item) for item in plugin_dependency_result.items
            ],
        }


class PluginPlanPayloadMixin:
    """
    插件依赖拓扑、执行动作和物理清理计划负载构建能力。
    """

    @staticmethod
    def build_plugin_plan_blocker(item: PluginDependencyPlanBlocker) -> PluginPlanBlockerPayload:
        """
        构建插件批量操作计划阻塞项负载。

        :param item: 插件批量操作计划阻塞项
        :return: 插件批量操作计划阻塞项负载
        """
        return {
            'pluginId': item.plugin_id,
            'dependencyId': item.dependency_id,
            'status': item.status,
            'message': item.message,
        }

    @classmethod
    def build_plugin_plan_item(cls, item: PluginDependencyPlanItem) -> PluginPlanItemPayload:
        """
        构建插件批量操作计划项负载。

        :param item: 插件批量操作计划项
        :return: 插件批量操作计划项负载
        """
        return {
            'pluginId': item.plugin_id,
            'name': item.name,
            'version': item.version,
            'operation': item.operation,
            'order': item.order,
            'requested': item.requested,
            'dependencies': item.dependencies,
            'installedVersion': item.installed_version,
            'enabled': item.enabled,
            'status': item.status,
            'ready': item.ready,
            'blockers': [cls.build_plugin_plan_blocker(blocker) for blocker in item.blockers],
        }

    @classmethod
    def build_plugin_plan(cls, plan: PluginDependencyPlan) -> PluginPlanPayloadDict:
        """
        构建插件批量操作拓扑计划负载。

        :param plan: 插件批量操作拓扑计划
        :return: 插件批量操作拓扑计划负载
        """
        return {
            'operation': plan.operation,
            'ok': plan.ok,
            'requestedPluginIds': plan.requested_plugin_ids,
            'orderedPluginIds': plan.ordered_plugin_ids,
            'items': [cls.build_plugin_plan_item(item) for item in plan.items],
            'blockers': [cls.build_plugin_plan_blocker(blocker) for blocker in plan.blockers],
            'blockerCount': len(plan.blockers),
        }

    @classmethod
    def build_plan_payload(cls, plan: PluginDependencyPlan) -> PluginPlanResponsePayload:
        """
        构建插件批量操作计划响应负载。

        :param plan: 插件批量操作拓扑计划
        :return: 插件批量操作计划响应负载
        """
        return PluginPlanPayload(plan, builder=cls).to_payload()

    @staticmethod
    def build_dependency_install_plan_item(item: DependencyInstallPlanItem) -> DependencyInstallPlanItemPayload:
        """
        构建依赖安装计划项负载。

        :param item: 依赖安装计划项
        :return: 依赖安装计划项负载
        """
        return {
            'kind': item.kind,
            'requirement': item.requirement,
            'name': item.name,
            'command': item.command,
            'commandText': ' '.join(item.command),
            'workdir': item.workdir,
            'reason': item.reason,
            'status': 'planned',
        }

    @staticmethod
    def build_dependency_install_result(
        item: DependencyInstallPlanItem,
        completed: CompletedProcess[str],
    ) -> DependencyInstallResultPayload:
        """
        构建依赖安装执行结果负载。

        :param item: 依赖安装计划项
        :param completed: 命令执行结果
        :return: 依赖安装执行结果
        """
        return {
            'kind': item.kind,
            'requirement': item.requirement,
            'name': item.name,
            'command': item.command,
            'commandText': ' '.join(item.command),
            'workdir': item.workdir,
            'returnCode': completed.returncode,
            'stdout': completed.stdout[-2000:],
            'stderr': completed.stderr[-2000:],
        }

    @staticmethod
    def build_command_result(completed: CompletedProcess[str]) -> CommandResultPayload:
        """
        构建通用系统命令执行结果负载。

        :param completed: 命令执行结果
        :return: 系统命令执行结果负载
        """
        return {
            'returnCode': completed.returncode,
            'stdout': completed.stdout[-4000:] if completed.stdout else '',
            'stderr': completed.stderr[-4000:] if completed.stderr else '',
        }

    @staticmethod
    def build_purge_plan_item(item: PluginPurgePlanItem) -> PurgePlanItemPayload:
        """
        构建插件物理清理计划项负载。

        :param item: 插件物理清理计划项
        :return: 插件物理清理计划项负载
        """
        return {
            'name': item.name,
            'label': item.label,
            'enabled': item.enabled,
            'destructive': item.destructive,
            'count': item.count,
            'target': item.target,
        }

    @classmethod
    def build_purge_plan(cls, plan: PluginPurgePlan) -> PurgePlanPayload:
        """
        构建插件物理清理计划负载。

        :param plan: 插件物理清理计划
        :return: 插件物理清理计划负载
        """
        return {
            'pluginId': plan.plugin_id,
            'removesSource': plan.removes_source,
            'requiresHook': plan.requires_hook,
            'destructiveCount': plan.destructive_count,
            'items': [cls.build_purge_plan_item(item) for item in plan.items],
        }

    @classmethod
    def build_install_actions(
        cls,
        discovered_plugin: DiscoveredPlugin,
        dependency_ok: bool,
        plugin_dependency_ok: bool,
        structure_ok: bool,
        menu_conflict_ok: bool,
    ) -> list[ActionPayload]:
        """
        构建插件安装动作计划。

        :param discovered_plugin: 已发现插件
        :param dependency_ok: 依赖检查是否通过
        :param plugin_dependency_ok: 插件间依赖检查是否通过
        :param structure_ok: 结构检查是否通过
        :param menu_conflict_ok: 菜单冲突检查是否通过
        :return: 安装动作计划
        """
        manifest = discovered_plugin.manifest
        return [
            {'name': 'upsert_plugin', 'label': '写入或更新插件状态', 'enabled': True},
            {
                'name': 'install_menus',
                'label': '幂等写入菜单和权限',
                'enabled': bool(manifest.frontend.menus),
                'count': PluginMenuTree.count(manifest.frontend.menus),
            },
            {
                'name': 'install_configs',
                'label': '写入默认插件配置',
                'enabled': bool(manifest.config.items),
                'count': len(manifest.config.items),
            },
            {'name': 'check_dependencies', 'label': '检查依赖声明', 'enabled': True, 'ok': dependency_ok},
            {
                'name': 'check_plugin_dependencies',
                'label': '检查插件间依赖',
                'enabled': bool(manifest.dependencies.plugins),
                'ok': plugin_dependency_ok,
                'count': len(manifest.dependencies.plugins),
            },
            {'name': 'check_structure', 'label': '检查插件结构', 'enabled': True, 'ok': structure_ok},
            {
                'name': 'check_menu_conflicts',
                'label': '检查菜单和权限冲突',
                'enabled': bool(manifest.frontend.menus),
                'ok': menu_conflict_ok,
            },
            {
                'name': 'run_migrations',
                'label': '执行 migration 脚本',
                'enabled': bool(manifest.backend.migrations),
                'count': len(manifest.backend.migrations),
            },
            {
                'name': 'run_seeds',
                'label': '执行 seed 脚本',
                'enabled': bool(manifest.backend.seeds),
                'count': len(manifest.backend.seeds),
            },
            {
                'name': 'run_install_hook',
                'label': '执行安装生命周期钩子',
                'enabled': bool(manifest.backend.hooks.on_install),
                'hook': manifest.backend.hooks.on_install,
            },
        ]

    @classmethod
    def build_upgrade_actions(
        cls,
        discovered_plugin: DiscoveredPlugin,
        dependency_ok: bool,
        plugin_dependency_ok: bool,
        structure_ok: bool,
        menu_conflict_ok: bool,
    ) -> list[ActionPayload]:
        """
        构建插件升级动作计划。

        :param discovered_plugin: 已发现插件
        :param dependency_ok: 依赖检查是否通过
        :param plugin_dependency_ok: 插件间依赖检查是否通过
        :param structure_ok: 结构检查是否通过
        :param menu_conflict_ok: 菜单冲突检查是否通过
        :return: 升级动作计划
        """
        manifest = discovered_plugin.manifest
        return [
            {'name': 'check_installed_version', 'label': '检查已安装版本', 'enabled': True},
            {'name': 'upsert_plugin', 'label': '刷新插件元数据', 'enabled': True},
            {
                'name': 'install_menus',
                'label': '幂等更新菜单和权限',
                'enabled': bool(manifest.frontend.menus),
                'count': PluginMenuTree.count(manifest.frontend.menus),
            },
            {
                'name': 'install_configs',
                'label': '刷新默认插件配置',
                'enabled': bool(manifest.config.items),
                'count': len(manifest.config.items),
            },
            {'name': 'check_dependencies', 'label': '检查依赖声明', 'enabled': True, 'ok': dependency_ok},
            {
                'name': 'check_plugin_dependencies',
                'label': '检查插件间依赖',
                'enabled': bool(manifest.dependencies.plugins),
                'ok': plugin_dependency_ok,
                'count': len(manifest.dependencies.plugins),
            },
            {'name': 'check_structure', 'label': '检查插件结构', 'enabled': True, 'ok': structure_ok},
            {
                'name': 'check_menu_conflicts',
                'label': '检查菜单和权限冲突',
                'enabled': bool(manifest.frontend.menus),
                'ok': menu_conflict_ok,
            },
            {
                'name': 'run_migrations',
                'label': '执行 migration 脚本',
                'enabled': bool(manifest.backend.migrations),
                'count': len(manifest.backend.migrations),
            },
            {
                'name': 'run_seeds',
                'label': '执行 seed 脚本',
                'enabled': bool(manifest.backend.seeds),
                'count': len(manifest.backend.seeds),
            },
            {
                'name': 'run_upgrade_hook',
                'label': '执行升级生命周期钩子',
                'enabled': bool(manifest.backend.hooks.on_upgrade),
                'hook': manifest.backend.hooks.on_upgrade,
            },
            {'name': 'mark_installed', 'label': '更新已安装版本', 'enabled': True},
        ]

    @staticmethod
    def build_upgrade_version_state(
        discovered_plugin: DiscoveredPlugin,
        database_plugin: object | None,
    ) -> VersionStatePayload:
        """
        构建插件升级版本状态。

        :param discovered_plugin: 已发现插件
        :param database_plugin: 数据库插件状态
        :return: 升级版本状态
        """
        installed_version = getattr(database_plugin, 'installed_version', None)
        current_version = discovered_plugin.manifest.version
        return {
            'installed': database_plugin is not None and bool(installed_version),
            'installedVersion': installed_version,
            'currentVersion': current_version,
            'needsUpgrade': PluginVersionComparator.is_upgrade_available(installed_version, current_version),
        }

    @classmethod
    def build_upgrade_dry_run_payload(
        cls,
        plugin_id: str,
        payload_context: UpgradeDryRunPayloadContext,
        database_error: str | None = None,
    ) -> UpgradeDryRunPayloadDict:
        """
        构建插件升级 dry-run 负载。

        :param plugin_id: 插件ID
        :param payload_context: dry-run 负载上下文
        :param database_error: 数据库状态读取错误
        :return: 插件升级 dry-run 负载
        """
        return PluginUpgradeDryRunPayload(
            plugin_id,
            payload_context,
            database_error=database_error,
            builder=cls,
        ).to_payload()

    @staticmethod
    def build_enabled_actions(enabled: bool, plugin_dependency_ok: bool = True) -> list[ActionPayload]:
        """
        构建插件启停动作计划。

        :param enabled: 是否启用
        :param plugin_dependency_ok: 插件间依赖检查是否通过
        :return: 插件启停动作计划
        """
        actions = [
            {
                'name': 'update_plugin_enabled',
                'label': '更新插件启停状态',
                'enabled': True,
                'targetEnabled': enabled,
            },
            {
                'name': 'update_plugin_menu_status',
                'label': '更新插件菜单状态',
                'enabled': True,
                'targetStatus': '0' if enabled else '1',
            },
        ]
        if enabled:
            actions.insert(
                0,
                {
                    'name': 'check_plugin_dependencies',
                    'label': '检查插件间依赖',
                    'enabled': True,
                    'ok': plugin_dependency_ok,
                },
            )

        return actions


class _DefaultPlanPayloadBuilder(PluginPlanPayloadMixin, PluginValidationPayloadMixin):
    """
    plan 模型直接序列化时使用的最小组合 builder。
    """
