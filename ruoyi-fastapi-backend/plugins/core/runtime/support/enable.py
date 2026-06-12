from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypedDict

from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, RUNTIME_ERROR
from plugins.core.validation.plugin_deps import PluginDependencyCheckResult

from .payload import ActionPayload, PluginDependencyItemPayload, PluginPayloadBuilder


class PluginEnableDependencyPayloadDict(TypedDict):
    """
    插件启停依赖检查 payload。
    """

    pluginDependencyOk: bool
    pluginDependencyErrors: list[PluginDependencyItemPayload]
    pluginDependencies: list[PluginDependencyItemPayload]


class PluginEnableStatePayloadDict(TypedDict, total=False):
    """
    插件启停状态 payload。
    """

    ok: bool
    message: object
    pluginId: str
    operation: str
    enabled: bool
    dryRun: bool
    actions: list[ActionPayload]
    pluginDependencyOk: object
    pluginDependencyErrors: object
    pluginDependencies: object
    exit_code: int


class PluginEnableUpdateFailurePayloadDict(TypedDict):
    """
    插件启停写入失败 payload。
    """

    ok: bool
    message: str
    pluginId: str
    operation: str
    enabled: bool
    dryRun: bool
    exit_code: int


class PluginSafeUninstallPayloadDict(TypedDict, total=False):
    """
    插件安全卸载 payload。
    """

    ok: object
    message: object
    pluginId: object
    operation: str
    safeMode: bool
    removesSource: bool
    removesMenus: bool


@dataclass(frozen=True)
class PluginEnableDependencyPayload:
    """
    插件启停依赖检查结构化负载。
    """

    plugin_dependency_result: PluginDependencyCheckResult

    def to_payload(self) -> PluginEnableDependencyPayloadDict:
        """
        序列化为现有插件启停依赖检查 payload 契约。

        :return: 插件启停依赖检查 payload
        """
        return {
            'pluginDependencyOk': self.plugin_dependency_result.ok,
            'pluginDependencyErrors': [
                PluginPayloadBuilder.build_plugin_dependency_item(item)
                for item in self.plugin_dependency_result.failed_items
            ],
            'pluginDependencies': [
                PluginPayloadBuilder.build_plugin_dependency_item(item) for item in self.plugin_dependency_result.items
            ],
        }


@dataclass(frozen=True)
class PluginEnableDependencyBlockerPayload:
    """
    插件启停依赖阻断结构化负载。
    """

    plugin_id: str
    operation: str
    enabled: bool
    dependency_payload: Mapping[str, object]

    def to_payload(self) -> PluginEnableStatePayloadDict:
        """
        序列化为现有插件启停依赖阻断 payload 契约。

        :return: 插件启停依赖阻断 payload
        """
        plugin_dependency_ok = bool(self.dependency_payload.get('pluginDependencyOk', True))
        return {
            'ok': False,
            'message': '插件间依赖检查失败，启用已中止',
            'pluginId': self.plugin_id,
            'operation': self.operation,
            'enabled': self.enabled,
            'dryRun': False,
            'actions': PluginPayloadBuilder.build_enabled_actions(self.enabled, plugin_dependency_ok),
            **self.dependency_payload,
            'exit_code': DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginEnableStatePayload:
    """
    插件启停状态结构化负载。
    """

    plugin_id: str
    operation: str
    enabled: bool
    dry_run: bool
    ok: bool
    message: str
    dependency_payload: Mapping[str, object]

    def to_payload(self) -> PluginEnableStatePayloadDict:
        """
        序列化为现有插件启停 payload 契约。

        :return: 插件启停 payload
        """
        plugin_dependency_ok = bool(self.dependency_payload.get('pluginDependencyOk', True))
        return {
            'ok': self.ok,
            'message': self.message,
            'pluginId': self.plugin_id,
            'operation': self.operation,
            'enabled': self.enabled,
            'dryRun': self.dry_run,
            'actions': PluginPayloadBuilder.build_enabled_actions(self.enabled, plugin_dependency_ok),
            **self.dependency_payload,
        }


@dataclass(frozen=True)
class PluginEnableUpdateFailurePayload:
    """
    插件启停写入失败结构化负载。
    """

    plugin_id: str
    operation: str
    enabled: bool
    message: str

    def to_payload(self) -> PluginEnableUpdateFailurePayloadDict:
        """
        序列化为现有插件启停写入失败 payload 契约。

        :return: 插件启停写入失败 payload
        """
        return {
            'ok': False,
            'message': self.message,
            'pluginId': self.plugin_id,
            'operation': self.operation,
            'enabled': self.enabled,
            'dryRun': False,
            'exit_code': RUNTIME_ERROR,
        }


@dataclass(frozen=True)
class PluginSafeUninstallPayload:
    """
    插件安全卸载结构化负载。
    """

    result: Mapping[str, object]
    dry_run: bool

    def to_payload(self) -> PluginSafeUninstallPayloadDict:
        """
        序列化为现有插件安全卸载 payload 契约。

        :return: 插件安全卸载 payload
        """
        return {
            **self.result,
            'operation': 'uninstall',
            'message': '插件卸载演练完成，未执行实际写入'
            if self.dry_run
            else self.result.get('message', '插件卸载完成'),
            'safeMode': True,
            'removesSource': False,
            'removesMenus': True,
        }


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
        return PluginEnableDependencyPayload(plugin_dependency_result).to_payload()

    @staticmethod
    def build_dependency_blocker_payload(
        plugin_id: str,
        *,
        operation: str,
        enabled: bool,
        dependency_payload: Mapping[str, object],
    ) -> PluginEnableStatePayloadDict:
        """
        构建插件启用依赖阻断负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param enabled: 是否启用
        :param dependency_payload: 插件依赖检查负载
        :return: 插件启用依赖阻断负载
        """
        return PluginEnableDependencyBlockerPayload(
            plugin_id=plugin_id,
            operation=operation,
            enabled=enabled,
            dependency_payload=dependency_payload,
        ).to_payload()

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
        return PluginEnableStatePayload(
            plugin_id=plugin_id,
            operation=operation,
            enabled=enabled,
            dry_run=True,
            ok=True,
            message='插件启停演练完成，未执行实际写入',
            dependency_payload=dependency_payload,
        ).to_payload()

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
            plugin_id=plugin_id,
            operation=operation,
            enabled=enabled,
            message=message,
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
        return PluginEnableStatePayload(
            plugin_id=plugin_id,
            operation=operation,
            enabled=enabled,
            dry_run=False,
            ok=True,
            message=message,
            dependency_payload=dependency_payload,
        ).to_payload()

    @staticmethod
    def build_uninstall_payload(result: Mapping[str, object], *, dry_run: bool) -> PluginSafeUninstallPayloadDict:
        """
        构建插件安全卸载负载。

        :param result: 插件停用结果负载
        :param dry_run: 是否预演
        :return: 插件安全卸载负载
        """
        return PluginSafeUninstallPayload(result=result, dry_run=dry_run).to_payload()
