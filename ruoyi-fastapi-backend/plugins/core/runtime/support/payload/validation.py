from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeAlias

from pydantic import Field

from plugins.core.validation.result import PluginValidationLevelResolver, ValidationLevel

from .base import PluginPayloadModel

if TYPE_CHECKING:
    from collections.abc import Mapping

    from plugins.core.validation.dependencies import DependencyCheckItem, DependencyCheckResult
    from plugins.core.validation.menus import PluginMenuConflictItem
    from plugins.core.validation.plugin_deps import PluginDependencyCheckItem
    from plugins.core.validation.result import PluginValidationIssue
    from plugins.core.validation.structure import PluginStructureCheckItem


class DependencyItemPayload(PluginPayloadModel):
    """
    Python/npm 依赖检查项 payload。
    """

    kind: str
    requirement: str
    name: str
    installed: bool
    version_satisfied: bool = Field(alias='versionSatisfied')
    installed_version: str | None = Field(alias='installedVersion')
    declared_version: str | None = Field(default=None, alias='declaredVersion')
    required_version: str | None = Field(alias='requiredVersion')
    ok: bool
    status: str
    level: ValidationLevel
    message: str


class PluginDependencyItemPayload(PluginPayloadModel):
    """
    插件间依赖检查项 payload。
    """

    plugin_id: str = Field(alias='pluginId')
    dependency_id: str = Field(alias='dependencyId')
    required_version: str | None = Field(alias='requiredVersion')
    installed_version: str | None = Field(alias='installedVersion')
    status: str
    ok: bool
    level: ValidationLevel
    message: str


class ValidationIssuePayload(PluginPayloadModel):
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


class StructureItemPayload(PluginPayloadModel):
    """
    插件结构检查项 payload。
    """

    kind: str
    path: str
    ok: bool
    level: ValidationLevel
    message: str
    suggestion: str


class MenuConflictItemPayload(PluginPayloadModel):
    """
    菜单冲突检查项 payload。
    """

    kind: str
    plugin_id: str = Field(alias='pluginId')
    conflict_plugin_id: str | None = Field(alias='conflictPluginId')
    value: str
    ok: bool
    level: ValidationLevel
    message: str


class PluginDependencyCheckPayload(PluginPayloadModel):
    """
    插件依赖检查 payload。
    """

    ok: bool
    message: str
    plugin_id: str = Field(alias='pluginId')
    dependency_ok: bool = Field(alias='dependencyOk')
    dependencies: list[dict[str, object]]
    missing_dependencies: list[str] = Field(alias='missingDependencies')
    unsatisfied_dependencies: list[str] = Field(alias='unsatisfiedDependencies')


class PluginCheckItemPayload(PluginPayloadModel):
    """
    插件检查单项 payload。
    """

    plugin_id: str = Field(alias='pluginId')
    ok: bool
    manifest_ok: bool | None = Field(default=None, alias='manifestOk')
    dependency_ok: bool | None = Field(default=None, alias='dependencyOk')
    plugin_dependency_ok: bool | None = Field(default=None, alias='pluginDependencyOk')
    structure_ok: bool | None = Field(default=None, alias='structureOk')
    menu_conflict_ok: bool | None = Field(default=None, alias='menuConflictOk')
    dependencies: list[dict[str, object]] | None = None
    plugin_dependencies: list[dict[str, object]] | None = Field(default=None, alias='pluginDependencies')
    plugin_dependency_errors: list[dict[str, object]] | None = Field(default=None, alias='pluginDependencyErrors')
    manifest_issues: list[dict[str, object]] | None = Field(default=None, alias='manifestIssues')
    manifest_warnings: list[dict[str, object]] | None = Field(default=None, alias='manifestWarnings')
    structure: list[dict[str, object]] | None = None
    missing_dependencies: list[str] | None = Field(default=None, alias='missingDependencies')
    unsatisfied_dependencies: list[str] | None = Field(default=None, alias='unsatisfiedDependencies')
    structure_errors: list[dict[str, object]] | None = Field(default=None, alias='structureErrors')
    menu_conflicts: list[dict[str, object]] | None = Field(default=None, alias='menuConflicts')


class PluginCheckPayload(PluginPayloadModel):
    """
    插件检查聚合 payload。
    """

    ok: bool
    message: str
    count: int
    database_available: bool = Field(alias='databaseAvailable')
    database_error: str | None = Field(alias='databaseError')
    checks: list[dict[str, object]]


DependencyItemPayloadDict: TypeAlias = dict[str, object]
PluginDependencyItemPayloadDict: TypeAlias = dict[str, object]
ValidationIssuePayloadDict: TypeAlias = dict[str, object]
StructureItemPayloadDict: TypeAlias = dict[str, object]
MenuConflictItemPayloadDict: TypeAlias = dict[str, object]
PluginDependencyCheckPayloadDict: TypeAlias = dict[str, object]
PluginCheckItemPayloadDict: TypeAlias = dict[str, object]
PluginCheckPayloadDict: TypeAlias = dict[str, object]


class PluginValidationPayloadBuilderProtocol(Protocol):
    """
    插件校验 payload builder 协议。
    """

    @staticmethod
    def build_dependency_item(item: DependencyCheckItem) -> DependencyItemPayloadDict:
        """
        构建依赖检查项负载。
        """
        ...

    @staticmethod
    def build_plugin_dependency_item(item: PluginDependencyCheckItem) -> PluginDependencyItemPayloadDict:
        """
        构建插件间依赖检查项负载。
        """
        ...

    @staticmethod
    def build_validation_issue(item: PluginValidationIssue) -> ValidationIssuePayloadDict:
        """
        构建统一校验问题项负载。
        """
        ...

    @staticmethod
    def build_structure_item(item: PluginStructureCheckItem) -> StructureItemPayloadDict:
        """
        构建结构检查项负载。
        """
        ...

    @staticmethod
    def build_menu_conflict_item(item: PluginMenuConflictItem) -> MenuConflictItemPayloadDict:
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


class PluginValidationPayloadMixin:
    """
    插件依赖、结构、manifest 和菜单冲突检查结果负载构建能力。
    """

    @staticmethod
    def build_dependency_item(item: DependencyCheckItem) -> DependencyItemPayloadDict:
        """
        构建依赖检查项负载。

        :param item: 依赖检查项
        :return: 依赖检查项负载
        """
        return DependencyItemPayload(
            kind=item.kind,
            requirement=item.requirement,
            name=item.name,
            installed=item.installed,
            version_satisfied=item.version_satisfied,
            installed_version=item.installed_version,
            declared_version=item.declared_version,
            required_version=item.required_version,
            ok=item.ok,
            status=item.status,
            level=PluginValidationLevelResolver.from_ok(item.ok),
            message=item.message,
        ).to_payload()

    @staticmethod
    def build_plugin_dependency_item(item: PluginDependencyCheckItem) -> PluginDependencyItemPayloadDict:
        """
        构建插件间依赖检查项负载。

        :param item: 插件间依赖检查项
        :return: 插件间依赖检查项负载
        """
        return PluginDependencyItemPayload(
            plugin_id=item.plugin_id,
            dependency_id=item.dependency_id,
            required_version=item.required_version,
            installed_version=item.installed_version,
            status=item.status,
            ok=item.ok,
            level=PluginValidationLevelResolver.from_ok(item.ok),
            message=item.message,
        ).to_payload()

    @staticmethod
    def build_validation_issue(item: PluginValidationIssue) -> ValidationIssuePayloadDict:
        """
        构建统一校验问题项负载。

        :param item: 统一校验问题项
        :return: 统一校验问题项负载
        """
        return ValidationIssuePayload(
            level=item.level,
            category=item.category,
            kind=item.kind,
            path=item.path,
            ok=item.ok,
            message=item.message,
            suggestion=item.suggestion,
        ).to_payload()

    @staticmethod
    def build_structure_item(item: PluginStructureCheckItem) -> StructureItemPayloadDict:
        """
        构建结构检查项负载。

        :param item: 结构检查项
        :return: 结构检查项负载
        """
        return StructureItemPayload(
            kind=item.kind,
            path=item.path,
            ok=item.ok,
            level=item.level,
            message=item.message,
            suggestion=item.suggestion,
        ).to_payload()

    @staticmethod
    def build_menu_conflict_item(item: PluginMenuConflictItem) -> MenuConflictItemPayloadDict:
        """
        构建菜单冲突检查项负载。

        :param item: 菜单冲突检查项
        :return: 菜单冲突检查项负载
        """
        return MenuConflictItemPayload(
            kind=item.kind,
            plugin_id=item.plugin_id,
            conflict_plugin_id=item.conflict_plugin_id,
            value=item.value,
            ok=False,
            level='error',
            message=item.message,
        ).to_payload()

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
        return PluginDependencyCheckPayload(
            ok=dependency_result.ok,
            message='插件依赖已满足' if dependency_result.ok else '插件依赖存在问题',
            plugin_id=plugin_id,
            dependency_ok=dependency_result.ok,
            dependencies=[cls.build_dependency_item(item) for item in dependency_result.items],
            missing_dependencies=[item.name for item in dependency_result.missing_items],
            unsatisfied_dependencies=[item.name for item in dependency_result.unsatisfied_items],
        ).to_payload()

    @staticmethod
    def build_check_item(plugin_id: str, precheck: PluginCheckPrecheckProtocol) -> PluginCheckItemPayloadDict:
        """
        构建插件检查单项负载。

        :param plugin_id: 插件ID
        :param precheck: 插件操作预检上下文
        :return: 插件检查单项负载
        """
        return PluginCheckItemPayload.model_validate(
            {
                'pluginId': plugin_id,
                'ok': precheck.ok,
                **precheck.check_payload,
            }
        ).to_payload(exclude_none=True)

    @staticmethod
    def build_check_payload(
        checks: list[PluginCheckItemPayloadDict],
        database_error: str | None = None,
    ) -> PluginCheckPayloadDict:
        """
        构建插件检查聚合负载。

        :param checks: 插件检查单项负载列表
        :param database_error: 数据库状态读取错误
        :return: 插件检查聚合负载
        """
        ok = all(check['ok'] for check in checks)
        return PluginCheckPayload(
            ok=ok,
            message='插件检查通过' if ok else '插件检查存在问题',
            count=len(checks),
            database_available=database_error is None,
            database_error=database_error,
            checks=checks,
        ).to_payload()
