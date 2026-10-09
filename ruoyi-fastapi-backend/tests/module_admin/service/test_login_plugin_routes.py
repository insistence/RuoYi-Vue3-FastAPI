from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from module_admin.dao.user_dao import UserDao
from module_admin.entity.do.menu_do import SysMenu
from module_admin.service.login_service import LoginService
from plugins.core.management.entity.do.models import SysPlugin, SysPluginMenu
from plugins.core.management.service.router_metadata import PluginRouterMetadataService


def _menu(menu_id: int, *, parent_id: int = 0, component: str = 'PluginFrame', menu_type: str = 'C') -> SysMenu:
    return SysMenu(
        menu_id=menu_id,
        parent_id=parent_id,
        menu_name=f'Menu {menu_id}',
        order_num=menu_id,
        path=f'unrelated-route-{menu_id}',
        component=component,
        query='{"pluginId":"untrusted-query-value"}',
        is_frame=1,
        is_cache=1,
        menu_type=menu_type,
        visible='0',
        status='0',
    )


def _plugin(plugin_id: str, **overrides: object) -> SysPlugin:
    values = {
        'plugin_id': plugin_id,
        'plugin_name': plugin_id,
        'version': '1.0.0',
        'installed_version': '1.0.0',
        'enabled': '0',
        'status': 'installed',
        **overrides,
    }
    return SysPlugin(**values)


@pytest.mark.asyncio
async def test_plugin_metadata_uses_menu_ownership_for_nested_and_root_pages() -> None:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SysPlugin.__table__.create)
            await connection.run_sync(SysPluginMenu.__table__.create)
        session_factory = async_sessionmaker(engine)
        async with session_factory() as db:
            db.add(_plugin('demo'))
            db.add_all(
                [
                    SysPluginMenu(plugin_id='demo', menu_id=11, menu_key='root'),
                    SysPluginMenu(plugin_id='demo', menu_id=12, menu_key='nested'),
                    SysPluginMenu(plugin_id='demo', menu_id=14, menu_key='source'),
                ]
            )
            await db.commit()
            menus = [
                _menu(10, component='Layout', menu_type='M'),
                _menu(11),
                _menu(12, parent_id=10),
                _menu(13, parent_id=10),
                _menu(14, parent_id=10, component='plugin:demo/source'),
            ]
            with patch.object(UserDao, 'get_user_by_id', new=AsyncMock(return_value={'user_menu_info': menus})):
                routers = await LoginService.get_current_user_routers(1, db)

        nested = routers[0]['children']
        assert nested[0]['component'] == 'PluginFrame'
        assert nested[0]['meta']['pluginId'] == 'demo'
        assert 'pluginId' not in nested[1]['meta']
        assert 'pluginId' not in nested[2]['meta']
        assert 'pluginId' not in routers[0]['meta']
        root = routers[1]
        assert root['component'] == 'Layout'
        assert root['meta'] is None
        assert root['children'][0]['component'] == 'PluginFrame'
        assert root['children'][0]['meta']['pluginId'] == 'demo'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_menu_ownership_rejects_inactive_uninstalled_and_ambiguous_plugins() -> None:
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SysPlugin.__table__.create)
            await connection.run_sync(SysPluginMenu.__table__.create)
        session_factory = async_sessionmaker(engine)
        async with session_factory() as db:
            db.add_all(
                [
                    _plugin('ready'),
                    _plugin('disabled', enabled='1'),
                    _plugin('failed', status='error'),
                    _plugin('uninstalled', installed_version=None, status='discovered'),
                    _plugin('other'),
                    _plugin('upgrading', status='pending_upgrade'),
                ]
            )
            db.add_all(
                [
                    SysPluginMenu(plugin_id=plugin_id, menu_id=menu_id, menu_key=str(menu_id))
                    for menu_id, plugin_id in (
                        (1, 'ready'),
                        (2, 'disabled'),
                        (3, 'failed'),
                        (4, 'uninstalled'),
                        (5, 'ready'),
                        (5, 'other'),
                        (6, 'upgrading'),
                        (99, 'ready'),
                    )
                ]
            )
            await db.commit()
            ownership = await PluginRouterMetadataService.get_menu_plugin_ids(db, [_menu(i) for i in range(1, 8)])

        assert ownership == {1: 'ready', 6: 'upgrading'}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ordinary_menus_do_not_query_plugin_tables() -> None:
    query_db = AsyncMock()

    assert await PluginRouterMetadataService.get_menu_plugin_ids(query_db, [_menu(1, component='system/user')]) == {}
    query_db.execute.assert_not_awaited()
