import os
from datetime import datetime
from typing import Annotated, Literal, Optional, Union

import aiofiles
from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, Response, UploadFile
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.data_scope import GetDataScope
from common.aspect.interface_auth import CheckUserInterfaceAuth
from common.enums import BusinessType
from config.env import UploadConfig
from config.get_db import get_db
from module_admin.entity.vo.dept_vo import DeptModel
from module_admin.entity.vo.user_vo import (
    AddUserModel,
    CrudUserRoleModel,
    CurrentUserModel,
    DeleteUserModel,
    EditUserModel,
    ResetPasswordModel,
    ResetUserModel,
    UserDetailModel,
    UserInfoModel,
    UserModel,
    UserPageQueryModel,
    UserProfileModel,
    UserRoleQueryModel,
    UserRoleResponseModel,
)
from module_admin.service.dept_service import DeptService
from module_admin.service.login_service import LoginService
from module_admin.service.role_service import RoleService
from module_admin.service.user_service import UserService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.page_util import PageResponseModel
from utils.pwd_util import PwdUtil
from utils.response_util import ResponseUtil
from utils.upload_util import UploadUtil

user_controller = APIRouter(prefix='/system/user', dependencies=[Depends(LoginService.get_current_user)])


@user_controller.get('/deptTree', dependencies=[Depends(CheckUserInterfaceAuth('system:user:list'))])
async def get_system_dept_tree(
    request: Request,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    dept_query_result = await DeptService.get_dept_tree_services(query_db, DeptModel(), data_scope_sql)
    logger.info('获取成功')

    return ResponseUtil.success(data=dept_query_result)


@user_controller.get(
    '/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:list'))]
)
async def get_system_user_list(
    request: Request,
    user_page_query: Annotated[UserPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
) -> Response:
    # 获取分页数据
    user_page_query_result = await UserService.get_user_list_services(
        query_db, user_page_query, data_scope_sql, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=user_page_query_result)


@user_controller.post('', dependencies=[Depends(CheckUserInterfaceAuth('system:user:add'))])
@ValidateFields(validate_model='add_user')
@Log(title='用户管理', business_type=BusinessType.INSERT)
async def add_system_user(
    request: Request,
    add_user: AddUserModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    dept_data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
    role_data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    if not current_user.user.admin:
        await DeptService.check_dept_data_scope_services(query_db, add_user.dept_id, dept_data_scope_sql)
        await RoleService.check_role_data_scope_services(
            query_db, ','.join([str(item) for item in add_user.role_ids]), role_data_scope_sql
        )
    add_user.password = PwdUtil.get_password_hash(add_user.password)
    add_user.create_by = current_user.user.user_name
    add_user.create_time = datetime.now()
    add_user.update_by = current_user.user.user_name
    add_user.update_time = datetime.now()
    add_user_result = await UserService.add_user_services(query_db, add_user)
    logger.info(add_user_result.message)

    return ResponseUtil.success(msg=add_user_result.message)


@user_controller.put('', dependencies=[Depends(CheckUserInterfaceAuth('system:user:edit'))])
@ValidateFields(validate_model='edit_user')
@Log(title='用户管理', business_type=BusinessType.UPDATE)
async def edit_system_user(
    request: Request,
    edit_user: EditUserModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    user_data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
    dept_data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
    role_data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    await UserService.check_user_allowed_services(edit_user)
    if not current_user.user.admin:
        await UserService.check_user_data_scope_services(query_db, edit_user.user_id, user_data_scope_sql)
        await DeptService.check_dept_data_scope_services(query_db, edit_user.dept_id, dept_data_scope_sql)
        await RoleService.check_role_data_scope_services(
            query_db, ','.join([str(item) for item in edit_user.role_ids]), role_data_scope_sql
        )
    edit_user.update_by = current_user.user.user_name
    edit_user.update_time = datetime.now()
    edit_user_result = await UserService.edit_user_services(query_db, edit_user)
    logger.info(edit_user_result.message)

    return ResponseUtil.success(msg=edit_user_result.message)


@user_controller.delete('/{user_ids}', dependencies=[Depends(CheckUserInterfaceAuth('system:user:remove'))])
@Log(title='用户管理', business_type=BusinessType.DELETE)
async def delete_system_user(
    request: Request,
    user_ids: Annotated[str, Path(description='需要删除的用户ID')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
) -> Response:
    user_id_list = user_ids.split(',') if user_ids else []
    if user_id_list:
        if current_user.user.user_id in list(map(int, user_id_list)):
            logger.warning('当前登录用户不能删除')

            return ResponseUtil.failure(msg='当前登录用户不能删除')
        for user_id in user_id_list:
            await UserService.check_user_allowed_services(UserModel(userId=int(user_id)))
            if not current_user.user.admin:
                await UserService.check_user_data_scope_services(query_db, int(user_id), data_scope_sql)
    delete_user = DeleteUserModel(userIds=user_ids, updateBy=current_user.user.user_name, updateTime=datetime.now())
    delete_user_result = await UserService.delete_user_services(query_db, delete_user)
    logger.info(delete_user_result.message)

    return ResponseUtil.success(msg=delete_user_result.message)


@user_controller.put('/resetPwd', dependencies=[Depends(CheckUserInterfaceAuth('system:user:resetPwd'))])
@Log(title='用户管理', business_type=BusinessType.UPDATE)
async def reset_system_user_pwd(
    request: Request,
    reset_user: EditUserModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
) -> Response:
    await UserService.check_user_allowed_services(reset_user)
    if not current_user.user.admin:
        await UserService.check_user_data_scope_services(query_db, reset_user.user_id, data_scope_sql)
    edit_user = EditUserModel(
        userId=reset_user.user_id,
        password=PwdUtil.get_password_hash(reset_user.password),
        pwdUpdateDate=datetime.now(),
        updateBy=current_user.user.user_name,
        updateTime=datetime.now(),
        type='pwd',
    )
    edit_user_result = await UserService.edit_user_services(query_db, edit_user)
    logger.info(edit_user_result.message)

    return ResponseUtil.success(msg=edit_user_result.message)


@user_controller.put('/changeStatus', dependencies=[Depends(CheckUserInterfaceAuth('system:user:edit'))])
@Log(title='用户管理', business_type=BusinessType.UPDATE)
async def change_system_user_status(
    request: Request,
    change_user: EditUserModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
) -> Response:
    await UserService.check_user_allowed_services(change_user)
    if not current_user.user.admin:
        await UserService.check_user_data_scope_services(query_db, change_user.user_id, data_scope_sql)
    edit_user = EditUserModel(
        userId=change_user.user_id,
        status=change_user.status,
        updateBy=current_user.user.user_name,
        updateTime=datetime.now(),
        type='status',
    )
    edit_user_result = await UserService.edit_user_services(query_db, edit_user)
    logger.info(edit_user_result.message)

    return ResponseUtil.success(msg=edit_user_result.message)


@user_controller.get('/profile', response_model=UserProfileModel)
async def query_detail_system_user_profile(
    request: Request,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    profile_user_result = await UserService.user_profile_services(query_db, current_user.user.user_id)
    logger.info(f'获取user_id为{current_user.user.user_id}的信息成功')

    return ResponseUtil.success(model_content=profile_user_result)


@user_controller.get(
    '/{user_id}', response_model=UserDetailModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:query'))]
)
@user_controller.get(
    '/', response_model=UserDetailModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:query'))]
)
async def query_detail_system_user(
    request: Request,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
    user_id: Optional[Union[int, Literal['']]] = '',
) -> Response:
    if user_id and not current_user.user.admin:
        await UserService.check_user_data_scope_services(query_db, user_id, data_scope_sql)
    detail_user_result = await UserService.user_detail_services(query_db, user_id)
    logger.info(f'获取user_id为{user_id}的信息成功')

    return ResponseUtil.success(model_content=detail_user_result)


@user_controller.post('/profile/avatar')
@Log(title='个人信息', business_type=BusinessType.UPDATE)
async def change_system_user_profile_avatar(
    request: Request,
    avatarfile: Annotated[bytes, File()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    if avatarfile:
        relative_path = (
            f'avatar/{datetime.now().strftime("%Y")}/{datetime.now().strftime("%m")}/{datetime.now().strftime("%d")}'
        )
        dir_path = os.path.join(UploadConfig.UPLOAD_PATH, relative_path)
        try:
            os.makedirs(dir_path)
        except FileExistsError:
            pass
        avatar_name = f'avatar_{datetime.now().strftime("%Y%m%d%H%M%S")}{UploadConfig.UPLOAD_MACHINE}{UploadUtil.generate_random_number()}.png'
        avatar_path = os.path.join(dir_path, avatar_name)
        async with aiofiles.open(avatar_path, 'wb') as f:
            await f.write(avatarfile)
        edit_user = EditUserModel(
            userId=current_user.user.user_id,
            avatar=f'{UploadConfig.UPLOAD_PREFIX}/{relative_path}/{avatar_name}',
            updateBy=current_user.user.user_name,
            updateTime=datetime.now(),
            type='avatar',
        )
        edit_user_result = await UserService.edit_user_services(query_db, edit_user)
        logger.info(edit_user_result.message)

        return ResponseUtil.success(dict_content={'imgUrl': edit_user.avatar}, msg=edit_user_result.message)
    return ResponseUtil.failure(msg='上传图片异常，请联系管理员')


@user_controller.put('/profile')
@Log(title='个人信息', business_type=BusinessType.UPDATE)
async def change_system_user_profile_info(
    request: Request,
    user_info: UserInfoModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    edit_user = EditUserModel(
        **user_info.model_dump(exclude_unset=True, by_alias=True, exclude={'role_ids', 'post_ids'}),
        userId=current_user.user.user_id,
        userName=current_user.user.user_name,
        updateBy=current_user.user.user_name,
        updateTime=datetime.now(),
        roleIds=current_user.user.role_ids.split(',') if current_user.user.role_ids else [],
        postIds=current_user.user.post_ids.split(',') if current_user.user.post_ids else [],
        role=current_user.user.role,
    )
    edit_user_result = await UserService.edit_user_services(query_db, edit_user)
    logger.info(edit_user_result.message)

    return ResponseUtil.success(msg=edit_user_result.message)


@user_controller.put('/profile/updatePwd')
@Log(title='个人信息', business_type=BusinessType.UPDATE)
async def reset_system_user_password(
    request: Request,
    reset_password: ResetPasswordModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    reset_user = ResetUserModel(
        userId=current_user.user.user_id,
        oldPassword=reset_password.old_password,
        password=reset_password.new_password,
        pwdUpdateDate=datetime.now(),
        updateBy=current_user.user.user_name,
        updateTime=datetime.now(),
    )
    reset_user_result = await UserService.reset_user_services(query_db, reset_user)
    logger.info(reset_user_result.message)

    return ResponseUtil.success(msg=reset_user_result.message)


@user_controller.post('/importData', dependencies=[Depends(CheckUserInterfaceAuth('system:user:import'))])
@Log(title='用户管理', business_type=BusinessType.IMPORT)
async def batch_import_system_user(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    update_support: Annotated[bool, Query(alias='updateSupport')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    user_data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
    dept_data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    batch_import_result = await UserService.batch_import_user_services(
        request, query_db, file, update_support, current_user, user_data_scope_sql, dept_data_scope_sql
    )
    logger.info(batch_import_result.message)

    return ResponseUtil.success(msg=batch_import_result.message)


@user_controller.post('/importTemplate', dependencies=[Depends(CheckUserInterfaceAuth('system:user:import'))])
async def export_system_user_template(request: Request, query_db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    user_import_template_result = await UserService.get_user_import_template_services()
    logger.info('获取成功')

    return ResponseUtil.streaming(data=bytes2file_response(user_import_template_result))


@user_controller.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('system:user:export'))])
@Log(title='用户管理', business_type=BusinessType.EXPORT)
async def export_system_user_list(
    request: Request,
    user_page_query: Annotated[UserPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
) -> Response:
    # 获取全量数据
    user_query_result = await UserService.get_user_list_services(
        query_db, user_page_query, data_scope_sql, is_page=False
    )
    user_export_result = await UserService.export_user_list_services(user_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(user_export_result))


@user_controller.get(
    '/authRole/{user_id}',
    response_model=UserRoleResponseModel,
    dependencies=[Depends(CheckUserInterfaceAuth('system:user:query'))],
)
async def get_system_allocated_role_list(
    request: Request,
    user_id: Annotated[int, Path(description='用户ID')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    user_role_query = UserRoleQueryModel(userId=user_id)
    user_role_allocated_query_result = await UserService.get_user_role_allocated_list_services(
        query_db, user_role_query
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=user_role_allocated_query_result)


@user_controller.put(
    '/authRole',
    response_model=UserRoleResponseModel,
    dependencies=[Depends(CheckUserInterfaceAuth('system:user:edit'))],
)
@Log(title='用户管理', business_type=BusinessType.GRANT)
async def update_system_role_user(
    request: Request,
    user_id: Annotated[int, Query(alias='userId')],
    role_ids: Annotated[str, Query(alias='roleIds')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
    user_data_scope_sql: Annotated[str, Depends(GetDataScope('SysUser'))],
    role_data_scope_sql: Annotated[str, Depends(GetDataScope('SysDept'))],
) -> Response:
    if not current_user.user.admin:
        await UserService.check_user_data_scope_services(query_db, user_id, user_data_scope_sql)
        await RoleService.check_role_data_scope_services(query_db, role_ids, role_data_scope_sql)
    add_user_role_result = await UserService.add_user_role_services(
        query_db, CrudUserRoleModel(userId=user_id, roleIds=role_ids)
    )
    logger.info(add_user_role_result.message)

    return ResponseUtil.success(msg=add_user_role_result.message)
