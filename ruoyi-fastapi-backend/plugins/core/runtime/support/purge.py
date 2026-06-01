from typing import Any

from plugins.core.lifecycle.purge import PluginPurgePlan

from .payload import PluginPayloadBuilder


class PluginPurgePayloadBuilder:
    """
    插件物理清理负载构建器。

    使用 Builder 模式集中 purge dry-run 和执行成功负载。
    """

    @staticmethod
    def build_dry_run_payload(plugin_id: str, plan: PluginPurgePlan) -> dict[str, Any]:
        """
        构建插件物理清理预演负载。

        :param plugin_id: 插件ID
        :param plan: 插件物理清理计划
        :return: 插件物理清理预演负载
        """
        return {
            'ok': True,
            'message': '插件物理清理演练完成，未执行实际删除',
            'pluginId': plugin_id,
            'operation': 'purge',
            'dryRun': True,
            'safeMode': False,
            'removesSource': plan.removes_source,
            'plan': PluginPayloadBuilder.build_purge_plan(plan),
        }

    @staticmethod
    def build_success_payload(
        plugin_id: str,
        plan: PluginPurgePlan,
        hook_result: Any | None,
    ) -> dict[str, Any]:
        """
        构建插件物理清理成功负载。

        :param plugin_id: 插件ID
        :param plan: 插件物理清理计划
        :param hook_result: 清理钩子执行结果
        :return: 插件物理清理成功负载
        """
        return {
            'ok': True,
            'message': '插件物理清理完成',
            'pluginId': plugin_id,
            'operation': 'purge',
            'dryRun': False,
            'safeMode': False,
            'removesSource': plan.removes_source,
            'plan': PluginPayloadBuilder.build_purge_plan(plan),
            'hooks': [hook_result.__dict__] if hook_result else [],
        }
