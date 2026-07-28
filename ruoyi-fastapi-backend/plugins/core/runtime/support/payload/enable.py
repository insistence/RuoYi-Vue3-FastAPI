from collections.abc import Mapping
from typing import TypeAlias

from pydantic import Field

from plugins.core.validation.plugin_deps import PluginDependencyCheckResult

from . import PluginPayloadBuilder
from .base import PluginPayloadModel


class PluginEnableDependencyPayload(PluginPayloadModel):
    """
    插件启停依赖检查 payload。
    """

    plugin_dependency_ok: bool = Field(alias='pluginDependencyOk')
    plugin_dependency_errors: list[dict[str, object]] = Field(alias='pluginDependencyErrors')
    plugin_dependencies: list[dict[str, object]] = Field(alias='pluginDependencies')


class PluginEnableStatePayload(PluginPayloadModel):
    """
    插件启停状态 payload。
    """

    ok: bool
    message: object
    plugin_id: str = Field(alias='pluginId')
    operation: str
    enabled: bool
    dry_run: bool = Field(alias='dryRun')
    actions: list[dict[str, object]]
    plugin_dependency_ok: object | None = Field(default=None, alias='pluginDependencyOk')
    plugin_dependency_errors: object | None = Field(default=None, alias='pluginDependencyErrors')
    plugin_dependencies: object | None = Field(default=None, alias='pluginDependencies')


class PluginEnableUpdateFailurePayload(PluginPayloadModel):
    """
    插件启停写入失败 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    operation: str
    enabled: bool
    dry_run: bool = Field(alias='dryRun')


class PluginSafeUninstallPayload(PluginPayloadModel):
    """
    插件安全卸载 payload。
    """

    ok: object | None = None
    message: object | None = None
    plugin_id: object | None = Field(default=None, alias='pluginId')
    operation: str
    enabled: bool | None = None
    dry_run: bool | None = Field(default=None, alias='dryRun')
    safe_mode: bool = Field(alias='safeMode')
    removes_source: bool = Field(alias='removesSource')
    removes_menus: bool = Field(alias='removesMenus')
    actions: list[dict[str, object]] | None = None
    precheck: dict[str, object] | None = None
    manifest_ok: object | None = Field(default=None, alias='manifestOk')
    dependency_ok: object | None = Field(default=None, alias='dependencyOk')
    plugin_dependency_ok: object | None = Field(default=None, alias='pluginDependencyOk')
    structure_ok: object | None = Field(default=None, alias='structureOk')
    menu_conflict_ok: object | None = Field(default=None, alias='menuConflictOk')
    manifest_issues: object | None = Field(default=None, alias='manifestIssues')
    manifest_warnings: object | None = Field(default=None, alias='manifestWarnings')
    plugin_dependency_errors: object | None = Field(default=None, alias='pluginDependencyErrors')
    structure_errors: object | None = Field(default=None, alias='structureErrors')
    menu_conflicts: object | None = Field(default=None, alias='menuConflicts')
    dependencies: object | None = None
    plugin_dependencies: object | None = Field(default=None, alias='pluginDependencies')
    error: object | None = None
    failed_step: str | None = Field(default=None, alias='failedStep')
    capability: dict[str, object] | None = None


PluginEnableDependencyPayloadDict: TypeAlias = dict[str, object]
PluginEnableStatePayloadDict: TypeAlias = dict[str, object]
PluginEnableUpdateFailurePayloadDict: TypeAlias = dict[str, object]
PluginSafeUninstallPayloadDict: TypeAlias = dict[str, object]


class PluginEnablePayloadBuilder:
    """
    插件启停负载构建器。

    使用 Builder 模式集中启用、停用和安全卸载的负载拼装。
    """

    @classmethod
    def build_dependency_payload(
        cls, plugin_dependency_result: PluginDependencyCheckResult
    ) -> PluginEnableDependencyPayloadDict:
        """
        构建插件启用依赖检查负载。

        :param plugin_dependency_result: 插件间依赖检查结果
        :return: 插件启用依赖检查负载
        """
        return PluginEnableDependencyPayload(
            plugin_dependency_ok=plugin_dependency_result.ok,
            plugin_dependency_errors=[
                PluginPayloadBuilder.build_plugin_dependency_item(item)
                for item in plugin_dependency_result.failed_items
            ],
            plugin_dependencies=[
                PluginPayloadBuilder.build_plugin_dependency_item(item) for item in plugin_dependency_result.items
            ],
        ).to_payload()

    @staticmethod
    def build_dependency_blocker_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        dependency_payload: Mapping[str, object],
        message: str | None = None,
    ) -> PluginEnableStatePayloadDict:
        """
        构建插件启用依赖阻断负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param dependency_payload: 插件依赖检查负载
        :param message: 自定义阻断提示
        :return: 插件启用依赖阻断负载
        """
        plugin_dependency_ok = bool(dependency_payload.get('pluginDependencyOk', True))
        resolved_message = message or (
            '插件仍被已启用插件依赖，操作已中止'
            if operation in ('disable', 'uninstall')
            else '插件间依赖检查失败，启用已中止'
        )
        return PluginEnableStatePayload.model_validate(
            {
                'ok': False,
                'message': resolved_message,
                'pluginId': plugin_id,
                'operation': operation,
                'enabled': enabled,
                'dryRun': False,
                'actions': PluginPayloadBuilder.build_enabled_actions(enabled, plugin_dependency_ok),
                **dependency_payload,
            }
        ).to_payload(exclude_none=True)

    @staticmethod
    def build_dry_run_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        dependency_payload: Mapping[str, object],
    ) -> PluginEnableStatePayloadDict:
        """
        构建插件启停预演负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param dependency_payload: 插件依赖检查负载
        :return: 插件启停预演负载
        """
        return PluginEnablePayloadBuilder._build_state_payload(
            plugin_id=plugin_id,
            operation=operation,
            enabled=enabled,
            dry_run=True,
            ok=True,
            message='插件启停演练完成，未执行实际写入',
            dependency_payload=dependency_payload,
        )

    @staticmethod
    def build_update_failure_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        message: str,
    ) -> PluginEnableUpdateFailurePayloadDict:
        """
        构建插件启停写入失败负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param message: 失败提示
        :return: 插件启停写入失败负载
        """
        return PluginEnableUpdateFailurePayload(
            ok=False,
            message=message,
            plugin_id=plugin_id,
            operation=operation,
            enabled=enabled,
            dry_run=False,
        ).to_payload()

    @staticmethod
    def build_success_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        message: str,
        dependency_payload: Mapping[str, object],
    ) -> PluginEnableStatePayloadDict:
        """
        构建插件启停成功负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param message: 成功提示
        :param dependency_payload: 插件依赖检查负载
        :return: 插件启停成功负载
        """
        return PluginEnablePayloadBuilder._build_state_payload(
            plugin_id=plugin_id,
            operation=operation,
            enabled=enabled,
            dry_run=False,
            ok=True,
            message=message,
            dependency_payload=dependency_payload,
        )

    @staticmethod
    def build_uninstall_payload(result: Mapping[str, object], *, dry_run: bool) -> PluginSafeUninstallPayloadDict:
        """
        构建插件安全卸载负载。

        :param result: 插件停用结果负载
        :param dry_run: 是否预演
        :return: 插件安全卸载负载
        """
        uninstall_payload = dict(result)
        uninstall_payload.update(
            {
                'operation': 'uninstall',
                'message': '插件卸载演练完成，未执行实际写入' if dry_run else result.get('message', '插件卸载完成'),
                'safeMode': True,
                'removesSource': False,
                'removesMenus': True,
            }
        )
        return PluginSafeUninstallPayload.model_validate(uninstall_payload).to_payload(exclude_none=True)

    @staticmethod
    def _build_state_payload(
        *,
        plugin_id: str,
        operation: str,
        enabled: bool,
        dry_run: bool,
        ok: bool,
        message: str,
        dependency_payload: Mapping[str, object],
    ) -> PluginEnableStatePayloadDict:
        """
        构建插件启停状态负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param dry_run: 是否预演
        :param ok: 操作是否成功
        :param message: 响应消息
        :param dependency_payload: 插件依赖检查负载
        :return: 插件启停状态负载
        """
        plugin_dependency_ok = bool(dependency_payload.get('pluginDependencyOk', True))
        return PluginEnableStatePayload.model_validate(
            {
                'ok': ok,
                'message': message,
                'pluginId': plugin_id,
                'operation': operation,
                'enabled': enabled,
                'dryRun': dry_run,
                'actions': PluginPayloadBuilder.build_enabled_actions(enabled, plugin_dependency_ok),
                **dependency_payload,
            }
        ).to_payload(exclude_none=True)
