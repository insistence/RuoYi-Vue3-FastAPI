from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.data_scope import GetDataScope
from common.aspect.interface_auth import CheckUserInterfaceAuth
from common.enums import BusinessType
from config.get_db import get_db
from module_admin.entity.vo.dept_vo import DeleteDeptModel, DeptModel, DeptQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.dept_service import DeptService
from module_admin.service.login_service import LoginService
from utils.log_util import logger
from utils.response_util import ResponseUtil

dept_controller = APIRouter(prefix='/system/dept', dependencies=[Depends(LoginService.get_current_user)])


@dept_controller.get(
    '/list/exclude/{dept_id}',
    response_model=list[DeptModel],
    dependencies=[Depends(CheckUserInterfaceAuth('system:dept:list'))],
)
async def get_system_dept_tree_for_edit_option(
    request: Request,
    dept_id: Annotated[int, Path(description='部门id')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    dept_query = DeptModel(deptId=dept_id)
    dept_query_result = await DeptService.get_dept_for_edit_option_services(query_db, dept_query, data_scope_sql)
    logger.info('获取成功')

    return ResponseUtil.success(data=dept_query_result)


@dept_controller.get(
    '/list', response_model=list[DeptModel], dependencies=[Depends(CheckUserInterfaceAuth('system:dept:list'))]
)
async def get_system_dept_list(
    request: Request,
    dept_query: Annotated[DeptQueryModel, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    dept_query_result = await DeptService.get_dept_list_services(query_db, dept_query, data_scope_sql)
    logger.info('获取成功')

    return ResponseUtil.success(data=dept_query_result)


@dept_controller.post('', dependencies=[Depends(CheckUserInterfaceAuth('system:dept:add'))])
@ValidateFields(validate_model='add_dept')
@Log(title='部门管理', business_type=BusinessType.INSERT)
async def add_system_dept(
    request: Request,
    add_dept: DeptModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    add_dept.create_by = current_user.user.user_name
    add_dept.create_time = datetime.now()
    add_dept.update_by = current_user.user.user_name
    add_dept.update_time = datetime.now()
    add_dept_result = await DeptService.add_dept_services(query_db, add_dept)
    logger.info(add_dept_result.message)

    return ResponseUtil.success(data=add_dept_result)


@dept_controller.put('', dependencies=[Depends(CheckUserInterfaceAuth('system:dept:edit'))])
@ValidateFields(validate_model='edit_dept')
@Log(title='部门管理', business_type=BusinessType.UPDATE)
async def edit_system_dept(
    request: Request,
    edit_dept: DeptModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    if not current_user.user.admin:
        await DeptService.check_dept_data_scope_services(query_db, edit_dept.dept_id, data_scope_sql)
    edit_dept.update_by = current_user.user.user_name
    edit_dept.update_time = datetime.now()
    edit_dept_result = await DeptService.edit_dept_services(query_db, edit_dept)
    logger.info(edit_dept_result.message)

    return ResponseUtil.success(msg=edit_dept_result.message)


@dept_controller.delete('/{dept_ids}', dependencies=[Depends(CheckUserInterfaceAuth('system:dept:remove'))])
@Log(title='部门管理', business_type=BusinessType.DELETE)
async def delete_system_dept(
    request: Request,
    dept_ids: Annotated[str, Path(description='需要删除的部门id')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
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
    '/{dept_id}', response_model=DeptModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dept:query'))]
)
async def query_detail_system_dept(
    request: Request,
    dept_id: Annotated[int, Path(description='部门id')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    if not current_user.user.admin:
        await DeptService.check_dept_data_scope_services(query_db, dept_id, data_scope_sql)
    detail_dept_result = await DeptService.dept_detail_services(query_db, dept_id)
    logger.info(f'获取dept_id为{dept_id}的信息成功')

    return ResponseUtil.success(data=detail_dept_result)
