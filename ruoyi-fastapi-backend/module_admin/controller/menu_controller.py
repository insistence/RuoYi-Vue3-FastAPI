from fastapi import APIRouter, Request
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService
from module_admin.service.menu_service import *
from utils.response_util import *
from utils.log_util import *
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


menuController = APIRouter(prefix='/system/menu', dependencies=[Depends(LoginService.get_current_user)])


@menuController.get("/treeselect")
async def get_system_menu_tree(request: Request, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        menu_query_result = MenuService.get_menu_tree_services(query_db, current_user)
        logger.info('获取成功')
        return ResponseUtil.success(data=menu_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@menuController.get("/roleMenuTreeselect/{role_id}")
async def get_system_role_menu_tree(request: Request, role_id: int, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        role_menu_query_result = MenuService.get_role_menu_tree_services(query_db, role_id, current_user)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=role_menu_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@menuController.get("/list", response_model=List[MenuModel], dependencies=[Depends(CheckUserInterfaceAuth('system:menu:list'))])
async def get_system_menu_list(request: Request, menu_query: MenuQueryModel = Depends(MenuQueryModel.as_query), query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        menu_query_result = MenuService.get_menu_list_services(query_db, menu_query, current_user)
        logger.info('获取成功')
        return ResponseUtil.success(data=menu_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@menuController.post("", dependencies=[Depends(CheckUserInterfaceAuth('system:menu:add'))])
@log_decorator(title='菜单管理', business_type=1)
async def add_system_menu(request: Request, add_menu: MenuModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_menu.create_by = current_user.user.user_name
        add_menu.update_by = current_user.user.user_name
        add_menu_result = MenuService.add_menu_services(query_db, add_menu)
        if add_menu_result.is_success:
            logger.info(add_menu_result.message)
            return ResponseUtil.success(msg=add_menu_result.message)
        else:
            logger.warning(add_menu_result.message)
            return ResponseUtil.failure(msg=add_menu_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@menuController.put("", dependencies=[Depends(CheckUserInterfaceAuth('system:menu:edit'))])
@log_decorator(title='菜单管理', business_type=2)
async def edit_system_menu(request: Request, edit_menu: MenuModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_menu.update_by = current_user.user.user_name
        edit_menu.update_time = datetime.now()
        edit_menu_result = MenuService.edit_menu_services(query_db, edit_menu)
        if edit_menu_result.is_success:
            logger.info(edit_menu_result.message)
            return ResponseUtil.success(msg=edit_menu_result.message)
        else:
            logger.warning(edit_menu_result.message)
            return ResponseUtil.failure(msg=edit_menu_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@menuController.delete("/{menu_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:menu:remove'))])
@log_decorator(title='菜单管理', business_type=3)
async def delete_system_menu(request: Request, menu_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_menu = DeleteMenuModel(menuIds=menu_ids)
        delete_menu_result = MenuService.delete_menu_services(query_db, delete_menu)
        if delete_menu_result.is_success:
            logger.info(delete_menu_result.message)
            return ResponseUtil.success(msg=delete_menu_result.message)
        else:
            logger.warning(delete_menu_result.message)
            return ResponseUtil.failure(msg=delete_menu_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@menuController.get("/{menu_id}", response_model=MenuModel, dependencies=[Depends(CheckUserInterfaceAuth('system:menu:query'))])
async def query_detail_system_menu(request: Request, menu_id: int, query_db: Session = Depends(get_db)):
    try:
        menu_detail_result = MenuService.menu_detail_services(query_db, menu_id)
        logger.info(f'获取menu_id为{menu_id}的信息成功')
        return ResponseUtil.success(data=menu_detail_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
