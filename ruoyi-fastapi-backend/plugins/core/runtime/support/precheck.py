from dataclasses import dataclass
from typing import Any

from plugins.core.validation.dependencies import DependencyCheckResult
from plugins.core.validation.plugin_deps import PluginDependencyCheckResult

from .payload import PluginPayloadBuilder


@dataclass(frozen=True)
class PluginPrecheckContext:
    """
    插件操作预检上下文。

    使用 Context Object 模式聚合依赖、manifest、插件间依赖、结构和菜单冲突检查结果，
    避免插件运行时在安装、升级和检查流程中重复拼装 payload。

    :param dependency_result: Python/npm 依赖检查结果
    :param manifest_result: manifest 非阻断检查结果
    :param plugin_dependency_result: 插件间依赖检查结果
    :param structure_result: 插件结构检查结果
    :param menu_conflict_result: 菜单冲突检查结果
    :param manifest_issues: manifest error 负载
    :param manifest_warnings: manifest warning 负载
    :param plugin_dependency_errors: 插件依赖错误负载
    :param structure_errors: 结构错误负载
    :param menu_conflicts: 菜单冲突负载
    :param dependencies: Python/npm 依赖检查负载
    :param plugin_dependencies: 插件依赖检查负载
    :param structure: 结构检查完整负载
    :param missing_dependencies: 缺失依赖名称列表
    :param unsatisfied_dependencies: 版本不满足依赖名称列表
    """

    dependency_result: DependencyCheckResult
    manifest_result: Any
    plugin_dependency_result: PluginDependencyCheckResult
    structure_result: Any
    menu_conflict_result: Any
    manifest_issues: list[dict[str, Any]]
    manifest_warnings: list[dict[str, Any]]
    plugin_dependency_errors: list[dict[str, Any]]
    structure_errors: list[dict[str, Any]]
    menu_conflicts: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    plugin_dependencies: list[dict[str, Any]]
    structure: list[dict[str, Any]]
    missing_dependencies: list[str]
    unsatisfied_dependencies: list[str]

    @classmethod
    def build(
        cls,
        dependency_result: DependencyCheckResult,
        manifest_result: Any,
        plugin_dependency_result: PluginDependencyCheckResult,
        structure_result: Any,
        menu_conflict_result: Any,
    ) -> 'PluginPrecheckContext':
        """
        从各类检查结果构建预检上下文。

        :param dependency_result: Python/npm 依赖检查结果
        :param manifest_result: manifest 非阻断检查结果
        :param plugin_dependency_result: 插件间依赖检查结果
        :param structure_result: 插件结构检查结果
        :param menu_conflict_result: 菜单冲突检查结果
        :return: 插件操作预检上下文
        """
        return cls(
            dependency_result=dependency_result,
            manifest_result=manifest_result,
            plugin_dependency_result=plugin_dependency_result,
            structure_result=structure_result,
            menu_conflict_result=menu_conflict_result,
            manifest_issues=[PluginPayloadBuilder.build_validation_issue(item) for item in manifest_result.issues],
            manifest_warnings=[
                PluginPayloadBuilder.build_validation_issue(item) for item in manifest_result.warning_issues
            ],
            plugin_dependency_errors=[
                PluginPayloadBuilder.build_plugin_dependency_item(item)
                for item in plugin_dependency_result.failed_items
            ],
            structure_errors=[
                PluginPayloadBuilder.build_structure_item(item) for item in structure_result.failed_items
            ],
            menu_conflicts=[PluginPayloadBuilder.build_menu_conflict_item(item) for item in menu_conflict_result.items],
            dependencies=[PluginPayloadBuilder.build_dependency_item(item) for item in dependency_result.items],
            plugin_dependencies=[
                PluginPayloadBuilder.build_plugin_dependency_item(item) for item in plugin_dependency_result.items
            ],
            structure=[PluginPayloadBuilder.build_structure_item(item) for item in structure_result.items],
            missing_dependencies=[item.name for item in dependency_result.missing_items],
            unsatisfied_dependencies=[item.name for item in dependency_result.unsatisfied_items],
        )

    @property
    def ok(self) -> bool:
        """
        判断阻断性预检是否全部通过。

        :return: 阻断性预检是否全部通过
        """
        return (
            self.dependency_result.ok
            and self.manifest_result.ok
            and self.plugin_dependency_result.ok
            and self.structure_result.ok
            and self.menu_conflict_result.ok
        )

    @property
    def operation_payload(self) -> dict[str, Any]:
        """
        构建安装和升级操作通用负载片段。

        :return: 安装和升级操作通用负载片段
        """
        return {
            'manifestOk': self.manifest_result.ok,
            'dependencyOk': self.dependency_result.ok,
            'pluginDependencyOk': self.plugin_dependency_result.ok,
            'structureOk': self.structure_result.ok,
            'menuConflictOk': self.menu_conflict_result.ok,
            'manifestIssues': self.manifest_issues,
            'manifestWarnings': self.manifest_warnings,
            'pluginDependencyErrors': self.plugin_dependency_errors,
            'structureErrors': self.structure_errors,
            'menuConflicts': self.menu_conflicts,
            'dependencies': self.dependencies,
            'pluginDependencies': self.plugin_dependencies,
        }

    @property
    def check_payload(self) -> dict[str, Any]:
        """
        构建插件检查命令通用负载片段。

        :return: 插件检查命令通用负载片段
        """
        return {
            'manifestOk': self.manifest_result.ok,
            'dependencyOk': self.dependency_result.ok,
            'pluginDependencyOk': self.plugin_dependency_result.ok,
            'structureOk': self.structure_result.ok,
            'menuConflictOk': self.menu_conflict_result.ok,
            'dependencies': self.dependencies,
            'pluginDependencies': self.plugin_dependencies,
            'pluginDependencyErrors': self.plugin_dependency_errors,
            'manifestIssues': self.manifest_issues,
            'manifestWarnings': self.manifest_warnings,
            'structure': self.structure,
            'missingDependencies': self.missing_dependencies,
            'unsatisfiedDependencies': self.unsatisfied_dependencies,
            'structureErrors': self.structure_errors,
            'menuConflicts': self.menu_conflicts,
        }
