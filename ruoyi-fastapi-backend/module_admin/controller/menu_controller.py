from datetime import datetime
from fastapi import APIRouter, Depends, Request
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from config.enums import BusinessType
from config.get_db import get_db
from module_admin.annotation.log_annotation import Log
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.menu_vo import DeleteMenuModel, MenuModel, MenuQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService
from module_admin.service.menu_service import MenuService
from utils.log_util import logger
from utils.response_util import ResponseUtil


menuController = APIRouter(prefix='/system/menu', dependencies=[Depends(LoginService.get_current_user)])


@menuController.get('/treeselect')
async def get_system_menu_tree(
    request: Request,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    menu_query_result = await MenuService.get_menu_tree_services(query_db, current_user)
    logger.info('获取成功')

    return ResponseUtil.success(data=menu_query_result)


@menuController.get('/roleMenuTreeselect/{role_id}')
async def get_system_role_menu_tree(
    request: Request,
    role_id: int,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    role_menu_query_result = await MenuService.get_role_menu_tree_services(query_db, role_id, current_user)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=role_menu_query_result)


@menuController.get(
    '/list', response_model=List[MenuModel], dependencies=[Depends(CheckUserInterfaceAuth('system:menu:list'))]
)
async def get_system_menu_list(
    request: Request,
    menu_query: MenuQueryModel = Depends(MenuQueryModel.as_query),
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    menu_query_result = await MenuService.get_menu_list_services(query_db, menu_query, current_user)
    logger.info('获取成功')

    return ResponseUtil.success(data=menu_query_result)


@menuController.post('', dependencies=[Depends(CheckUserInterfaceAuth('system:menu:add'))])
@ValidateFields(validate_model='add_menu')
@Log(title='菜单管理', business_type=BusinessType.INSERT)
async def add_system_menu(
    request: Request,
    add_menu: MenuModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_menu.create_by = current_user.user.user_name
    add_menu.create_time = datetime.now()
    add_menu.update_by = current_user.user.user_name
    add_menu.update_time = datetime.now()
    add_menu_result = await MenuService.add_menu_services(query_db, add_menu)
    logger.info(add_menu_result.message)

    return ResponseUtil.success(msg=add_menu_result.message)


@menuController.put('', dependencies=[Depends(CheckUserInterfaceAuth('system:menu:edit'))])
@ValidateFields(validate_model='edit_menu')
@Log(title='菜单管理', business_type=BusinessType.UPDATE)
async def edit_system_menu(
    request: Request,
    edit_menu: MenuModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    edit_menu.update_by = current_user.user.user_name
    edit_menu.update_time = datetime.now()
    edit_menu_result = await MenuService.edit_menu_services(query_db, edit_menu)
    logger.info(edit_menu_result.message)

    return ResponseUtil.success(msg=edit_menu_result.message)


@menuController.delete('/{menu_ids}', dependencies=[Depends(CheckUserInterfaceAuth('system:menu:remove'))])
@Log(title='菜单管理', business_type=BusinessType.DELETE)
async def delete_system_menu(request: Request, menu_ids: str, query_db: AsyncSession = Depends(get_db)):
    delete_menu = DeleteMenuModel(menuIds=menu_ids)
    delete_menu_result = await MenuService.delete_menu_services(query_db, delete_menu)
    logger.info(delete_menu_result.message)

    return ResponseUtil.success(msg=delete_menu_result.message)


@menuController.get(
    '/{menu_id}', response_model=MenuModel, dependencies=[Depends(CheckUserInterfaceAuth('system:menu:query'))]
)
async def query_detail_system_menu(request: Request, menu_id: int, query_db: AsyncSession = Depends(get_db)):
    menu_detail_result = await MenuService.menu_detail_services(query_db, menu_id)
    logger.info(f'获取menu_id为{menu_id}的信息成功')

    return ResponseUtil.success(data=menu_detail_result)
