from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeAlias

from pydantic import Field

from utils.log_util import logger

from . import PluginPayloadBuilder
from .base import PluginPayloadModel

if TYPE_CHECKING:
    from collections.abc import Mapping

    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.lifecycle.purge import PluginPurgePlan
    from plugins.core.types import JSONObject
    from plugins.core.validation.plugin_deps import PluginBatchOperation

    from .catalog import PluginMenuDiagnosticPlanPayload
    from .plan import ActionPayload, VersionStatePayload


class SupportsOk(Protocol):
    """
    支持 ok 属性的检查结果协议。
    """

    ok: bool


class PluginRuntimePrecheckProtocol(Protocol):
    """
    runtime payload 所需的预检上下文协议。
    """

    ok: bool
    dependency_result: SupportsOk
    manifest_result: SupportsOk
    plugin_dependency_result: SupportsOk
    structure_result: SupportsOk
    menu_conflict_result: SupportsOk
    operation_payload: Mapping[str, object]
    check_payload: Mapping[str, object]


class PluginHealthResultProtocol(Protocol):
    """
    runtime 健康检查结果协议。
    """

    plugin_id: str
    ok: bool
    status: str
    message: str
    checker: str | None
    duration_ms: float
    details: JSONObject
    error: str | None


class PluginRuntimeDiagnosePayload(PluginPayloadModel):
    """
    插件诊断包 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    info: object
    check: dict[str, object]
    menu_plan: dict[str, object] = Field(alias='menuPlan')
    config: dict[str, object]
    audit: dict[str, object]


class PluginRuntimeHealthPayload(PluginPayloadModel):
    """
    插件健康检查 payload。
    """

    plugin_id: str = Field(alias='pluginId')
    ok: bool
    status: str
    message: str
    checker: str | None
    duration_ms: float = Field(alias='durationMs')
    details: object
    error: str | None


class PluginRuntimeHealthResponsePayload(PluginPayloadModel):
    """
    插件健康检查响应 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    health: dict[str, object]


class PluginRuntimePrecheckPayload(PluginPayloadModel):
    """
    插件操作预检 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    operation: str
    database_available: bool = Field(alias='databaseAvailable')
    database_error: str | None = Field(alias='databaseError')
    purge_plan_error: str | None = Field(default=None, alias='purgePlanError')
    installed: bool | None = None
    installed_version: str | None = Field(default=None, alias='installedVersion')
    current_version: str | None = Field(default=None, alias='currentVersion')
    needs_upgrade: bool | None = Field(default=None, alias='needsUpgrade')
    manifest_ok: bool | None = Field(default=None, alias='manifestOk')
    dependency_ok: bool | None = Field(default=None, alias='dependencyOk')
    plugin_dependency_ok: bool | None = Field(default=None, alias='pluginDependencyOk')
    structure_ok: bool | None = Field(default=None, alias='structureOk')
    menu_conflict_ok: bool | None = Field(default=None, alias='menuConflictOk')
    manifest_issues: list[dict[str, object]] | None = Field(default=None, alias='manifestIssues')
    manifest_warnings: list[dict[str, object]] | None = Field(default=None, alias='manifestWarnings')
    plugin_dependency_errors: list[dict[str, object]] | None = Field(default=None, alias='pluginDependencyErrors')
    structure_errors: list[dict[str, object]] | None = Field(default=None, alias='structureErrors')
    menu_conflicts: list[dict[str, object]] | None = Field(default=None, alias='menuConflicts')
    dependencies: list[dict[str, object]] | None = None
    plugin_dependencies: list[dict[str, object]] | None = Field(default=None, alias='pluginDependencies')
    actions: list[dict[str, object]]
    precheck: dict[str, object]
    plan: dict[str, object] | None = None


class PluginRuntimeExceptionPayload(PluginPayloadModel):
    """
    插件运行时异常 payload。
    """

    ok: bool
    message: str
    error: str
    plugin_id: str | None = Field(default=None, alias='pluginId')
    failed_step: str | None = Field(default=None, alias='failedStep')
    migration_recovery: object | None = Field(default=None, alias='migrationRecovery')


class PluginRuntimeInvalidOperationPayload(PluginPayloadModel):
    """
    插件非法操作 payload。
    """

    ok: bool
    message: str
    operation: str
    plugin_id: str | None = Field(default=None, alias='pluginId')


class PluginRuntimeBatchItemUnsupportedPayload(PluginPayloadModel):
    """
    插件批量单项不支持 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')


class PluginRuntimeDiagnoseFailurePayload(PluginPayloadModel):
    """
    插件诊断包失败 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    info: dict[str, object]


class PluginRuntimeUpgradeBlockerPayload(PluginPayloadModel):
    """
    插件升级前置阻断 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    dry_run: bool = Field(alias='dryRun')
    installed: bool
    installed_version: str | None = Field(alias='installedVersion')
    current_version: str = Field(alias='currentVersion')
    needs_upgrade: bool = Field(alias='needsUpgrade')
    manifest_ok: bool = Field(alias='manifestOk')
    dependency_ok: bool = Field(alias='dependencyOk')
    plugin_dependency_ok: bool | None = Field(default=None, alias='pluginDependencyOk')
    structure_ok: bool | None = Field(default=None, alias='structureOk')
    menu_conflict_ok: bool | None = Field(default=None, alias='menuConflictOk')
    manifest_issues: list[dict[str, object]] | None = Field(default=None, alias='manifestIssues')
    manifest_warnings: list[dict[str, object]] | None = Field(default=None, alias='manifestWarnings')
    plugin_dependency_errors: list[dict[str, object]] | None = Field(default=None, alias='pluginDependencyErrors')
    structure_errors: list[dict[str, object]] | None = Field(default=None, alias='structureErrors')
    menu_conflicts: list[dict[str, object]] | None = Field(default=None, alias='menuConflicts')
    dependencies: list[dict[str, object]] | None = None
    plugin_dependencies: list[dict[str, object]] | None = Field(default=None, alias='pluginDependencies')
    actions: list[dict[str, object]]


PluginRuntimeDiagnosePayloadDict: TypeAlias = dict[str, object]
PluginRuntimeHealthPayloadDict: TypeAlias = dict[str, object]
PluginRuntimeHealthResponsePayloadDict: TypeAlias = dict[str, object]
PluginRuntimePrecheckPayloadDict: TypeAlias = dict[str, object]
PluginRuntimeExceptionPayloadDict: TypeAlias = dict[str, object]
PluginRuntimeInvalidOperationPayloadDict: TypeAlias = dict[str, object]
PluginRuntimeBatchItemUnsupportedPayloadDict: TypeAlias = dict[str, object]
PluginRuntimeDiagnoseFailurePayloadDict: TypeAlias = dict[str, object]
PluginRuntimeUpgradeBlockerPayloadDict: TypeAlias = dict[str, object]


class PluginRuntimePayloadBuilder:
    """
    插件运行时通用负载构建器。
    """

    @staticmethod
    def build_exception_payload(
        message: str,
        error: Exception,
        *,
        plugin_id: str | None = None,
        failed_step: str | None = None,
        extra_payload: Mapping[str, object] | None = None,
    ) -> PluginRuntimeExceptionPayloadDict:
        """
        构建运行时异常负载。

        :param message: 异常场景提示
        :param error: 异常对象
        :param plugin_id: 插件ID
        :param failed_step: 失败生命周期步骤
        :param extra_payload: 额外结构化负载
        :return: 运行时异常负载
        """
        logger.exception(f'{message}：{error}')
        return PluginRuntimeExceptionPayload(
            ok=False,
            message=message,
            error=str(error),
            plugin_id=plugin_id,
            failed_step=failed_step,
            **(extra_payload or {}),
        ).to_payload(exclude_none=True)

    @staticmethod
    def build_invalid_operation_payload(
        plugin_id: str | None,
        operation: str,
        *,
        message: str,
    ) -> PluginRuntimeInvalidOperationPayloadDict:
        """
        构建非法操作负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param message: 错误提示
        :return: 非法操作负载
        """
        return PluginRuntimeInvalidOperationPayload(
            ok=False,
            message=message,
            operation=operation,
            plugin_id=plugin_id,
        ).to_payload(exclude_none=True)

    @staticmethod
    def build_health_response_payload(
        plugin_id: str, health_result: PluginHealthResultProtocol
    ) -> PluginRuntimeHealthResponsePayloadDict:
        """
        构建插件健康检查响应负载。

        :param plugin_id: 插件ID
        :param health_result: 插件健康检查结果
        :return: 插件健康检查响应负载
        """
        return PluginRuntimeHealthResponsePayload(
            ok=health_result.ok,
            message=health_result.message,
            plugin_id=plugin_id,
            health=PluginRuntimePayloadBuilder.build_health_payload(health_result),
        ).to_payload()

    @staticmethod
    def build_batch_item_unsupported_payload(
        operation: PluginBatchOperation, plugin_id: str
    ) -> PluginRuntimeBatchItemUnsupportedPayloadDict:
        """
        构建批量单项不支持负载。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 批量单项不支持负载
        """
        return PluginRuntimeBatchItemUnsupportedPayload(
            ok=False,
            message=f'插件批量操作不支持：{operation}',
            plugin_id=plugin_id,
        ).to_payload()

    @staticmethod
    def build_diagnose_failure_payload(
        plugin_id: str, info_payload: Mapping[str, object]
    ) -> PluginRuntimeDiagnoseFailurePayloadDict:
        """
        构建插件诊断包失败负载。

        :param plugin_id: 插件ID
        :param info_payload: 插件详情负载
        :return: 插件诊断包失败负载
        """
        return PluginRuntimeDiagnoseFailurePayload(
            ok=False,
            message='插件诊断包生成失败',
            plugin_id=plugin_id,
            info=dict(info_payload),
        ).to_payload()

    @staticmethod
    def build_empty_menu_plan() -> PluginMenuDiagnosticPlanPayload:
        """
        构建空插件菜单诊断计划。

        :return: 空插件菜单诊断计划
        """
        return {'total': 0, 'permissionCount': 0, 'enabledCount': 0, 'visibleCount': 0, 'items': []}

    @staticmethod
    def build_diagnose_payload(
        plugin_id: str,
        *,
        info_payload: Mapping[str, object],
        check_payload: Mapping[str, object],
        menu_plan: PluginMenuDiagnosticPlanPayload,
        config_payload: Mapping[str, object],
        audit_payload: Mapping[str, object],
    ) -> PluginRuntimeDiagnosePayloadDict:
        """
        构建插件诊断包负载。

        :param plugin_id: 插件ID
        :param info_payload: 插件详情负载
        :param check_payload: 插件检查负载
        :param menu_plan: 菜单诊断计划
        :param config_payload: 配置诊断负载
        :param audit_payload: 最近审计负载
        :return: 插件诊断包负载
        """
        ok = bool(info_payload.get('ok')) and bool(check_payload.get('ok')) and bool(config_payload.get('ok'))
        return PluginRuntimeDiagnosePayload(
            ok=ok,
            message='插件诊断包生成完成' if ok else '插件诊断包生成完成，发现问题',
            plugin_id=plugin_id,
            info=info_payload.get('plugin'),
            check=dict(check_payload),
            menu_plan=dict(menu_plan),
            config=dict(config_payload),
            audit=dict(audit_payload),
        ).to_payload()

    @staticmethod
    def build_precheck_payload(
        plugin_id: str,
        operation: PluginBatchOperation,
        *,
        precheck: PluginRuntimePrecheckProtocol,
        version_state: VersionStatePayload,
        actions: list[ActionPayload],
        database_error: str | None,
        purge_plan: PluginPurgePlan | None = None,
        purge_plan_error: str | None = None,
    ) -> PluginRuntimePrecheckPayloadDict:
        """
        构建插件操作预检负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param precheck: 插件操作预检上下文
        :param version_state: 插件升级版本状态
        :param actions: 操作动作清单
        :param database_error: 数据库状态读取错误信息
        :param purge_plan: 插件物理清理计划
        :param purge_plan_error: 插件物理清理计划构建错误
        :return: 插件操作预检负载
        """
        check_payload = dict(precheck.check_payload)
        if purge_plan_error:
            check_payload['warnings'] = [
                *[str(warning) for warning in check_payload.get('warnings', [])],
                f'插件物理清理计划构建失败：{purge_plan_error}',
            ]
        payload: PluginRuntimePrecheckPayloadDict = {
            'ok': precheck.ok and purge_plan_error is None,
            'message': '插件操作预检通过' if precheck.ok and purge_plan_error is None else '插件操作预检存在问题',
            'pluginId': plugin_id,
            'operation': operation,
            'databaseAvailable': database_error is None,
            'databaseError': database_error,
            'purgePlanError': purge_plan_error,
            **version_state,
            'actions': actions,
            **precheck.operation_payload,
            'precheck': check_payload,
        }
        if purge_plan:
            payload['plan'] = PluginPayloadBuilder.build_purge_plan(purge_plan)

        result = PluginRuntimePrecheckPayload.model_validate(payload).to_payload()
        if purge_plan_error is None:
            result.pop('purgePlanError', None)
        return result

    @staticmethod
    def build_health_payload(health_result: PluginHealthResultProtocol) -> PluginRuntimeHealthPayloadDict:
        """
        构建插件健康检查负载。

        :param health_result: 插件健康检查结果
        :return: 插件健康检查负载
        """
        return PluginRuntimeHealthPayload(
            plugin_id=health_result.plugin_id,
            ok=health_result.ok,
            status=health_result.status,
            message=health_result.message,
            checker=health_result.checker,
            duration_ms=health_result.duration_ms,
            details=health_result.details,
            error=health_result.error,
        ).to_payload()

    @staticmethod
    def build_failure_state_message(payload: Mapping[str, object], default_message: str) -> str:
        """
        构建插件失败状态错误信息。

        :param payload: 插件操作返回负载
        :param default_message: 缺省失败信息
        :return: 失败状态错误信息
        """
        message = payload.get('message') or default_message
        error = payload.get('error')
        if error:
            return f'{message}：{error}'[:1000]

        return str(message)[:1000]

    @staticmethod
    def build_precheck_actions(
        operation: PluginBatchOperation,
        discovered_plugin: DiscoveredPlugin,
        precheck: PluginRuntimePrecheckProtocol,
    ) -> list[ActionPayload]:
        """
        构建插件操作预检动作清单。

        :param operation: 操作类型
        :param discovered_plugin: 已发现插件
        :param precheck: 插件操作预检上下文
        :return: 动作清单
        """
        if operation == 'install':
            return PluginPayloadBuilder.build_install_actions(
                discovered_plugin,
                precheck.dependency_result.ok,
                precheck.plugin_dependency_result.ok,
                precheck.structure_result.ok,
                precheck.menu_conflict_result.ok,
            )
        if operation == 'upgrade':
            return PluginPayloadBuilder.build_upgrade_actions(
                discovered_plugin,
                precheck.dependency_result.ok,
                precheck.plugin_dependency_result.ok,
                precheck.structure_result.ok,
                precheck.menu_conflict_result.ok,
            )
        if operation == 'enable':
            return PluginPayloadBuilder.build_enabled_actions(True, precheck.plugin_dependency_result.ok)
        if operation == 'uninstall':
            return PluginPayloadBuilder.build_enabled_actions(False, True)

        return [{'name': 'build_purge_plan', 'label': '生成插件物理清理计划', 'enabled': True}]

    @staticmethod
    def build_upgrade_pre_execution_blocker(
        plugin_id: str,
        version_state: VersionStatePayload,
        actions: list[ActionPayload],
        precheck: PluginRuntimePrecheckProtocol,
    ) -> PluginRuntimeUpgradeBlockerPayloadDict | None:
        """
        构建插件升级前置阻断负载。

        :param plugin_id: 插件ID
        :param version_state: 插件升级版本状态
        :param actions: 升级动作计划
        :param precheck: 插件操作预检上下文
        :return: 阻断负载，不需要阻断时返回 None
        """
        if not version_state['installed']:
            return PluginRuntimePayloadBuilder._build_upgrade_blocker_payload(
                plugin_id=plugin_id,
                message='插件尚未安装，升级已中止',
                version_state=version_state,
                actions=actions,
                precheck=precheck,
            )
        if not precheck.manifest_result.ok:
            return PluginRuntimePayloadBuilder._build_upgrade_blocker_payload(
                plugin_id=plugin_id,
                message='插件 manifest 检查失败，升级已中止',
                version_state=version_state,
                actions=actions,
                precheck=precheck,
            )

        return None

    @staticmethod
    def _build_upgrade_blocker_payload(
        *,
        plugin_id: str,
        message: str,
        version_state: VersionStatePayload,
        actions: list[ActionPayload],
        precheck: PluginRuntimePrecheckProtocol,
    ) -> PluginRuntimeUpgradeBlockerPayloadDict:
        """
        构建插件升级前置阻断负载。

        :param plugin_id: 插件ID
        :param message: 阻断提示
        :param version_state: 插件升级版本状态
        :param actions: 升级动作计划
        :param precheck: 插件操作预检上下文
        :return: 插件升级前置阻断负载
        """
        return PluginRuntimeUpgradeBlockerPayload.model_validate(
            {
                'ok': False,
                'message': message,
                'pluginId': plugin_id,
                'dryRun': False,
                **version_state,
                'actions': actions,
                **precheck.operation_payload,
            }
        ).to_payload()
