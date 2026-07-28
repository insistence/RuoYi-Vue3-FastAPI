from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.core.manifest.schema import PluginManifest, PluginMenuManifest

MIN_PLUGIN_COMPONENT_PARTS = 3


class PluginMenuTree:
    """
    插件菜单树领域工具。

    统一处理 manifest 菜单树的遍历、统计、权限和组件路径解析，避免校验、管理和
    运行时负载构建各自维护递归逻辑。
    """

    @classmethod
    def flatten(cls, menus: list[PluginMenuManifest]) -> list[PluginMenuManifest]:
        """
        展平插件菜单树。

        :param menus: 插件菜单声明列表
        :return: 展平后的插件菜单列表
        """
        flattened_menus = []
        for menu in menus:
            flattened_menus.append(menu)
            flattened_menus.extend(cls.flatten(menu.children))

        return flattened_menus

    @classmethod
    def count(cls, menus: list[PluginMenuManifest]) -> int:
        """
        统计插件菜单树节点数量。

        :param menus: 插件菜单声明列表
        :return: 菜单节点数量
        """
        return len(cls.flatten(menus))

    @classmethod
    def collect_permissions(cls, menus: list[PluginMenuManifest]) -> set[str]:
        """
        收集插件菜单树中的权限标识。

        :param menus: 插件菜单声明列表
        :return: 菜单权限标识集合
        """
        return {menu.perms for menu in cls.flatten(menus) if menu.perms}

    @classmethod
    def collect_route_paths(
        cls,
        menus: list[PluginMenuManifest],
        parent_path: str = '',
    ) -> list[str]:
        """
        收集插件菜单树中的完整路由路径。

        :param menus: 插件菜单声明列表
        :param parent_path: 父级菜单路径
        :return: 完整路由路径列表
        """
        route_paths = []
        for menu in menus:
            current_path = f'{parent_path}/{menu.path}' if parent_path else menu.path
            if menu.type != 'F':
                route_paths.append(current_path)
            route_paths.extend(cls.collect_route_paths(menu.children, current_path))

        return route_paths

    @staticmethod
    def is_plugin_component(component: str) -> bool:
        """
        判断菜单组件是否引用插件前端视图。

        :param component: 菜单组件路径
        :return: 是否为插件组件路径
        """
        return component.startswith('plugin/')

    @staticmethod
    def resolve_plugin_view_path(manifest: PluginManifest, component: str) -> Path | None:
        """
        将插件组件路径解析为前端插件内视图路径。

        :param manifest: 插件清单
        :param component: 菜单组件路径
        :return: Vue 文件相对路径
        """
        parts = component.split('/')
        plugin_id = manifest.frontend.plugin_id or manifest.id
        if len(parts) < MIN_PLUGIN_COMPONENT_PARTS or parts[0] != 'plugin' or parts[1] != plugin_id:
            return None

        return Path(manifest.frontend.views_path, *parts[2:]).with_suffix('.vue')
