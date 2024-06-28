from fastapi import APIRouter, Request
from fastapi import Depends, File, Query
from config.get_db import get_db
from config.env import UploadConfig
from module_admin.service.login_service import LoginService
from module_admin.service.user_service import *
from module_admin.service.dept_service import DeptService
from utils.page_util import PageResponseModel
from utils.response_util import *
from utils.log_util import *
from utils.common_util import bytes2file_response
from utils.upload_util import UploadUtil
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.aspect.data_scope import GetDataScope
from module_admin.annotation.log_annotation import log_decorator


userController = APIRouter(prefix='/system/user', dependencies=[Depends(LoginService.get_current_user)])


@userController.get("/deptTree", dependencies=[Depends(CheckUserInterfaceAuth('system:user:list'))])
async def get_system_dept_tree(request: Request, query_db: AsyncSession = Depends(get_db), data_scope_sql: str = Depends(GetDataScope('SysDept'))):
    try:
        dept_query_result = await DeptService.get_dept_tree_services(query_db, DeptModel(**{}), data_scope_sql)
        logger.info('获取成功')
        return ResponseUtil.success(data=dept_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.get("/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:list'))])
async def get_system_user_list(request: Request, user_page_query: UserPageQueryModel = Depends(UserPageQueryModel.as_query), query_db: AsyncSession = Depends(get_db), data_scope_sql: str = Depends(GetDataScope('SysUser'))):
    try:
        # 获取分页数据
        user_page_query_result = await UserService.get_user_list_services(query_db, user_page_query, data_scope_sql, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=user_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.post("", dependencies=[Depends(CheckUserInterfaceAuth('system:user:add'))])
@log_decorator(title='用户管理', business_type=1)
async def add_system_user(request: Request, add_user: AddUserModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_user.password = PwdUtil.get_password_hash(add_user.password)
        add_user.create_by = current_user.user.user_name
        add_user.create_time = datetime.now()
        add_user.update_by = current_user.user.user_name
        add_user.update_time = datetime.now()
        add_user_result = await UserService.add_user_services(query_db, add_user)
        if add_user_result.is_success:
            logger.info(add_user_result.message)
            return ResponseUtil.success(msg=add_user_result.message)
        else:
            logger.warning(add_user_result.message)
            return ResponseUtil.failure(msg=add_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.put("", dependencies=[Depends(CheckUserInterfaceAuth('system:user:edit'))])
@log_decorator(title='用户管理', business_type=2)
async def edit_system_user(request: Request, edit_user: EditUserModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_user.update_by = current_user.user.user_name
        edit_user.update_time = datetime.now()
        edit_user_result = await UserService.edit_user_services(query_db, edit_user)
        if edit_user_result.is_success:
            logger.info(edit_user_result.message)
            return ResponseUtil.success(msg=edit_user_result.message)
        else:
            logger.warning(edit_user_result.message)
            return ResponseUtil.failure(msg=edit_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.delete("/{user_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:user:remove'))])
@log_decorator(title='用户管理', business_type=3)
async def delete_system_user(request: Request, user_ids: str, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        delete_user = DeleteUserModel(
            userIds=user_ids,
            updateBy=current_user.user.user_name,
            updateTime=datetime.now()
        )
        delete_user_result = await UserService.delete_user_services(query_db, delete_user)
        if delete_user_result.is_success:
            logger.info(delete_user_result.message)
            return ResponseUtil.success(msg=delete_user_result.message)
        else:
            logger.warning(delete_user_result.message)
            return ResponseUtil.failure(msg=delete_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.put("/resetPwd", dependencies=[Depends(CheckUserInterfaceAuth('system:user:resetPwd'))])
@log_decorator(title='用户管理', business_type=2)
async def reset_system_user_pwd(request: Request, edit_user: EditUserModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_user.password = PwdUtil.get_password_hash(edit_user.password)
        edit_user.update_by = current_user.user.user_name
        edit_user.update_time = datetime.now()
        edit_user.type = 'pwd'
        edit_user_result = await UserService.edit_user_services(query_db, edit_user)
        if edit_user_result.is_success:
            logger.info(edit_user_result.message)
            return ResponseUtil.success(msg=edit_user_result.message)
        else:
            logger.warning(edit_user_result.message)
            return ResponseUtil.failure(msg=edit_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.put("/changeStatus", dependencies=[Depends(CheckUserInterfaceAuth('system:user:edit'))])
@log_decorator(title='用户管理', business_type=2)
async def change_system_user_status(request: Request, edit_user: EditUserModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_user.update_by = current_user.user.user_name
        edit_user.update_time = datetime.now()
        edit_user.type = 'status'
        edit_user_result = await UserService.edit_user_services(query_db, edit_user)
        if edit_user_result.is_success:
            logger.info(edit_user_result.message)
            return ResponseUtil.success(msg=edit_user_result.message)
        else:
            logger.warning(edit_user_result.message)
            return ResponseUtil.failure(msg=edit_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.get("/profile", response_model=UserProfileModel)
async def query_detail_system_user(request: Request, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        profile_user_result = await UserService.user_profile_services(query_db, current_user.user.user_id)
        logger.info(f'获取user_id为{current_user.user.user_id}的信息成功')
        return ResponseUtil.success(model_content=profile_user_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.get("/{user_id}", response_model=UserDetailModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:query'))])
@userController.get("/", response_model=UserDetailModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:query'))])
async def query_detail_system_user(request: Request, user_id: Optional[Union[int, str]] = '', query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        detail_user_result = await UserService.user_detail_services(query_db, user_id)
        logger.info(f'获取user_id为{user_id}的信息成功')
        return ResponseUtil.success(model_content=detail_user_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.post("/profile/avatar")
@log_decorator(title='个人信息', business_type=2)
async def change_system_user_profile_avatar(request: Request, avatarfile: bytes = File(), query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        relative_path = f'avatar/{datetime.now().strftime("%Y")}/{datetime.now().strftime("%m")}/{datetime.now().strftime("%d")}'
        dir_path = os.path.join(UploadConfig.UPLOAD_PATH, relative_path)
        try:
            os.makedirs(dir_path)
        except FileExistsError:
            pass
        avatar_name = f'avatar_{datetime.now().strftime("%Y%m%d%H%M%S")}{UploadConfig.UPLOAD_MACHINE}{UploadUtil.generate_random_number()}.png'
        avatar_path = os.path.join(dir_path, avatar_name)
        with open(avatar_path, 'wb') as f:
            f.write(avatarfile)
        edit_user = EditUserModel(
            userId=current_user.user.user_id,
            avatar=f'{UploadConfig.UPLOAD_PREFIX}/{relative_path}/{avatar_name}',
            updateBy=current_user.user.user_name,
            updateTime=datetime.now(),
            type='avatar'
        )
        edit_user_result = await UserService.edit_user_services(query_db, edit_user)
        if edit_user_result.is_success:
            logger.info(edit_user_result.message)
            return ResponseUtil.success(dict_content={'imgUrl': edit_user.avatar}, msg=edit_user_result.message)
        else:
            logger.warning(edit_user_result.message)
            return ResponseUtil.failure(msg=edit_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.put("/profile")
@log_decorator(title='个人信息', business_type=2)
async def change_system_user_profile_info(request: Request, user_info: UserInfoModel, query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_user = EditUserModel(
            **user_info.model_dump(
                exclude_unset=True,
                by_alias=True,
                exclude={'role_ids', 'post_ids'}
            ),
            userId=current_user.user.user_id,
            userName=current_user.user.user_name,
            updateBy=current_user.user.user_name,
            updateTime=datetime.now(),
            roleIds=current_user.user.role_ids.split(',') if current_user.user.role_ids else [],
            postIds=current_user.user.post_ids.split(',') if current_user.user.post_ids else [],
            role=current_user.user.role
        )
        edit_user_result = await UserService.edit_user_services(query_db, edit_user)
        if edit_user_result.is_success:
            logger.info(edit_user_result.message)
            return ResponseUtil.success(msg=edit_user_result.message)
        else:
            logger.warning(edit_user_result.message)
            return ResponseUtil.failure(msg=edit_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.put("/profile/updatePwd")
@log_decorator(title='个人信息', business_type=2)
async def reset_system_user_password(request: Request, reset_password: ResetPasswordModel = Depends(ResetPasswordModel.as_query), query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        reset_user = ResetUserModel(
            userId=current_user.user.user_id,
            oldPassword=reset_password.old_password,
            password=PwdUtil.get_password_hash(reset_password.new_password),
            updateBy=current_user.user.user_name,
            updateTime=datetime.now()
        )
        reset_user_result = await UserService.reset_user_services(query_db, reset_user)
        if reset_user_result.is_success:
            logger.info(reset_user_result.message)
            return ResponseUtil.success(msg=reset_user_result.message)
        else:
            logger.warning(reset_user_result.message)
            return ResponseUtil.failure(msg=reset_user_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.post("/importData", dependencies=[Depends(CheckUserInterfaceAuth('system:user:import'))])
@log_decorator(title='用户管理', business_type=6)
async def batch_import_system_user(request: Request, file: UploadFile = File(...), update_support: bool = Query(alias='updateSupport'), query_db: AsyncSession = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        batch_import_result = await UserService.batch_import_user_services(query_db, file, update_support, current_user)
        if batch_import_result.is_success:
            logger.info(batch_import_result.message)
            return ResponseUtil.success(msg=batch_import_result.message)
        else:
            logger.warning(batch_import_result.message)
            return ResponseUtil.failure(msg=batch_import_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.post("/importTemplate", dependencies=[Depends(CheckUserInterfaceAuth('system:user:import'))])
async def export_system_user_template(request: Request, query_db: AsyncSession = Depends(get_db)):
    try:
        user_import_template_result = await UserService.get_user_import_template_services()
        logger.info('获取成功')
        return ResponseUtil.streaming(data=bytes2file_response(user_import_template_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.post("/export", dependencies=[Depends(CheckUserInterfaceAuth('system:user:export'))])
@log_decorator(title='用户管理', business_type=5)
async def export_system_user_list(request: Request, user_page_query: UserPageQueryModel = Depends(UserPageQueryModel.as_form), query_db: AsyncSession = Depends(get_db), data_scope_sql: str = Depends(GetDataScope('SysUser'))):
    try:
        # 获取全量数据
        user_query_result = await UserService.get_user_list_services(query_db, user_page_query, data_scope_sql, is_page=False)
        user_export_result = await UserService.export_user_list_services(user_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(user_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.get("/authRole/{user_id}", response_model=UserRoleResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:query'))])
async def get_system_allocated_role_list(request: Request, user_id: int, query_db: AsyncSession = Depends(get_db)):
    try:
        user_role_query = UserRoleQueryModel(userId=user_id)
        user_role_allocated_query_result = await UserService.get_user_role_allocated_list_services(query_db, user_role_query)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=user_role_allocated_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@userController.put("/authRole", response_model=UserRoleResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:user:edit'))])
async def update_system_role_user(request: Request, user_id: int = Query(alias='userId'), role_ids: str = Query(alias='roleIds'), query_db: AsyncSession = Depends(get_db)):
    try:
        add_user_role_result = await UserService.add_user_role_services(query_db, CrudUserRoleModel(userId=user_id, roleIds=role_ids))
        if add_user_role_result.is_success:
            logger.info(add_user_role_result.message)
            return ResponseUtil.success(msg=add_user_role_result.message)
        else:
            logger.warning(add_user_role_result.message)
            return ResponseUtil.failure(msg=add_user_role_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
