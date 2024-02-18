from fastapi import APIRouter, Request
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, CurrentUserModel
from module_admin.service.dept_service import *
from utils.response_util import *
from utils.log_util import *
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.aspect.data_scope import GetDataScope
from module_admin.annotation.log_annotation import log_decorator


deptController = APIRouter(prefix='/system/dept', dependencies=[Depends(LoginService.get_current_user)])


@deptController.get("/list/exclude/{dept_id}", response_model=List[DeptModel], dependencies=[Depends(CheckUserInterfaceAuth('system:dept:list'))])
async def get_system_dept_tree_for_edit_option(request: Request, dept_id: int, query_db: Session = Depends(get_db), data_scope_sql: str = Depends(GetDataScope('SysDept'))):
    try:
        dept_query = DeptModel(deptId=dept_id)
        dept_query_result = DeptService.get_dept_for_edit_option_services(query_db, dept_query, data_scope_sql)
        logger.info('获取成功')
        return ResponseUtil.success(data=dept_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@deptController.get("/list", response_model=List[DeptModel], dependencies=[Depends(CheckUserInterfaceAuth('system:dept:list'))])
async def get_system_dept_list(request: Request, dept_query: DeptQueryModel = Depends(DeptQueryModel.as_query), query_db: Session = Depends(get_db), data_scope_sql: str = Depends(GetDataScope('SysDept'))):
    try:
        dept_query_result = DeptService.get_dept_list_services(query_db, dept_query, data_scope_sql)
        logger.info('获取成功')
        return ResponseUtil.success(data=dept_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@deptController.post("", dependencies=[Depends(CheckUserInterfaceAuth('system:dept:add'))])
@log_decorator(title='部门管理', business_type=1)
async def add_system_dept(request: Request, add_dept: DeptModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_dept.create_by = current_user.user.user_name
        add_dept.update_by = current_user.user.user_name
        add_dept_result = DeptService.add_dept_services(query_db, add_dept)
        if add_dept_result.is_success:
            logger.info(add_dept_result.message)
            return ResponseUtil.success(data=add_dept_result)
        else:
            logger.warning(add_dept_result.message)
            return ResponseUtil.failure(msg=add_dept_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@deptController.put("", dependencies=[Depends(CheckUserInterfaceAuth('system:dept:edit'))])
@log_decorator(title='部门管理', business_type=2)
async def edit_system_dept(request: Request, edit_dept: DeptModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_dept.update_by = current_user.user.user_name
        edit_dept.update_time = datetime.now()
        edit_dept_result = DeptService.edit_dept_services(query_db, edit_dept)
        if edit_dept_result.is_success:
            logger.info(edit_dept_result.message)
            return ResponseUtil.success(msg=edit_dept_result.message)
        else:
            logger.warning(edit_dept_result.message)
            return ResponseUtil.failure(msg=edit_dept_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@deptController.delete("/{dept_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:dept:remove'))])
@log_decorator(title='部门管理', business_type=3)
async def delete_system_dept(request: Request, dept_ids: str, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        delete_dept = DeleteDeptModel(deptIds=dept_ids)
        delete_dept.update_by = current_user.user.user_name
        delete_dept.update_time = datetime.now()
        delete_dept_result = DeptService.delete_dept_services(query_db, delete_dept)
        if delete_dept_result.is_success:
            logger.info(delete_dept_result.message)
            return ResponseUtil.success(msg=delete_dept_result.message)
        else:
            logger.warning(delete_dept_result.message)
            return ResponseUtil.failure(msg=delete_dept_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@deptController.get("/{dept_id}", response_model=DeptModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dept:query'))])
async def query_detail_system_dept(request: Request, dept_id: int, query_db: Session = Depends(get_db)):
    try:
        detail_dept_result = DeptService.dept_detail_services(query_db, dept_id)
        logger.info(f'获取dept_id为{dept_id}的信息成功')
        return ResponseUtil.success(data=detail_dept_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
