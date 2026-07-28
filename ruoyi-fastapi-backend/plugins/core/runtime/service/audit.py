from collections.abc import Mapping

from plugins.core.runtime.support import PluginRuntimePayloadBuilder
from utils.log_util import logger

from .dependency_container import PluginRuntimeDependencies


class PluginAuditUseCase:
    """
    插件操作审计和失败状态记录 use case。
    """

    def __init__(self, dependencies: PluginRuntimeDependencies) -> None:
        """
        初始化插件审计 use case。

        :param dependencies: 插件运行时依赖容器
        """
        self.dependencies = dependencies

    async def record_plugin_operation_log(
        self,
        payload: Mapping[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """
        记录插件操作审计日志。

        dry-run 不调用该方法，保持预演无写入语义。

        :param payload: 插件操作结果负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: None
        """
        await self.dependencies.audit_gateway.add_plugin_operation_log(
            dict(payload),
            dry_run=dry_run,
            continue_on_error=continue_on_error,
        )

    async def record_plugin_failure_state(
        self,
        payload: Mapping[str, object],
        default_message: str,
    ) -> None:
        """
        记录插件操作失败状态。

        失败状态写入仅作为可恢复运行状态提示，不改变原始操作返回结果。

        :param payload: 插件操作返回负载
        :param default_message: 缺省失败信息
        :return: None
        """
        if payload.get('ok') is not False:
            return
        plugin_id = payload.get('pluginId')
        if not isinstance(plugin_id, str) or not plugin_id:
            return

        error_message = PluginRuntimePayloadBuilder.build_failure_state_message(payload, default_message)
        try:
            await self.dependencies.audit_gateway.mark_plugin_error(plugin_id, error_message)
        except Exception:
            logger.exception('记录插件失败状态失败：plugin_id=%s', plugin_id)
            return
