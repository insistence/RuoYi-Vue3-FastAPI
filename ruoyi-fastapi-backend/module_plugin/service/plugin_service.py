from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.dao.dict_dao import DictDataDao
from plugins.core.management.entity.vo.schemas import (
    PluginOperationLogDetailModel,
    PluginOperationLogExportQueryModel,
)
from plugins.core.management.service.gateway import PluginManagementRuntimeGateway
from plugins.core.management.service.service import PluginService
from plugins.core.runtime.service import PluginRuntimeService


class PluginOperationService:
    """
    插件管理操作服务。

    使用 Facade 模式复用插件应用运行时能力，为插件管理页面接口提供检查、安装和升级入口。
    """

    def __init__(self, runtime_service: PluginRuntimeService | None = None) -> None:
        """
        初始化插件管理操作服务。

        :param runtime_service: 插件运行时服务
        :return: None
        """
        self.runtime_service = runtime_service or PluginRuntimeService(
            infrastructure_gateway=PluginManagementRuntimeGateway(),
        )

    async def check_plugin_services(self, plugin_id: str) -> dict[str, Any]:
        """
        检查插件状态。

        :param plugin_id: 插件ID
        :return: 插件检查结果负载
        """
        return self.runtime_service.check_plugin(plugin_id)

    async def precheck_plugin_services(self, plugin_id: str, operation: str) -> dict[str, Any]:
        """
        执行插件操作预检。

        :param plugin_id: 插件ID
        :param operation: 预检操作类型
        :return: 插件操作预检负载
        """
        return await self.runtime_service.precheck_plugin_operation(plugin_id, operation)

    async def health_plugin_services(self, plugin_id: str) -> dict[str, Any]:
        """
        执行插件健康检查。

        :param plugin_id: 插件ID
        :return: 插件健康检查负载
        """
        return await self.runtime_service.health_plugin(plugin_id)

    async def diagnose_plugin_services(self, plugin_id: str) -> dict[str, Any]:
        """
        生成插件诊断包。

        :param plugin_id: 插件ID
        :return: 插件诊断包负载
        """
        return await self.runtime_service.diagnose_plugin(plugin_id)

    async def generate_plugin_docs_services(self, plugin_id: str) -> dict[str, Any]:
        """
        生成插件 Markdown 文档片段。

        :param plugin_id: 插件ID
        :return: 插件文档生成负载
        """
        return self.runtime_service.generate_plugin_docs(plugin_id)

    async def diagnose_plugin_with_audit_services(
        self,
        query_db: AsyncSession,
        plugin_id: str,
        *,
        audit_limit: int = 5,
    ) -> dict[str, Any]:
        """
        生成包含最近审计记录的插件诊断包。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param audit_limit: 最近审计记录数量
        :return: 插件诊断包负载
        """
        payload = await self.runtime_service.diagnose_plugin(plugin_id)
        payload['audit'] = await self._build_recent_audit_snapshot(query_db, plugin_id, audit_limit=audit_limit)

        return payload

    async def install_plugin_services(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        安装插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件安装结果负载
        """
        return await self.runtime_service.install_plugin(plugin_id, dry_run=dry_run)

    async def upgrade_plugin_services(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        升级插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件升级结果负载
        """
        return await self.runtime_service.upgrade_plugin(plugin_id, dry_run=dry_run)

    async def uninstall_plugin_services(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        安全卸载插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件卸载结果负载
        """
        return await self.runtime_service.uninstall_plugin(plugin_id, dry_run=dry_run)

    async def purge_plugin_services(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        物理清理插件平台元数据。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件物理清理结果负载
        """
        return await self.runtime_service.purge_plugin(plugin_id, dry_run=dry_run)

    async def set_plugin_enabled_services(
        self,
        plugin_id: str,
        *,
        enabled: bool,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        更新插件启停状态。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :return: 插件启停结果负载
        """
        return await self.runtime_service.set_plugin_enabled(plugin_id, enabled=enabled, dry_run=dry_run)

    async def get_plugin_config_services(self, plugin_id: str) -> dict[str, Any]:
        """
        获取插件配置。

        :param plugin_id: 插件ID
        :return: 插件配置负载
        """
        return await self.runtime_service.get_plugin_config(plugin_id)

    async def export_plugin_config_services(self, plugin_id: str, *, reveal_secret: bool = False) -> dict[str, Any]:
        """
        导出插件配置快照。

        :param plugin_id: 插件ID
        :param reveal_secret: 是否导出敏感配置明文
        :return: 插件配置导出负载
        """
        return await self.runtime_service.export_plugin_config(plugin_id, reveal_secret=reveal_secret)

    async def import_plugin_config_services(self, plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """
        导入插件配置。

        :param plugin_id: 插件ID
        :param values: 待导入配置键值
        :return: 插件配置导入负载
        """
        return await self.runtime_service.import_plugin_config(plugin_id, values)

    async def update_plugin_config_services(self, plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """
        更新插件配置。

        :param plugin_id: 插件ID
        :param values: 配置键值
        :return: 插件配置更新负载
        """
        return await self.runtime_service.set_plugin_config(plugin_id, values)

    async def check_plugin_dependencies_services(self, plugin_id: str) -> dict[str, Any]:
        """
        检查插件依赖。

        :param plugin_id: 插件ID
        :return: 插件依赖检查负载
        """
        return self.runtime_service.check_plugin_dependencies(plugin_id)

    async def plan_plugins_services(self, operation: str, plugin_ids: list[str] | None = None) -> dict[str, Any]:
        """
        生成插件批量操作拓扑计划。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :return: 插件批量操作拓扑计划负载
        """
        return self.runtime_service.plan_plugins(operation, plugin_ids)

    async def batch_plugins_services(
        self,
        operation: str,
        plugin_ids: list[str] | None = None,
        *,
        dry_run: bool = True,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        """
        批量执行插件操作。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :param dry_run: 是否仅预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量执行结果负载
        """
        return await self.runtime_service.batch_plugins(
            operation,
            plugin_ids,
            dry_run=dry_run,
            continue_on_error=continue_on_error,
        )

    async def install_plugin_dependencies_services(self, plugin_id: str, *, dry_run: bool = True) -> dict[str, Any]:
        """
        生成或执行插件依赖安装计划。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件依赖安装负载
        """
        return self.runtime_service.install_plugin_dependencies(plugin_id, dry_run=dry_run)

    @classmethod
    async def get_plugin_operation_dict_services(cls, query_db: AsyncSession) -> dict[str, str]:
        """
        获取插件管理页面使用的操作类型字典映射。

        :param query_db: orm对象
        :return: 插件操作类型字典映射
        """
        dict_data_list = await DictDataDao.query_dict_data_list(query_db, 'plugin_operation_type')

        return {
            dict_data.dict_value: dict_data.dict_label
            for dict_data in dict_data_list
            if dict_data and dict_data.dict_value
        }

    @classmethod
    async def _build_recent_audit_snapshot(
        cls,
        query_db: AsyncSession,
        plugin_id: str,
        *,
        audit_limit: int,
    ) -> dict[str, Any]:
        """
        构建插件最近审计记录快照。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param audit_limit: 最近审计记录数量
        :return: 最近审计记录快照
        """
        operation_logs = await PluginService.get_plugin_operation_log_export_list_services(
            query_db,
            PluginOperationLogExportQueryModel(exportLimit=max(audit_limit * 3, audit_limit)),
        )
        recent_logs = [
            operation_log
            for operation_log in operation_logs
            if isinstance(operation_log, PluginOperationLogDetailModel) and plugin_id in operation_log.plugin_ids
        ][:audit_limit]

        return {
            'available': True,
            'count': len(recent_logs),
            'items': [operation_log.model_dump(by_alias=True) for operation_log in recent_logs],
        }
