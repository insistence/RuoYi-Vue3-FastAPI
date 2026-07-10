from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.dao.dict_dao import DictDataDao
from plugins.core.management.entity.vo.schemas import (
    PluginOperationLogDetailModel,
    PluginOperationLogExportQueryModel,
)
from plugins.core.management.service.gateway import PluginManagementRuntimeGateway
from plugins.core.management.service.service import PluginService
from plugins.core.runtime.service import PluginRuntimeService
from plugins.core.runtime.service.dependency_container import PluginRuntimeGatewayOverrides
from plugins.core.runtime.service.lifecycle_lock import RedisPluginLifecycleLock
from plugins.core.runtime.service.responses import PluginDiagnoseResponse
from plugins.core.runtime.support import PluginAuditPayloadBuilder, PluginAuditSnapshotPayloadDict

AUDIT_LOG_OVERFETCH_MULTIPLIER = 3


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
        self.runtime_service = runtime_service or get_plugin_runtime_service()

    async def diagnose_plugin_with_audit_services(
        self,
        query_db: AsyncSession,
        plugin_id: str,
        *,
        audit_limit: int = 5,
    ) -> PluginDiagnoseResponse:
        """
        生成包含最近审计记录的插件诊断包。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param audit_limit: 最近审计记录数量
        :return: 插件诊断包负载
        """
        payload = cast('dict[str, object]', await self.runtime_service.diagnose_plugin(plugin_id))
        payload['audit'] = await self._build_recent_audit_snapshot(query_db, plugin_id, audit_limit=audit_limit)

        return cast('PluginDiagnoseResponse', payload)

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
    ) -> PluginAuditSnapshotPayloadDict:
        """
        构建插件最近审计记录快照。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param audit_limit: 最近审计记录数量
        :return: 最近审计记录快照
        """
        operation_logs = await PluginService.get_plugin_operation_log_export_list_services(
            query_db,
            PluginOperationLogExportQueryModel(exportLimit=audit_limit * AUDIT_LOG_OVERFETCH_MULTIPLIER),
        )
        return PluginAuditPayloadBuilder.build_recent_snapshot_payload(
            plugin_id,
            [
                operation_log
                for operation_log in operation_logs
                if isinstance(operation_log, PluginOperationLogDetailModel)
            ],
            audit_limit=audit_limit,
        )


_PLUGIN_OPERATION_SERVICE_CACHE: dict[str, PluginOperationService] = {}
_PLUGIN_RUNTIME_SERVICE_CACHE: dict[str, PluginRuntimeService] = {}


def get_plugin_runtime_service() -> PluginRuntimeService:
    """
    获取 Web 侧插件运行时服务单例。

    :return: 插件运行时服务
    """
    runtime_service = _PLUGIN_RUNTIME_SERVICE_CACHE.get('default')
    if runtime_service is None:
        runtime_gateway = PluginManagementRuntimeGateway()
        runtime_service = PluginRuntimeService(
            gateways=PluginRuntimeGatewayOverrides(
                config_gateway=runtime_gateway,
                audit_gateway=runtime_gateway,
                state_query_gateway=runtime_gateway,
                migration_history_gateway=runtime_gateway,
                purge_plan_gateway=runtime_gateway,
                lifecycle_state_gateway=runtime_gateway,
                lifecycle_uow_gateway=runtime_gateway,
                migration_execution_gateway=runtime_gateway,
            ),
            model_gateway=runtime_gateway,
            command_gateway=runtime_gateway,
            lifecycle_lock=RedisPluginLifecycleLock(),
        )
        _PLUGIN_RUNTIME_SERVICE_CACHE['default'] = runtime_service

    return runtime_service


def get_plugin_operation_service() -> PluginOperationService:
    """
    获取 Web 侧插件操作服务单例。

    :return: 插件操作服务
    """
    operation_service = _PLUGIN_OPERATION_SERVICE_CACHE.get('default')
    if operation_service is None:
        operation_service = PluginOperationService()
        _PLUGIN_OPERATION_SERVICE_CACHE['default'] = operation_service

    return operation_service
