from collections.abc import Awaitable, Callable, Mapping
from typing import Annotated, Literal

from fastapi import Form, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_session import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_plugin.service.plugin_service import (
    PluginOperationService,
    PluginService,
    get_plugin_operation_service,
    get_plugin_runtime_service,
)
from plugins.core.management.entity.vo.schemas import (
    PluginBatchActionModel,
    PluginConfigImportModel,
    PluginConfigUpdateModel,
    PluginMigrationRecoveryModel,
    PluginModel,
    PluginOperationLogDetailModel,
    PluginOperationLogExportQueryModel,
    PluginOperationLogPageQueryModel,
    PluginOperationLogRetentionModel,
    PluginOperationLogRetentionResultModel,
    PluginPageQueryModel,
)
from plugins.core.runtime.result import PluginOperationResult
from plugins.core.validation.dependency_policy import DependencyInstallPolicyConfig
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

plugin_controller = APIRouterPro(
    prefix='/system/plugin',
    order_num=6,
    tags=['系统管理-插件管理'],
    dependencies=[PreAuthDependency()],
)


def _public_plugin_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """
    构造 Web API 可见的插件运行时 payload。

    :param payload: 插件运行时负载
    :return: Web API 响应负载
    """
    public_payload = dict(payload)
    public_payload.pop('exit_code', None)

    return public_payload


def _plugin_operation_response(payload: dict, default_message: str) -> Response:
    """
    按插件运行时 payload ok 字段统一构造操作响应。

    :param payload: 插件运行时负载
    :param default_message: 默认响应消息
    :return: 响应对象
    """
    operation_result = PluginOperationResult.from_payload(payload, default_message=default_message)
    response_payload = _public_plugin_payload(operation_result.payload)
    if not operation_result.ok:
        return ResponseUtil.failure(msg=operation_result.message, data=response_payload)

    return ResponseUtil.success(msg=operation_result.message, data=response_payload)


async def _execute_plugin_operation(
    operation: Callable[[], Awaitable[dict]],
    default_message: str,
) -> Response:
    """
    执行插件操作并统一处理异常与响应构造。

    :param operation: 返回插件操作协程的可调用对象
    :param default_message: 默认响应消息
    :return: 响应对象
    """
    try:
        payload = await operation()
    except Exception:
        logger.exception('插件操作执行异常：%s', default_message)
        return ResponseUtil.failure(msg=default_message)

    logger.info(payload.get('message', default_message))
    return _plugin_operation_response(payload, default_message)


@plugin_controller.get(
    '/list',
    summary='获取插件分页列表接口',
    description='用于获取插件分页列表',
    response_model=PageResponseModel[PluginModel],
    dependencies=[UserInterfaceAuthDependency('system:plugin:list')],
)
async def get_system_plugin_list(
    request: Request,
    plugin_page_query: Annotated[PluginPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    """
    获取插件分页列表。

    :param request: 请求对象
    :param plugin_page_query: 插件分页查询对象
    :param query_db: orm对象
    :return: 插件分页列表响应
    """
    plugin_page_query_result = await PluginService.get_plugin_page_list_services(
        query_db,
        plugin_page_query,
        is_page=True,
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=plugin_page_query_result)


@plugin_controller.get(
    '/plan',
    summary='生成插件批量操作计划接口',
    description='用于生成批量安装、启用或升级插件的拓扑排序计划',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def plan_system_plugins(
    request: Request,
    operation: Annotated[
        Literal['install', 'enable', 'upgrade'], Query(description='计划操作类型：install、enable 或 upgrade')
    ],
    plugin_ids: Annotated[list[str] | None, Query(alias='pluginIds', description='插件ID列表')] = None,
) -> Response:
    """
    生成插件批量操作拓扑计划。

    :param request: 请求对象
    :param operation: 计划操作类型
    :param plugin_ids: 插件ID列表
    :return: 插件批量操作拓扑计划响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().plan_plugins_async(operation, plugin_ids),
        '插件批量操作计划生成完成',
    )


@plugin_controller.get(
    '/{plugin_id}/precheck',
    summary='执行插件操作预检接口',
    description='用于在安装、启用、升级、卸载或清理前执行统一预检',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def precheck_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    operation: Annotated[
        Literal['install', 'enable', 'upgrade', 'uninstall', 'purge'],
        Query(description='预检操作类型：install、enable、upgrade、uninstall 或 purge'),
    ],
) -> Response:
    """
    执行插件操作预检。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param operation: 预检操作类型
    :return: 插件操作预检响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().precheck_plugin_operation(plugin_id, operation),
        '插件操作预检完成',
    )


@plugin_controller.post(
    '/batch',
    summary='批量执行插件操作接口',
    description='用于按插件依赖拓扑顺序批量安装、启用或升级插件',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def batch_system_plugins(
    request: Request,
    batch_action: PluginBatchActionModel,
) -> Response:
    """
    批量执行插件操作。

    :param request: 请求对象
    :param batch_action: 插件批量执行请求体
    :return: 插件批量执行结果响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().batch_plugins(
            batch_action.operation,
            batch_action.plugin_ids,
            dry_run=batch_action.dry_run,
            continue_on_error=batch_action.continue_on_error,
        ),
        '插件批量操作完成',
    )


@plugin_controller.get(
    '/operation-log/list',
    summary='获取插件操作审计日志分页列表接口',
    description='用于获取插件批量操作审计日志分页列表',
    response_model=PageResponseModel[PluginOperationLogDetailModel],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def get_system_plugin_operation_log_list(
    request: Request,
    operation_log_page_query: Annotated[PluginOperationLogPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    """
    获取插件批量操作审计日志分页列表。

    :param request: 请求对象
    :param operation_log_page_query: 插件批量操作审计日志分页查询对象
    :param query_db: orm对象
    :return: 插件批量操作审计日志分页列表响应
    """
    operation_log_page_result = await PluginService.get_plugin_operation_log_page_list_services(
        query_db,
        operation_log_page_query,
        is_page=True,
    )
    logger.info('获取插件批量操作审计日志成功')

    return ResponseUtil.success(model_content=operation_log_page_result)


@plugin_controller.post(
    '/operation-log/export',
    summary='导出插件操作审计日志接口',
    description='用于导出当前符合查询条件的插件操作审计日志数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回插件操作审计日志excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('system:plugin:export')],
)
@Log(title='插件管理', business_type=BusinessType.EXPORT)
async def export_system_plugin_operation_log_list(
    request: Request,
    operation_log_export_query: Annotated[PluginOperationLogExportQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    """
    导出插件操作审计日志。

    :param request: 请求对象
    :param operation_log_export_query: 插件操作审计日志导出查询对象
    :param query_db: orm对象
    :return: 插件操作审计日志导出响应
    """
    operation_log_export_list = await PluginService.get_plugin_operation_log_export_list_services(
        query_db,
        operation_log_export_query,
    )
    operation_dict = await PluginOperationService.get_plugin_operation_dict_services(query_db)
    operation_log_export_result = PluginService.export_plugin_operation_log_list_services(
        operation_log_export_list,
        operation_dict,
    )
    logger.info('导出插件操作审计日志成功')

    return ResponseUtil.streaming(data=bytes2file_response(operation_log_export_result))


@plugin_controller.delete(
    '/operation-log/retention',
    summary='执行插件操作审计日志保留策略接口',
    description='用于按保留天数预览或清理插件操作审计日志',
    response_model=DataResponseModel[PluginOperationLogRetentionResultModel],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.CLEAN)
async def retain_system_plugin_operation_log(
    request: Request,
    retention_query: Annotated[PluginOperationLogRetentionModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    """
    执行插件操作审计日志保留策略。

    :param request: 请求对象
    :param retention_query: 插件操作审计日志保留策略查询对象
    :param query_db: orm对象
    :return: 插件操作审计日志保留策略执行响应
    """
    retention_result = await PluginService.retain_plugin_operation_log_services(query_db, retention_query)
    await query_db.commit()
    logger.info('插件操作审计日志保留策略执行完成')

    return ResponseUtil.success(data=retention_result, msg='插件操作审计日志保留策略执行完成')


@plugin_controller.get(
    '/operation-log/{operation_id}',
    summary='获取插件操作审计日志详情接口',
    description='用于获取插件批量操作审计日志详情',
    response_model=DataResponseModel[PluginOperationLogDetailModel],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def query_detail_system_plugin_operation_log(
    request: Request,
    operation_id: Annotated[int, Path(description='操作日志ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    """
    获取插件批量操作审计日志详情。

    :param request: 请求对象
    :param operation_id: 操作日志ID
    :param query_db: orm对象
    :return: 插件批量操作审计日志详情响应
    """
    operation_log_detail_result = await PluginService.plugin_operation_log_detail_services(query_db, operation_id)
    if not operation_log_detail_result:
        logger.warning(f'插件批量操作审计日志不存在：{operation_id}')
        return ResponseUtil.failure(msg='插件批量操作审计日志不存在')
    logger.info(f'获取operation_id为{operation_id}的插件批量操作审计日志成功')

    return ResponseUtil.success(data=operation_log_detail_result)


@plugin_controller.get(
    '/{plugin_id}/migrations',
    summary='获取插件 migration 历史接口',
    description='用于获取指定插件的 migration 执行历史',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def list_system_plugin_migrations(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    status: Annotated[
        Literal['running', 'success', 'failed', 'unknown'] | None,
        Query(description='migration 执行状态'),
    ] = None,
) -> Response:
    """
    获取插件 migration 历史。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param status: migration 执行状态
    :return: 插件 migration 历史响应
    """
    migration_result = await get_plugin_runtime_service().list_plugin_migrations(plugin_id, status)
    logger.info(migration_result.get('message', '插件 migration 历史查询完成'))

    return _plugin_operation_response(migration_result, '插件 migration 历史查询完成')


@plugin_controller.post(
    '/{plugin_id}/migrations/mark-success',
    summary='人工标记插件 migration 成功接口',
    description='用于人工确认指定 migration 已执行成功并更新历史状态',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def mark_system_plugin_migration_success(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    recovery: PluginMigrationRecoveryModel,
) -> Response:
    """
    人工标记插件 migration 为成功。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param recovery: migration 人工恢复请求
    :return: 插件 migration 状态标记响应
    """
    mark_result = await get_plugin_runtime_service().mark_plugin_migration_success(
        plugin_id,
        recovery.migration_path,
        note=recovery.note,
    )
    logger.info(mark_result.get('message', '插件 migration 已人工标记为成功'))

    return _plugin_operation_response(mark_result, '插件 migration 已人工标记为成功')


@plugin_controller.post(
    '/{plugin_id}/migrations/mark-failed',
    summary='人工标记插件 migration 失败接口',
    description='用于人工确认指定 migration 未完成并更新历史状态为可重试失败',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def mark_system_plugin_migration_failed(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    recovery: PluginMigrationRecoveryModel,
) -> Response:
    """
    人工标记插件 migration 为失败。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param recovery: migration 人工恢复请求
    :return: 插件 migration 状态标记响应
    """
    mark_result = await get_plugin_runtime_service().mark_plugin_migration_failed(
        plugin_id,
        recovery.migration_path,
        note=recovery.note,
    )
    logger.info(mark_result.get('message', '插件 migration 已人工标记为失败'))

    return _plugin_operation_response(mark_result, '插件 migration 已人工标记为失败')


@plugin_controller.get(
    '/{plugin_id}',
    summary='获取插件详情接口',
    description='用于获取指定插件的详情信息',
    response_model=DataResponseModel[PluginModel],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def query_detail_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    """
    获取插件详情。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param query_db: orm对象
    :return: 插件详情响应
    """
    plugin_detail_result = await PluginService.plugin_detail_services(query_db, plugin_id)
    if not plugin_detail_result:
        logger.warning(f'插件不存在：{plugin_id}')
        return ResponseUtil.failure(msg='插件不存在')
    logger.info(f'获取plugin_id为{plugin_id}的信息成功')

    return ResponseUtil.success(data=plugin_detail_result)


@plugin_controller.put(
    '/{plugin_id}/enable',
    summary='启用插件接口',
    description='用于启用指定插件',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def enable_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    """
    启用插件。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param query_db: orm对象
    :return: 启用结果响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().set_plugin_enabled(plugin_id, enabled=True),
        '插件启用完成',
    )


@plugin_controller.put(
    '/{plugin_id}/disable',
    summary='停用插件接口',
    description='用于停用指定插件',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def disable_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
) -> Response:
    """
    停用插件。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :return: 停用结果响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().set_plugin_enabled(plugin_id, enabled=False),
        '插件停用完成',
    )


@plugin_controller.get(
    '/{plugin_id}/check',
    summary='检查插件接口',
    description='用于检查指定插件的目录结构、依赖和菜单冲突',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def check_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
) -> Response:
    """
    检查插件。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :return: 插件检查结果响应
    """
    check_plugin_result = await get_plugin_runtime_service().check_plugin_async(plugin_id)
    logger.info(check_plugin_result.get('message', '插件检查完成'))

    return _plugin_operation_response(check_plugin_result, '插件检查完成')


@plugin_controller.get(
    '/{plugin_id}/health',
    summary='执行插件健康检查接口',
    description='用于执行指定插件声明的只读健康检查',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def health_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
) -> Response:
    """
    执行插件健康检查。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :return: 插件健康检查响应
    """
    health_plugin_result = await get_plugin_runtime_service().health_plugin(plugin_id)
    logger.info(health_plugin_result.get('message', '插件健康检查完成'))

    return _plugin_operation_response(health_plugin_result, '插件健康检查完成')


@plugin_controller.get(
    '/{plugin_id}/diagnose',
    summary='生成插件诊断包接口',
    description='用于生成指定插件的只读诊断信息，包含详情、检查结果、配置脱敏快照和审计预留信息',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def diagnose_system_plugin(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    plugin_id: Annotated[str, Path(description='插件ID')],
) -> Response:
    """
    生成插件诊断包。

    :param request: 请求对象
    :param query_db: orm对象
    :param plugin_id: 插件ID
    :return: 插件诊断包响应
    """
    diagnose_plugin_result = await get_plugin_operation_service().diagnose_plugin_with_audit_services(
        query_db, plugin_id
    )
    logger.info(diagnose_plugin_result.get('message', '插件诊断包生成完成'))

    return _plugin_operation_response(diagnose_plugin_result, '插件诊断包生成完成')


@plugin_controller.get(
    '/{plugin_id}/docs',
    summary='生成插件文档接口',
    description='用于根据 plugin.yaml 生成插件 Markdown 文档片段',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def generate_system_plugin_docs(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
) -> Response:
    """
    生成插件 Markdown 文档片段。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :return: 插件文档生成响应
    """
    docs_result = get_plugin_runtime_service().generate_plugin_docs(plugin_id)
    logger.info(docs_result.get('message', '插件文档生成完成'))

    return _plugin_operation_response(docs_result, '插件文档生成完成')


@plugin_controller.post(
    '/{plugin_id}/install',
    summary='安装插件接口',
    description='用于安装指定插件',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.INSERT)
async def install_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    dry_run: Annotated[bool, Query(alias='dryRun', description='是否仅预演操作')] = False,
) -> Response:
    """
    安装插件。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param dry_run: 是否仅预演操作
    :param current_user: 当前登录用户
    :return: 插件安装结果响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().install_plugin(
            plugin_id,
            dry_run=dry_run,
            operated_by=current_user.user.user_name,
        ),
        '插件安装完成',
    )


@plugin_controller.post(
    '/{plugin_id}/upgrade',
    summary='升级插件接口',
    description='用于升级指定插件',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def upgrade_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    dry_run: Annotated[bool, Query(alias='dryRun', description='是否仅预演操作')] = False,
) -> Response:
    """
    升级插件。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param dry_run: 是否仅预演操作
    :param current_user: 当前登录用户
    :return: 插件升级结果响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().upgrade_plugin(
            plugin_id,
            dry_run=dry_run,
            operated_by=current_user.user.user_name,
        ),
        '插件升级完成',
    )


@plugin_controller.post(
    '/{plugin_id}/uninstall',
    summary='安全卸载插件接口',
    description='用于安全卸载指定插件，第一阶段等价于停用插件和菜单',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def uninstall_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    dry_run: Annotated[bool, Query(alias='dryRun', description='是否仅预演操作')] = False,
) -> Response:
    """
    安全卸载插件。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param dry_run: 是否仅预演操作
    :param current_user: 当前登录用户
    :return: 插件安全卸载结果响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().uninstall_plugin(
            plugin_id,
            dry_run=dry_run,
            operated_by=current_user.user.user_name,
        ),
        '插件卸载完成',
    )


@plugin_controller.post(
    '/{plugin_id}/purge',
    summary='物理清理插件接口',
    description='用于物理清理指定插件的平台元数据，默认不删除源码目录',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:remove')],
)
@Log(title='插件管理', business_type=BusinessType.DELETE)
async def purge_system_plugin(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    dry_run: Annotated[bool, Query(alias='dryRun', description='是否仅预演操作')] = False,
) -> Response:
    """
    物理清理插件平台元数据。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param dry_run: 是否仅预演操作
    :param current_user: 当前登录用户
    :return: 插件物理清理结果响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().purge_plugin(
            plugin_id,
            dry_run=dry_run,
            operated_by=current_user.user.user_name,
        ),
        '插件物理清理完成',
    )


@plugin_controller.get(
    '/{plugin_id}/config',
    summary='获取插件配置接口',
    description='用于获取指定插件的配置项',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def query_system_plugin_config(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
) -> Response:
    """
    获取插件配置。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :return: 插件配置响应
    """
    plugin_config_result = await get_plugin_runtime_service().get_plugin_config(plugin_id)
    logger.info(plugin_config_result.get('message', '插件配置读取完成'))

    return _plugin_operation_response(plugin_config_result, '插件配置读取完成')


@plugin_controller.put(
    '/{plugin_id}/config',
    summary='更新插件配置接口',
    description='用于更新指定插件的配置项',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def update_system_plugin_config(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    plugin_config: PluginConfigUpdateModel,
) -> Response:
    """
    更新插件配置。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param plugin_config: 插件配置更新对象
    :return: 插件配置更新响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().set_plugin_config(
            plugin_id,
            plugin_config.values,
        ),
        '插件配置已更新',
    )


@plugin_controller.get(
    '/{plugin_id}/config/export',
    summary='导出插件配置接口',
    description='用于导出指定插件的配置快照，默认敏感配置保持脱敏',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:export')],
)
async def export_system_plugin_config(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    reveal_secret: Annotated[bool, Query(alias='revealSecret', description='是否导出敏感配置明文')] = False,
) -> Response:
    """
    导出插件配置。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param reveal_secret: 是否导出敏感配置明文
    :return: 插件配置导出响应
    """
    if reveal_secret:
        return ResponseUtil.failure(msg='Web 端不允许导出敏感配置明文，请使用 CLI 通道')
    plugin_config_result = await get_plugin_runtime_service().export_plugin_config(
        plugin_id,
        reveal_secret=False,
    )
    logger.info(plugin_config_result.get('message', '插件配置导出完成'))

    return _plugin_operation_response(plugin_config_result, '插件配置导出完成')


@plugin_controller.post(
    '/{plugin_id}/config/import',
    summary='导入插件配置接口',
    description='用于导入指定插件的配置快照',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:edit')],
)
@Log(title='插件管理', business_type=BusinessType.UPDATE)
async def import_system_plugin_config(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    plugin_config: PluginConfigImportModel,
) -> Response:
    """
    导入插件配置。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param plugin_config: 插件配置导入对象
    :return: 插件配置导入响应
    """
    return await _execute_plugin_operation(
        lambda: get_plugin_runtime_service().import_plugin_config(
            plugin_id,
            plugin_config.values,
        ),
        '插件配置导入完成',
    )


@plugin_controller.get(
    '/{plugin_id}/dependencies',
    summary='检查插件依赖接口',
    description='用于检查指定插件的 Python 和 npm 依赖',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def check_system_plugin_dependencies(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
) -> Response:
    """
    检查插件依赖。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :return: 插件依赖检查响应
    """
    dependency_result = get_plugin_runtime_service().check_plugin_dependencies(plugin_id)
    logger.info(dependency_result.get('message', '插件依赖检查完成'))

    return _plugin_operation_response(dependency_result, '插件依赖检查完成')


@plugin_controller.post(
    '/{plugin_id}/dependencies/install',
    summary='插件依赖安装计划接口',
    description='用于生成指定插件的依赖安装计划，Web 第一版仅支持 dry-run',
    response_model=DataResponseModel[dict],
    dependencies=[UserInterfaceAuthDependency('system:plugin:query')],
)
async def install_system_plugin_dependencies(
    request: Request,
    plugin_id: Annotated[str, Path(description='插件ID')],
    dry_run: Annotated[bool, Query(alias='dryRun', description='是否仅预演操作')] = True,
) -> Response:
    """
    生成插件依赖安装计划。

    :param request: 请求对象
    :param plugin_id: 插件ID
    :param dry_run: 是否仅预演操作
    :return: 插件依赖安装计划响应
    """
    dependency_result = get_plugin_runtime_service().install_plugin_dependencies(
        plugin_id,
        dry_run=dry_run if dry_run else True,
        policy_config=DependencyInstallPolicyConfig(mode='plan_only', env='web'),
    )
    logger.info(dependency_result.get('message', '插件依赖安装演练完成'))

    return _plugin_operation_response(dependency_result, '插件依赖安装演练完成')
