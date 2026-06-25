from dataclasses import dataclass
from pathlib import Path

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.state import PluginStateResolver, PluginStateSnapshot
from plugins.core.types import PluginStateRecord


@dataclass(frozen=True)
class RegisteredPlugin:
    """
    已注册插件运行时快照。
    """

    discovered_plugin: DiscoveredPlugin
    database_plugin: PluginStateRecord | None
    enabled: bool
    status: str

    @property
    def plugin_id(self) -> str:
        """
        获取插件 ID。

        :return: 插件 ID
        """
        return self.discovered_plugin.manifest.id

    @property
    def backend_path(self) -> Path:
        """
        获取插件后端路径。

        :return: 插件后端路径
        """
        return self.discovered_plugin.backend_path


class PluginRegistry:
    """
    插件运行时注册表。

    使用 Registry 模式维护已发现插件与数据库状态合并后的运行时快照。
    """

    def __init__(self, registered_plugins: list[RegisteredPlugin]) -> None:
        """
        初始化插件运行时注册表。

        :param registered_plugins: 已注册插件运行时快照列表
        """
        self._registered_plugins = {plugin.plugin_id: plugin for plugin in registered_plugins}

    @classmethod
    def build(
        cls,
        discovered_plugins: list[DiscoveredPlugin],
        database_plugins: list[PluginStateRecord] | None = None,
    ) -> 'PluginRegistry':
        """
        根据已发现插件和数据库状态构建插件运行时注册表。

        :param discovered_plugins: 已发现插件列表
        :param database_plugins: 数据库插件状态列表
        :return: 插件运行时注册表
        """
        database_plugin_map = {plugin.plugin_id: plugin for plugin in database_plugins or []}
        registered_plugins = [
            cls._build_registered_plugin(discovered_plugin, database_plugin_map.get(discovered_plugin.manifest.id))
            for discovered_plugin in discovered_plugins
        ]

        return cls(registered_plugins)

    def get_plugin(self, plugin_id: str) -> RegisteredPlugin | None:
        """
        根据插件 ID 获取运行时插件快照。

        :param plugin_id: 插件 ID
        :return: 运行时插件快照
        """
        return self._registered_plugins.get(plugin_id)

    def list_plugins(self) -> list[RegisteredPlugin]:
        """
        获取全部运行时插件快照。

        :return: 运行时插件快照列表
        """
        return list(self._registered_plugins.values())

    def list_enabled_plugins(self) -> list[RegisteredPlugin]:
        """
        获取启用插件运行时快照列表。

        :return: 启用插件运行时快照列表
        """
        return [plugin for plugin in self._registered_plugins.values() if plugin.enabled]

    def get_enabled_controller_dirs(self) -> list[Path]:
        """
        获取启用插件控制器目录列表。

        :return: 控制器目录列表
        """
        controller_dirs = [
            plugin.backend_path / 'controller'
            for plugin in self.list_enabled_plugins()
            if plugin.discovered_plugin.manifest.backend.routers.auto_scan
        ]

        return [controller_dir for controller_dir in controller_dirs if controller_dir.is_dir()]

    def get_enabled_entity_do_dirs(self) -> list[Path]:
        """
        获取启用插件 DO 实体目录列表。

        :return: DO 实体目录列表
        """
        entity_do_dirs = [plugin.backend_path / 'entity' / 'do' for plugin in self.list_enabled_plugins()]

        return [entity_do_dir for entity_do_dir in entity_do_dirs if entity_do_dir.is_dir()]

    @staticmethod
    def _build_registered_plugin(
        discovered_plugin: DiscoveredPlugin,
        database_plugin: PluginStateRecord | None,
    ) -> RegisteredPlugin:
        """
        构建单个运行时插件快照。

        :param discovered_plugin: 已发现插件
        :param database_plugin: 数据库插件状态
        :return: 运行时插件快照
        """
        enabled = PluginRegistry._resolve_enabled(discovered_plugin, database_plugin)
        status = PluginRegistry._resolve_status(discovered_plugin, database_plugin, enabled)

        return RegisteredPlugin(
            discovered_plugin=discovered_plugin,
            database_plugin=database_plugin,
            enabled=enabled,
            status=status,
        )

    @staticmethod
    def _resolve_enabled(discovered_plugin: DiscoveredPlugin, database_plugin: PluginStateRecord | None) -> bool:
        """
        解析插件启用状态。

        :param discovered_plugin: 已发现插件
        :param database_plugin: 数据库插件状态
        :return: 是否启用
        """
        return PluginStateResolver.is_enabled(database_plugin)

    @staticmethod
    def _resolve_status(
        discovered_plugin: DiscoveredPlugin,
        database_plugin: PluginStateRecord | None,
        enabled: bool,
    ) -> str:
        """
        解析插件运行时状态。

        :param discovered_plugin: 已发现插件
        :param database_plugin: 数据库插件状态
        :param enabled: 是否启用
        :return: 插件运行时状态
        """
        return PluginStateResolver.resolve(
            PluginStateSnapshot(
                source_version=discovered_plugin.manifest.version,
                installed_version=getattr(database_plugin, 'installed_version', None),
                enabled=enabled,
                current_status=getattr(database_plugin, 'status', None),
            )
        )
