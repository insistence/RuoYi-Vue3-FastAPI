from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict

from plugins.core.runtime.exit_codes import DEPENDENCY_ERROR, SUCCESS
from plugins.core.validation.result import PluginValidationLevelResolver, ValidationLevel

if TYPE_CHECKING:
    from collections.abc import Mapping

    from plugins.core.validation.dependencies import DependencyCheckItem, DependencyCheckResult
    from plugins.core.validation.menus import PluginMenuConflictItem
    from plugins.core.validation.plugin_deps import PluginDependencyCheckItem
    from plugins.core.validation.result import PluginValidationIssue
    from plugins.core.validation.structure import PluginStructureCheckItem


class DependencyItemPayload(TypedDict):
    """
    Python/npm 依赖检查项 payload。
    """

    kind: str
    requirement: str
    name: str
    installed: bool
    versionSatisfied: bool
    installedVersion: str | None
    requiredVersion: str | None
    ok: bool
    status: str
    level: ValidationLevel
    message: str


class PluginDependencyItemPayload(TypedDict):
    """
    插件间依赖检查项 payload。
    """

    pluginId: str
    dependencyId: str
    requiredVersion: str | None
    installedVersion: str | None
    status: str
    ok: bool
    level: ValidationLevel
    message: str


class ValidationIssuePayload(TypedDict):
    """
    manifest 校验问题项 payload。
    """

    level: ValidationLevel
    category: str
    kind: str
    path: str
    ok: bool
    message: str
    suggestion: str


class StructureItemPayload(TypedDict):
    """
    插件结构检查项 payload。
    """

    kind: str
    path: str
    ok: bool
    level: ValidationLevel
    message: str
    suggestion: str


class MenuConflictItemPayload(TypedDict):
    """
    菜单冲突检查项 payload。
    """

    kind: str
    pluginId: str
    conflictPluginId: str | None
    value: str
    ok: bool
    level: ValidationLevel
    message: str


class PluginDependencyCheckPayloadDict(TypedDict):
    """
    插件依赖检查 payload。
    """

    ok: bool
    message: str
    pluginId: str
    dependencyOk: bool
    dependencies: list[DependencyItemPayload]
    missingDependencies: list[str]
    unsatisfiedDependencies: list[str]
    exit_code: int


class PluginCheckItemPayloadDict(TypedDict, total=False):
    """
    插件检查单项 payload。
    """

    pluginId: str
    ok: bool
    manifestOk: bool
    dependencyOk: bool
    pluginDependencyOk: bool
    structureOk: bool
    menuConflictOk: bool
    dependencies: list[DependencyItemPayload]
    pluginDependencies: list[PluginDependencyItemPayload]
    pluginDependencyErrors: list[PluginDependencyItemPayload]
    manifestIssues: list[ValidationIssuePayload]
    manifestWarnings: list[ValidationIssuePayload]
    structure: list[StructureItemPayload]
    missingDependencies: list[str]
    unsatisfiedDependencies: list[str]
    structureErrors: list[StructureItemPayload]
    menuConflicts: list[MenuConflictItemPayload]


class PluginCheckPayloadDict(TypedDict):
    """
    插件检查聚合 payload。
    """

    ok: bool
    message: str
    count: int
    checks: list[PluginCheckItemPayloadDict]
    exit_code: int


class PluginValidationPayloadBuilderProtocol(Protocol):
    """
    插件校验 payload builder 协议。
    """

    @staticmethod
    def build_dependency_item(item: DependencyCheckItem) -> DependencyItemPayload:
        """
        构建依赖检查项负载。
        """
        ...

    @staticmethod
    def build_plugin_dependency_item(item: PluginDependencyCheckItem) -> PluginDependencyItemPayload:
        """
        构建插件间依赖检查项负载。
        """
        ...

    @staticmethod
    def build_validation_issue(item: PluginValidationIssue) -> ValidationIssuePayload:
        """
        构建统一校验问题项负载。
        """
        ...

    @staticmethod
    def build_structure_item(item: PluginStructureCheckItem) -> StructureItemPayload:
        """
        构建结构检查项负载。
        """
        ...

    @staticmethod
    def build_menu_conflict_item(item: PluginMenuConflictItem) -> MenuConflictItemPayload:
        """
        构建菜单冲突检查项负载。
        """
        ...


class PluginCheckPrecheckProtocol(Protocol):
    """
    插件检查单项所需的预检上下文协议。
    """

    ok: bool

    @property
    def check_payload(self) -> Mapping[str, object]:
        """
        获取插件检查命令通用负载片段。
        """
        ...


@dataclass(frozen=True)
class PluginDependencyCheckPayload:
    """
    插件依赖检查结构化负载。
    """

    plugin_id: str
    dependency_result: DependencyCheckResult
    builder: type[PluginValidationPayloadBuilderProtocol] | None = None

    def to_payload(self) -> PluginDependencyCheckPayloadDict:
        """
        序列化为现有插件依赖检查 payload 契约。

        :return: 插件依赖检查 payload
        """
        builder = self.builder or PluginValidationPayloadMixin
        return {
            'ok': self.dependency_result.ok,
            'message': '插件依赖已满足' if self.dependency_result.ok else '插件依赖存在问题',
            'pluginId': self.plugin_id,
            'dependencyOk': self.dependency_result.ok,
            'dependencies': [builder.build_dependency_item(item) for item in self.dependency_result.items],
            'missingDependencies': [item.name for item in self.dependency_result.missing_items],
            'unsatisfiedDependencies': [item.name for item in self.dependency_result.unsatisfied_items],
            'exit_code': SUCCESS if self.dependency_result.ok else DEPENDENCY_ERROR,
        }


@dataclass(frozen=True)
class PluginCheckItemPayload:
    """
    插件检查单项结构化负载。
    """

    plugin_id: str
    precheck: PluginCheckPrecheckProtocol

    def to_payload(self) -> PluginCheckItemPayloadDict:
        """
        序列化为现有插件检查单项 payload 契约。

        :return: 插件检查单项 payload
        """
        return {
            'pluginId': self.plugin_id,
            'ok': self.precheck.ok,
            **self.precheck.check_payload,
        }


@dataclass(frozen=True)
class PluginCheckPayload:
    """
    插件检查聚合结构化负载。
    """

    checks: list[PluginCheckItemPayloadDict]

    def to_payload(self) -> PluginCheckPayloadDict:
        """
        序列化为现有插件检查聚合 payload 契约。

        :return: 插件检查聚合 payload
        """
        ok = all(check['ok'] for check in self.checks)
        return {
            'ok': ok,
            'message': '插件检查通过' if ok else '插件检查存在问题',
            'count': len(self.checks),
            'checks': self.checks,
            'exit_code': SUCCESS if ok else DEPENDENCY_ERROR,
        }


class PluginValidationPayloadMixin:
    """
    插件依赖、结构、manifest 和菜单冲突检查结果负载构建能力。
    """

    @staticmethod
    def build_dependency_item(item: DependencyCheckItem) -> DependencyItemPayload:
        """
        构建依赖检查项负载。

        :param item: 依赖检查项
        :return: 依赖检查项负载
        """
        return {
            'kind': item.kind,
            'requirement': item.requirement,
            'name': item.name,
            'installed': item.installed,
            'versionSatisfied': item.version_satisfied,
            'installedVersion': item.installed_version,
            'requiredVersion': item.required_version,
            'ok': item.ok,
            'status': item.status,
            'level': PluginValidationLevelResolver.from_ok(item.ok),
            'message': item.message,
        }

    @staticmethod
    def build_plugin_dependency_item(item: PluginDependencyCheckItem) -> PluginDependencyItemPayload:
        """
        构建插件间依赖检查项负载。

        :param item: 插件间依赖检查项
        :return: 插件间依赖检查项负载
        """
        return {
            'pluginId': item.plugin_id,
            'dependencyId': item.dependency_id,
            'requiredVersion': item.required_version,
            'installedVersion': item.installed_version,
            'status': item.status,
            'ok': item.ok,
            'level': PluginValidationLevelResolver.from_ok(item.ok),
            'message': item.message,
        }

    @staticmethod
    def build_validation_issue(item: PluginValidationIssue) -> ValidationIssuePayload:
        """
        构建统一校验问题项负载。

        :param item: 统一校验问题项
        :return: 统一校验问题项负载
        """
        return {
            'level': item.level,
            'category': item.category,
            'kind': item.kind,
            'path': item.path,
            'ok': item.ok,
            'message': item.message,
            'suggestion': item.suggestion,
        }

    @staticmethod
    def build_structure_item(item: PluginStructureCheckItem) -> StructureItemPayload:
        """
        构建结构检查项负载。

        :param item: 结构检查项
        :return: 结构检查项负载
        """
        return {
            'kind': item.kind,
            'path': item.path,
            'ok': item.ok,
            'level': item.level,
            'message': item.message,
            'suggestion': item.suggestion,
        }

    @staticmethod
    def build_menu_conflict_item(item: PluginMenuConflictItem) -> MenuConflictItemPayload:
        """
        构建菜单冲突检查项负载。

        :param item: 菜单冲突检查项
        :return: 菜单冲突检查项负载
        """
        return {
            'kind': item.kind,
            'pluginId': item.plugin_id,
            'conflictPluginId': item.conflict_plugin_id,
            'value': item.value,
            'ok': False,
            'level': 'error',
            'message': item.message,
        }

    @classmethod
    def build_dependency_check_payload(
        cls,
        plugin_id: str,
        dependency_result: DependencyCheckResult,
    ) -> PluginDependencyCheckPayloadDict:
        """
        构建插件依赖检查负载。

        :param plugin_id: 插件ID
        :param dependency_result: 依赖检查结果
        :return: 插件依赖检查负载
        """
        return PluginDependencyCheckPayload(plugin_id, dependency_result, builder=cls).to_payload()

    @staticmethod
    def build_check_item(plugin_id: str, precheck: PluginCheckPrecheckProtocol) -> PluginCheckItemPayloadDict:
        """
        构建插件检查单项负载。

        :param plugin_id: 插件ID
        :param precheck: 插件操作预检上下文
        :return: 插件检查单项负载
        """
        return PluginCheckItemPayload(plugin_id, precheck).to_payload()

    @staticmethod
    def build_check_payload(checks: list[PluginCheckItemPayloadDict]) -> PluginCheckPayloadDict:
        """
        构建插件检查聚合负载。

        :param checks: 插件检查单项负载列表
        :return: 插件检查聚合负载
        """
        return PluginCheckPayload(checks).to_payload()
