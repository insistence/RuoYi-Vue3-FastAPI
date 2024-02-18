from fastapi import APIRouter, Request
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, CurrentUserModel
from module_admin.service.role_service import *
from module_admin.service.dept_service import DeptService, DeptModel
from module_admin.service.user_service import UserService, UserRoleQueryModel, UserRolePageQueryModel, CrudUserRoleModel
from utils.response_util import *
from utils.log_util import *
from utils.page_util import PageResponseModel
from utils.common_util import bytes2file_response
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.aspect.data_scope import GetDataScope
from module_admin.annotation.log_annotation import log_decorator


roleController = APIRouter(prefix='/system/role', dependencies=[Depends(LoginService.get_current_user)])


@roleController.get("/deptTree/{role_id}", dependencies=[Depends(CheckUserInterfaceAuth('system:role:query'))])
async def get_system_role_dept_tree(request: Request, role_id: int, query_db: Session = Depends(get_db), data_scope_sql: str = Depends(GetDataScope('SysDept'))):
    try:
        dept_query_result = DeptService.get_dept_tree_services(query_db, DeptModel(**{}), data_scope_sql)
        role_dept_query_result = RoleService.get_role_dept_tree_services(query_db, role_id)
        role_dept_query_result.depts = dept_query_result
        logger.info('获取成功')
        return ResponseUtil.success(model_content=role_dept_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
    
    
@roleController.get("/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:role:list'))])
async def get_system_role_list(request: Request, role_page_query: RolePageQueryModel = Depends(RolePageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        role_page_query_result = RoleService.get_role_list_services(query_db, role_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=role_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
    
    
@roleController.post("", dependencies=[Depends(CheckUserInterfaceAuth('system:role:add'))])
@log_decorator(title='角色管理', business_type=1)
async def add_system_role(request: Request, add_role: AddRoleModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_role.create_by = current_user.user.user_name
        add_role.update_by = current_user.user.user_name
        add_role_result = RoleService.add_role_services(query_db, add_role)
        if add_role_result.is_success:
            logger.info(add_role_result.message)
            return ResponseUtil.success(msg=add_role_result.message)
        else:
            logger.warning(add_role_result.message)
            return ResponseUtil.failure(msg=add_role_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
    
    
@roleController.put("", dependencies=[Depends(CheckUserInterfaceAuth('system:role:edit'))])
@log_decorator(title='角色管理', business_type=2)
async def edit_system_role(request: Request, edit_role: AddRoleModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_role.update_by = current_user.user.user_name
        edit_role.update_time = datetime.now()
        edit_role_result = RoleService.edit_role_services(query_db, edit_role)
        if edit_role_result.is_success:
            logger.info(edit_role_result.message)
            return ResponseUtil.success(msg=edit_role_result.message)
        else:
            logger.warning(edit_role_result.message)
            return ResponseUtil.failure(msg=edit_role_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.put("/dataScope", dependencies=[Depends(CheckUserInterfaceAuth('system:role:edit'))])
@log_decorator(title='角色管理', business_type=4)
async def edit_system_role_datascope(request: Request, role_data_scope: AddRoleModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        role_data_scope.update_by = current_user.user.user_name
        role_data_scope.update_time = datetime.now()
        role_data_scope_result = RoleService.role_datascope_services(query_db, role_data_scope)
        if role_data_scope_result.is_success:
            logger.info(role_data_scope_result.message)
            return ResponseUtil.success(msg=role_data_scope_result.message)
        else:
            logger.warning(role_data_scope_result.message)
            return ResponseUtil.failure(msg=role_data_scope_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
    
    
@roleController.delete("/{role_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:role:remove'))])
@log_decorator(title='角色管理', business_type=3)
async def delete_system_role(request: Request, role_ids: str, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        delete_role = DeleteRoleModel(
            roleIds=role_ids,
            updateBy=current_user.user.user_name,
            updateTime=datetime.now()
        )
        delete_role_result = RoleService.delete_role_services(query_db, delete_role)
        if delete_role_result.is_success:
            logger.info(delete_role_result.message)
            return ResponseUtil.success(msg=delete_role_result.message)
        else:
            logger.warning(delete_role_result.message)
            return ResponseUtil.failure(msg=delete_role_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
    
    
@roleController.get("/{role_id}", response_model=RoleModel, dependencies=[Depends(CheckUserInterfaceAuth('system:role:query'))])
async def query_detail_system_role(request: Request, role_id: int, query_db: Session = Depends(get_db)):
    try:
        role_detail_result = RoleService.role_detail_services(query_db, role_id)
        logger.info(f'获取role_id为{role_id}的信息成功')
        return ResponseUtil.success(data=role_detail_result.model_dump(by_alias=True))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.post("/export", dependencies=[Depends(CheckUserInterfaceAuth('system:role:export'))])
@log_decorator(title='角色管理', business_type=5)
async def export_system_role_list(request: Request, role_page_query: RolePageQueryModel = Depends(RolePageQueryModel.as_form), query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        role_query_result = RoleService.get_role_list_services(query_db, role_page_query, is_page=False)
        role_export_result = RoleService.export_role_list_services(role_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(role_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.put("/changeStatus", dependencies=[Depends(CheckUserInterfaceAuth('system:role:edit'))])
@log_decorator(title='角色管理', business_type=2)
async def reset_system_role_status(request: Request, edit_role: AddRoleModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_role.update_by = current_user.user.user_name
        edit_role.update_time = datetime.now()
        edit_role.type = 'status'
        edit_role_result = RoleService.edit_role_services(query_db, edit_role)
        if edit_role_result.is_success:
            logger.info(edit_role_result.message)
            return ResponseUtil.success(msg=edit_role_result.message)
        else:
            logger.warning(edit_role_result.message)
            return ResponseUtil.failure(msg=edit_role_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.get("/authUser/allocatedList", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:role:list'))])
async def get_system_allocated_user_list(request: Request, user_role: UserRolePageQueryModel = Depends(UserRolePageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        role_user_allocated_page_query_result = RoleService.get_role_user_allocated_list_services(query_db, user_role, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=role_user_allocated_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.get("/authUser/unallocatedList", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:role:list'))])
async def get_system_unallocated_user_list(request: Request, user_role: UserRolePageQueryModel = Depends(UserRolePageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        role_user_unallocated_page_query_result = RoleService.get_role_user_unallocated_list_services(query_db, user_role, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=role_user_unallocated_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.put("/authUser/selectAll", dependencies=[Depends(CheckUserInterfaceAuth('system:role:edit'))])
@log_decorator(title='角色管理', business_type=4)
async def add_system_role_user(request: Request, add_role_user: CrudUserRoleModel = Depends(CrudUserRoleModel.as_query), query_db: Session = Depends(get_db)):
    try:
        add_role_user_result = UserService.add_user_role_services(query_db, add_role_user)
        if add_role_user_result.is_success:
            logger.info(add_role_user_result.message)
            return ResponseUtil.success(msg=add_role_user_result.message)
        else:
            logger.warning(add_role_user_result.message)
            return ResponseUtil.failure(msg=add_role_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.put("/authUser/cancel", dependencies=[Depends(CheckUserInterfaceAuth('system:role:edit'))])
@log_decorator(title='角色管理', business_type=4)
async def cancel_system_role_user(request: Request, cancel_user_role: CrudUserRoleModel, query_db: Session = Depends(get_db)):
    try:
        cancel_user_role_result = UserService.delete_user_role_services(query_db, cancel_user_role)
        if cancel_user_role_result.is_success:
            logger.info(cancel_user_role_result.message)
            return ResponseUtil.success(msg=cancel_user_role_result.message)
        else:
            logger.warning(cancel_user_role_result.message)
            return ResponseUtil.failure(msg=cancel_user_role_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@roleController.put("/authUser/cancelAll", dependencies=[Depends(CheckUserInterfaceAuth('system:role:edit'))])
@log_decorator(title='角色管理', business_type=4)
async def batch_cancel_system_role_user(request: Request, batch_cancel_user_role: CrudUserRoleModel = Depends(CrudUserRoleModel.as_query), query_db: Session = Depends(get_db)):
    try:
        batch_cancel_user_role_result = UserService.delete_user_role_services(query_db, batch_cancel_user_role)
        if batch_cancel_user_role_result.is_success:
            logger.info(batch_cancel_user_role_result.message)
            return ResponseUtil.success(msg=batch_cancel_user_role_result.message)
        else:
            logger.warning(batch_cancel_user_role_result.message)
            return ResponseUtil.failure(msg=batch_cancel_user_role_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
