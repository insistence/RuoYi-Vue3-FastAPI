from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict

from plugins.core.discovery.registry import RegisteredPlugin
from plugins.core.manifest.menu_tree import PluginMenuTree

from .validation import PluginValidationPayloadBuilderProtocol, PluginValidationPayloadMixin

if TYPE_CHECKING:
    from plugins.core.discovery.scanner import DiscoveredPlugin
    from plugins.core.manifest.schema import PluginConfigItemManifest, PluginJobManifest, PluginMenuManifest
    from plugins.core.types import PluginConfigValue, PluginStateRecord, SupportsToPayload
    from plugins.core.validation.dependencies import DependencyCheckItem


class PluginCatalogSummaryPayloadDict(TypedDict):
    """
    插件目录摘要 payload。
    """

    pluginId: str
    name: str
    version: str
    enabled: bool
    status: str
    description: str
    backendPath: str
    menuCount: int
    permissionCount: int
    capability: dict[str, object] | None


class PluginCatalogDatabaseStatePayloadDict(TypedDict, total=False):
    """
    插件目录数据库状态 payload。
    """

    available: bool
    installed: bool
    error: str
    installedVersion: str | None
    enabled: str | None
    status: str | None
    lastError: str | None


class PluginManifestConfigItemPayload(TypedDict):
    """
    manifest 配置声明 payload。
    """

    key: str
    label: str | None
    type: str
    default: PluginConfigValue
    required: bool
    secret: bool
    group: str
    order: int
    placeholder: str
    min: float | None
    max: float | None
    pattern: str | None
    description: str
    options: list[dict[str, PluginConfigValue]]


class PluginMenuDiagnosticPlanItemPayload(TypedDict):
    """
    菜单诊断计划项 payload。
    """

    name: str
    path: str
    component: str
    perms: str
    type: str
    visible: str
    status: str
    children: int


class PluginMenuDiagnosticPlanPayload(TypedDict):
    """
    菜单诊断计划 payload。
    """

    total: int
    permissionCount: int
    enabledCount: int
    visibleCount: int
    items: list[PluginMenuDiagnosticPlanItemPayload]


class PluginManifestJobItemPayload(TypedDict):
    """
    manifest 定时任务声明 payload。
    """

    id: str
    name: str | None
    callable: str
    trigger: str
    cronExpression: str
    args: list[str]
    kwargs: dict[str, object]
    enabled: bool
    description: str
    misfirePolicy: str
    concurrent: str
    executor: str


class PluginCatalogPayloadBuilderProtocol(PluginValidationPayloadBuilderProtocol, Protocol):
    """
    插件目录 payload builder 协议。
    """

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
        """
        ...

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
        """
        ...


@dataclass(frozen=True)
class PluginCatalogListPayload:
    """
    插件目录列表结构化负载。
    """

    plugins: list[RegisteredPlugin]
    builder: type[PluginCatalogPayloadBuilderProtocol] | None = None

    def to_payload(self) -> dict[str, object]:
        """
        序列化为现有插件列表 payload 契约。

        :return: 插件列表 payload
        """
        builder = self.builder or _get_default_catalog_builder()
        plugin_items = [
            builder.build_plugin_summary(plugin.discovered_plugin, plugin.enabled, plugin.status)
            for plugin in self.plugins
        ]
        return {'ok': True, 'count': len(plugin_items), 'plugins': plugin_items}


@dataclass(frozen=True)
class PluginCatalogInfoPayload:
    """
    插件目录详情响应结构化负载。
    """

    plugin: RegisteredPlugin | DiscoveredPlugin
    dependency_items: list[DependencyCheckItem]
    builder: type[PluginCatalogPayloadBuilderProtocol] | None = None
    database_error: str | None = None
    capability: SupportsToPayload | None = None

    def to_payload(self) -> dict[str, object]:
        """
        序列化为现有插件详情响应 payload 契约。

        :return: 插件详情响应 payload
        """
        builder = self.builder or _get_default_catalog_builder()
        return {
            'ok': True,
            'plugin': builder.build_plugin_detail(
                self.plugin,
                self.dependency_items,
                database_error=self.database_error,
                capability=self.capability,
            ),
        }


@dataclass(frozen=True)
class PluginCatalogSummaryPayload:
    """
    插件目录摘要结构化负载。
    """

    plugin: DiscoveredPlugin
    enabled: bool
    status: str
    capability: SupportsToPayload | None = None

    def to_payload(self) -> PluginCatalogSummaryPayloadDict:
        """
        序列化为现有插件摘要 payload 契约。

        :return: 插件摘要 payload
        """
        manifest = self.plugin.manifest
        return {
            'pluginId': manifest.id,
            'name': manifest.name,
            'version': manifest.version,
            'enabled': self.enabled,
            'status': self.status,
            'description': manifest.description,
            'backendPath': str(self.plugin.backend_path),
            'menuCount': PluginMenuTree.count(manifest.frontend.menus),
            'permissionCount': len(manifest.permissions),
            'capability': self.capability.to_payload() if self.capability else None,
        }


@dataclass(frozen=True)
class PluginCatalogDatabaseStatePayload:
    """
    插件目录数据库状态结构化负载。
    """

    database_plugin: PluginStateRecord | None
    database_error: str | None = None

    def to_payload(self) -> PluginCatalogDatabaseStatePayloadDict:
        """
        序列化为现有插件数据库状态 payload 契约。

        :return: 插件数据库状态 payload
        """
        if self.database_error:
            return {
                'available': False,
                'installed': False,
                'error': self.database_error,
            }

        return {
            'available': True,
            'installed': self.database_plugin is not None,
            'installedVersion': self.database_plugin.installed_version if self.database_plugin else None,
            'enabled': self.database_plugin.enabled if self.database_plugin else None,
            'status': self.database_plugin.status if self.database_plugin else None,
            'lastError': self.database_plugin.last_error if self.database_plugin else None,
        }


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
        return PluginCatalogListPayload(plugins, builder=cls).to_payload()

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
        return PluginCatalogInfoPayload(
            plugin,
            dependency_items,
            builder=cls,
            database_error=database_error,
            capability=capability,
        ).to_payload()

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
        return PluginCatalogSummaryPayload(
            plugin,
            enabled=enabled,
            status=status,
            capability=capability,
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
        enabled = plugin.enabled if isinstance(plugin, RegisteredPlugin) else discovered_plugin.manifest.enabled
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
            'permissions': manifest.permissions,
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
    def build_manifest_config_items(
        config_items: list[PluginConfigItemManifest],
    ) -> list[PluginManifestConfigItemPayload]:
        """
        构建 manifest 配置声明负载。

        :param config_items: manifest 配置项声明列表
        :return: 配置声明负载列表
        """
        return [
            {
                'key': item.key,
                'label': item.label,
                'type': item.type,
                'default': item.default,
                'required': item.required,
                'secret': item.secret,
                'group': item.group,
                'order': item.order,
                'placeholder': item.placeholder,
                'min': item.min_value,
                'max': item.max_value,
                'pattern': item.pattern,
                'description': item.description,
                'options': [option.model_dump() for option in item.options],
            }
            for item in config_items
        ]

    @classmethod
    def build_menu_diagnostic_plan(cls, discovered_plugin: DiscoveredPlugin) -> PluginMenuDiagnosticPlanPayload:
        """
        构建插件菜单诊断计划。

        :param discovered_plugin: 已发现插件
        :return: 菜单诊断计划负载
        """
        menus = PluginMenuTree.flatten(discovered_plugin.manifest.frontend.menus)
        permission_menus = [menu for menu in menus if menu.perms]
        enabled_menus = [menu for menu in menus if menu.status == '0']
        visible_menus = [menu for menu in menus if menu.visible == '0']

        return {
            'total': len(menus),
            'permissionCount': len(permission_menus),
            'enabledCount': len(enabled_menus),
            'visibleCount': len(visible_menus),
            'items': [cls._build_menu_plan_item(menu) for menu in menus],
        }

    @classmethod
    def _build_menu_plan_item(cls, menu: PluginMenuManifest) -> PluginMenuDiagnosticPlanItemPayload:
        """
        构建菜单诊断计划项。

        :param menu: 插件菜单声明
        :return: 菜单诊断计划项
        """
        return {
            'name': menu.name,
            'path': menu.path,
            'component': menu.component,
            'perms': menu.perms,
            'type': menu.type,
            'visible': menu.visible,
            'status': menu.status,
            'children': len(menu.children),
        }

    @staticmethod
    def build_manifest_job_item(job: PluginJobManifest) -> PluginManifestJobItemPayload:
        """
        构建 manifest 定时任务声明负载。

        :param job: manifest 定时任务声明
        :return: 定时任务声明负载
        """
        return {
            'id': job.id,
            'name': job.name,
            'callable': job.callable,
            'trigger': job.trigger,
            'cronExpression': job.cron_expression,
            'args': job.args,
            'kwargs': job.kwargs,
            'enabled': job.enabled,
            'description': job.description,
            'misfirePolicy': job.misfire_policy,
            'concurrent': job.concurrent,
            'executor': job.executor,
        }

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
        return PluginCatalogDatabaseStatePayload(database_plugin, database_error).to_payload()


class _DefaultCatalogPayloadBuilder(PluginCatalogPayloadMixin, PluginValidationPayloadMixin):
    """
    catalog 模型直接序列化时使用的最小组合 builder。
    """


def _get_default_catalog_builder() -> type[PluginCatalogPayloadBuilderProtocol]:
    """
    获取 catalog 模型直接序列化时使用的默认 builder。

    :return: 默认 catalog 组合 builder
    """
    return _DefaultCatalogPayloadBuilder
