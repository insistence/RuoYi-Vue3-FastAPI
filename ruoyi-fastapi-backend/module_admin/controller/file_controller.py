from typing import Annotated, Literal
from uuid import UUID

from fastapi import BackgroundTasks, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from common.aspect.data_scope import DataScopeDependency
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.constant import ApiNamespace
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.dept_vo import DeptTreeModel
from module_admin.entity.vo.file_vo import (
    BatchSaveFileAclModel,
    DeleteFileModel,
    DisposeExpiredFileModel,
    ExtendFileRetentionModel,
    FileAccessLogModel,
    FileAccessLogPageQueryModel,
    FileAclListModel,
    FileAclSubjectOptionModel,
    FileInfoDisplayModel,
    FileInfoPageQueryModel,
    FileReconcileHandleModel,
    FileReconcileIssueModel,
    FileReconcileIssuePageQueryModel,
    FileReconcileRunModel,
    FileReconcileRunPageQueryModel,
    FileReconcileStartModel,
    FileReconcileStatsModel,
    FileReferenceModel,
    FileRetentionNoticeModel,
    FileRetentionNoticePageQueryModel,
    FileRetentionPolicyModel,
    FileRetentionScanModel,
    FileStatsModel,
    SaveFileAclModel,
    TransferFileModel,
)
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from module_admin.service.file_access_service import FileAclService
from module_admin.service.file_business_service import (
    FileReferenceService,
    FileRetentionNoticeService,
    FileRetentionPolicyService,
)
from module_admin.service.file_service import (
    FileLifecycleService,
    FileQueryService,
    FileReconcileService,
    FileRetentionDispositionService,
    FileTransferService,
)
from utils.log_util import logger
from utils.response_util import ResponseUtil
from utils.upload_util import UploadUtil

file_controller = APIRouterPro(
    prefix='/system/file', order_num=11, tags=['系统管理-文件管理'], dependencies=[PreAuthDependency()]
)


@file_controller.get(
    '/list',
    summary='获取文件分页列表接口',
    description='用于获取文件分页列表',
    response_model=PageResponseModel[FileInfoDisplayModel],
    dependencies=[UserInterfaceAuthDependency('system:file:list')],
)
async def get_system_file_list(
    request: Request,
    file_page_query: Annotated[FileInfoPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    file_page_query_result = await FileQueryService.get_file_list_services(
        query_db,
        file_page_query,
        file_data_scope_sql,
        is_page=True,
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=file_page_query_result)


@file_controller.get(
    '/stats',
    summary='获取文件管理统计接口',
    description='用于获取当前数据范围和查询条件下的文件统计信息',
    response_model=DataResponseModel[FileStatsModel],
    dependencies=[UserInterfaceAuthDependency('system:file:list')],
)
async def get_system_file_stats(
    request: Request,
    file_page_query: Annotated[FileInfoPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    file_stats_result = await FileQueryService.get_file_stats_services(
        query_db,
        file_page_query,
        file_data_scope_sql,
    )
    logger.info('文件统计获取成功')

    return ResponseUtil.success(data=file_stats_result)


@file_controller.get(
    '/reconcile/issues/list',
    summary='获取文件存储对账异常分页列表接口',
    description='用于获取文件存储对账异常和可用处理动作',
    response_model=PageResponseModel[FileReconcileIssueModel],
    dependencies=[UserInterfaceAuthDependency('system:file:reconcile')],
)
async def get_system_file_reconcile_issue_list(
    request: Request,
    issue_page_query: Annotated[FileReconcileIssuePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    issue_page_query_result = await FileReconcileService.get_reconcile_issue_list_services(
        query_db,
        current_user,
        issue_page_query,
        is_page=True,
    )
    logger.info('文件存储对账异常列表获取成功')

    return ResponseUtil.success(model_content=issue_page_query_result)


@file_controller.get(
    '/reconcile/runs/list',
    summary='获取文件存储对账任务分页列表接口',
    description='用于获取文件存储对账任务执行记录',
    response_model=PageResponseModel[FileReconcileRunModel],
    dependencies=[UserInterfaceAuthDependency('system:file:reconcile')],
)
async def get_system_file_reconcile_run_list(
    request: Request,
    run_page_query: Annotated[FileReconcileRunPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    run_page_query_result = await FileReconcileService.get_reconcile_run_list_services(
        query_db,
        current_user,
        run_page_query,
        is_page=True,
    )
    logger.info('文件存储对账任务列表获取成功')

    return ResponseUtil.success(model_content=run_page_query_result)


@file_controller.get(
    '/reconcile/stats',
    summary='获取文件存储对账统计接口',
    description='用于获取待处理异常和最近任务统计',
    response_model=DataResponseModel[FileReconcileStatsModel],
    dependencies=[UserInterfaceAuthDependency('system:file:reconcile')],
)
async def get_system_file_reconcile_stats(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    reconcile_stats = await FileReconcileService.get_reconcile_stats_services(
        query_db,
        current_user,
    )
    logger.info('文件存储对账统计获取成功')

    return ResponseUtil.success(data=reconcile_stats)


@file_controller.post(
    '/reconcile/run',
    summary='启动文件存储对账任务接口',
    description='用于启动数据库和本地文件系统双向对账任务',
    response_model=DataResponseModel[FileReconcileRunModel],
    dependencies=[UserInterfaceAuthDependency('system:file:reconcile')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_RECONCILE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件存储对账', business_type=BusinessType.UPDATE)
async def start_system_file_reconcile(
    request: Request,
    start_reconcile: FileReconcileStartModel,
    background_tasks: BackgroundTasks,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    reconcile_run = await FileReconcileService.start_reconcile_run_services(
        query_db,
        check_hash=start_reconcile.check_hash,
        current_user=current_user,
    )
    background_tasks.add_task(FileReconcileService.execute_reconcile_run_services, reconcile_run.run_id)
    logger.info(f'文件存储对账任务{reconcile_run.run_id}已启动')

    return ResponseUtil.success(data=reconcile_run, msg='文件存储对账任务已启动')


@file_controller.put(
    '/reconcile/issues/{issue_id}',
    summary='处理文件存储对账异常接口',
    description='用于忽略、修复、隔离或登记文件存储异常',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:reconcile')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_RECONCILE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件存储对账', business_type=BusinessType.UPDATE)
async def handle_system_file_reconcile_issue(
    request: Request,
    issue_id: Annotated[int, Path(gt=0, description='对账异常ID')],
    handle_reconcile: FileReconcileHandleModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    handle_result = await FileReconcileService.handle_reconcile_issue_services(
        query_db,
        current_user,
        issue_id,
        handle_reconcile,
        request=request,
    )
    logger.info(handle_result.message)

    return ResponseUtil.success(msg=handle_result.message)


@file_controller.get(
    '/retention-policy/list',
    summary='获取文件业务保留策略列表接口',
    description='用于获取文件业务类型对应的保留策略',
    response_model=DataResponseModel[list[FileRetentionPolicyModel]],
    dependencies=[UserInterfaceAuthDependency('system:file:list')],
)
async def get_system_file_retention_policy_list(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    policy_list_result = await FileRetentionPolicyService.get_file_retention_policy_list_services(query_db)
    logger.info('文件业务保留策略列表获取成功')

    return ResponseUtil.success(data=policy_list_result)


@file_controller.post(
    '/retention-policy',
    summary='新增文件业务保留策略接口',
    description='用于新增文件业务类型对应的保留策略',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_FILE_RETENTION_POLICY,
    preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION,
)
@Log(title='文件保留策略', business_type=BusinessType.INSERT)
async def add_system_file_retention_policy(
    request: Request,
    policy: FileRetentionPolicyModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    policy_result = await FileRetentionPolicyService.add_file_retention_policy_services(
        query_db,
        policy,
        current_user.user.user_name,
    )
    logger.info(policy_result.message)

    return ResponseUtil.success(msg=policy_result.message)


@file_controller.put(
    '/retention-policy',
    summary='修改文件业务保留策略接口',
    description='用于修改文件业务类型对应的保留策略',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_FILE_RETENTION_POLICY,
    preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION,
)
@Log(title='文件保留策略', business_type=BusinessType.UPDATE)
async def edit_system_file_retention_policy(
    request: Request,
    policy: FileRetentionPolicyModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    policy_result = await FileRetentionPolicyService.edit_file_retention_policy_services(
        query_db,
        policy,
        current_user.user.user_name,
    )
    logger.info(policy_result.message)

    return ResponseUtil.success(msg=policy_result.message)


@file_controller.delete(
    '/retention-policy/{business_type}',
    summary='删除文件业务保留策略接口',
    description='用于删除文件业务类型对应的保留策略',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_FILE_RETENTION_POLICY,
    preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION,
)
@Log(title='文件保留策略', business_type=BusinessType.DELETE)
async def delete_system_file_retention_policy(
    request: Request,
    business_type: Annotated[str, Path(min_length=1, max_length=50, description='业务类型')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    policy_result = await FileRetentionPolicyService.delete_file_retention_policy_services(
        query_db,
        business_type,
    )
    logger.info(policy_result.message)

    return ResponseUtil.success(msg=policy_result.message)


@file_controller.get(
    '/retention-reminder/list',
    summary='获取文件保留期限提醒分页列表接口',
    description='用于获取当前数据权限范围内的文件保留期限提醒',
    response_model=PageResponseModel[FileRetentionNoticeModel],
    dependencies=[UserInterfaceAuthDependency('system:file:list')],
)
async def get_system_file_retention_reminder_list(
    request: Request,
    reminder_page_query: Annotated[FileRetentionNoticePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    reminder_page_query_result = await FileRetentionNoticeService.get_file_retention_notice_list_services(
        query_db,
        reminder_page_query,
        file_data_scope_sql,
        is_page=True,
    )
    logger.info('文件保留期限提醒获取成功')

    return ResponseUtil.success(model_content=reminder_page_query_result)


@file_controller.post(
    '/retention-reminder/scan',
    summary='执行文件保留期限提醒扫描接口',
    description='用于扫描当前数据权限范围内即将到期和已到期的受保护文件',
    response_model=DataResponseModel[FileRetentionScanModel],
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_FILE_RETENTION_POLICY,
    preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION,
)
@Log(title='文件保留期限提醒', business_type=BusinessType.UPDATE)
async def scan_system_file_retention_reminder(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    scan_result = await FileRetentionNoticeService.scan_file_retention_notices_services(
        query_db,
        file_data_scope_sql=file_data_scope_sql,
    )
    logger.info(
        f'文件保留期限提醒扫描成功，即将到期{scan_result.expiring_count}个，已到期{scan_result.expired_count}个'
    )

    return ResponseUtil.success(data=scan_result)


@file_controller.put(
    '/retention-reminder/{notice_ids}/read',
    summary='标记文件保留期限提醒已读接口',
    description='用于将当前数据权限范围内的文件保留期限提醒标记为已读',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:list')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_FILE_RETENTION_POLICY,
    preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION,
)
async def read_system_file_retention_reminder(
    request: Request,
    notice_ids: Annotated[str, Path(description='提醒ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    read_result = await FileRetentionNoticeService.mark_file_retention_notices_read_services(
        query_db,
        notice_ids,
        current_user.user.user_name,
        file_data_scope_sql,
    )
    logger.info(read_result.message)

    return ResponseUtil.success(msg=read_result.message)


@file_controller.put(
    '/retention-reminder/{notice_id}/extend',
    summary='延长文件保留期限接口',
    description='用于延长当前数据权限范围内文件的保留期限',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_FILE_RETENTION_POLICY,
    preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION,
)
@Log(title='文件到期处置', business_type=BusinessType.UPDATE)
async def extend_system_file_retention(
    request: Request,
    notice_id: Annotated[int, Path(gt=0, description='提醒ID')],
    extend_retention: ExtendFileRetentionModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    extend_result = await FileRetentionDispositionService.extend_file_retention_services(
        query_db,
        current_user,
        notice_id,
        extend_retention,
        file_data_scope_sql,
        request=request,
    )
    logger.info(extend_result.message)

    return ResponseUtil.success(msg=extend_result.message)


@file_controller.put(
    '/retention-reminder/{notice_id}/dispose',
    summary='处置到期文件接口',
    description='用于释放已到期业务引用并将文件移入回收站',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:remove')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_DELETE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件到期处置', business_type=BusinessType.DELETE)
async def dispose_system_expired_file(
    request: Request,
    notice_id: Annotated[int, Path(gt=0, description='提醒ID')],
    dispose_file: DisposeExpiredFileModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    dispose_result = await FileRetentionDispositionService.dispose_expired_file_services(
        query_db,
        current_user,
        notice_id,
        dispose_file,
        file_data_scope_sql,
        request=request,
    )
    logger.info(dispose_result.message)

    return ResponseUtil.success(msg=dispose_result.message)


@file_controller.get(
    '/acl/subjects',
    summary='查询文件授权主体选项接口',
    description='用于按用户、角色或部门查询文件授权主体选项',
    response_model=DataResponseModel[list[FileAclSubjectOptionModel]],
    dependencies=[UserInterfaceAuthDependency(['system:file:list', 'system:file:edit', 'system:file:transfer'])],
)
async def search_system_file_acl_subjects(
    request: Request,
    subject_type: Annotated[Literal['user', 'role', 'dept'], Query(alias='subjectType')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    user_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
    dept_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
    keyword: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Response:
    subject_list_result = await FileAclService.search_file_acl_subjects_services(
        query_db,
        subject_type,
        keyword,
        limit,
        user_data_scope_sql,
        dept_data_scope_sql,
    )
    logger.info('文件授权主体查询成功')

    return ResponseUtil.success(data=subject_list_result)


@file_controller.get(
    '/acl/dept-tree',
    summary='获取文件授权部门树接口',
    description='用于获取文件授权可选的有效部门树',
    response_model=DataResponseModel[list[DeptTreeModel]],
    dependencies=[UserInterfaceAuthDependency(['system:file:list', 'system:file:edit', 'system:file:transfer'])],
)
async def get_system_file_acl_dept_tree(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    dept_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    dept_tree_result = await FileAclService.get_file_acl_dept_tree_services(query_db, dept_data_scope_sql)
    logger.info('文件授权部门树获取成功')

    return ResponseUtil.success(data=dept_tree_result)


@file_controller.put(
    '/acl/batch',
    summary='批量保存文件访问控制接口',
    description='用于批量替换受保护文件的访问控制配置',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_ACL, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件管理', business_type=BusinessType.UPDATE)
async def batch_save_system_file_acl(
    request: Request,
    batch_save_file_acl: BatchSaveFileAclModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
    user_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
    dept_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    save_file_acl_result = await FileAclService.batch_save_file_acl_services(
        query_db,
        current_user,
        batch_save_file_acl,
        file_data_scope_sql,
        user_data_scope_sql,
        dept_data_scope_sql,
        request=request,
    )
    logger.info(save_file_acl_result.message)

    return ResponseUtil.success(msg=save_file_acl_result.message)


@file_controller.get(
    '/{file_id}/acl/list',
    summary='获取文件访问控制列表接口',
    description='用于获取指定文件的访问控制列表',
    response_model=DataResponseModel[FileAclListModel],
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
async def get_system_file_acl_list(
    request: Request,
    file_id: UUID,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
    user_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
    dept_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    file_acl_list_result = await FileAclService.get_file_acl_list_services(
        query_db,
        str(file_id),
        file_data_scope_sql,
        user_data_scope_sql,
        dept_data_scope_sql,
    )
    logger.info('文件访问控制列表获取成功')

    return ResponseUtil.success(data=file_acl_list_result)


@file_controller.put(
    '/{file_id}/acl',
    summary='保存文件访问控制接口',
    description='用于替换指定私有文件的访问控制配置',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_ACL, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件管理', business_type=BusinessType.UPDATE)
async def save_system_file_acl(
    request: Request,
    file_id: UUID,
    save_file_acl: SaveFileAclModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
    user_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
    dept_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    save_file_acl_result = await FileAclService.save_file_acl_services(
        query_db,
        current_user,
        str(file_id),
        save_file_acl,
        file_data_scope_sql,
        user_data_scope_sql,
        dept_data_scope_sql,
        request=request,
    )
    logger.info(save_file_acl_result.message)

    return ResponseUtil.success(msg=save_file_acl_result.message)


@file_controller.get(
    '/{file_id}/reference/list',
    summary='获取文件业务引用列表接口',
    description='用于获取指定文件的业务引用列表',
    response_model=DataResponseModel[list[FileReferenceModel]],
    dependencies=[UserInterfaceAuthDependency('system:file:query')],
)
async def get_system_file_reference_list(
    request: Request,
    file_id: UUID,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    file_reference_list_result = await FileReferenceService.get_file_reference_list_services(
        query_db,
        str(file_id),
        file_data_scope_sql,
    )
    logger.info('文件业务引用列表获取成功')

    return ResponseUtil.success(data=file_reference_list_result)


@file_controller.get(
    '/{file_id}/access-log/list',
    summary='获取文件访问审计分页列表接口',
    description='用于获取指定文件的访问审计分页列表',
    response_model=PageResponseModel[FileAccessLogModel],
    dependencies=[UserInterfaceAuthDependency('system:file:query')],
)
async def get_system_file_access_log_list(
    request: Request,
    file_id: UUID,
    access_log_page_query: Annotated[FileAccessLogPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    access_log_page_query_result = await FileQueryService.get_file_access_log_list_services(
        query_db,
        str(file_id),
        access_log_page_query,
        file_data_scope_sql,
        is_page=True,
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=access_log_page_query_result)


@file_controller.get(
    '/download/{file_id}/{display_name}',
    summary='文件管理下载接口',
    description='用于具有文件管理权限的用户下载文件',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回文件',
            'content': {
                'application/octet-stream': {},
            },
        },
        206: {'description': '分段返回文件'},
        416: {'description': '请求的字节范围不可满足'},
    },
    dependencies=[UserInterfaceAuthDependency('system:file:download')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_DOWNLOAD, preset=ApiRateLimitPreset.USER_RESOURCE_DOWNLOAD)
@Log(title='文件管理', business_type=BusinessType.EXPORT)
async def download_system_file(
    request: Request,
    file_id: UUID,
    display_name: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    download_result = await CommonService.download_managed_file_services(
        request,
        query_db,
        current_user,
        str(file_id),
        enforce_owner_permission=False,
        file_data_scope_sql=file_data_scope_sql,
        range_header=request.headers.get('Range'),
    )
    logger.info(f'文件{file_id}下载成功')

    return ResponseUtil.streaming(
        data=download_result.data,
        headers=UploadUtil.build_download_headers(
            download_result.filename,
            download_result.byte_range,
            download_result.accept_ranges,
        ),
        media_type='application/octet-stream',
        status_code=206 if download_result.byte_range.is_partial else 200,
    )


@file_controller.put(
    '/{file_ids}/transfer',
    summary='转移文件接口',
    description='用于批量转移文件所有者和所属部门',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:transfer')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_TRANSFER, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件管理', business_type=BusinessType.UPDATE)
async def transfer_system_file(
    request: Request,
    file_ids: Annotated[str, Path(description='需要转移的文件ID')],
    transfer_file: TransferFileModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
    user_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
    dept_data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    transfer_file_result = await FileTransferService.transfer_file_services(
        query_db,
        current_user,
        file_ids,
        transfer_file,
        file_data_scope_sql,
        user_data_scope_sql,
        dept_data_scope_sql,
        request=request,
    )
    logger.info(transfer_file_result.message)

    return ResponseUtil.success(msg=transfer_file_result.message)


@file_controller.delete(
    '/{file_ids}',
    summary='删除文件接口',
    description='用于批量删除文件及其物理内容',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:remove')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_DELETE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件管理', business_type=BusinessType.DELETE)
async def delete_system_file(
    request: Request,
    file_ids: Annotated[str, Path(description='需要删除的文件ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    delete_file_result = await FileLifecycleService.delete_file_services(
        query_db,
        current_user,
        DeleteFileModel(fileIds=file_ids),
        file_data_scope_sql,
        request=request,
    )
    logger.info(delete_file_result.message)

    return ResponseUtil.success(msg=delete_file_result.message)


@file_controller.put(
    '/{file_ids}/restore',
    summary='恢复文件接口',
    description='用于批量恢复回收站中的文件',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:restore')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_RESTORE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件管理', business_type=BusinessType.UPDATE)
async def restore_system_file(
    request: Request,
    file_ids: Annotated[str, Path(description='需要恢复的文件ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    restore_file_result = await FileLifecycleService.restore_file_services(
        query_db,
        current_user,
        file_ids,
        file_data_scope_sql,
        request=request,
    )
    logger.info(restore_file_result.message)

    return ResponseUtil.success(msg=restore_file_result.message)


@file_controller.delete(
    '/purge/{file_ids}',
    summary='永久清理回收站文件接口',
    description='用于批量永久清理回收站文件及其管理元数据，操作不可恢复',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:file:purge')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_FILE_DELETE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='文件管理', business_type=BusinessType.CLEAN)
async def purge_system_file(
    request: Request,
    file_ids: Annotated[str, Path(description='需要永久清理的文件ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    purge_file_result = await FileLifecycleService.purge_file_services(
        query_db,
        current_user,
        file_ids,
        file_data_scope_sql,
        request=request,
    )
    logger.info(purge_file_result.message)

    return ResponseUtil.success(msg=purge_file_result.message)


@file_controller.get(
    '/{file_id}',
    summary='获取文件详情接口',
    description='用于获取指定文件的详细信息',
    response_model=DataResponseModel[FileInfoDisplayModel],
    dependencies=[UserInterfaceAuthDependency('system:file:query')],
)
async def get_system_file_detail(
    request: Request,
    file_id: UUID,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    file_data_scope_sql: Annotated[
        ColumnElement,
        DataScopeDependency(SysFileInfo, user_alias='owner_user_id', dept_alias='dept_id'),
    ],
) -> Response:
    file_detail_result = await FileQueryService.file_detail_services(query_db, str(file_id), file_data_scope_sql)
    logger.info(f'获取file_id为{file_id}的信息成功')

    return ResponseUtil.success(data=file_detail_result)
