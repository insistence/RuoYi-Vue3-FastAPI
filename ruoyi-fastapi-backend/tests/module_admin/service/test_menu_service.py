from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.constant import CommonConstant
from config.database import Base
from exceptions.exception import ServiceException
from module_admin.dao.menu_dao import MenuDao
from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.vo.menu_vo import MenuModel
from module_admin.service.menu_service import MenuService


def _menu(
    *,
    menu_id: int,
    parent_id: int,
    path: str,
    route_name: str | None,
    menu_name: str = '已有菜单',
) -> SimpleNamespace:
    return SimpleNamespace(
        menu_id=menu_id,
        parent_id=parent_id,
        path=path,
        route_name=route_name,
        menu_name=menu_name,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('page_object', 'existing_menu'),
    [
        (
            MenuModel(menuId=2, parentId=1, path='system/user', routeName='SystemUser'),
            _menu(menu_id=1, parent_id=1, path='SYSTEM/USER', route_name='OtherRoute'),
        ),
        (
            MenuModel(menuId=2, parentId=0, path='system/user', routeName='SystemUser'),
            _menu(menu_id=1, parent_id=9, path='SYSTEM/USER', route_name='OtherRoute'),
        ),
        (
            MenuModel(menuId=2, parentId=2, path='different/path', routeName='SystemUser'),
            _menu(menu_id=1, parent_id=1, path='system/user', route_name='systemuser'),
        ),
    ],
)
async def test_check_route_config_unique_rejects_route_conflicts(
    page_object: MenuModel, existing_menu: SimpleNamespace
) -> None:
    with patch.object(
        MenuDao,
        'get_menus_by_path_or_route_name',
        new=AsyncMock(return_value=[existing_menu]),
    ):
        result = await MenuService.check_route_config_unique_services(object(), page_object)

    assert result == CommonConstant.NOT_UNIQUE


@pytest.mark.asyncio
async def test_check_route_config_unique_allows_same_path_under_different_parent_with_distinct_route_name() -> None:
    page_object = MenuModel(menuId=2, parentId=2, path='system/user', routeName='SecondSystemUser')
    existing_menu = _menu(menu_id=1, parent_id=1, path='system/user', route_name='FirstSystemUser')
    with patch.object(
        MenuDao,
        'get_menus_by_path_or_route_name',
        new=AsyncMock(return_value=[existing_menu]),
    ):
        result = await MenuService.check_route_config_unique_services(object(), page_object)

    assert result == CommonConstant.UNIQUE


@pytest.mark.asyncio
async def test_check_route_config_unique_ignores_current_menu() -> None:
    page_object = MenuModel(menuId=1, parentId=1, path='system/user', routeName='SystemUser')
    current_menu = _menu(menu_id=1, parent_id=1, path='system/user', route_name='SystemUser')
    with patch.object(
        MenuDao,
        'get_menus_by_path_or_route_name',
        new=AsyncMock(return_value=[current_menu]),
    ):
        result = await MenuService.check_route_config_unique_services(object(), page_object)

    assert result == CommonConstant.UNIQUE


@pytest.mark.asyncio
async def test_add_menu_rejects_duplicate_route_config() -> None:
    page_object = MenuModel(menuName='用户管理', parentId=1, path='system/user', routeName='SystemUser', isFrame=1)
    with (
        patch.object(MenuService, 'check_menu_name_unique_services', new=AsyncMock(return_value=True)),
        patch.object(MenuService, 'check_route_config_unique_services', new=AsyncMock(return_value=False)),
        patch.object(MenuDao, 'add_menu_dao', new_callable=AsyncMock) as add_menu,
        pytest.raises(ServiceException) as exc_info,
    ):
        await MenuService.add_menu_services(object(), page_object)

    assert exc_info.value.message == '新增菜单用户管理失败，路由名称或地址已存在'
    add_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_menus_by_path_or_route_name_is_case_insensitive_and_excludes_buttons() -> None:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysMenu.__table__])

    try:
        async with session_maker() as session:
            session.add_all(
                [
                    SysMenu(
                        menu_id=1,
                        menu_name='路径匹配',
                        parent_id=1,
                        path='SYSTEM/USER',
                        route_name='ExistingUser',
                        menu_type='M',
                    ),
                    SysMenu(
                        menu_id=2,
                        menu_name='名称匹配',
                        parent_id=2,
                        path='different/path',
                        route_name='SYSTEMUSER',
                        menu_type='C',
                    ),
                    SysMenu(
                        menu_id=3,
                        menu_name='按钮',
                        parent_id=2,
                        path='system/user',
                        route_name='SystemUser',
                        menu_type='F',
                    ),
                ]
            )
            await session.flush()

            result = await MenuDao.get_menus_by_path_or_route_name(session, 'system/user', 'systemuser')

        assert {menu.menu_id for menu in result} == {1, 2}
    finally:
        await engine.dispose()
