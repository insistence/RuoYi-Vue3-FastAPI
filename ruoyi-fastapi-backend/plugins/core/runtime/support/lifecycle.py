from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, SUCCESS

from .payload import ActionPayload, MenuConflictItemPayload, PluginPayloadBuilder, VersionStatePayload

if TYPE_CHECKING:
    from collections.abc import Mapping

    from plugins.core.lifecycle.migration import PluginMigrationResult
    from plugins.core.lifecycle.seed import PluginSeedResult
    from plugins.core.runtime.hooks import PluginHookResult
    from plugins.core.types import SupportsModelDump
    from plugins.core.validation.menus import PluginMenuConflictItem


class SupportsOk(Protocol):
    """
    支持 ok 属性的检查结果协议。
    """

    ok: bool


class PluginLifecyclePrecheckProtocol(Protocol):
    """
    lifecycle payload 所需的预检上下文协议。
    """

    ok: bool
    dependency_result: SupportsOk
    manifest_result: SupportsOk
    plugin_dependency_result: SupportsOk
    structure_result: SupportsOk
    menu_conflict_result: SupportsOk
    operation_payload: Mapping[str, object]
    check_payload: Mapping[str, object]
    menu_conflicts: list[MenuConflictItemPayload]


class PluginLifecyclePayloadDict(TypedDict, total=False):
    """
    插件生命周期通用 payload。
    """

    ok: bool
    message: str
    pluginId: str
    dryRun: bool
    operation: str
    actions: list[ActionPayload]
    precheck: Mapping[str, object]
    exit_code: int
    plugin: dict[str, object]
    configs: list[dict[str, object]]
    migrations: list[dict[str, object]]
    seeds: list[dict[str, object]]
    hooks: list[dict[str, object]]
    menuConflicts: list[MenuConflictItemPayload]
    menuConflictOk: object
    manifestOk: object
    dependencyOk: object
    pluginDependencyOk: object
    structureOk: object
    manifestIssues: object
    manifestWarnings: object
    pluginDependencyErrors: object
    structureErrors: object
    dependencies: object
    pluginDependencies: object
    installed: bool
    installedVersion: str | None
    currentVersion: str
    needsUpgrade: bool
    dependencyInstall: object


def _object_payload(value: object) -> dict[str, object]:
    """
    将生命周期执行结果对象转换为 payload 字典。

    :param value: 生命周期执行结果对象
    :return: payload 字典
    """
    return dict(vars(value))


@dataclass(frozen=True)
class PluginInstallDryRunPayload:
    """
    插件安装预演结构化负载。
    """

    plugin_id: str
    actions: list[ActionPayload]
    precheck: PluginLifecyclePrecheckProtocol
    message: str = '插件安装演练完成，未执行实际写入'

    def to_payload(self) -> PluginLifecyclePayloadDict:
        """
        序列化为现有插件安装预演 payload 契约。

        :return: 插件安装预演 payload
        """
        return {
            'ok': True,
            'message': self.message,
            'pluginId': self.plugin_id,
            'dryRun': True,
            'actions': self.actions,
            **self.precheck.operation_payload,
        }


@dataclass(frozen=True)
class PluginLifecyclePrecheckBlockerPayload:
    """
    插件生命周期预检阻断结构化负载。
    """

    plugin_id: str
    message: str
    actions: list[ActionPayload]
    precheck: PluginLifecyclePrecheckProtocol
    dry_run: bool = False
    extra_payload: Mapping[str, object] | None = None

    def to_payload(self) -> PluginLifecyclePayloadDict:
        """
        序列化为现有插件生命周期预检阻断 payload 契约。

        :return: 插件生命周期预检阻断 payload
        """
        return {
            'ok': False,
            'message': self.message,
            'pluginId': self.plugin_id,
            'dryRun': self.dry_run,
            **(self.extra_payload or {}),
            'actions': self.actions,
            **self.precheck.operation_payload,
            'exit_code': DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginLifecycleOperationDryRunPayload:
    """
    插件生命周期操作预演结构化负载。
    """

    plugin_id: str
    operation: str
    message: str
    actions: list[ActionPayload]
    precheck: PluginLifecyclePrecheckProtocol
    extra_payload: Mapping[str, object] | None = None
    ok_from_precheck: bool = True

    def to_payload(self) -> PluginLifecyclePayloadDict:
        """
        序列化为现有插件生命周期操作预演 payload 契约。

        :return: 插件生命周期操作预演 payload
        """
        ok = self.precheck.ok if self.ok_from_precheck else True
        return {
            'ok': ok,
            'message': self.message if ok else '插件操作预检存在问题，未执行实际写入',
            'pluginId': self.plugin_id,
            'operation': self.operation,
            'dryRun': True,
            **(self.extra_payload or {}),
            'actions': self.actions,
            **self.precheck.operation_payload,
            'precheck': self.precheck.check_payload,
            'exit_code': SUCCESS if ok else DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginLifecycleMenuConflictPayload:
    """
    插件生命周期已安装菜单冲突结构化负载。
    """

    plugin_id: str
    message: str
    actions: list[ActionPayload]
    precheck: PluginLifecyclePrecheckProtocol
    installed_menu_conflicts: list[PluginMenuConflictItem]
    extra_payload: Mapping[str, object] | None = None

    def to_payload(self) -> PluginLifecyclePayloadDict:
        """
        序列化为现有插件生命周期菜单冲突 payload 契约。

        :return: 插件生命周期菜单冲突 payload
        """
        menu_conflicts = [
            *self.precheck.menu_conflicts,
            *[PluginPayloadBuilder.build_menu_conflict_item(item) for item in self.installed_menu_conflicts],
        ]
        return {
            'ok': False,
            'message': self.message,
            'pluginId': self.plugin_id,
            'dryRun': False,
            **(self.extra_payload or {}),
            'actions': self.actions,
            **self.precheck.operation_payload,
            'menuConflicts': menu_conflicts,
            'menuConflictOk': False,
            'exit_code': DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginLifecycleUpgradeLatestPayload:
    """
    插件生命周期无需升级结构化负载。
    """

    plugin_id: str
    version_state: VersionStatePayload
    precheck: PluginLifecyclePrecheckProtocol

    def to_payload(self) -> PluginLifecyclePayloadDict:
        """
        序列化为现有插件无需升级 payload 契约。

        :return: 插件无需升级 payload
        """
        return {
            'ok': True,
            'message': '插件已是最新版本，无需升级',
            'pluginId': self.plugin_id,
            'dryRun': False,
            **self.version_state,
            'actions': [],
            **self.precheck.operation_payload,
        }


@dataclass(frozen=True)
class PluginLifecycleSuccessPayload:
    """
    插件生命周期成功结构化负载。
    """

    plugin_id: str
    message: str
    actions: list[ActionPayload]
    precheck: PluginLifecyclePrecheckProtocol
    plugin: SupportsModelDump
    installed_configs: list[SupportsModelDump]
    migration_results: list[PluginMigrationResult]
    seed_results: list[PluginSeedResult]
    hook_result: PluginHookResult | None
    extra_payload: Mapping[str, object] | None = None

    def to_payload(self) -> PluginLifecyclePayloadDict:
        """
        序列化为现有插件生命周期成功 payload 契约。

        :return: 插件生命周期成功 payload
        """
        return {
            'ok': True,
            'message': self.message,
            'pluginId': self.plugin_id,
            'dryRun': False,
            **(self.extra_payload or {}),
            'actions': self.actions,
            **self.precheck.operation_payload,
            'plugin': cast('dict[str, object]', self.plugin.model_dump(by_alias=True)),
            'configs': [
                cast('dict[str, object]', config.model_dump(by_alias=True)) for config in self.installed_configs
            ],
            'migrations': [_object_payload(migration_result) for migration_result in self.migration_results],
            'seeds': [_object_payload(seed_result) for seed_result in self.seed_results],
            'hooks': [_object_payload(self.hook_result)] if self.hook_result else [],
        }


class PluginLifecyclePayloadBuilder:
    """
    插件安装与升级生命周期负载构建器。

    使用 Builder 模式集中安装、升级流程中的 dry-run、阻断和成功结果负载。
    """

    @staticmethod
    def build_install_dry_run_payload(
        plugin_id: str,
        actions: list[ActionPayload],
        precheck: PluginLifecyclePrecheckProtocol,
    ) -> PluginLifecyclePayloadDict:
        """
        构建插件安装预演负载。

        :param plugin_id: 插件ID
        :param actions: 安装动作清单
        :param precheck: 插件操作预检上下文
        :return: 插件安装预演负载
        """
        return PluginInstallDryRunPayload(
            plugin_id=plugin_id,
            actions=actions,
            precheck=precheck,
        ).to_payload()

    @staticmethod
    def build_precheck_blocker_payload(
        plugin_id: str,
        *,
        message: str,
        actions: list[ActionPayload],
        precheck: PluginLifecyclePrecheckProtocol,
        dry_run: bool = False,
        extra_payload: Mapping[str, object] | None = None,
    ) -> PluginLifecyclePayloadDict:
        """
        构建插件安装或升级预检阻断负载。

        :param plugin_id: 插件ID
        :param message: 阻断提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param dry_run: 是否预演
        :param extra_payload: 额外负载
        :return: 插件安装或升级预检阻断负载
        """
        return PluginLifecyclePrecheckBlockerPayload(
            plugin_id=plugin_id,
            message=message,
            actions=actions,
            precheck=precheck,
            dry_run=dry_run,
            extra_payload=extra_payload,
        ).to_payload()

    @classmethod
    def build_first_precheck_blocker_payload(
        cls,
        plugin_id: str,
        *,
        operation: str,
        actions: list[ActionPayload],
        precheck: PluginLifecyclePrecheckProtocol,
        extra_payload: Mapping[str, object] | None = None,
    ) -> PluginLifecyclePayloadDict | None:
        """
        按统一优先级构建首个预检阻断负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param extra_payload: 额外负载
        :return: 预检阻断负载，无需阻断时返回 None
        """
        operation_label = {
            'install': '安装',
            'enable': '启用',
            'upgrade': '升级',
            'uninstall': '卸载',
            'purge': '物理清理',
        }.get(operation, '操作')
        blocker_specs = [
            (precheck.manifest_result.ok, 'manifestOk', f'插件 manifest 检查失败，{operation_label}已中止'),
            (
                precheck.plugin_dependency_result.ok,
                'pluginDependencyOk',
                f'插件间依赖检查失败，{operation_label}已中止',
            ),
            (precheck.structure_result.ok, 'structureOk', f'插件结构检查失败，{operation_label}已中止'),
            (precheck.menu_conflict_result.ok, 'menuConflictOk', f'插件菜单存在冲突，{operation_label}已中止'),
        ]
        for ok, payload_key, message in blocker_specs:
            if ok:
                continue
            return cls.build_precheck_blocker_payload(
                plugin_id,
                message=message,
                actions=actions,
                precheck=precheck,
                extra_payload={**(extra_payload or {}), payload_key: False},
            )

        return None

    @classmethod
    def build_dependency_blocker_payload(
        cls,
        plugin_id: str,
        *,
        actions: list[ActionPayload],
        precheck: PluginLifecyclePrecheckProtocol,
        dependency_install_payload: Mapping[str, object],
    ) -> PluginLifecyclePayloadDict | None:
        """
        构建依赖自动安装后仍未满足时的阻断负载。

        :param plugin_id: 插件ID
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param dependency_install_payload: 依赖安装执行负载
        :return: 依赖阻断负载，无需阻断时返回 None
        """
        if precheck.dependency_result.ok:
            return None

        return cls.build_precheck_blocker_payload(
            plugin_id,
            message='插件依赖检查失败，安装已中止',
            actions=actions,
            precheck=precheck,
            extra_payload={'dependencyOk': False, 'dependencyInstall': dependency_install_payload},
        )

    @staticmethod
    def build_operation_dry_run_payload(
        plugin_id: str,
        *,
        operation: str,
        message: str,
        actions: list[ActionPayload],
        precheck: PluginLifecyclePrecheckProtocol,
        extra_payload: Mapping[str, object] | None = None,
        ok_from_precheck: bool = True,
    ) -> PluginLifecyclePayloadDict:
        """
        构建统一预检后的操作预演负载。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :param message: 预演提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param extra_payload: 额外负载
        :param ok_from_precheck: 是否使用预检结果决定操作是否成功
        :return: 操作预演负载
        """
        return PluginLifecycleOperationDryRunPayload(
            plugin_id=plugin_id,
            operation=operation,
            message=message,
            actions=actions,
            precheck=precheck,
            extra_payload=extra_payload,
            ok_from_precheck=ok_from_precheck,
        ).to_payload()

    @staticmethod
    def build_installed_menu_conflict_payload(
        plugin_id: str,
        *,
        message: str,
        actions: list[ActionPayload],
        precheck: PluginLifecyclePrecheckProtocol,
        installed_menu_conflicts: list[PluginMenuConflictItem],
        extra_payload: Mapping[str, object] | None = None,
    ) -> PluginLifecyclePayloadDict:
        """
        构建已安装菜单冲突阻断负载。

        :param plugin_id: 插件ID
        :param message: 阻断提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param installed_menu_conflicts: 已安装菜单冲突列表
        :param extra_payload: 额外负载
        :return: 已安装菜单冲突阻断负载
        """
        return PluginLifecycleMenuConflictPayload(
            plugin_id=plugin_id,
            message=message,
            actions=actions,
            precheck=precheck,
            installed_menu_conflicts=installed_menu_conflicts,
            extra_payload=extra_payload,
        ).to_payload()

    @staticmethod
    def build_upgrade_latest_payload(
        plugin_id: str,
        version_state: VersionStatePayload,
        precheck: PluginLifecyclePrecheckProtocol,
    ) -> PluginLifecyclePayloadDict:
        """
        构建插件无需升级负载。

        :param plugin_id: 插件ID
        :param version_state: 插件升级版本状态
        :param precheck: 插件操作预检上下文
        :return: 插件无需升级负载
        """
        return PluginLifecycleUpgradeLatestPayload(
            plugin_id=plugin_id,
            version_state=version_state,
            precheck=precheck,
        ).to_payload()

    @staticmethod
    def build_success_payload(
        plugin_id: str,
        *,
        message: str,
        actions: list[ActionPayload],
        precheck: PluginLifecyclePrecheckProtocol,
        plugin: SupportsModelDump,
        installed_configs: list[SupportsModelDump],
        migration_results: list[PluginMigrationResult],
        seed_results: list[PluginSeedResult],
        hook_result: PluginHookResult | None,
        extra_payload: Mapping[str, object] | None = None,
    ) -> PluginLifecyclePayloadDict:
        """
        构建插件安装或升级成功负载。

        :param plugin_id: 插件ID
        :param message: 成功提示
        :param actions: 动作清单
        :param precheck: 插件操作预检上下文
        :param plugin: 插件数据库模型
        :param installed_configs: 已安装配置列表
        :param migration_results: migration 执行结果列表
        :param seed_results: seed 执行结果列表
        :param hook_result: 生命周期钩子执行结果
        :param extra_payload: 额外负载
        :return: 插件安装或升级成功负载
        """
        return PluginLifecycleSuccessPayload(
            plugin_id=plugin_id,
            message=message,
            actions=actions,
            precheck=precheck,
            plugin=plugin,
            installed_configs=installed_configs,
            migration_results=migration_results,
            seed_results=seed_results,
            hook_result=hook_result,
            extra_payload=extra_payload,
        ).to_payload()
