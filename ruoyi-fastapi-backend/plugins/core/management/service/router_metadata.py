from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.menu_do import SysMenu
from plugins.core.management.entity.do.models import SysPlugin, SysPluginMenu


class PluginRouterMetadataService:
    """
    按平台菜单关联读取插件页面归属，仅查询当前用户可见的插件页面。
    """

    @staticmethod
    async def get_menu_plugin_ids(query_db: AsyncSession, menus: Iterable[SysMenu]) -> dict[int, str]:
        """
        根据可见 PluginFrame 菜单关联查询已安装且启用的唯一插件归属。

        :param query_db: 当前查询使用的数据库会话
        :param menus: 当前用户可见的菜单记录集合
        :return: 菜单ID到插件ID的映射，归属不明确的菜单不返回
        """
        menu_ids = {menu.menu_id for menu in menus if menu.component == 'PluginFrame' and menu.menu_id is not None}
        if not menu_ids:
            return {}
        result = await query_db.execute(
            select(SysPluginMenu.menu_id, SysPluginMenu.plugin_id)
            .join(SysPlugin, SysPlugin.plugin_id == SysPluginMenu.plugin_id)
            .where(
                SysPluginMenu.menu_id.in_(menu_ids),
                SysPlugin.enabled == '0',
                SysPlugin.status != 'error',
                SysPlugin.installed_version.is_not(None),
                SysPlugin.installed_version != '',
            )
        )
        owners: dict[int, set[str]] = {}
        for menu_id, plugin_id in result.all():
            owners.setdefault(menu_id, set()).add(plugin_id)
        # 历史损坏数据可能把同一菜单关联到多个插件，此时拒绝替前端猜测目标。
        return {menu_id: next(iter(plugin_ids)) for menu_id, plugin_ids in owners.items() if len(plugin_ids) == 1}
