from datetime import datetime
from typing import Annotated

from fastapi import Path, Query, Request, Response
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, DynamicResponseModel, ResponseBaseModel
from module_admin.entity.vo.menu_vo import DeleteMenuModel, MenuModel, MenuQueryModel, MenuTreeModel
from module_admin.entity.vo.role_vo import RoleMenuQueryModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.menu_service import MenuService
from utils.log_util import logger
from utils.response_util import ResponseUtil

menu_controller = APIRouterPro(
    prefix='/system/menu', order_num=5, tags=['系统管理-菜单管理'], dependencies=[PreAuthDependency()]
)


@menu_controller.get(
    '/treeselect',
    summary='获取菜单树接口',
    description='用于获取当前用户可见的菜单树',
    response_model=DataResponseModel[list[MenuTreeModel]],
)
async def get_system_menu_tree(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    menu_query_result = await MenuService.get_menu_tree_services(query_db, current_user)
    logger.info('获取成功')

    return ResponseUtil.success(data=menu_query_result)


@menu_controller.get(
    '/roleMenuTreeselect/{role_id}',
    summary='获取角色菜单树接口',
    description='用于获取指定角色可见的菜单树',
    response_model=DynamicResponseModel[RoleMenuQueryModel],
)
async def get_system_role_menu_tree(
    request: Request,
    role_id: Annotated[int, Path(description='角色ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    role_menu_query_result = await MenuService.get_role_menu_tree_services(query_db, role_id, current_user)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=role_menu_query_result)


@menu_controller.get(
    '/list',
    summary='获取菜单列表接口',
    description='用于获取当前用户可见的菜单列表',
    response_model=DataResponseModel[list[MenuModel]],
    dependencies=[UserInterfaceAuthDependency('system:menu:list')],
)
async def get_system_menu_list(
    request: Request,
    menu_query: Annotated[MenuQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    menu_query_result = await MenuService.get_menu_list_services(query_db, menu_query, current_user)
    logger.info('获取成功')

    return ResponseUtil.success(data=menu_query_result)


@menu_controller.post(
    '',
    summary='新增菜单接口',
    description='用于新增菜单',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:menu:add')],
)
@ValidateFields(validate_model='add_menu')
@Log(title='菜单管理', business_type=BusinessType.INSERT)
async def add_system_menu(
    request: Request,
    add_menu: MenuModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_menu.create_by = current_user.user.user_name
    add_menu.create_time = datetime.now()
    add_menu.update_by = current_user.user.user_name
    add_menu.update_time = datetime.now()
    add_menu_result = await MenuService.add_menu_services(query_db, add_menu)
    logger.info(add_menu_result.message)

    return ResponseUtil.success(msg=add_menu_result.message)


@menu_controller.put(
    '',
    summary='编辑菜单接口',
    description='用于编辑菜单',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:menu:edit')],
)
@ValidateFields(validate_model='edit_menu')
@Log(title='菜单管理', business_type=BusinessType.UPDATE)
async def edit_system_menu(
    request: Request,
    edit_menu: MenuModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_menu.update_by = current_user.user.user_name
    edit_menu.update_time = datetime.now()
    edit_menu_result = await MenuService.edit_menu_services(query_db, edit_menu)
    logger.info(edit_menu_result.message)

    return ResponseUtil.success(msg=edit_menu_result.message)


@menu_controller.delete(
    '/{menu_ids}',
    summary='删除菜单接口',
    description='用于删除菜单',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:menu:remove')],
)
@Log(title='菜单管理', business_type=BusinessType.DELETE)
async def delete_system_menu(
    request: Request,
    menu_ids: Annotated[str, Path(description='需要删除的菜单ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_menu = DeleteMenuModel(menuIds=menu_ids)
    delete_menu_result = await MenuService.delete_menu_services(query_db, delete_menu)
    logger.info(delete_menu_result.message)

    return ResponseUtil.success(msg=delete_menu_result.message)


@menu_controller.get(
    '/{menu_id}',
    summary='获取菜单详情接口',
    description='用于获取指定菜单的详情信息',
    response_model=DataResponseModel[MenuModel],
    dependencies=[UserInterfaceAuthDependency('system:menu:query')],
)
async def query_detail_system_menu(
    request: Request,
    menu_id: Annotated[int, Path(description='菜单ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    menu_detail_result = await MenuService.menu_detail_services(query_db, menu_id)
    logger.info(f'获取menu_id为{menu_id}的信息成功')

    return ResponseUtil.success(data=menu_detail_result)
