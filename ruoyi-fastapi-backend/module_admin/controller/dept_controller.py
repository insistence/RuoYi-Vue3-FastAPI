from datetime import datetime
from fastapi import APIRouter, Depends, Request
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from config.enums import BusinessType
from config.get_db import get_db
from module_admin.annotation.log_annotation import Log
from module_admin.aspect.data_scope import GetDataScope
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.dept_vo import DeleteDeptModel, DeptModel, DeptQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.dept_service import DeptService
from module_admin.service.login_service import LoginService
from utils.log_util import logger
from utils.response_util import ResponseUtil


deptController = APIRouter(prefix='/system/dept', dependencies=[Depends(LoginService.get_current_user)])


@deptController.get(
    '/list/exclude/{dept_id}',
    response_model=List[DeptModel],
    dependencies=[Depends(CheckUserInterfaceAuth('system:dept:list'))],
)
async def get_system_dept_tree_for_edit_option(
    request: Request,
    dept_id: int,
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('SysDept')),
):
    dept_query = DeptModel(deptId=dept_id)
    dept_query_result = await DeptService.get_dept_for_edit_option_services(query_db, dept_query, data_scope_sql)
    logger.info('获取成功')

    return ResponseUtil.success(data=dept_query_result)


@deptController.get(
    '/list', response_model=List[DeptModel], dependencies=[Depends(CheckUserInterfaceAuth('system:dept:list'))]
)
async def get_system_dept_list(
    request: Request,
    dept_query: DeptQueryModel = Depends(DeptQueryModel.as_query),
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('SysDept')),
):
    dept_query_result = await DeptService.get_dept_list_services(query_db, dept_query, data_scope_sql)
    logger.info('获取成功')

    return ResponseUtil.success(data=dept_query_result)


@deptController.post('', dependencies=[Depends(CheckUserInterfaceAuth('system:dept:add'))])
@ValidateFields(validate_model='add_dept')
@Log(title='部门管理', business_type=BusinessType.INSERT)
async def add_system_dept(
    request: Request,
    add_dept: DeptModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dept.create_by = current_user.user.user_name
    add_dept.create_time = datetime.now()
    add_dept.update_by = current_user.user.user_name
    add_dept.update_time = datetime.now()
    add_dept_result = await DeptService.add_dept_services(query_db, add_dept)
    logger.info(add_dept_result.message)

    return ResponseUtil.success(data=add_dept_result)


@deptController.put('', dependencies=[Depends(CheckUserInterfaceAuth('system:dept:edit'))])
@ValidateFields(validate_model='edit_dept')
@Log(title='部门管理', business_type=BusinessType.UPDATE)
async def edit_system_dept(
    request: Request,
    edit_dept: DeptModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
    data_scope_sql: str = Depends(GetDataScope('SysDept')),
):
    if not current_user.user.admin:
        await DeptService.check_dept_data_scope_services(query_db, edit_dept.dept_id, data_scope_sql)
    edit_dept.update_by = current_user.user.user_name
    edit_dept.update_time = datetime.now()
    edit_dept_result = await DeptService.edit_dept_services(query_db, edit_dept)
    logger.info(edit_dept_result.message)

    return ResponseUtil.success(msg=edit_dept_result.message)


@deptController.delete('/{dept_ids}', dependencies=[Depends(CheckUserInterfaceAuth('system:dept:remove'))])
@Log(title='部门管理', business_type=BusinessType.DELETE)
async def delete_system_dept(
    request: Request,
    dept_ids: str,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
    data_scope_sql: str = Depends(GetDataScope('SysDept')),
):
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


@deptController.get(
    '/{dept_id}', response_model=DeptModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dept:query'))]
)
async def query_detail_system_dept(
    request: Request,
    dept_id: int,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
    data_scope_sql: str = Depends(GetDataScope('SysDept')),
):
    if not current_user.user.admin:
        await DeptService.check_dept_data_scope_services(query_db, dept_id, data_scope_sql)
    detail_dept_result = await DeptService.dept_detail_services(query_db, dept_id)
    logger.info(f'获取dept_id为{dept_id}的信息成功')

    return ResponseUtil.success(data=detail_dept_result)
