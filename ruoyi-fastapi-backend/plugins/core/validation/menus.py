from dataclasses import dataclass

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.schema import PluginMenuManifest


@dataclass(frozen=True)
class PluginMenuConflictItem:
    """
    插件菜单冲突检查项。

    :param kind: 冲突类型
    :param plugin_id: 当前插件 ID
    :param value: 冲突值
    :param message: 冲突说明
    :param conflict_plugin_id: 冲突插件 ID
    """

    kind: str
    plugin_id: str
    value: str
    message: str
    conflict_plugin_id: str | None = None


@dataclass(frozen=True)
class PluginMenuConflictResult:
    """
    插件菜单冲突检查结果。

    :param plugin_id: 插件 ID
    :param items: 冲突检查项列表
    """

    plugin_id: str
    items: list[PluginMenuConflictItem]

    @property
    def ok(self) -> bool:
        """
        判断菜单冲突检查是否通过。

        :return: 是否通过
        """
        return not self.items


@dataclass(frozen=True)
class PluginMenuSnapshot:
    """
    插件菜单快照。

    :param plugin_id: 插件 ID
    :param menu: 插件菜单声明
    :param menu_key: 插件内菜单自然键
    """

    plugin_id: str
    menu: PluginMenuManifest
    menu_key: str


class PluginMenuConflictChecker:
    """
    插件菜单冲突检查器。

    使用 Checker 模式在安装前检查 manifest 层面的菜单自然键和权限冲突。
    """

    def check(
        self,
        plugin: DiscoveredPlugin,
        all_plugins: list[DiscoveredPlugin] | None = None,
    ) -> PluginMenuConflictResult:
        """
        检查指定插件菜单冲突。

        :param plugin: 当前待检查插件
        :param all_plugins: 全量已发现插件列表
        :return: 菜单冲突检查结果
        """
        all_plugin_list = all_plugins or [plugin]
        snapshots_by_plugin = {
            discovered_plugin.manifest.id: self._build_menu_snapshots(discovered_plugin)
            for discovered_plugin in all_plugin_list
        }
        current_snapshots = snapshots_by_plugin.get(plugin.manifest.id, [])
        items = []
        items.extend(self._check_duplicate_menu_keys(plugin.manifest.id, current_snapshots))
        items.extend(self._check_duplicate_permissions(plugin.manifest.id, current_snapshots, snapshots_by_plugin))

        return PluginMenuConflictResult(plugin_id=plugin.manifest.id, items=items)

    def _check_duplicate_menu_keys(
        self,
        plugin_id: str,
        snapshots: list[PluginMenuSnapshot],
    ) -> list[PluginMenuConflictItem]:
        """
        检查同一插件内菜单自然键重复。

        :param plugin_id: 插件 ID
        :param snapshots: 当前插件菜单快照列表
        :return: 冲突检查项列表
        """
        seen_keys = set()
        conflicts = []
        for snapshot in snapshots:
            if snapshot.menu_key in seen_keys:
                conflicts.append(
                    PluginMenuConflictItem(
                        kind='duplicate_menu_key',
                        plugin_id=plugin_id,
                        value=snapshot.menu_key,
                        message=f'插件 {plugin_id} 存在重复菜单自然键：{snapshot.menu_key}',
                    )
                )
            seen_keys.add(snapshot.menu_key)

        return conflicts

    def _check_duplicate_permissions(
        self,
        plugin_id: str,
        current_snapshots: list[PluginMenuSnapshot],
        snapshots_by_plugin: dict[str, list[PluginMenuSnapshot]],
    ) -> list[PluginMenuConflictItem]:
        """
        检查不同插件之间权限标识重复。

        :param plugin_id: 当前插件 ID
        :param current_snapshots: 当前插件菜单快照列表
        :param snapshots_by_plugin: 全量插件菜单快照
        :return: 冲突检查项列表
        """
        permission_owner_map = self._build_permission_owner_map(snapshots_by_plugin)
        conflicts = []
        for snapshot in current_snapshots:
            if not snapshot.menu.perms:
                continue
            conflict_plugin_id = permission_owner_map.get(snapshot.menu.perms)
            if conflict_plugin_id and conflict_plugin_id != plugin_id:
                conflicts.append(
                    PluginMenuConflictItem(
                        kind='duplicate_permission',
                        plugin_id=plugin_id,
                        conflict_plugin_id=conflict_plugin_id,
                        value=snapshot.menu.perms,
                        message=(f'插件 {plugin_id} 权限 {snapshot.menu.perms} 与插件 {conflict_plugin_id} 冲突'),
                    )
                )

        return conflicts

    def _build_permission_owner_map(
        self,
        snapshots_by_plugin: dict[str, list[PluginMenuSnapshot]],
    ) -> dict[str, str]:
        """
        构建权限标识归属映射。

        :param snapshots_by_plugin: 全量插件菜单快照
        :return: 权限标识与插件 ID 映射
        """
        permission_owner_map = {}
        for plugin_id, snapshots in snapshots_by_plugin.items():
            for snapshot in snapshots:
                if snapshot.menu.perms and snapshot.menu.perms not in permission_owner_map:
                    permission_owner_map[snapshot.menu.perms] = plugin_id

        return permission_owner_map

    def _build_menu_snapshots(self, plugin: DiscoveredPlugin) -> list[PluginMenuSnapshot]:
        """
        构建插件菜单快照列表。

        :param plugin: 已发现插件
        :return: 菜单快照列表
        """
        snapshots = []
        for menu in plugin.manifest.frontend.menus:
            snapshots.extend(
                self._build_menu_tree_snapshots(
                    plugin_id=plugin.manifest.id,
                    menu=menu,
                    parent_key=plugin.manifest.id,
                )
            )

        return snapshots

    def _build_menu_tree_snapshots(
        self,
        plugin_id: str,
        menu: PluginMenuManifest,
        parent_key: str,
    ) -> list[PluginMenuSnapshot]:
        """
        递归构建菜单树快照。

        :param plugin_id: 插件 ID
        :param menu: 插件菜单声明
        :param parent_key: 父菜单自然键
        :return: 菜单快照列表
        """
        menu_key = self._build_menu_key(menu, parent_key)
        snapshots = [PluginMenuSnapshot(plugin_id=plugin_id, menu=menu, menu_key=menu_key)]
        for child_menu in menu.children:
            snapshots.extend(self._build_menu_tree_snapshots(plugin_id, child_menu, menu_key))

        return snapshots

    @staticmethod
    def _build_menu_key(menu: PluginMenuManifest, parent_key: str) -> str:
        """
        构建插件菜单自然键。

        :param menu: 插件菜单声明
        :param parent_key: 父级菜单自然键
        :return: 插件菜单自然键
        """
        if menu.type == 'F':
            return f'button:{parent_key}/{menu.name}#{menu.perms}'
        if menu.perms:
            return f'perm:{menu.perms}'

        return f'route:{parent_key}/{menu.path}#{menu.component}'
