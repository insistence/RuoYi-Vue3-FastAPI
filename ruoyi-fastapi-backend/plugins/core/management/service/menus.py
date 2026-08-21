from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.vo.menu_vo import MenuModel
from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.entity.vo.schemas import PluginMenuModel
from plugins.core.manifest.menu_key import InstalledPluginMenu, PluginMenuKeyBuilder
from plugins.core.manifest.schema import PluginManifest, PluginMenuManifest, PluginPermissionManifest
from utils.log_util import logger

ROOT_MENU_ID = 0
AUTO_BUTTON_ORDER_START = 1000
PERMISSION_PREFIX_PART_COUNT = 2
PERMISSION_BUTTON_LABELS = {
    'add': '新增',
    'edit': '修改',
    'remove': '删除',
    'delete': '删除',
    'query': '查询',
    'export': '导出',
    'import': '导入',
    'list': '列表',
    'view': '查看',
}


class PluginMenuInstaller:
    """
    插件管理模块菜单安装器。

    使用 Service Object 模式封装插件菜单幂等写入、状态切换和关联维护逻辑。
    """

    def __init__(self, query_db: AsyncSession) -> None:
        """
        初始化插件菜单安装器。

        :param query_db: orm对象
        :return: None
        """
        self.query_db = query_db

    async def install_manifest_menus(self, manifest: PluginManifest) -> list[InstalledPluginMenu]:
        """
        安装插件清单中的菜单。

        :param manifest: 插件清单
        :return: 已安装插件菜单快照列表
        """
        installed_menus = []
        seen_menu_keys = set()
        for menu in manifest.frontend.menus:
            installed_menus.extend(
                await self._install_menu_tree(
                    plugin_id=manifest.id,
                    menu=menu,
                    parent_id=ROOT_MENU_ID,
                    parent_key=manifest.id,
                    seen_menu_keys=seen_menu_keys,
                )
            )
        installed_menus.extend(
            await self._install_permission_button_menus(
                manifest,
                installed_menus,
                seen_menu_keys,
            )
        )
        await self._remove_stale_menus(manifest.id, seen_menu_keys)

        return installed_menus

    async def set_plugin_menu_status(self, plugin_id: str, status: str) -> None:
        """
        更新插件菜单状态。

        :param plugin_id: 插件ID
        :param status: 菜单状态（0正常 1停用）
        :return: None
        """
        plugin_menus = await PluginDao.get_plugin_menu_list(self.query_db, plugin_id)
        menu_ids = [plugin_menu.menu_id for plugin_menu in plugin_menus]
        await PluginDao.update_sys_menu_status_by_ids(self.query_db, menu_ids, status)

    async def _install_menu_tree(
        self,
        plugin_id: str,
        menu: PluginMenuManifest,
        parent_id: int,
        parent_key: str,
        seen_menu_keys: set[str],
    ) -> list[InstalledPluginMenu]:
        """
        递归安装插件菜单树。

        :param plugin_id: 插件ID
        :param menu: 插件菜单声明
        :param parent_id: 父菜单ID
        :param parent_key: 父级菜单自然键
        :param seen_menu_keys: 当前插件已处理自然键集合
        :return: 已安装插件菜单快照列表
        """
        menu_key = PluginMenuKeyBuilder.build(menu, parent_key)
        if menu_key in seen_menu_keys:
            raise ValueError(f'插件 {plugin_id} 存在重复菜单自然键：{menu_key}')
        seen_menu_keys.add(menu_key)

        sys_menu = await self._upsert_menu(plugin_id, menu, menu_key, parent_id)
        installed_menu = InstalledPluginMenu(menu_id=sys_menu.menu_id, menu_key=menu_key, manifest_menu=menu)
        installed_menus = [installed_menu]

        for child_menu in menu.children:
            installed_menus.extend(
                await self._install_menu_tree(
                    plugin_id=plugin_id,
                    menu=child_menu,
                    parent_id=sys_menu.menu_id,
                    parent_key=menu_key,
                    seen_menu_keys=seen_menu_keys,
                )
            )

        return installed_menus

    async def _install_permission_button_menus(
        self,
        manifest: PluginManifest,
        installed_menus: list[InstalledPluginMenu],
        seen_menu_keys: set[str],
    ) -> list[InstalledPluginMenu]:
        """
        为未显式声明为菜单的权限生成按钮菜单。

        :param manifest: 插件清单
        :param installed_menus: 已安装菜单快照列表
        :param seen_menu_keys: 当前插件已处理自然键集合
        :return: 自动生成的按钮菜单快照列表
        """
        declared_menu_permissions = {installed_menu.manifest_menu.perms for installed_menu in installed_menus}
        missing_permissions = [
            permission_manifest
            for permission_manifest in manifest.permissions
            if permission_manifest.code and permission_manifest.code not in declared_menu_permissions
        ]
        if not missing_permissions:
            return []

        auto_buttons = []
        for index, permission in enumerate(missing_permissions, start=1):
            parent_menu = self._find_permission_parent_menu(permission.code, installed_menus)
            if not parent_menu:
                continue
            button_menu = self._build_permission_button_menu(permission, index)
            auto_buttons.extend(
                await self._install_menu_tree(
                    plugin_id=manifest.id,
                    menu=button_menu,
                    parent_id=parent_menu.menu_id,
                    parent_key=parent_menu.menu_key,
                    seen_menu_keys=seen_menu_keys,
                )
            )

        return auto_buttons

    @classmethod
    def _find_permission_parent_menu(
        cls,
        permission: str,
        installed_menus: list[InstalledPluginMenu],
    ) -> InstalledPluginMenu | None:
        """
        查找权限按钮应挂载的页面菜单。

        :param permission: 权限标识
        :param installed_menus: 已安装菜单快照列表
        :return: 父级菜单快照
        """
        candidate_menus = [
            installed_menu for installed_menu in installed_menus if installed_menu.manifest_menu.type != 'F'
        ]
        if not candidate_menus:
            return None

        permission_prefix = cls._permission_prefix(permission)
        for installed_menu in candidate_menus:
            menu_permission = installed_menu.manifest_menu.perms
            if menu_permission and cls._permission_prefix(menu_permission) == permission_prefix:
                return installed_menu

        return candidate_menus[-1]

    @staticmethod
    def _permission_prefix(permission: str) -> str:
        """
        提取权限前缀。

        :param permission: 权限标识
        :return: 权限前缀
        """
        parts = permission.split(':', maxsplit=PERMISSION_PREFIX_PART_COUNT)
        return (
            ':'.join(parts[:PERMISSION_PREFIX_PART_COUNT]) if len(parts) >= PERMISSION_PREFIX_PART_COUNT else permission
        )

    @staticmethod
    def _build_permission_button_menu(permission: PluginPermissionManifest, order_index: int) -> PluginMenuManifest:
        """
        构建权限按钮菜单声明。

        :param permission: 权限声明
        :param order_index: 自动按钮排序序号
        :return: 按钮菜单声明
        """
        action = permission.code.rsplit(':', maxsplit=1)[-1]
        return PluginMenuManifest(
            name=permission.name or PERMISSION_BUTTON_LABELS.get(action, action),
            path=action,
            component='',
            perms=permission.code,
            type='F',
            orderNum=AUTO_BUTTON_ORDER_START + order_index,
            icon='#',
        )

    async def _upsert_menu(
        self,
        plugin_id: str,
        menu: PluginMenuManifest,
        menu_key: str,
        parent_id: int,
    ) -> SysMenu:
        """
        写入或更新单个插件菜单。

        :param plugin_id: 插件ID
        :param menu: 插件菜单声明
        :param menu_key: 插件菜单自然键
        :param parent_id: 父菜单ID
        :return: 系统菜单对象
        """
        sys_menu = await self._find_existing_menu(plugin_id, menu_key)
        menu_model = self._build_menu_model(
            plugin_id,
            menu,
            parent_id,
            sys_menu.menu_id if sys_menu else None,
            sys_menu.remark if sys_menu else None,
        )

        if sys_menu:
            await PluginDao.update_sys_menu(self.query_db, menu_model.model_dump(exclude_unset=True))
            if not await PluginDao.get_plugin_menu_by_key(self.query_db, plugin_id, menu_key):
                logger.warning(f'⚠️ 插件 {plugin_id} 复用已有菜单：{menu_key}')
            await self._upsert_plugin_menu(plugin_id, sys_menu.menu_id, menu_key)
            return await PluginDao.get_sys_menu_by_id(self.query_db, sys_menu.menu_id) or sys_menu

        new_menu = await PluginDao.add_sys_menu(self.query_db, menu_model)
        await self._upsert_plugin_menu(plugin_id, new_menu.menu_id, menu_key)

        return new_menu

    async def _find_existing_menu(
        self,
        plugin_id: str,
        menu_key: str,
    ) -> SysMenu | None:
        """
        查找已有系统菜单。

        :param plugin_id: 插件ID
        :param menu_key: 插件菜单自然键
        :return: 系统菜单对象
        """
        plugin_menu = await PluginDao.get_plugin_menu_by_key(self.query_db, plugin_id, menu_key)
        if plugin_menu:
            return await PluginDao.get_sys_menu_by_id(self.query_db, plugin_menu.menu_id)
        return None

    async def _upsert_plugin_menu(self, plugin_id: str, menu_id: int, menu_key: str) -> None:
        """
        写入或更新插件菜单关联。

        :param plugin_id: 插件ID
        :param menu_id: 菜单ID
        :param menu_key: 插件菜单自然键
        :return: None
        """
        plugin_menu_model = PluginMenuModel(pluginId=plugin_id, menuId=menu_id, menuKey=menu_key)
        existing_plugin_menu = await PluginDao.get_plugin_menu_by_key(self.query_db, plugin_id, menu_key)
        if existing_plugin_menu and existing_plugin_menu.menu_id != menu_id:
            await PluginDao.update_plugin_menu_by_key(self.query_db, plugin_menu_model)
        elif not existing_plugin_menu:
            existing_menu_owner = await PluginDao.get_plugin_menu_by_menu_id(self.query_db, menu_id)
            if existing_menu_owner and existing_menu_owner.plugin_id == plugin_id:
                await PluginDao.update_plugin_menu_key_by_menu_id(self.query_db, plugin_menu_model)
            else:
                await PluginDao.add_plugin_menu(self.query_db, plugin_menu_model)

    async def _remove_stale_menus(self, plugin_id: str, desired_menu_keys: set[str]) -> None:
        """
        删除已不在当前 manifest 中的插件菜单及角色授权。

        :param plugin_id: 插件ID
        :param desired_menu_keys: manifest 当前菜单自然键集合
        :return: None
        """
        plugin_menus = await PluginDao.get_plugin_menu_list(self.query_db, plugin_id)
        stale_menu_ids = [
            plugin_menu.menu_id for plugin_menu in plugin_menus if plugin_menu.menu_key not in desired_menu_keys
        ]
        await PluginDao.delete_plugin_menus_by_ids(self.query_db, plugin_id, stale_menu_ids)
        await PluginDao.delete_sys_menus_by_ids(self.query_db, stale_menu_ids)

    @staticmethod
    def _build_menu_model(
        plugin_id: str,
        menu: PluginMenuManifest,
        parent_id: int,
        menu_id: int | None = None,
        existing_remark: str | None = None,
    ) -> MenuModel:
        """
        构建系统菜单模型。

        :param plugin_id: 插件ID
        :param menu: 插件菜单声明
        :param parent_id: 父菜单ID
        :param menu_id: 菜单ID
        :param existing_remark: 已有菜单备注
        :return: 系统菜单模型
        """
        menu_remark = PluginMenuInstaller._build_remark(plugin_id, existing_remark)
        return MenuModel(
            menuId=menu_id,
            menuName=menu.name,
            parentId=parent_id,
            orderNum=menu.order_num,
            path=menu.path,
            component=menu.component,
            query=menu.query,
            routeName=menu.route_name,
            isFrame=menu.is_frame,
            isCache=menu.is_cache,
            menuType=menu.type,
            visible=menu.visible,
            status=menu.status,
            perms=menu.perms or None,
            icon=menu.icon,
            remark=menu_remark,
        )

    @staticmethod
    def _build_remark(plugin_id: str, existing_remark: str | None = None) -> str:
        """
        构建插件菜单备注。

        :param plugin_id: 插件ID
        :param existing_remark: 已有菜单备注
        :return: 菜单备注
        """
        plugin_remark = f'plugin:{plugin_id}'
        if not existing_remark:
            return plugin_remark
        if plugin_remark in existing_remark:
            return existing_remark

        return f'{existing_remark} | {plugin_remark}'
