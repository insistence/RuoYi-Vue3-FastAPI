from datetime import datetime
from typing import Annotated

from fastapi import Path, Query, Request, Response
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
from common.vo import DataResponseModel, ResponseBaseModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.vo.dept_vo import DeleteDeptModel, DeptModel, DeptQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.dept_service import DeptService
from utils.log_util import logger
from utils.response_util import ResponseUtil

dept_controller = APIRouterPro(
    prefix='/system/dept', order_num=6, tags=['系统管理-部门管理'], dependencies=[PreAuthDependency()]
)


@dept_controller.get(
    '/list/exclude/{dept_id}',
    summary='获取编辑部门的下拉树接口',
    description='用于获取部门下拉树，不包含指定部门及其子部门',
    response_model=DataResponseModel[list[DeptModel]],
    dependencies=[UserInterfaceAuthDependency('system:dept:list')],
)
async def get_system_dept_tree_for_edit_option(
    request: Request,
    dept_id: Annotated[int, Path(description='部门id')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    dept_query = DeptModel(deptId=dept_id)
    dept_query_result = await DeptService.get_dept_for_edit_option_services(query_db, dept_query, data_scope_sql)
    logger.info('获取成功')

    return ResponseUtil.success(data=dept_query_result)


@dept_controller.get(
    '/list',
    summary='获取部门列表接口',
    description='用于获取部门列表',
    response_model=DataResponseModel[list[DeptModel]],
    dependencies=[UserInterfaceAuthDependency('system:dept:list')],
)
async def get_system_dept_list(
    request: Request,
    dept_query: Annotated[DeptQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    dept_query_result = await DeptService.get_dept_list_services(query_db, dept_query, data_scope_sql)
    logger.info('获取成功')

    return ResponseUtil.success(data=dept_query_result)


@dept_controller.post(
    '',
    summary='新增部门接口',
    description='用于新增部门',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dept:add')],
)
@ValidateFields(validate_model='add_dept')
@Log(title='部门管理', business_type=BusinessType.INSERT)
async def add_system_dept(
    request: Request,
    add_dept: DeptModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_dept.create_by = current_user.user.user_name
    add_dept.create_time = datetime.now()
    add_dept.update_by = current_user.user.user_name
    add_dept.update_time = datetime.now()
    add_dept_result = await DeptService.add_dept_services(query_db, add_dept)
    logger.info(add_dept_result.message)

    return ResponseUtil.success(msg=add_dept_result.message)


@dept_controller.put(
    '',
    summary='编辑部门接口',
    description='用于编辑部门',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dept:edit')],
)
@ValidateFields(validate_model='edit_dept')
@Log(title='部门管理', business_type=BusinessType.UPDATE)
async def edit_system_dept(
    request: Request,
    edit_dept: DeptModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    if not current_user.user.admin:
        await DeptService.check_dept_data_scope_services(query_db, edit_dept.dept_id, data_scope_sql)
    edit_dept.update_by = current_user.user.user_name
    edit_dept.update_time = datetime.now()
    edit_dept_result = await DeptService.edit_dept_services(query_db, edit_dept)
    logger.info(edit_dept_result.message)

    return ResponseUtil.success(msg=edit_dept_result.message)


@dept_controller.delete(
    '/{dept_ids}',
    summary='删除部门接口',
    description='用于删除部门',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dept:remove')],
)
@Log(title='部门管理', business_type=BusinessType.DELETE)
async def delete_system_dept(
    request: Request,
    dept_ids: Annotated[str, Path(description='需要删除的部门id')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    dept_id_list = dept_ids.split(',') if dept_ids else []
    if dept_id_list:
        for dept_id in dept_id_list:
            if not current_user.user.admin:
                await DeptService.check_dept_data_scope_services(query_db, int(dept_id), data_scope_sql)
    delete_dept = DeleteDeptModel(deptIds=dept_ids)
    delete_dept.update_by = current_user.user.user_name
    delete_dept.update_time = datetime.now()
    delete_dept_result = await DeptService.delete_dept_services(query_db, delete_dept)
    logger.info(delete_dept_result.message)

    return ResponseUtil.success(msg=delete_dept_result.message)


@dept_controller.get(
    '/{dept_id}',
    summary='获取部门详情接口',
    description='用于获取指定部门的详情信息',
    response_model=DataResponseModel[DeptModel],
    dependencies=[UserInterfaceAuthDependency('system:dept:query')],
)
async def query_detail_system_dept(
    request: Request,
    dept_id: Annotated[int, Path(description='部门id')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysDept)],
) -> Response:
    if not current_user.user.admin:
        await DeptService.check_dept_data_scope_services(query_db, dept_id, data_scope_sql)
    detail_dept_result = await DeptService.dept_detail_services(query_db, dept_id)
    logger.info(f'获取dept_id为{dept_id}的信息成功')

    return ResponseUtil.success(data=detail_dept_result)
