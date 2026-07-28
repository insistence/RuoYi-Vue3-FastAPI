from dataclasses import dataclass

from plugins.core.manifest.schema import PluginMenuManifest


@dataclass(frozen=True)
class InstalledPluginMenu:
    """
    已安装插件菜单快照。
    """

    menu_id: int
    menu_key: str
    manifest_menu: PluginMenuManifest


class PluginMenuKeyBuilder:
    """
    插件菜单自然键构建器。

    使用 Strategy 思路将菜单自然键计算逻辑集中封装，便于后续调整匹配规则时
    不影响菜单安装流程。
    """

    @classmethod
    def build(cls, menu: PluginMenuManifest, parent_key: str) -> str:
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
