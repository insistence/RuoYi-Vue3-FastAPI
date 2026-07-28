from dataclasses import dataclass

from plugins.core.discovery.scanner import DiscoveredPlugin


@dataclass(frozen=True)
class PluginPurgePlanItem:
    """
    插件物理清理计划项。

    :param name: 计划项名称
    :param label: 计划项展示名称
    :param enabled: 是否启用该计划项
    :param destructive: 是否为破坏性操作
    :param count: 计划项数量
    :param target: 计划项目标
    """

    name: str
    label: str
    enabled: bool
    destructive: bool
    count: int | None = None
    target: str | None = None


@dataclass(frozen=True)
class PluginPurgePlan:
    """
    插件物理清理计划。

    :param plugin_id: 插件ID
    :param items: 清理计划项列表
    :param removes_source: 是否删除源码目录
    :param requires_hook: 是否需要执行清理钩子
    """

    plugin_id: str
    items: list[PluginPurgePlanItem]
    removes_source: bool
    requires_hook: bool

    @property
    def destructive_count(self) -> int:
        """
        获取破坏性清理项数量。

        :return: 破坏性清理项数量
        """
        return len([item for item in self.items if item.enabled and item.destructive])


class PluginPurgePlanner:
    """
    插件物理清理计划生成器。

    使用 Planner 模式生成 dry-run 和实际执行共享的可审计清理范围。
    """

    @classmethod
    def build_plan(
        cls,
        discovered_plugin: DiscoveredPlugin,
        *,
        menu_count: int = 0,
        config_count: int = 0,
        migration_count: int = 0,
        job_count: int = 0,
    ) -> PluginPurgePlan:
        """
        构建插件物理清理计划。

        :param discovered_plugin: 已发现插件对象
        :param menu_count: 插件菜单数量
        :param config_count: 插件配置数量
        :param migration_count: 插件 migration 历史数量
        :param job_count: 插件任务数量
        :return: 插件物理清理计划
        """
        manifest = discovered_plugin.manifest
        items = [
            PluginPurgePlanItem(
                name='disable_plugin',
                label='停用插件和菜单',
                enabled=True,
                destructive=False,
                target=manifest.id,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_menus',
                label='删除插件菜单关联和插件菜单',
                enabled=menu_count > 0,
                destructive=True,
                count=menu_count,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_configs',
                label='删除插件配置',
                enabled=config_count > 0,
                destructive=True,
                count=config_count,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_migrations',
                label='删除插件 migration 历史',
                enabled=migration_count > 0,
                destructive=True,
                count=migration_count,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_jobs',
                label='删除插件定时任务',
                enabled=job_count > 0,
                destructive=True,
                count=job_count,
            ),
            PluginPurgePlanItem(
                name='run_purge_hook',
                label='执行插件 onPurge 钩子',
                enabled=bool(manifest.backend.hooks.on_purge),
                destructive=True,
                target=manifest.backend.hooks.on_purge,
            ),
            *cls._build_resource_items(manifest),
            PluginPurgePlanItem(
                name='delete_plugin_state',
                label='删除插件状态记录',
                enabled=True,
                destructive=True,
                count=1,
            ),
            PluginPurgePlanItem(
                name='remove_source',
                label='删除插件源码目录',
                enabled=False,
                destructive=True,
                target=str(discovered_plugin.backend_path),
            ),
        ]

        return PluginPurgePlan(
            plugin_id=manifest.id,
            items=items,
            removes_source=False,
            requires_hook=bool(manifest.backend.hooks.on_purge),
        )

    @classmethod
    def build_metadata_plan(
        cls,
        plugin_id: str,
        *,
        state_count: int = 0,
        menu_count: int = 0,
        config_count: int = 0,
        migration_count: int = 0,
        job_count: int = 0,
    ) -> PluginPurgePlan:
        """
        为源码已经缺失的孤儿插件构建平台元数据清理计划。

        metadata-only 清理无法推断业务表和文件资源，也不会伪装执行 onPurge；
        计划只包含平台能够按插件 ID 明确归属的资源。

        :param plugin_id: 插件ID
        :param state_count: 插件状态记录数量
        :param menu_count: 插件菜单数量
        :param config_count: 插件配置数量
        :param migration_count: 插件 migration 历史数量
        :param job_count: 插件任务数量
        :return: 插件物理清理计划
        """
        items = [
            PluginPurgePlanItem(
                name='disable_plugin',
                label='停用插件和菜单',
                enabled=state_count > 0,
                destructive=False,
                count=state_count,
                target=plugin_id,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_menus',
                label='删除插件菜单关联和插件菜单',
                enabled=menu_count > 0,
                destructive=True,
                count=menu_count,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_configs',
                label='删除插件配置',
                enabled=config_count > 0,
                destructive=True,
                count=config_count,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_migrations',
                label='删除插件 migration 历史',
                enabled=migration_count > 0,
                destructive=True,
                count=migration_count,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_jobs',
                label='删除插件定时任务',
                enabled=job_count > 0,
                destructive=True,
                count=job_count,
            ),
            PluginPurgePlanItem(
                name='delete_plugin_state',
                label='删除插件状态记录',
                enabled=state_count > 0,
                destructive=True,
                count=state_count,
            ),
            PluginPurgePlanItem(
                name='remove_source',
                label='删除插件源码目录',
                enabled=False,
                destructive=True,
            ),
        ]
        return PluginPurgePlan(
            plugin_id=plugin_id,
            items=items,
            removes_source=False,
            requires_hook=False,
        )

    @staticmethod
    def _build_resource_items(manifest: object) -> list[PluginPurgePlanItem]:
        """
        构建插件声明资源的清理提示项。

        :param manifest: 插件 manifest
        :return: 插件资源清理提示项列表
        """
        resources = getattr(manifest, 'resources', None)
        if resources is None:
            return []
        resource_groups = [
            ('resource_static', '插件静态资源需显式处理', getattr(resources, 'static', [])),
            ('resource_uploads', '插件上传资源需显式处理', getattr(resources, 'uploads', [])),
            ('resource_temp', '插件临时资源需显式处理', getattr(resources, 'temp', [])),
        ]

        return [
            PluginPurgePlanItem(
                name=name,
                label=label,
                enabled=bool(paths),
                destructive=False,
                count=len(paths),
                target=', '.join(paths),
            )
            for name, label, paths in resource_groups
            if paths
        ]
