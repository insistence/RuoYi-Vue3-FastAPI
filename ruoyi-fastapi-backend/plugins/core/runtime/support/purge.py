from dataclasses import dataclass
from typing import Any

from plugins.core.lifecycle.purge import PluginPurgePlan

from .payload import PluginPayloadBuilder


@dataclass(frozen=True)
class PluginPurgeStatePayload:
    """
    插件物理清理状态结构化负载。
    """

    plugin_id: str
    plan: PluginPurgePlan
    dry_run: bool
    message: str
    hook_result: Any | None = None

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为现有插件物理清理 payload 契约。

        :return: 插件物理清理 payload
        """
        payload = {
            'ok': True,
            'message': self.message,
            'pluginId': self.plugin_id,
            'operation': 'purge',
            'dryRun': self.dry_run,
            'safeMode': False,
            'removesSource': self.plan.removes_source,
            'plan': PluginPayloadBuilder.build_purge_plan(self.plan),
        }
        if not self.dry_run:
            payload['hooks'] = [self.hook_result.__dict__] if self.hook_result else []
        return payload


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
        return PluginPurgeStatePayload(
            plugin_id=plugin_id,
            plan=plan,
            dry_run=True,
            message='插件物理清理演练完成，未执行实际删除',
        ).to_payload()

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
        return PluginPurgeStatePayload(
            plugin_id=plugin_id,
            plan=plan,
            dry_run=False,
            message='插件物理清理完成',
            hook_result=hook_result,
        ).to_payload()
