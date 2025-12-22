from datetime import datetime
from typing import Annotated

from fastapi import Form, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic_validation_decorator import ValidateFields
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.data_scope import DataScopeDependency
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, DynamicResponseModel, PageResponseModel, ResponseBaseModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.dept_vo import DeptModel
from module_admin.entity.vo.role_vo import (
    AddRoleModel,
    DeleteRoleModel,
    RoleDeptQueryModel,
    RoleModel,
    RolePageQueryModel,
)
from module_admin.entity.vo.user_vo import CrudUserRoleModel, CurrentUserModel, UserInfoModel, UserRolePageQueryModel
from module_admin.service.dept_service import DeptService
from module_admin.service.role_service import RoleService
from module_admin.service.user_service import UserService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

role_controller = APIRouterPro(
    prefix='/system/role', order_num=4, tags=['系统管理-角色管理'], dependencies=[PreAuthDependency()]
)


@role_controller.get(
    '/deptTree/{role_id}',
    summary='获取自定义数据权限时可见的部门树接口',
    description='用于自定义数据权限时获取当前用户可见的部门树',
    response_model=DynamicResponseModel[RoleDeptQueryModel],
    dependencies=[UserInterfaceAuthDependency('system:role:query')],
)
async def get_system_role_dept_tree(
    request: Request,
    role_id: Annotated[int, Path(description='角色ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    dept_query_result = await DeptService.get_dept_tree_services(query_db, DeptModel(), data_scope_sql)
    role_dept_query_result = await RoleService.get_role_dept_tree_services(query_db, role_id)
    role_dept_query_result.depts = dept_query_result
    logger.info('获取成功')

    return ResponseUtil.success(model_content=role_dept_query_result)


@role_controller.get(
    '/list',
    summary='获取角色分页列表接口',
    description='用于获取角色分页列表',
    response_model=PageResponseModel[RoleModel],
    dependencies=[UserInterfaceAuthDependency('system:role:list')],
)
async def get_system_role_list(
    request: Request,
    role_page_query: Annotated[RolePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    role_page_query_result = await RoleService.get_role_list_services(
        query_db, role_page_query, data_scope_sql, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=role_page_query_result)


@role_controller.post(
    '',
    summary='新增角色接口',
    description='用于新增角色',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:add')],
)
@ValidateFields(validate_model='add_role')
@Log(title='角色管理', business_type=BusinessType.INSERT)
async def add_system_role(
    request: Request,
    add_role: AddRoleModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_role.create_by = current_user.user.user_name
    add_role.create_time = datetime.now()
    add_role.update_by = current_user.user.user_name
    add_role.update_time = datetime.now()
    add_role_result = await RoleService.add_role_services(query_db, add_role)
    logger.info(add_role_result.message)

    return ResponseUtil.success(msg=add_role_result.message)


@role_controller.put(
    '',
    summary='编辑角色接口',
    description='用于编辑角色',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:edit')],
)
@ValidateFields(validate_model='edit_role')
@Log(title='角色管理', business_type=BusinessType.UPDATE)
async def edit_system_role(
    request: Request,
    edit_role: AddRoleModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    await RoleService.check_role_allowed_services(edit_role)
    if not current_user.user.admin:
        await RoleService.check_role_data_scope_services(query_db, str(edit_role.role_id), data_scope_sql)
    edit_role.update_by = current_user.user.user_name
    edit_role.update_time = datetime.now()
    edit_role_result = await RoleService.edit_role_services(query_db, edit_role)
    logger.info(edit_role_result.message)

    return ResponseUtil.success(msg=edit_role_result.message)


@role_controller.put(
    '/dataScope',
    summary='编辑角色数据权限接口',
    description='用于编辑角色数据权限',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:edit')],
)
@Log(title='角色管理', business_type=BusinessType.GRANT)
async def edit_system_role_datascope(
    request: Request,
    role_data_scope: AddRoleModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    await RoleService.check_role_allowed_services(role_data_scope)
    if not current_user.user.admin:
        await RoleService.check_role_data_scope_services(query_db, str(role_data_scope.role_id), data_scope_sql)
    edit_role = AddRoleModel(
        roleId=role_data_scope.role_id,
        dataScope=role_data_scope.data_scope,
        deptIds=role_data_scope.dept_ids,
        deptCheckStrictly=role_data_scope.dept_check_strictly,
        updateBy=current_user.user.user_name,
        updateTime=datetime.now(),
    )
    role_data_scope_result = await RoleService.role_datascope_services(query_db, edit_role)
    logger.info(role_data_scope_result.message)

    return ResponseUtil.success(msg=role_data_scope_result.message)


@role_controller.delete(
    '/{role_ids}',
    summary='删除角色接口',
    description='用于删除角色',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:remove')],
)
@Log(title='角色管理', business_type=BusinessType.DELETE)
async def delete_system_role(
    request: Request,
    role_ids: Annotated[str, Path(description='需要删除的角色ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    role_id_list = role_ids.split(',') if role_ids else []
    if role_id_list:
        for role_id in role_id_list:
            await RoleService.check_role_allowed_services(RoleModel(roleId=int(role_id)))
            if not current_user.user.admin:
                await RoleService.check_role_data_scope_services(query_db, role_id, data_scope_sql)
    delete_role = DeleteRoleModel(roleIds=role_ids, updateBy=current_user.user.user_name, updateTime=datetime.now())
    delete_role_result = await RoleService.delete_role_services(query_db, delete_role)
    logger.info(delete_role_result.message)

    return ResponseUtil.success(msg=delete_role_result.message)


@role_controller.get(
    '/{role_id}',
    summary='获取角色详情接口',
    description='用于获取指定角色的详细信息',
    response_model=DataResponseModel[RoleModel],
    dependencies=[UserInterfaceAuthDependency('system:role:query')],
)
async def query_detail_system_role(
    request: Request,
    role_id: Annotated[int, Path(description='角色ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    if not current_user.user.admin:
        await RoleService.check_role_data_scope_services(query_db, str(role_id), data_scope_sql)
    role_detail_result = await RoleService.role_detail_services(query_db, role_id)
    logger.info(f'获取role_id为{role_id}的信息成功')

    return ResponseUtil.success(data=role_detail_result.model_dump(by_alias=True))


@role_controller.post(
    '/export',
    summary='导出角色列表接口',
    description='用于导出当前符合查询条件的角色列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回角色列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('system:role:export')],
)
@Log(title='角色管理', business_type=BusinessType.EXPORT)
async def export_system_role_list(
    request: Request,
    role_page_query: Annotated[RolePageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    # 获取全量数据
    role_query_result = await RoleService.get_role_list_services(
        query_db, role_page_query, data_scope_sql, is_page=False
    )
    role_export_result = await RoleService.export_role_list_services(role_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(role_export_result))


@role_controller.put(
    '/changeStatus',
    summary='修改角色状态接口',
    description='用于修改角色状态',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:edit')],
)
@Log(title='角色管理', business_type=BusinessType.UPDATE)
async def reset_system_role_status(
    request: Request,
    change_role: AddRoleModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    await RoleService.check_role_allowed_services(change_role)
    if not current_user.user.admin:
        await RoleService.check_role_data_scope_services(query_db, str(change_role.role_id), data_scope_sql)
    edit_role = AddRoleModel(
        roleId=change_role.role_id,
        status=change_role.status,
        updateBy=current_user.user.user_name,
        updateTime=datetime.now(),
        type='status',
    )
    edit_role_result = await RoleService.edit_role_services(query_db, edit_role)
    logger.info(edit_role_result.message)

    return ResponseUtil.success(msg=edit_role_result.message)


@role_controller.get(
    '/authUser/allocatedList',
    summary='获取已分配用户分页列表接口',
    description='用于获取指定角色已分配的用户分页列表',
    response_model=PageResponseModel[UserInfoModel],
    dependencies=[UserInterfaceAuthDependency('system:role:list')],
)
async def get_system_allocated_user_list(
    request: Request,
    user_role: Annotated[UserRolePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
) -> Response:
    role_user_allocated_page_query_result = await RoleService.get_role_user_allocated_list_services(
        query_db, user_role, data_scope_sql, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=role_user_allocated_page_query_result)


@role_controller.get(
    '/authUser/unallocatedList',
    summary='获取未分配用户分页列表接口',
    description='用于获取指定角色未分配的用户分页列表',
    response_model=PageResponseModel[UserInfoModel],
    dependencies=[UserInterfaceAuthDependency('system:role:list')],
)
async def get_system_unallocated_user_list(
    request: Request,
    user_role: Annotated[UserRolePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
) -> Response:
    role_user_unallocated_page_query_result = await RoleService.get_role_user_unallocated_list_services(
        query_db, user_role, data_scope_sql, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=role_user_unallocated_page_query_result)


@role_controller.put(
    '/authUser/selectAll',
    summary='分配用户给角色接口',
    description='用于给指定角色分配用户',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:edit')],
)
@Log(title='角色管理', business_type=BusinessType.GRANT)
async def add_system_role_user(
    request: Request,
    add_role_user: Annotated[CrudUserRoleModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    if not current_user.user.admin:
        await RoleService.check_role_data_scope_services(query_db, str(add_role_user.role_id), data_scope_sql)
    add_role_user_result = await UserService.add_user_role_services(query_db, add_role_user)
    logger.info(add_role_user_result.message)

    return ResponseUtil.success(msg=add_role_user_result.message)


@role_controller.put(
    '/authUser/cancel',
    summary='取消分配用户给角色接口',
    description='用于取消指定用户分配给角色',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:edit')],
)
@Log(title='角色管理', business_type=BusinessType.GRANT)
async def cancel_system_role_user(
    request: Request,
    cancel_user_role: CrudUserRoleModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    cancel_user_role_result = await UserService.delete_user_role_services(query_db, cancel_user_role)
    logger.info(cancel_user_role_result.message)

    return ResponseUtil.success(msg=cancel_user_role_result.message)


@role_controller.put(
    '/authUser/cancelAll',
    summary='批量取消分配用户给角色接口',
    description='用于批量取消用户分配给角色',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:role:edit')],
)
@Log(title='角色管理', business_type=BusinessType.GRANT)
async def batch_cancel_system_role_user(
    request: Request,
    batch_cancel_user_role: Annotated[CrudUserRoleModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    batch_cancel_user_role_result = await UserService.delete_user_role_services(query_db, batch_cancel_user_role)
    logger.info(batch_cancel_user_role_result.message)

    return ResponseUtil.success(msg=batch_cancel_user_role_result.message)
