from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from pydantic import Field

from plugins.core.discovery.registry import RegisteredPlugin
from plugins.core.manifest.menu_tree import PluginMenuTree

from .base import PluginPayloadModel

if TYPE_CHECKING:
    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.manifest.schema import (
        PluginConfigItemManifest,
        PluginJobManifest,
        PluginMenuManifest,
        PluginPermissionManifest,
    )
    from plugins.core.types import PluginStateRecord, SupportsToPayload
    from plugins.core.validation.dependencies import DependencyCheckItem


class PluginCatalogSummaryPayload(PluginPayloadModel):
    """
    插件目录摘要 payload。
    """

    plugin_id: str = Field(alias='pluginId')
    name: str
    version: str
    enabled: bool
    status: str
    description: str
    backend_path: str = Field(alias='backendPath')
    menu_count: int = Field(alias='menuCount')
    permission_count: int = Field(alias='permissionCount')
    capability: dict[str, object] | None


class PluginCatalogDatabaseStatePayload(PluginPayloadModel):
    """
    插件目录数据库状态 payload。
    """

    available: bool
    installed: bool
    error: str | None = None
    installed_version: str | None = Field(default=None, alias='installedVersion')
    enabled: str | None
    status: str | None
    last_error: str | None = Field(default=None, alias='lastError')


class PluginManifestConfigItemPayload(PluginPayloadModel):
    """
    manifest 配置声明 payload。
    """

    key: str
    label: str | None
    type: str
    default: object
    required: bool
    secret: bool
    group: str
    order: int
    placeholder: str
    min_value: float | None = Field(alias='min')
    max_value: float | None = Field(alias='max')
    pattern: str | None
    description: str
    options: list[dict[str, object]]


class PluginManifestPermissionItemPayload(PluginPayloadModel):
    """
    manifest 权限声明 payload。
    """

    code: str
    name: str | None
    description: str


class PluginMenuDiagnosticPlanItemPayload(PluginPayloadModel):
    """
    菜单诊断计划项 payload。
    """

    name: str
    path: str
    component: str
    perms: str
    type: str
    query: str | None
    route_name: str | None = Field(alias='routeName')
    is_frame: int = Field(alias='isFrame')
    is_cache: int = Field(alias='isCache')
    visible: str
    status: str
    children: int


class PluginMenuDiagnosticPlanPayload(PluginPayloadModel):
    """
    菜单诊断计划 payload。
    """

    total: int
    permission_count: int = Field(alias='permissionCount')
    enabled_count: int = Field(alias='enabledCount')
    visible_count: int = Field(alias='visibleCount')
    items: list[dict[str, object]]


class PluginManifestJobItemPayload(PluginPayloadModel):
    """
    manifest 定时任务声明 payload。
    """

    id: str
    name: str | None
    callable: str
    trigger: str
    cron_expression: str = Field(alias='cronExpression')
    args: list[str]
    kwargs: dict[str, object]
    enabled: bool
    description: str
    misfire_policy: str = Field(alias='misfirePolicy')
    concurrent: str
    executor: str


PluginCatalogSummaryPayloadDict: TypeAlias = dict[str, object]
PluginCatalogDatabaseStatePayloadDict: TypeAlias = dict[str, object]


class PluginCatalogPayloadMixin:
    """
    插件目录、详情和 manifest 基础信息负载构建能力。
    """

    @classmethod
    def build_plugin_list_payload(cls, plugins: list[RegisteredPlugin]) -> dict[str, object]:
        """
        构建插件列表负载。

        :param plugins: 已注册插件列表
        :return: 插件列表负载
        """
        plugin_items = [
            cls.build_plugin_summary(plugin.discovered_plugin, plugin.enabled, plugin.status) for plugin in plugins
        ]
        return {'ok': True, 'count': len(plugin_items), 'plugins': plugin_items}

    @classmethod
    def build_plugin_info_payload(
        cls,
        plugin: RegisteredPlugin | DiscoveredPlugin,
        dependency_items: list[DependencyCheckItem],
        *,
        database_error: str | None = None,
        capability: SupportsToPayload | None = None,
    ) -> dict[str, object]:
        """
        构建插件详情响应负载。

        :param plugin: 已注册插件运行时快照或已发现插件
        :param dependency_items: 依赖检查项列表
        :param database_error: 数据库状态读取错误信息
        :return: 插件详情响应负载
        """
        return {
            'ok': True,
            'plugin': cls.build_plugin_detail(
                plugin,
                dependency_items,
                database_error=database_error,
                capability=capability,
            ),
        }

    @classmethod
    def build_plugin_summary(
        cls,
        plugin: DiscoveredPlugin,
        enabled: bool,
        status: str,
        capability: SupportsToPayload | None = None,
    ) -> PluginCatalogSummaryPayloadDict:
        """
        构建插件摘要负载。

        :param plugin: 已发现插件
        :param enabled: 是否启用
        :param status: 插件状态
        :return: 插件摘要负载
        """
        manifest = plugin.manifest
        return PluginCatalogSummaryPayload(
            plugin_id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            enabled=enabled,
            status=status,
            description=manifest.description,
            backend_path=str(plugin.backend_path),
            menu_count=PluginMenuTree.count(manifest.frontend.menus),
            permission_count=len(manifest.permissions),
            capability=capability.to_payload() if capability else None,
        ).to_payload()

    @classmethod
    def build_plugin_detail(
        cls,
        plugin: RegisteredPlugin | DiscoveredPlugin,
        dependency_items: list[DependencyCheckItem],
        *,
        database_error: str | None = None,
        capability: SupportsToPayload | None = None,
    ) -> dict[str, object]:
        """
        构建插件详情负载。

        :param plugin: 已注册插件运行时快照或已发现插件
        :param dependency_items: 依赖检查项列表
        :param database_error: 数据库状态读取错误信息
        :return: 插件详情负载
        """
        discovered_plugin = plugin.discovered_plugin if isinstance(plugin, RegisteredPlugin) else plugin
        database_plugin = plugin.database_plugin if isinstance(plugin, RegisteredPlugin) else None
        enabled = plugin.enabled if isinstance(plugin, RegisteredPlugin) else False
        status = plugin.status if isinstance(plugin, RegisteredPlugin) else 'discovered'
        manifest = discovered_plugin.manifest
        installed_version = getattr(database_plugin, 'installed_version', None)
        last_error = getattr(database_plugin, 'last_error', None)
        source = getattr(database_plugin, 'source', None) or 'local'
        frontend_path = getattr(database_plugin, 'frontend_path', None)

        return {
            **cls.build_plugin_summary(discovered_plugin, enabled, status, capability=capability),
            'installedVersion': installed_version,
            'source': source,
            'lastError': last_error,
            'frontendPath': frontend_path,
            'database': cls.build_database_state(database_plugin, database_error),
            'backend': {
                'module': manifest.backend.module,
                'autoScanRouters': manifest.backend.routers.auto_scan,
                'migrations': manifest.backend.migrations,
                'seeds': manifest.backend.seeds,
                'jobs': [cls.build_manifest_job_item(job) for job in manifest.backend.jobs],
            },
            'frontend': {
                'pluginId': manifest.frontend.plugin_id,
                'basePath': manifest.frontend.base_path,
                'viewsPath': manifest.frontend.views_path,
                'apiPath': manifest.frontend.api_path,
                'delivery': {
                    'type': manifest.frontend.delivery.type,
                    'buildRequired': manifest.frontend.delivery.build_required,
                },
            },
            'permissions': cls.build_manifest_permission_items(manifest.permissions),
            'config': cls.build_manifest_config_items(manifest.config.items),
            'pluginDependencies': [
                {
                    'id': dependency.id,
                    'version': dependency.version,
                    'description': dependency.description,
                }
                for dependency in manifest.dependencies.plugins
            ],
            'dependencies': [cls.build_dependency_item(item) for item in dependency_items],
        }

    @staticmethod
    def build_manifest_permission_items(
        permissions: list[PluginPermissionManifest],
    ) -> list[dict[str, object]]:
        """
        构建 manifest 权限声明 payload。

        :param permissions: 权限声明列表
        :return: 权限声明 payload 列表
        """
        return [
            PluginManifestPermissionItemPayload(
                code=permission.code,
                name=permission.name,
                description=permission.description,
            ).to_payload()
            for permission in permissions
        ]

    @staticmethod
    def build_manifest_config_items(
        config_items: list[PluginConfigItemManifest],
    ) -> list[dict[str, object]]:
        """
        构建 manifest 配置声明负载。

        :param config_items: manifest 配置项声明列表
        :return: 配置声明负载列表
        """
        return [
            PluginManifestConfigItemPayload(
                key=item.key,
                label=item.label,
                type=item.type,
                default=item.default,
                required=item.required,
                secret=item.secret,
                group=item.group,
                order=item.order,
                placeholder=item.placeholder,
                min_value=item.min_value,
                max_value=item.max_value,
                pattern=item.pattern,
                description=item.description,
                options=[option.model_dump() for option in item.options],
            ).to_payload()
            for item in config_items
        ]

    @classmethod
    def build_menu_diagnostic_plan(cls, discovered_plugin: DiscoveredPlugin) -> dict[str, object]:
        """
        构建插件菜单诊断计划。

        :param discovered_plugin: 已发现插件
        :return: 菜单诊断计划负载
        """
        menus = PluginMenuTree.flatten(discovered_plugin.manifest.frontend.menus)
        permission_menus = [menu for menu in menus if menu.perms]
        enabled_menus = [menu for menu in menus if menu.status == '0']
        visible_menus = [menu for menu in menus if menu.visible == '0']

        return PluginMenuDiagnosticPlanPayload(
            total=len(menus),
            permission_count=len(permission_menus),
            enabled_count=len(enabled_menus),
            visible_count=len(visible_menus),
            items=[cls._build_menu_plan_item(menu) for menu in menus],
        ).to_payload()

    @classmethod
    def _build_menu_plan_item(cls, menu: PluginMenuManifest) -> dict[str, object]:
        """
        构建菜单诊断计划项。

        :param menu: 插件菜单声明
        :return: 菜单诊断计划项
        """
        return PluginMenuDiagnosticPlanItemPayload(
            name=menu.name,
            path=menu.path,
            component=menu.component,
            perms=menu.perms,
            type=menu.type,
            query=menu.query,
            routeName=menu.route_name,
            isFrame=menu.is_frame,
            isCache=menu.is_cache,
            visible=menu.visible,
            status=menu.status,
            children=len(menu.children),
        ).to_payload()

    @staticmethod
    def build_manifest_job_item(job: PluginJobManifest) -> dict[str, object]:
        """
        构建 manifest 定时任务声明负载。

        :param job: manifest 定时任务声明
        :return: 定时任务声明负载
        """
        return PluginManifestJobItemPayload(
            id=job.id,
            name=job.name,
            callable=job.callable,
            trigger=job.trigger,
            cron_expression=job.cron_expression,
            args=job.args,
            kwargs=job.kwargs,
            enabled=job.enabled,
            description=job.description,
            misfire_policy=job.misfire_policy,
            concurrent=job.concurrent,
            executor=job.executor,
        ).to_payload()

    @staticmethod
    def build_database_state(
        database_plugin: PluginStateRecord | None,
        database_error: str | None = None,
    ) -> PluginCatalogDatabaseStatePayloadDict:
        """
        构建插件数据库状态负载。

        :param database_plugin: 数据库插件状态对象
        :param database_error: 数据库状态读取错误信息
        :return: 数据库状态负载
        """
        if database_error:
            return PluginCatalogDatabaseStatePayload(
                available=False,
                installed=False,
                error=database_error,
                enabled=None,
                status=None,
            ).to_payload(exclude_none=True)

        return PluginCatalogDatabaseStatePayload(
            available=True,
            installed=database_plugin is not None,
            installed_version=database_plugin.installed_version if database_plugin else None,
            enabled=database_plugin.enabled if database_plugin else None,
            status=database_plugin.status if database_plugin else None,
            last_error=database_plugin.last_error if database_plugin else None,
        ).to_payload()
