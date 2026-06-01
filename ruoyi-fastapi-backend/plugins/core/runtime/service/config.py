from typing import Any

from plugins.core.runtime.support import (
    PluginConfigPayloadBuilder,
    PluginPayloadBuilder,
    PluginRuntimePayloadBuilder,
)


class PluginConfigOperationMixin:
    """
    插件配置读取、导出、更新和导入操作。
    """

    async def get_plugin_config(self, plugin_id: str, *, reveal_secret: bool = False) -> dict[str, Any]:
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

            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
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

    async def export_plugin_config(self, plugin_id: str, *, reveal_secret: bool = False) -> dict[str, Any]:
        """
        导出插件配置快照。

        :param plugin_id: 插件ID
        :param reveal_secret: 是否导出敏感配置明文
        :return: 插件配置导出负载
        """
        payload = await self.get_plugin_config(plugin_id, reveal_secret=reveal_secret)
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
        values: dict[str, Any],
        *,
        audit_operation: str = 'config_set',
        success_message: str = '插件配置已更新',
    ) -> dict[str, Any]:
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

            async_session_local = self.infrastructure_gateway.get_async_session_local()
            plugin_service = self.infrastructure_gateway.get_plugin_service()
            async with async_session_local() as session:
                before_configs = await plugin_service.get_plugin_config_services(
                    session,
                    discovered_plugin,
                    reveal_secret=True,
                )
                configs = await plugin_service.update_plugin_config_services(
                    session,
                    discovered_plugin,
                    self.infrastructure_gateway.build_config_update(values),
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

    async def import_plugin_config(self, plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """
        导入插件配置。

        :param plugin_id: 插件ID
        :param values: 待导入配置键值
        :return: 插件配置导入负载
        """
        payload = await self.set_plugin_config(
            plugin_id,
            values,
            audit_operation='config_import',
            success_message='插件配置导入完成',
        )
        return PluginConfigPayloadBuilder.build_import_payload(plugin_id, payload, values)
