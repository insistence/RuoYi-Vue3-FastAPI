from typing import Any

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.lifecycle.purge import PluginPurgePlan
from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, RUNTIME_ERROR, SUCCESS
from plugins.core.validation.plugin_deps import PluginBatchOperation

from .payload import PluginPayloadBuilder
from .precheck import PluginPrecheckContext


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
        return {
            'ok': False,
            'message': message,
            'error': str(error),
            'exit_code': RUNTIME_ERROR,
        }

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
        payload: dict[str, Any] = {
            'ok': False,
            'message': message,
            'operation': operation,
            'exit_code': RUNTIME_ERROR,
        }
        if plugin_id is not None:
            payload['pluginId'] = plugin_id

        return payload

    @staticmethod
    def build_health_response_payload(plugin_id: str, health_result: Any) -> dict[str, Any]:
        """
        构建插件健康检查响应负载。

        :param plugin_id: 插件ID
        :param health_result: 插件健康检查结果
        :return: 插件健康检查响应负载
        """
        return {
            'ok': health_result.ok,
            'message': health_result.message,
            'pluginId': plugin_id,
            'health': PluginRuntimePayloadBuilder.build_health_payload(health_result),
            'exit_code': SUCCESS if health_result.ok else DEPENDENCY_ERROR,
        }

    @staticmethod
    def build_batch_item_unsupported_payload(operation: PluginBatchOperation, plugin_id: str) -> dict[str, Any]:
        """
        构建批量单项不支持负载。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 批量单项不支持负载
        """
        return {
            'ok': False,
            'message': f'插件批量操作不支持：{operation}',
            'pluginId': plugin_id,
            'exit_code': RUNTIME_ERROR,
        }

    @staticmethod
    def build_diagnose_failure_payload(plugin_id: str, info_payload: dict[str, Any]) -> dict[str, Any]:
        """
        构建插件诊断包失败负载。

        :param plugin_id: 插件ID
        :param info_payload: 插件详情负载
        :return: 插件诊断包失败负载
        """
        return {
            'ok': False,
            'message': '插件诊断包生成失败',
            'pluginId': plugin_id,
            'info': info_payload,
            'exit_code': info_payload.get('exit_code', RUNTIME_ERROR),
        }

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
        ok = bool(info_payload.get('ok')) and bool(check_payload.get('ok')) and bool(config_payload.get('ok'))
        return {
            'ok': ok,
            'message': '插件诊断包生成完成' if ok else '插件诊断包生成完成，发现问题',
            'pluginId': plugin_id,
            'info': info_payload.get('plugin'),
            'check': check_payload,
            'menuPlan': menu_plan,
            'config': config_payload,
            'audit': audit_payload,
            'exit_code': SUCCESS if ok else DEPENDENCY_ERROR,
        }

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
        payload = {
            'ok': precheck.ok,
            'message': '插件操作预检通过' if precheck.ok else '插件操作预检存在问题',
            'pluginId': plugin_id,
            'operation': operation,
            'databaseAvailable': database_error is None,
            'databaseError': database_error,
            **version_state,
            'actions': actions,
            **precheck.operation_payload,
            'precheck': precheck.check_payload,
            'exit_code': SUCCESS if precheck.ok else DEPENDENCY_ERROR,
        }
        if purge_plan:
            payload['plan'] = PluginPayloadBuilder.build_purge_plan(purge_plan)

        return payload

    @staticmethod
    def build_health_payload(health_result: Any) -> dict[str, Any]:
        """
        构建插件健康检查负载。

        :param health_result: 插件健康检查结果
        :return: 插件健康检查负载
        """
        return {
            'pluginId': health_result.plugin_id,
            'ok': health_result.ok,
            'status': health_result.status,
            'message': health_result.message,
            'checker': health_result.checker,
            'durationMs': health_result.duration_ms,
            'details': health_result.details,
            'error': health_result.error,
        }

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
            return {
                'ok': False,
                'message': '插件尚未安装，升级已中止',
                'pluginId': plugin_id,
                'dryRun': False,
                **version_state,
                'actions': actions,
                **precheck.operation_payload,
                'exit_code': RUNTIME_ERROR,
            }
        if not precheck.manifest_result.ok:
            return {
                'ok': False,
                'message': '插件 manifest 检查失败，升级已中止',
                'pluginId': plugin_id,
                'dryRun': False,
                **version_state,
                'actions': actions,
                **precheck.operation_payload,
                'exit_code': DEPENDENCY_ERROR,
            }

        return None
