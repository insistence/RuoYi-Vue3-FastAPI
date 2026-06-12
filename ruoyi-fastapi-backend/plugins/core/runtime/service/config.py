from typing import cast

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.support import (
    PluginConfigPayloadBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)
from plugins.core.types import PluginConfigValue

from .context import PluginRuntimeContextService
from .dependency_container import PluginRuntimeDependencies
from .responses import PluginConfigExportResponse, PluginConfigImportResponse, PluginConfigStateResponse


class PluginConfigUseCase:
    """
    插件配置 use case。
    """

    def __init__(self, dependencies: PluginRuntimeDependencies, context: PluginRuntimeContextService) -> None:
        """
        初始化插件配置 use case。

        :param dependencies: 插件运行时依赖容器
        :param context: 插件运行时上下文服务
        """
        self.dependencies = dependencies
        self.context = context

    def _get_discovered_plugin(self, plugin_id: str) -> DiscoveredPlugin | None:
        """
        根据插件 ID 获取已发现插件。

        :param plugin_id: 插件ID
        :return: 已发现插件对象
        """
        return self.context.get_discovered_plugin(plugin_id)

    async def get_plugin_config(self, plugin_id: str, *, reveal_secret: bool = False) -> PluginConfigStateResponse:
        """
        获取插件配置。

        :param plugin_id: 插件ID
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)

            gateway = self.dependencies.state_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                configs = await plugin_service.get_plugin_config_services(
                    session,
                    discovered_plugin,
                    reveal_secret=reveal_secret,
                )
                await session.commit()

            return PluginConfigPayloadBuilder.build_read_payload(plugin_id, configs)
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('读取插件配置失败', exc)

    async def export_plugin_config(self, plugin_id: str, *, reveal_secret: bool = False) -> PluginConfigExportResponse:
        """
        导出插件配置快照。

        :param plugin_id: 插件ID
        :param reveal_secret: 是否导出敏感配置明文
        :return: 插件配置导出负载
        """
        payload = cast('dict[str, object]', await self.get_plugin_config(plugin_id, reveal_secret=reveal_secret))
        if not payload.get('ok', False):
            return PluginConfigPayloadBuilder.build_export_failure_payload(
                plugin_id,
                payload,
                reveal_secret=reveal_secret,
            )

        configs = payload.get('configs') if isinstance(payload.get('configs'), list) else []
        return PluginConfigPayloadBuilder.build_export_payload(plugin_id, configs, reveal_secret=reveal_secret)

    async def set_plugin_config(
        self,
        plugin_id: str,
        values: dict[str, PluginConfigValue],
        *,
        audit_operation: str = 'config_set',
        success_message: str = '插件配置已更新',
    ) -> PluginConfigStateResponse:
        """
        更新插件配置。

        :param plugin_id: 插件ID
        :param values: 配置键值
        :param audit_operation: 审计操作类型
        :param success_message: 操作成功提示
        :return: 插件配置更新负载
        """
        try:
            discovered_plugin = self._get_discovered_plugin(plugin_id)
            if not discovered_plugin:
                return PluginPayloadBuilder.build_plugin_not_found_payload(plugin_id)

            gateway = self.dependencies.state_gateway
            model_gateway = self.dependencies.model_gateway
            async_session_local = gateway.get_async_session_local()
            plugin_service = gateway.get_plugin_service()
            async with async_session_local() as session:
                before_configs = await plugin_service.get_plugin_config_services(
                    session,
                    discovered_plugin,
                    reveal_secret=True,
                )
                configs = await plugin_service.update_plugin_config_services(
                    session,
                    discovered_plugin,
                    model_gateway.build_config_update(values),
                )
                audit_payload = PluginConfigPayloadBuilder.build_audit_payload(
                    plugin_id,
                    operation=audit_operation,
                    values=values,
                    before_configs=before_configs,
                    after_configs=configs,
                    message=success_message,
                )
                await plugin_service.add_plugin_operation_log_services(
                    session,
                    audit_payload,
                    dry_run=False,
                    continue_on_error=False,
                )
                await session.commit()

            return PluginConfigPayloadBuilder.build_update_payload(
                plugin_id,
                operation=audit_operation,
                message=success_message,
                configs=configs,
            )
        except Exception as exc:
            return PluginRuntimePayloadBuilder.build_exception_payload('更新插件配置失败', exc)

    async def import_plugin_config(
        self, plugin_id: str, values: dict[str, PluginConfigValue]
    ) -> PluginConfigImportResponse:
        """
        导入插件配置。

        :param plugin_id: 插件ID
        :param values: 待导入配置键值
        :return: 插件配置导入负载
        """
        payload = cast(
            'dict[str, object]',
            await self.set_plugin_config(
                plugin_id,
                values,
                audit_operation='config_import',
                success_message='插件配置导入完成',
            ),
        )
        return PluginConfigPayloadBuilder.build_import_payload(plugin_id, payload, values)
