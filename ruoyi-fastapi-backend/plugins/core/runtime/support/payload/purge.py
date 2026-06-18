from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from pydantic import Field

from . import PluginPayloadBuilder
from .base import PluginPayloadModel

if TYPE_CHECKING:
    from plugins.core.lifecycle.purge import PluginPurgePlan


class PluginPurgeStatePayload(PluginPayloadModel):
    """
    插件物理清理状态 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    operation: str
    dry_run: bool = Field(alias='dryRun')
    safe_mode: bool = Field(alias='safeMode')
    removes_source: bool = Field(alias='removesSource')
    plan: dict[str, object]
    hooks: list[dict[str, object]] | None = None


PluginPurgeStatePayloadDict: TypeAlias = dict[str, object]


class PluginPurgePayloadBuilder:
    """
    插件物理清理负载构建器。

    使用 Builder 模式集中 purge dry-run 和执行成功负载。
    """

    @staticmethod
    def build_dry_run_payload(plugin_id: str, plan: PluginPurgePlan) -> PluginPurgeStatePayloadDict:
        """
        构建插件物理清理预演负载。

        :param plugin_id: 插件ID
        :param plan: 插件物理清理计划
        :return: 插件物理清理预演负载
        """
        return PluginPurgePayloadBuilder._build_state_payload(
            plugin_id=plugin_id,
            plan=plan,
            dry_run=True,
            message='插件物理清理演练完成，未执行实际删除',
        )

    @staticmethod
    def build_success_payload(
        plugin_id: str,
        plan: PluginPurgePlan,
        hook_result: object | None,
    ) -> PluginPurgeStatePayloadDict:
        """
        构建插件物理清理成功负载。

        :param plugin_id: 插件ID
        :param plan: 插件物理清理计划
        :param hook_result: 清理钩子执行结果
        :return: 插件物理清理成功负载
        """
        return PluginPurgePayloadBuilder._build_state_payload(
            plugin_id=plugin_id,
            plan=plan,
            dry_run=False,
            message='插件物理清理完成',
            hook_result=hook_result,
        )

    @staticmethod
    def _build_state_payload(
        *,
        plugin_id: str,
        plan: PluginPurgePlan,
        dry_run: bool,
        message: str,
        hook_result: object | None = None,
    ) -> PluginPurgeStatePayloadDict:
        """
        构建插件物理清理状态负载。

        :param plugin_id: 插件ID
        :param plan: 插件物理清理计划
        :param dry_run: 是否预演
        :param message: 响应消息
        :param hook_result: 清理钩子执行结果
        :return: 插件物理清理状态负载
        """
        payload: PluginPurgeStatePayloadDict = {
            'ok': True,
            'message': message,
            'pluginId': plugin_id,
            'operation': 'purge',
            'dryRun': dry_run,
            'safeMode': False,
            'removesSource': plan.removes_source,
            'plan': PluginPayloadBuilder.build_purge_plan(plan),
        }
        if not dry_run:
            payload['hooks'] = [vars(hook_result)] if hook_result else []
        return PluginPurgeStatePayload.model_validate(payload).to_payload(exclude_none=True)
