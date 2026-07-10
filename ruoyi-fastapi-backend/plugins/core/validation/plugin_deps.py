from dataclasses import dataclass
from typing import Literal

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.schema import PluginDependencyManifest, PluginManifest
from plugins.core.state import PluginStateResolver
from plugins.core.types import PluginStateRecord
from plugins.core.validation.dependencies import DependencyRequirementParser, ParsedDependency
from plugins.core.validation.versioning import PluginVersionConstraintMatcher

PluginDependencyStatus = Literal[
    'satisfied',
    'missing',
    'not_installed',
    'disabled',
    'version_unsatisfied',
    'cycle',
    'dependent',
]
PluginBatchOperation = Literal['install', 'enable', 'upgrade', 'uninstall', 'purge']
PluginDependencyPlanBlockerStatus = Literal[
    'missing',
    'not_installed',
    'disabled',
    'version_unsatisfied',
    'source_version_unsatisfied',
    'cycle',
    'unknown_operation',
]


class PluginDependencyVersionMatcher:
    """
    插件依赖版本匹配器。

    使用 Matcher 模式将插件依赖声明中的版本约束转换为统一版本匹配逻辑，
    避免检查器和计划构建器分别解析约束。
    """

    @staticmethod
    def is_satisfied(installed_version: str | None, version_constraint: str | None) -> bool:
        """
        判断插件版本是否满足约束。

        :param installed_version: 已安装或源码版本
        :param version_constraint: 版本约束
        :return: 是否满足
        """
        if not version_constraint:
            return True
        parsed_dependency = PluginDependencyVersionMatcher._parse_constraint(version_constraint)
        return PluginVersionConstraintMatcher.is_satisfied(
            installed_version,
            parsed_dependency.operator,
            parsed_dependency.version,
        )

    @staticmethod
    def _parse_constraint(version_constraint: str) -> ParsedDependency:
        """
        解析插件版本约束。

        :param version_constraint: 版本约束
        :return: 已解析依赖声明
        """
        normalized_constraint = version_constraint.strip()
        if normalized_constraint.startswith(('>=', '<=', '==', '!=', '>', '<', '=', '^', '~')):
            return DependencyRequirementParser.parse(f'plugin{normalized_constraint}')

        parsed_dependency = DependencyRequirementParser.parse(f'plugin=={normalized_constraint}')
        return parsed_dependency


@dataclass(frozen=True)
class PluginDependencyCheckItem:
    """
    插件间依赖检查项。
    """

    plugin_id: str
    dependency_id: str
    required_version: str | None
    installed_version: str | None
    status: PluginDependencyStatus
    message: str

    @property
    def ok(self) -> bool:
        """
        判断插件依赖检查项是否通过。

        :return: 是否通过
        """
        return self.status == 'satisfied'


@dataclass(frozen=True)
class PluginDependencyCheckResult:
    """
    插件间依赖检查结果。
    """

    plugin_id: str
    items: list[PluginDependencyCheckItem]

    @property
    def ok(self) -> bool:
        """
        判断插件间依赖是否整体通过。

        :return: 是否通过
        """
        return all(item.ok for item in self.items)

    @property
    def failed_items(self) -> list[PluginDependencyCheckItem]:
        """
        获取失败的插件依赖检查项。

        :return: 失败检查项列表
        """
        return [item for item in self.items if not item.ok]


@dataclass(frozen=True)
class PluginDependencyPlanBlocker:
    """
    插件批量操作计划阻塞项。
    """

    plugin_id: str
    dependency_id: str
    status: PluginDependencyPlanBlockerStatus
    message: str


@dataclass(frozen=True)
class PluginDependencyPlanItem:
    """
    插件批量操作计划项。
    """

    plugin_id: str
    name: str
    version: str
    operation: PluginBatchOperation
    order: int
    requested: bool
    dependencies: list[str]
    installed_version: str | None
    enabled: str | None
    status: str | None
    blockers: list[PluginDependencyPlanBlocker]

    @property
    def ready(self) -> bool:
        """
        判断当前计划项是否可执行。

        :return: 是否可执行
        """
        return not self.blockers


@dataclass(frozen=True)
class PluginDependencyPlan:
    """
    插件批量操作拓扑计划。
    """

    operation: PluginBatchOperation
    requested_plugin_ids: list[str]
    ordered_plugin_ids: list[str]
    items: list[PluginDependencyPlanItem]
    blockers: list[PluginDependencyPlanBlocker]

    @property
    def ok(self) -> bool:
        """
        判断插件批量操作计划是否可执行。

        :return: 是否可执行
        """
        return not self.blockers


class PluginDependencyChecker:
    """
    插件间依赖检查器。

    使用 Checker 模式校验插件之间的存在性、安装状态、启用状态、版本约束和循环依赖。
    """

    def __init__(
        self,
        discovered_plugins: list[DiscoveredPlugin],
        database_plugins: list[PluginStateRecord] | None = None,
    ) -> None:
        """
        初始化插件间依赖检查器。

        :param discovered_plugins: 已发现插件列表
        :param database_plugins: 数据库插件状态列表
        :return: None
        """
        self.discovered_plugin_map = {plugin.manifest.id: plugin for plugin in discovered_plugins}
        self.database_plugin_map = {plugin.plugin_id: plugin for plugin in database_plugins or []}

    def check_manifest(self, manifest: PluginManifest) -> PluginDependencyCheckResult:
        """
        检查单个插件清单的插件间依赖。

        :param manifest: 插件清单
        :return: 插件间依赖检查结果
        """
        items = [self._check_dependency(manifest.id, dependency) for dependency in manifest.dependencies.plugins]
        items.extend(self._check_cycles(manifest.id))

        return PluginDependencyCheckResult(plugin_id=manifest.id, items=items)

    def check_enabled_dependents(self, plugin_id: str) -> PluginDependencyCheckResult:
        """
        检查指定插件是否仍被已启用插件依赖。

        :param plugin_id: 被停用或卸载的插件ID
        :return: 被依赖方检查结果
        """
        target_plugin = self.discovered_plugin_map.get(plugin_id)
        target_database_plugin = self.database_plugin_map.get(plugin_id)
        installed_version = self._resolve_installed_version(target_plugin, target_database_plugin)
        items: list[PluginDependencyCheckItem] = []
        for dependent_id, dependency in PluginDependencyGraph(self.discovered_plugin_map).find_direct_dependents(
            plugin_id
        ):
            database_plugin = self.database_plugin_map.get(dependent_id)
            if not getattr(database_plugin, 'installed_version', None):
                continue
            if not PluginStateResolver.is_database_plugin_enabled(database_plugin):
                continue
            items.append(
                PluginDependencyCheckItem(
                    plugin_id=dependent_id,
                    dependency_id=plugin_id,
                    required_version=dependency.version,
                    installed_version=installed_version,
                    status='dependent',
                    message=f'插件正在被已启用插件依赖：{dependent_id} -> {plugin_id}',
                )
            )

        return PluginDependencyCheckResult(plugin_id=plugin_id, items=items)

    def _check_dependency(
        self,
        plugin_id: str,
        dependency: PluginDependencyManifest,
    ) -> PluginDependencyCheckItem:
        """
        检查单条插件依赖。

        :param plugin_id: 当前插件ID
        :param dependency: 插件依赖声明
        :return: 插件依赖检查项
        """
        discovered_plugin = self.discovered_plugin_map.get(dependency.id)
        database_plugin = self.database_plugin_map.get(dependency.id)
        installed_version = self._resolve_installed_version(discovered_plugin, database_plugin)
        if not discovered_plugin:
            return self._build_item(plugin_id, dependency, None, 'missing', f'依赖插件不存在：{dependency.id}')
        if not database_plugin or not getattr(database_plugin, 'installed_version', None):
            return self._build_item(
                plugin_id,
                dependency,
                installed_version,
                'not_installed',
                f'依赖插件未安装：{dependency.id}',
            )
        if not PluginStateResolver.is_database_plugin_enabled(database_plugin):
            return self._build_item(
                plugin_id,
                dependency,
                installed_version,
                'disabled',
                f'依赖插件未启用：{dependency.id}',
            )
        if not PluginDependencyVersionMatcher.is_satisfied(installed_version, dependency.version):
            return self._build_item(
                plugin_id,
                dependency,
                installed_version,
                'version_unsatisfied',
                f'依赖插件版本不满足：{dependency.id} installed={installed_version} required={dependency.version}',
            )

        return self._build_item(
            plugin_id,
            dependency,
            installed_version,
            'satisfied',
            f'依赖插件已满足：{dependency.id}',
        )

    def _check_cycles(self, plugin_id: str) -> list[PluginDependencyCheckItem]:
        """
        检查从当前插件出发的循环依赖。

        :param plugin_id: 当前插件ID
        :return: 循环依赖检查项列表
        """
        cycle_path = PluginDependencyGraph(self.discovered_plugin_map).find_cycle_from(plugin_id)
        if not cycle_path:
            return []

        cycle_text = ' -> '.join(cycle_path)
        return [
            PluginDependencyCheckItem(
                plugin_id=plugin_id,
                dependency_id=cycle_path[-1],
                required_version=None,
                installed_version=None,
                status='cycle',
                message=f'插件依赖存在循环：{cycle_text}',
            )
        ]

    @staticmethod
    def _resolve_installed_version(
        discovered_plugin: DiscoveredPlugin | None,
        database_plugin: PluginStateRecord | None,
    ) -> str | None:
        """
        解析依赖插件已安装版本。

        :param discovered_plugin: 已发现插件
        :param database_plugin: 数据库插件状态
        :return: 已安装版本
        """
        installed_version = getattr(database_plugin, 'installed_version', None)
        if installed_version:
            return installed_version
        return discovered_plugin.manifest.version if discovered_plugin else None

    @staticmethod
    def _build_item(
        plugin_id: str,
        dependency: PluginDependencyManifest,
        installed_version: str | None,
        status: PluginDependencyStatus,
        message: str,
    ) -> PluginDependencyCheckItem:
        """
        构建插件依赖检查项。

        :param plugin_id: 当前插件ID
        :param dependency: 插件依赖声明
        :param installed_version: 已安装版本
        :param status: 检查状态
        :param message: 检查消息
        :return: 插件依赖检查项
        """
        return PluginDependencyCheckItem(
            plugin_id=plugin_id,
            dependency_id=dependency.id,
            required_version=dependency.version,
            installed_version=installed_version,
            status=status,
            message=message,
        )


class PluginDependencyGraph:
    """
    插件依赖图。

    使用 Graph 模式为插件间依赖提供循环检测，并为后续拓扑排序保留扩展点。
    """

    def __init__(self, discovered_plugin_map: dict[str, DiscoveredPlugin]) -> None:
        """
        初始化插件依赖图。

        :param discovered_plugin_map: 已发现插件映射
        :return: None
        """
        self.discovered_plugin_map = discovered_plugin_map

    def find_cycle_from(self, plugin_id: str) -> list[str]:
        """
        查找从指定插件出发的循环依赖路径。

        :param plugin_id: 插件ID
        :return: 循环依赖路径，不存在时返回空列表
        """
        return self._find_cycle(plugin_id, [], set())

    def find_direct_dependents(self, plugin_id: str) -> list[tuple[str, PluginDependencyManifest]]:
        """
        查找直接依赖指定插件的插件。

        :param plugin_id: 被依赖插件ID
        :return: 依赖方插件ID和依赖声明列表
        """
        return [
            (dependent_id, dependency)
            for dependent_id, discovered_plugin in sorted(self.discovered_plugin_map.items())
            for dependency in discovered_plugin.manifest.dependencies.plugins
            if dependency.id == plugin_id
        ]

    def _find_cycle(self, plugin_id: str, path: list[str], visited: set[str]) -> list[str]:
        """
        深度优先查找循环依赖。

        :param plugin_id: 当前插件ID
        :param path: 当前访问路径
        :param visited: 已访问插件ID集合
        :return: 循环依赖路径
        """
        if plugin_id in path:
            cycle_start = path.index(plugin_id)
            return [*path[cycle_start:], plugin_id]
        if plugin_id in visited:
            return []
        visited.add(plugin_id)

        discovered_plugin = self.discovered_plugin_map.get(plugin_id)
        if not discovered_plugin:
            return []
        for dependency in discovered_plugin.manifest.dependencies.plugins:
            cycle_path = self._find_cycle(dependency.id, [*path, plugin_id], visited)
            if cycle_path:
                return cycle_path

        return []


class PluginDependencyPlanBuilder:
    """
    插件批量操作拓扑计划生成器。

    使用 Planner 模式为批量安装、启用和升级生成依赖优先的执行顺序，并输出阻塞原因。
    """

    def __init__(
        self,
        discovered_plugins: list[DiscoveredPlugin],
        database_plugins: list[PluginStateRecord] | None = None,
    ) -> None:
        """
        初始化插件批量操作拓扑计划生成器。

        :param discovered_plugins: 已发现插件列表
        :param database_plugins: 数据库插件状态列表
        :return: None
        """
        self.discovered_plugin_map = {plugin.manifest.id: plugin for plugin in discovered_plugins}
        self.database_plugin_map = {plugin.plugin_id: plugin for plugin in database_plugins or []}

    def build_plan(
        self,
        operation: PluginBatchOperation,
        plugin_ids: list[str] | None = None,
    ) -> PluginDependencyPlan:
        """
        构建插件批量操作拓扑计划。

        :param operation: 批量操作类型
        :param plugin_ids: 指定插件ID列表，不传时计划全部已发现插件
        :return: 插件批量操作拓扑计划
        """
        requested_plugin_ids = plugin_ids or sorted(self.discovered_plugin_map)
        closure, closure_blockers = self._collect_dependency_closure(requested_plugin_ids)
        ordered_plugin_ids, topology_blockers = self._sort_dependency_first(closure)
        blockers_by_plugin = self._group_blockers([*closure_blockers, *topology_blockers])
        items = [
            self._build_plan_item(
                plugin_id,
                order,
                operation,
                requested=plugin_id in requested_plugin_ids,
                existing_blockers=blockers_by_plugin.get(plugin_id, []),
            )
            for order, plugin_id in enumerate(ordered_plugin_ids, start=1)
        ]
        all_blockers = [*closure_blockers, *topology_blockers]
        for item in items:
            all_blockers.extend(item.blockers)
        all_blockers = self._deduplicate_blockers(all_blockers)

        return PluginDependencyPlan(
            operation=operation,
            requested_plugin_ids=requested_plugin_ids,
            ordered_plugin_ids=ordered_plugin_ids,
            items=items,
            blockers=all_blockers,
        )

    def _collect_dependency_closure(
        self,
        plugin_ids: list[str],
    ) -> tuple[set[str], list[PluginDependencyPlanBlocker]]:
        """
        收集目标插件及其递归依赖闭包。

        :param plugin_ids: 目标插件ID列表
        :return: 插件依赖闭包和阻塞项列表
        """
        closure: set[str] = set()
        blockers: list[PluginDependencyPlanBlocker] = []
        visiting: list[str] = []

        def visit(plugin_id: str, requested_by: str) -> None:
            if plugin_id in visiting:
                blockers.extend(self._build_cycle_blockers([*visiting[visiting.index(plugin_id) :], plugin_id]))
                return
            discovered_plugin = self.discovered_plugin_map.get(plugin_id)
            if not discovered_plugin:
                blockers.append(
                    PluginDependencyPlanBlocker(
                        plugin_id=requested_by,
                        dependency_id=plugin_id,
                        status='missing',
                        message=f'依赖插件不存在：{plugin_id}',
                    )
                )
                return
            if plugin_id in closure:
                return
            visiting.append(plugin_id)
            closure.add(plugin_id)
            for dependency in discovered_plugin.manifest.dependencies.plugins:
                visit(dependency.id, plugin_id)
            visiting.pop()

        for plugin_id in plugin_ids:
            visit(plugin_id, plugin_id)

        return closure, blockers

    def _sort_dependency_first(
        self,
        plugin_ids: set[str],
    ) -> tuple[list[str], list[PluginDependencyPlanBlocker]]:
        """
        对插件依赖闭包执行依赖优先拓扑排序。

        :param plugin_ids: 插件ID集合
        :return: 排序后的插件ID列表和阻塞项列表
        """
        ordered_plugin_ids: list[str] = []
        blockers: list[PluginDependencyPlanBlocker] = []
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(plugin_id: str) -> None:
            if plugin_id in visited:
                return
            if plugin_id in visiting:
                cycle_path = [*visiting[visiting.index(plugin_id) :], plugin_id]
                blockers.extend(self._build_cycle_blockers(cycle_path))
                return

            discovered_plugin = self.discovered_plugin_map.get(plugin_id)
            if not discovered_plugin:
                return
            visiting.append(plugin_id)
            for dependency in discovered_plugin.manifest.dependencies.plugins:
                if dependency.id in plugin_ids:
                    visit(dependency.id)
            visiting.pop()
            visited.add(plugin_id)
            ordered_plugin_ids.append(plugin_id)

        for plugin_id in sorted(plugin_ids):
            visit(plugin_id)

        return ordered_plugin_ids, blockers

    @staticmethod
    def _build_cycle_blockers(cycle_path: list[str]) -> list[PluginDependencyPlanBlocker]:
        """
        构建循环依赖阻塞项。

        :param cycle_path: 循环依赖路径
        :return: 循环依赖阻塞项列表
        """
        cycle_text = ' -> '.join(cycle_path)
        return [
            PluginDependencyPlanBlocker(
                plugin_id=plugin_id,
                dependency_id=cycle_path[-1],
                status='cycle',
                message=f'插件依赖存在循环：{cycle_text}',
            )
            for plugin_id in set(cycle_path)
        ]

    def _build_plan_item(
        self,
        plugin_id: str,
        order: int,
        operation: PluginBatchOperation,
        *,
        requested: bool,
        existing_blockers: list[PluginDependencyPlanBlocker],
    ) -> PluginDependencyPlanItem:
        """
        构建单个插件批量操作计划项。

        :param plugin_id: 插件ID
        :param order: 执行顺序
        :param operation: 批量操作类型
        :param requested: 是否为用户显式指定插件
        :param existing_blockers: 已收集的阻塞项
        :return: 插件批量操作计划项
        """
        discovered_plugin = self.discovered_plugin_map[plugin_id]
        database_plugin = self.database_plugin_map.get(plugin_id)
        blockers = [
            *existing_blockers,
            *self._build_dependency_blockers(discovered_plugin.manifest, operation),
        ]
        return PluginDependencyPlanItem(
            plugin_id=plugin_id,
            name=discovered_plugin.manifest.name,
            version=discovered_plugin.manifest.version,
            operation=operation,
            order=order,
            requested=requested,
            dependencies=[dependency.id for dependency in discovered_plugin.manifest.dependencies.plugins],
            installed_version=getattr(database_plugin, 'installed_version', None),
            enabled=getattr(database_plugin, 'enabled', None),
            status=getattr(database_plugin, 'status', None),
            blockers=blockers,
        )

    def _build_dependency_blockers(
        self,
        manifest: PluginManifest,
        operation: PluginBatchOperation,
    ) -> list[PluginDependencyPlanBlocker]:
        """
        根据操作类型构建插件依赖阻塞项。

        :param manifest: 插件清单
        :param operation: 批量操作类型
        :return: 插件依赖阻塞项列表
        """
        blockers = []
        for dependency in manifest.dependencies.plugins:
            blockers.extend(self._build_single_dependency_blocker(manifest, dependency, operation))

        return blockers

    def _build_single_dependency_blocker(
        self,
        manifest: PluginManifest,
        dependency: PluginDependencyManifest,
        operation: PluginBatchOperation,
    ) -> list[PluginDependencyPlanBlocker]:
        """
        检查单个依赖的阻塞项。

        :param manifest: 插件清单
        :param dependency: 插件依赖声明
        :param operation: 批量操作类型
        :return: 依赖阻塞项列表
        """
        discovered_dependency = self.discovered_plugin_map.get(dependency.id)
        if not discovered_dependency:
            return []

        database_dependency = self.database_plugin_map.get(dependency.id)
        source_version = discovered_dependency.manifest.version
        installed_version = getattr(database_dependency, 'installed_version', None)

        if not PluginDependencyVersionMatcher.is_satisfied(source_version, dependency.version):
            return [
                self._build_blocker(
                    manifest.id,
                    dependency.id,
                    'source_version_unsatisfied',
                    f'依赖插件源码版本不满足：{dependency.id} source={source_version} required={dependency.version}',
                )
            ]

        if operation == 'install':
            if database_dependency and not PluginStateResolver.is_database_plugin_enabled(database_dependency):
                return [
                    self._build_blocker(
                        manifest.id,
                        dependency.id,
                        'disabled',
                        f'依赖插件未启用：{dependency.id}',
                    )
                ]
            return []

        if not database_dependency or not installed_version:
            return [
                self._build_blocker(
                    manifest.id,
                    dependency.id,
                    'not_installed',
                    f'依赖插件未安装：{dependency.id}',
                )
            ]

        if operation == 'enable' and not PluginDependencyVersionMatcher.is_satisfied(
            installed_version,
            dependency.version,
        ):
            return [
                self._build_blocker(
                    manifest.id,
                    dependency.id,
                    'version_unsatisfied',
                    (
                        f'依赖插件版本不满足：{dependency.id} '
                        f'installed={installed_version} required={dependency.version}'
                    ),
                )
            ]

        if operation == 'upgrade' and not PluginStateResolver.is_database_plugin_enabled(database_dependency):
            return [
                self._build_blocker(
                    manifest.id,
                    dependency.id,
                    'disabled',
                    f'依赖插件未启用：{dependency.id}',
                )
            ]

        return []

    @staticmethod
    def _build_blocker(
        plugin_id: str,
        dependency_id: str,
        status: PluginDependencyPlanBlockerStatus,
        message: str,
    ) -> PluginDependencyPlanBlocker:
        """
        构建插件批量操作计划阻塞项。

        :param plugin_id: 插件ID
        :param dependency_id: 依赖插件ID
        :param status: 阻塞状态
        :param message: 阻塞说明
        :return: 插件批量操作计划阻塞项
        """
        return PluginDependencyPlanBlocker(
            plugin_id=plugin_id,
            dependency_id=dependency_id,
            status=status,
            message=message,
        )

    @staticmethod
    def _group_blockers(
        blockers: list[PluginDependencyPlanBlocker],
    ) -> dict[str, list[PluginDependencyPlanBlocker]]:
        """
        按插件 ID 分组阻塞项。

        :param blockers: 阻塞项列表
        :return: 阻塞项分组
        """
        blocker_map: dict[str, list[PluginDependencyPlanBlocker]] = {}
        for blocker in blockers:
            blocker_map.setdefault(blocker.plugin_id, []).append(blocker)

        return blocker_map

    @staticmethod
    def _deduplicate_blockers(
        blockers: list[PluginDependencyPlanBlocker],
    ) -> list[PluginDependencyPlanBlocker]:
        """
        去重插件批量操作计划阻塞项。

        :param blockers: 阻塞项列表
        :return: 去重后的阻塞项列表
        """
        blocker_map = {
            (blocker.plugin_id, blocker.dependency_id, blocker.status, blocker.message): blocker for blocker in blockers
        }

        return list(blocker_map.values())
