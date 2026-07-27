import json
import re
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Literal

from packaging.requirements import InvalidRequirement

from plugins.core.environment import PLUGIN_RUNTIME_ENVIRONMENT
from plugins.core.manifest.schema import PluginManifest
from plugins.core.validation.python_requirements import PythonRequirementParser
from plugins.core.validation.versioning import PluginVersionComparator, PluginVersionConstraintMatcher

DependencyKind = Literal['python', 'npm', 'npmDev']
DependencyStatus = Literal['checked', 'skipped']
DEPENDENCY_PATTERN = re.compile(r'^\s*([A-Za-z0-9_.@/\-]+)\s*([<>=!~^]{1,2})?\s*([A-Za-z0-9_.+\-!*]+)?\s*$')
PYTHON_PACKAGE_SEPARATOR_PATTERN = re.compile(r'[-_.]+')
PLUGIN_STARTUP_DEPENDENCY_ERROR_PREFIX = '插件启动依赖检查失败：'


@dataclass(frozen=True)
class DependencyCheckItem:
    """
    单条依赖检查结果。
    """

    kind: DependencyKind
    requirement: str
    name: str
    installed: bool
    version_satisfied: bool
    installed_version: str | None
    required_version: str | None
    message: str
    status: DependencyStatus = 'checked'
    declared_version: str | None = None

    @property
    def ok(self) -> bool:
        """
        判断依赖检查是否通过。

        :return: 是否通过
        """
        return self.status == 'skipped' or (self.installed and self.version_satisfied)


@dataclass(frozen=True)
class DependencyCheckResult:
    """
    插件依赖检查结果。
    """

    plugin_id: str
    items: list[DependencyCheckItem]

    @property
    def ok(self) -> bool:
        """
        判断插件依赖检查是否整体通过。

        :return: 是否通过
        """
        return all(item.ok for item in self.items)

    @property
    def missing_items(self) -> list[DependencyCheckItem]:
        """
        获取缺失依赖列表。

        :return: 缺失依赖列表
        """
        return [item for item in self.items if item.status != 'skipped' and not item.installed]

    @property
    def unsatisfied_items(self) -> list[DependencyCheckItem]:
        """
        获取版本不满足依赖列表。

        :return: 版本不满足依赖列表
        """
        return [
            item for item in self.items if item.status != 'skipped' and item.installed and not item.version_satisfied
        ]


@dataclass(frozen=True)
class DependencyInstallPlanItem:
    """
    依赖安装计划项。
    """

    kind: DependencyKind
    requirement: str
    name: str
    command: list[str]
    workdir: str
    reason: str


@dataclass(frozen=True)
class DependencyInstallPlan:
    """
    插件依赖安装计划。
    """

    plugin_id: str
    items: list[DependencyInstallPlanItem]

    @property
    def has_actions(self) -> bool:
        """
        判断安装计划是否包含待执行动作。

        :return: 是否包含待执行动作
        """
        return bool(self.items)


@dataclass(frozen=True)
class ParsedDependency:
    """
    已解析依赖声明。
    """

    name: str
    operator: str | None
    version: str | None

    @property
    def required_version(self) -> str | None:
        """
        获取完整版本约束。

        :return: 完整版本约束
        """
        if not self.operator or not self.version:
            return None
        return f'{self.operator}{self.version}'


class DependencyRequirementParser:
    """
    依赖声明解析器。

    使用 Strategy 模式为 Python 与 npm 提供共享的轻量依赖声明解析能力。

    注意：该解析器基于正则，不支持 PEP 508 的逗号范围（``openai>=2,<3``）和 marker。
    Python 依赖请使用 :class:`PythonRequirementParser`。
    """

    @classmethod
    def parse(cls, requirement: str) -> ParsedDependency:
        """
        解析依赖声明。

        :param requirement: 依赖声明
        :return: 已解析依赖声明
        """
        matched_requirement = DEPENDENCY_PATTERN.match(requirement)
        if not matched_requirement:
            return ParsedDependency(name=requirement.strip(), operator=None, version=None)
        name, operator, version = matched_requirement.groups()

        return ParsedDependency(name=name, operator=operator, version=version)


class VersionConstraintMatcher:
    """
    版本约束匹配器。
    """

    @classmethod
    def is_satisfied(cls, installed_version: str | None, parsed_dependency: ParsedDependency) -> bool:
        """
        判断已安装版本是否满足依赖声明。

        :param installed_version: 已安装版本
        :param parsed_dependency: 已解析依赖声明
        :return: 是否满足
        """
        if not installed_version:
            return False
        if not parsed_dependency.operator or not parsed_dependency.version:
            return True
        if parsed_dependency.operator in {'^', '~'}:
            return PluginVersionConstraintMatcher.match_compatible(
                installed_version,
                parsed_dependency.version,
                parsed_dependency.operator,
            )

        comparison = PluginVersionConstraintMatcher.is_satisfied(
            installed_version,
            parsed_dependency.operator,
            parsed_dependency.version,
        )
        if not comparison and not cls._can_compare(installed_version, parsed_dependency.version):
            return cls._match_text_version(installed_version, parsed_dependency)

        return comparison

    @staticmethod
    def _match_text_version(installed_version: str, parsed_dependency: ParsedDependency) -> bool:
        """
        匹配非纯数字版本声明。

        :param installed_version: 已安装版本
        :param parsed_dependency: 已解析依赖声明
        :return: 是否满足
        """
        if parsed_dependency.operator in {'==', '='}:
            return installed_version == parsed_dependency.version
        if parsed_dependency.operator == '!=':
            return installed_version != parsed_dependency.version

        return True

    @staticmethod
    def _can_compare(installed_version: str, required_version: str) -> bool:
        """
        判断两个版本是否可按插件版本规则比较。

        :param installed_version: 已安装版本
        :param required_version: 约束版本
        :return: 是否可比较
        """
        return PluginVersionComparator.compare(installed_version, required_version) is not None


class PythonDependencyInspector:
    """
    Python 依赖检查器。
    """

    def __init__(self, installed_packages: dict[str, str] | None = None) -> None:
        """
        初始化 Python 依赖检查器。

        :param installed_packages: 已安装 Python 包版本映射
        """
        self._installed_packages_overridden = installed_packages is not None
        self.installed_packages = (
            self._normalize_installed_packages(installed_packages)
            if installed_packages is not None
            else self._load_installed_packages()
        )

    def refresh(self) -> None:
        """
        刷新当前 Python 环境的已安装包快照。

        显式传入 ``installed_packages`` 的检查器保持固定快照，便于测试和离线检查；
        从运行环境创建的检查器会重新读取 distribution 元数据。

        :return: None
        """
        if self._installed_packages_overridden:
            return
        self.installed_packages = self._load_installed_packages()

    def check(self, requirements: list[str]) -> list[DependencyCheckItem]:
        """
        检查 Python 依赖声明。

        :param requirements: Python 依赖声明列表
        :return: 依赖检查结果列表
        """
        return [self._check_requirement(requirement) for requirement in requirements]

    def _check_requirement(self, requirement: str) -> DependencyCheckItem:
        """
        检查单条 Python 依赖声明。

        含 marker 的声明先评估 marker，不适用当前环境时返回 ``status='skipped'``，
        避免合法的条件依赖阻断插件启动。

        :param requirement: Python 依赖声明
        :return: 依赖检查结果
        """
        try:
            parsed = PythonRequirementParser.parse(requirement)
        except InvalidRequirement as exc:
            return DependencyCheckItem(
                kind='python',
                requirement=requirement,
                name=requirement.strip(),
                installed=False,
                version_satisfied=False,
                installed_version=None,
                required_version=None,
                message=f'Python 依赖声明无效：{requirement}，{exc}',
            )
        if not parsed.is_marker_applicable():
            return DependencyCheckItem(
                kind='python',
                requirement=requirement,
                name=parsed.name,
                installed=False,
                version_satisfied=True,
                installed_version=None,
                required_version=parsed.required_version,
                message=f'Python 依赖 marker 不适用当前环境，已跳过：{parsed.name}',
                status='skipped',
            )

        installed_version = self.installed_packages.get(self._normalize_package_name(parsed.name))
        installed = installed_version is not None
        version_satisfied = parsed.is_version_satisfied(installed_version)
        message = self._build_message(
            parsed.name,
            installed,
            version_satisfied,
            installed_version,
            parsed.required_version,
        )

        return DependencyCheckItem(
            kind='python',
            requirement=requirement,
            name=parsed.name,
            installed=installed,
            version_satisfied=version_satisfied,
            installed_version=installed_version,
            required_version=parsed.required_version,
            message=message,
        )

    @staticmethod
    def _load_installed_packages() -> dict[str, str]:
        """
        读取当前 Python 环境已安装包版本。

        :return: 已安装包版本映射
        """
        return {
            PythonDependencyInspector._normalize_package_name(distribution.metadata['Name']): distribution.version
            for distribution in metadata.distributions()
        }

    @classmethod
    def _normalize_installed_packages(cls, installed_packages: dict[str, str]) -> dict[str, str]:
        """
        归一化已安装 Python 包名称映射。

        :param installed_packages: 已安装 Python 包版本映射
        :return: 归一化包名后的版本映射
        """
        return {cls._normalize_package_name(name): version for name, version in installed_packages.items()}

    @staticmethod
    def _normalize_package_name(name: str) -> str:
        """
        按 PEP 503 规则归一化 Python distribution 名称。

        :param name: Python 包名
        :return: 归一化包名
        """
        return PYTHON_PACKAGE_SEPARATOR_PATTERN.sub('-', name).lower()

    @staticmethod
    def _build_message(
        name: str,
        installed: bool,
        version_satisfied: bool,
        installed_version: str | None,
        required_version: str | None,
    ) -> str:
        """
        构建 Python 依赖检查消息。

        :param name: 包名
        :param installed: 是否已安装
        :param version_satisfied: 版本是否满足
        :param installed_version: 已安装版本
        :param required_version: 版本约束
        :return: 检查消息
        """
        if not installed:
            return f'Python 依赖未安装：{name}'
        if not version_satisfied:
            return f'Python 依赖版本不满足：{name} installed={installed_version} required={required_version}'
        return f'Python 依赖已满足：{name}'


class NpmDependencyInspector:
    """
    npm 依赖检查器。
    """

    def __init__(
        self, frontend_root: Path | str | None = None, installed_packages: dict[str, str] | None = None
    ) -> None:
        """
        初始化 npm 依赖检查器。

        :param frontend_root: 前端项目根目录
        :param installed_packages: 已声明 npm 包版本映射
        """
        self.frontend_root = (
            Path(frontend_root) if frontend_root else Path(PLUGIN_RUNTIME_ENVIRONMENT.get_frontend_dir())
        )
        self.installed_packages = (
            installed_packages if installed_packages is not None else self._load_installed_packages()
        )

    def check(self, requirements: list[str], *, dev: bool = False) -> list[DependencyCheckItem]:
        """
        检查 npm 依赖声明。

        :param requirements: npm 依赖声明列表
        :param dev: 是否为 npm 开发依赖
        :return: 依赖检查结果列表
        """
        return [self._check_requirement(requirement, dev=dev) for requirement in requirements]

    def skip(self, requirements: list[str], *, dev: bool = False) -> list[DependencyCheckItem]:
        """
        跳过 npm 依赖实际检查。

        :param requirements: npm 依赖声明列表
        :param dev: 是否为 npm 开发依赖
        :return: 跳过检查结果列表
        """
        return [self._skip_requirement(requirement, dev=dev) for requirement in requirements]

    def _skip_requirement(self, requirement: str, *, dev: bool = False) -> DependencyCheckItem:
        """
        构建单条 npm 依赖跳过结果。

        :param requirement: npm 依赖声明
        :param dev: 是否为 npm 开发依赖
        :return: 依赖跳过结果
        """
        parsed_dependency = DependencyRequirementParser.parse(requirement)
        return DependencyCheckItem(
            kind='npmDev' if dev else 'npm',
            requirement=requirement,
            name=parsed_dependency.name,
            installed=False,
            version_satisfied=True,
            installed_version=None,
            required_version=parsed_dependency.required_version,
            message='当前为已构建前端环境，前端依赖需在构建前安装。',
            status='skipped',
        )

    def _check_requirement(self, requirement: str, *, dev: bool = False) -> DependencyCheckItem:
        """
        检查单条 npm 依赖声明。

        :param requirement: npm 依赖声明
        :param dev: 是否为 npm 开发依赖
        :return: 依赖检查结果
        """
        parsed_dependency = DependencyRequirementParser.parse(requirement)
        installed_version = self.installed_packages.get(parsed_dependency.name)
        version_satisfied = VersionConstraintMatcher.is_satisfied(
            self._normalize_npm_version(installed_version), parsed_dependency
        )
        installed = installed_version is not None

        return DependencyCheckItem(
            kind='npmDev' if dev else 'npm',
            requirement=requirement,
            name=parsed_dependency.name,
            installed=installed,
            version_satisfied=version_satisfied,
            installed_version=installed_version,
            required_version=parsed_dependency.required_version,
            message=self._build_message(parsed_dependency, installed, version_satisfied, installed_version),
            declared_version=installed_version,
        )

    def _load_installed_packages(self) -> dict[str, str]:
        """
        读取前端 package.json 中声明的 npm 包版本。

        :return: npm 包版本映射
        """
        package_json_path = self.frontend_root / 'package.json'
        if not package_json_path.is_file():
            return {}
        package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
        dependencies = package_json.get('dependencies', {})
        dev_dependencies = package_json.get('devDependencies', {})

        return {**dependencies, **dev_dependencies}

    @staticmethod
    def _normalize_npm_version(version: str | None) -> str | None:
        """
        归一化 package.json 中的 npm 版本声明。

        :param version: npm 版本声明
        :return: 归一化版本
        """
        if not version:
            return None
        return version.lstrip('^~>=<')

    @staticmethod
    def _build_message(
        parsed_dependency: ParsedDependency,
        installed: bool,
        version_satisfied: bool,
        installed_version: str | None,
    ) -> str:
        """
        构建 npm 依赖检查消息。

        :param parsed_dependency: 已解析依赖声明
        :param installed: 是否已声明
        :param version_satisfied: 版本是否满足
        :param installed_version: 已声明版本
        :return: 检查消息
        """
        if not installed:
            return f'npm 依赖未声明：{parsed_dependency.name}'
        if not version_satisfied:
            return f'npm 依赖版本不满足：{parsed_dependency.name} declared={installed_version} required={parsed_dependency.required_version}'
        return f'npm 依赖已满足：{parsed_dependency.name}'


class PluginDependencyChecker:
    """
    插件依赖检查器。
    """

    def __init__(
        self,
        python_inspector: PythonDependencyInspector | None = None,
        npm_inspector: NpmDependencyInspector | None = None,
        frontend_mode: Literal['dev', 'built'] = 'dev',
    ) -> None:
        """
        初始化插件依赖检查器。

        :param python_inspector: Python 依赖检查器
        :param npm_inspector: npm 依赖检查器
        """
        self.python_inspector = python_inspector or PythonDependencyInspector()
        self.npm_inspector = npm_inspector or NpmDependencyInspector()
        self.frontend_mode = frontend_mode

    def check_manifest(self, manifest: PluginManifest) -> DependencyCheckResult:
        """
        检查插件清单依赖。

        :param manifest: 插件清单
        :return: 插件依赖检查结果
        """
        items = []
        items.extend(self.python_inspector.check(manifest.dependencies.python))
        if self.frontend_mode == 'built':
            items.extend(self.npm_inspector.skip(manifest.dependencies.npm))
            items.extend(self.npm_inspector.skip(manifest.dependencies.npm_dev, dev=True))
        else:
            items.extend(self.npm_inspector.check(manifest.dependencies.npm))
            items.extend(self.npm_inspector.check(manifest.dependencies.npm_dev, dev=True))

        return DependencyCheckResult(plugin_id=manifest.id, items=items)


class PluginDependencyInstallPlanner:
    """
    插件依赖安装计划生成器。

    使用 Planner 模式将依赖检查结果转换为可审计、可 dry-run 的安装计划。
    """

    def __init__(self, python_executable: str | None = None, frontend_root: Path | str | None = None) -> None:
        """
        初始化插件依赖安装计划生成器。

        :param python_executable: Python 可执行文件路径
        :param frontend_root: 前端工程根目录
        """
        self.python_executable = python_executable or sys.executable
        self.frontend_root = (
            Path(frontend_root) if frontend_root else Path(PLUGIN_RUNTIME_ENVIRONMENT.get_frontend_dir())
        )

    def build_plan(self, dependency_result: DependencyCheckResult) -> DependencyInstallPlan:
        """
        构建依赖安装计划。

        :param dependency_result: 依赖检查结果
        :return: 依赖安装计划
        """
        items = [
            self._build_plan_item(item)
            for item in dependency_result.items
            if item.status != 'skipped' and (not item.installed or not item.version_satisfied)
        ]

        return DependencyInstallPlan(plugin_id=dependency_result.plugin_id, items=items)

    def _build_plan_item(self, item: DependencyCheckItem) -> DependencyInstallPlanItem:
        """
        构建单个依赖安装计划项。

        :param item: 依赖检查项
        :return: 依赖安装计划项
        """
        if item.kind == 'python':
            return DependencyInstallPlanItem(
                kind=item.kind,
                requirement=item.requirement,
                name=item.name,
                command=[self.python_executable, '-m', 'pip', 'install', item.requirement],
                workdir=str(Path.cwd()),
                reason=item.message,
            )

        command = ['npm', 'install', self._build_npm_install_target(item)]
        if item.kind == 'npmDev':
            command.insert(2, '--save-dev')

        return DependencyInstallPlanItem(
            kind=item.kind,
            requirement=item.requirement,
            name=item.name,
            command=command,
            workdir=str(self.frontend_root),
            reason=item.message,
        )

    @staticmethod
    def _build_npm_install_target(item: DependencyCheckItem) -> str:
        """
        构建 npm install 目标声明。

        :param item: 依赖检查项
        :return: npm install 目标
        """
        parsed_dependency = DependencyRequirementParser.parse(item.requirement)
        if not parsed_dependency.operator or not parsed_dependency.version:
            return parsed_dependency.name
        if parsed_dependency.operator in {'==', '='}:
            return f'{parsed_dependency.name}@{parsed_dependency.version}'

        return f'{parsed_dependency.name}@{parsed_dependency.required_version}'
