from dataclasses import dataclass
from typing import Any

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.purge import PluginPurgePlan
from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, RUNTIME_ERROR, SUCCESS
from plugins.core.validation.plugin_deps import PluginBatchOperation

from .payload import PluginPayloadBuilder
from .precheck import PluginPrecheckContext


@dataclass(frozen=True)
class PluginRuntimeDiagnosePayload:
    """
    插件诊断包结构化负载。
    """

    plugin_id: str
    info_payload: dict[str, Any]
    check_payload: dict[str, Any]
    menu_plan: dict[str, Any]
    config_payload: dict[str, Any]
    audit_payload: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件诊断包 payload 契约。

        :return: 插件诊断包 payload
        """
        ok = (
            bool(self.info_payload.get('ok'))
            and bool(self.check_payload.get('ok'))
            and bool(self.config_payload.get('ok'))
        )
        return {
            'ok': ok,
            'message': '插件诊断包生成完成' if ok else '插件诊断包生成完成，发现问题',
            'pluginId': self.plugin_id,
            'info': self.info_payload.get('plugin'),
            'check': self.check_payload,
            'menuPlan': self.menu_plan,
            'config': self.config_payload,
            'audit': self.audit_payload,
            'exit_code': SUCCESS if ok else DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginRuntimeHealthPayload:
    """
    插件健康检查结构化负载。
    """

    health_result: Any

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件健康检查 payload 契约。

        :return: 插件健康检查 payload
        """
        return {
            'pluginId': self.health_result.plugin_id,
            'ok': self.health_result.ok,
            'status': self.health_result.status,
            'message': self.health_result.message,
            'checker': self.health_result.checker,
            'durationMs': self.health_result.duration_ms,
            'details': self.health_result.details,
            'error': self.health_result.error,
        }


@dataclass(frozen=True)
class PluginRuntimeHealthResponsePayload:
    """
    插件健康检查响应结构化负载。
    """

    plugin_id: str
    health_result: Any

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件健康检查响应 payload 契约。

        :return: 插件健康检查响应 payload
        """
        return {
            'ok': self.health_result.ok,
            'message': self.health_result.message,
            'pluginId': self.plugin_id,
            'health': PluginRuntimeHealthPayload(self.health_result).to_payload(),
            'exit_code': SUCCESS if self.health_result.ok else DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginRuntimePrecheckPayload:
    """
    插件操作预检结构化负载。
    """

    plugin_id: str
    operation: PluginBatchOperation
    precheck: PluginPrecheckContext
    version_state: dict[str, Any]
    actions: list[dict[str, Any]]
    database_error: str | None
    purge_plan: PluginPurgePlan | None = None

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件操作预检 payload 契约。

        :return: 插件操作预检 payload
        """
        payload = {
            'ok': self.precheck.ok,
            'message': '插件操作预检通过' if self.precheck.ok else '插件操作预检存在问题',
            'pluginId': self.plugin_id,
            'operation': self.operation,
            'databaseAvailable': self.database_error is None,
            'databaseError': self.database_error,
            **self.version_state,
            'actions': self.actions,
            **self.precheck.operation_payload,
            'precheck': self.precheck.check_payload,
            'exit_code': SUCCESS if self.precheck.ok else DEPENDENCY_ERROR,
        }
        if self.purge_plan:
            payload['plan'] = PluginPayloadBuilder.build_purge_plan(self.purge_plan)

        return payload


@dataclass(frozen=True)
class PluginRuntimeExceptionPayload:
    """
    插件运行时异常结构化负载。
    """

    message: str
    error: Exception

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件运行时异常 payload 契约。

        :return: 插件运行时异常 payload
        """
        return {
            'ok': False,
            'message': self.message,
            'error': str(self.error),
            'exit_code': RUNTIME_ERROR,
        }


@dataclass(frozen=True)
class PluginRuntimeInvalidOperationPayload:
    """
    插件非法操作结构化负载。
    """

    plugin_id: str | None
    operation: str
    message: str

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件非法操作 payload 契约。

        :return: 插件非法操作 payload
        """
        payload: dict[str, Any] = {
            'ok': False,
            'message': self.message,
            'operation': self.operation,
            'exit_code': RUNTIME_ERROR,
        }
        if self.plugin_id is not None:
            payload['pluginId'] = self.plugin_id

        return payload


@dataclass(frozen=True)
class PluginRuntimeBatchItemUnsupportedPayload:
    """
    插件批量单项不支持结构化负载。
    """

    operation: PluginBatchOperation
    plugin_id: str

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件批量单项不支持 payload 契约。

        :return: 插件批量单项不支持 payload
        """
        return {
            'ok': False,
            'message': f'插件批量操作不支持：{self.operation}',
            'pluginId': self.plugin_id,
            'exit_code': RUNTIME_ERROR,
        }


@dataclass(frozen=True)
class PluginRuntimeDiagnoseFailurePayload:
    """
    插件诊断包失败结构化负载。
    """

    plugin_id: str
    info_payload: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件诊断包失败 payload 契约。

        :return: 插件诊断包失败 payload
        """
        return {
            'ok': False,
            'message': '插件诊断包生成失败',
            'pluginId': self.plugin_id,
            'info': self.info_payload,
            'exit_code': self.info_payload.get('exit_code', RUNTIME_ERROR),
        }


@dataclass(frozen=True)
class PluginRuntimeUpgradeBlockerPayload:
    """
    插件升级前置阻断结构化负载。
    """

    plugin_id: str
    message: str
    version_state: dict[str, Any]
    actions: list[dict[str, Any]]
    precheck: PluginPrecheckContext
    exit_code: int

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件升级前置阻断 payload 契约。

        :return: 插件升级前置阻断 payload
        """
        return {
            'ok': False,
            'message': self.message,
            'pluginId': self.plugin_id,
            'dryRun': False,
            **self.version_state,
            'actions': self.actions,
            **self.precheck.operation_payload,
            'exit_code': self.exit_code,
        }


class PluginRuntimePayloadBuilder:
    """
    插件运行时通用负载构建器。
    """

    @staticmethod
    def build_exception_payload(message: str, error: Exception) -> dict[str, Any]:
        """
        构建运行时异常负载。

        :param message: 异常场景提示
        :param error: 异常对象
        :return: 运行时异常负载
        """
        return PluginRuntimeExceptionPayload(message, error).to_payload()

    @staticmethod
    def build_invalid_operation_payload(
        plugin_id: str | None,
        operation: str,
        *,
        message: str,
    ) -> dict[str, Any]:
        """
        构建非法操作负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param message: 错误提示
        :return: 非法操作负载
        """
        return PluginRuntimeInvalidOperationPayload(plugin_id, operation, message).to_payload()

    @staticmethod
    def build_health_response_payload(plugin_id: str, health_result: Any) -> dict[str, Any]:
        """
        构建插件健康检查响应负载。

        :param plugin_id: 插件ID
        :param health_result: 插件健康检查结果
        :return: 插件健康检查响应负载
        """
        return PluginRuntimeHealthResponsePayload(plugin_id, health_result).to_payload()

    @staticmethod
    def build_batch_item_unsupported_payload(operation: PluginBatchOperation, plugin_id: str) -> dict[str, Any]:
        """
        构建批量单项不支持负载。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 批量单项不支持负载
        """
        return PluginRuntimeBatchItemUnsupportedPayload(operation, plugin_id).to_payload()

    @staticmethod
    def build_diagnose_failure_payload(plugin_id: str, info_payload: dict[str, Any]) -> dict[str, Any]:
        """
        构建插件诊断包失败负载。

        :param plugin_id: 插件ID
        :param info_payload: 插件详情负载
        :return: 插件诊断包失败负载
        """
        return PluginRuntimeDiagnoseFailurePayload(plugin_id, info_payload).to_payload()

    @staticmethod
    def build_empty_menu_plan() -> dict[str, Any]:
        """
        构建空插件菜单诊断计划。

        :return: 空插件菜单诊断计划
        """
        return {'total': 0, 'permissionCount': 0, 'enabledCount': 0, 'visibleCount': 0, 'items': []}

    @staticmethod
    def build_diagnose_payload(
        plugin_id: str,
        *,
        info_payload: dict[str, Any],
        check_payload: dict[str, Any],
        menu_plan: dict[str, Any],
        config_payload: dict[str, Any],
        audit_payload: dict[str, Any],
    ) -> dict[str, Any]:
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
        return PluginRuntimeDiagnosePayload(
            plugin_id=plugin_id,
            info_payload=info_payload,
            check_payload=check_payload,
            menu_plan=menu_plan,
            config_payload=config_payload,
            audit_payload=audit_payload,
        ).to_payload()

    @staticmethod
    def build_precheck_payload(
        plugin_id: str,
        operation: PluginBatchOperation,
        *,
        precheck: PluginPrecheckContext,
        version_state: dict[str, Any],
        actions: list[dict[str, Any]],
        database_error: str | None,
        purge_plan: PluginPurgePlan | None = None,
    ) -> dict[str, Any]:
        """
        构建插件操作预检负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param precheck: 插件操作预检上下文
        :param version_state: 插件升级版本状态
        :param actions: 操作动作清单
        :param database_error: 数据库状态读取错误信息
        :param purge_plan: 插件物理清理计划
        :return: 插件操作预检负载
        """
        return PluginRuntimePrecheckPayload(
            plugin_id=plugin_id,
            operation=operation,
            precheck=precheck,
            version_state=version_state,
            actions=actions,
            database_error=database_error,
            purge_plan=purge_plan,
        ).to_payload()

    @staticmethod
    def build_health_payload(health_result: Any) -> dict[str, Any]:
        """
        构建插件健康检查负载。

        :param health_result: 插件健康检查结果
        :return: 插件健康检查负载
        """
        return PluginRuntimeHealthPayload(health_result).to_payload()

    @staticmethod
    def build_failure_state_message(payload: dict[str, Any], default_message: str) -> str:
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
        precheck: PluginPrecheckContext,
    ) -> list[dict[str, Any]]:
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
        version_state: dict[str, Any],
        actions: list[dict[str, Any]],
        precheck: PluginPrecheckContext,
    ) -> dict[str, Any] | None:
        """
        构建插件升级前置阻断负载。

        :param plugin_id: 插件ID
        :param version_state: 插件升级版本状态
        :param actions: 升级动作计划
        :param precheck: 插件操作预检上下文
        :return: 阻断负载，不需要阻断时返回 None
        """
        if not version_state['installed']:
            return PluginRuntimeUpgradeBlockerPayload(
                plugin_id=plugin_id,
                message='插件尚未安装，升级已中止',
                version_state=version_state,
                actions=actions,
                precheck=precheck,
                exit_code=RUNTIME_ERROR,
            ).to_payload()
        if not precheck.manifest_result.ok:
            return PluginRuntimeUpgradeBlockerPayload(
                plugin_id=plugin_id,
                message='插件 manifest 检查失败，升级已中止',
                version_state=version_state,
                actions=actions,
                precheck=precheck,
                exit_code=DEPENDENCY_ERROR,
            ).to_payload()

        return None
