from typing import Any

from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, RUNTIME_ERROR
from plugins.core.validation.plugin_deps import PluginDependencyCheckResult

from .payload import PluginPayloadBuilder


class PluginEnablePayloadBuilder:
    """
    插件启停负载构建器。

    使用 Builder 模式集中启用、停用和安全卸载的负载拼装。
    """

    @classmethod
    def build_dependency_payload(cls, plugin_dependency_result: PluginDependencyCheckResult) -> dict[str, Any]:
        """
        构建插件启用依赖检查负载。

        :param plugin_dependency_result: 插件间依赖检查结果
        :return: 插件启用依赖检查负载
        """
        return {
            'pluginDependencyOk': plugin_dependency_result.ok,
            'pluginDependencyErrors': [
                PluginPayloadBuilder.build_plugin_dependency_item(item)
                for item in plugin_dependency_result.failed_items
            ],
            'pluginDependencies': [
                PluginPayloadBuilder.build_plugin_dependency_item(item) for item in plugin_dependency_result.items
            ],
        }

    @staticmethod
    def build_dependency_blocker_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        dependency_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        构建插件启用依赖阻断负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param dependency_payload: 插件依赖检查负载
        :return: 插件启用依赖阻断负载
        """
        plugin_dependency_ok = bool(dependency_payload.get('pluginDependencyOk', True))
        return {
            'ok': False,
            'message': '插件间依赖检查失败，启用已中止',
            'pluginId': plugin_id,
            'operation': operation,
            'enabled': enabled,
            'dryRun': False,
            'actions': PluginPayloadBuilder.build_enabled_actions(enabled, plugin_dependency_ok),
            **dependency_payload,
            'exit_code': DEPENDENCY_ERROR,
        }

    @staticmethod
    def build_dry_run_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        dependency_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        构建插件启停预演负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param dependency_payload: 插件依赖检查负载
        :return: 插件启停预演负载
        """
        plugin_dependency_ok = bool(dependency_payload.get('pluginDependencyOk', True))
        return {
            'ok': True,
            'message': '插件启停演练完成，未执行实际写入',
            'pluginId': plugin_id,
            'operation': operation,
            'enabled': enabled,
            'dryRun': True,
            'actions': PluginPayloadBuilder.build_enabled_actions(enabled, plugin_dependency_ok),
            **dependency_payload,
        }

    @staticmethod
    def build_update_failure_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        message: str,
    ) -> dict[str, Any]:
        """
        构建插件启停写入失败负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param message: 失败提示
        :return: 插件启停写入失败负载
        """
        return {
            'ok': False,
            'message': message,
            'pluginId': plugin_id,
            'operation': operation,
            'enabled': enabled,
            'dryRun': False,
            'exit_code': RUNTIME_ERROR,
        }

    @staticmethod
    def build_success_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        message: str,
        dependency_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        构建插件启停成功负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param message: 成功提示
        :param dependency_payload: 插件依赖检查负载
        :return: 插件启停成功负载
        """
        plugin_dependency_ok = bool(dependency_payload.get('pluginDependencyOk', True))
        return {
            'ok': True,
            'message': message,
            'pluginId': plugin_id,
            'operation': operation,
            'enabled': enabled,
            'dryRun': False,
            'actions': PluginPayloadBuilder.build_enabled_actions(enabled, plugin_dependency_ok),
            **dependency_payload,
        }

    @staticmethod
    def build_uninstall_payload(result: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        """
        构建插件安全卸载负载。

        :param result: 插件停用结果负载
        :param dry_run: 是否预演
        :return: 插件安全卸载负载
        """
        return {
            **result,
            'operation': 'uninstall',
            'message': '插件卸载演练完成，未执行实际写入' if dry_run else result.get('message', '插件卸载完成'),
            'safeMode': True,
            'removesSource': False,
            'removesMenus': True,
        }
