import json
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from config.env import DataBaseConfig
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.manifest.menu_tree import PluginMenuTree
from plugins.core.manifest.schema import PluginManifest
from plugins.core.validation.dependencies import DependencyRequirementParser
from plugins.core.validation.python_requirements import PythonRequirementParser
from plugins.core.validation.result import PluginValidationIssue
from plugins.core.validation.versioning import PluginVersionConstraintMatcher

COMPATIBILITY_CONSTRAINT_PATTERN = re.compile(r'^\s*([<>=!~^]{1,2})?\s*([A-Za-z0-9_.+\-!*]+)\s*$')
UNRESOLVED_NODE_VERSION = object()


@dataclass(frozen=True)
class PluginManifestCheckResult:
    """
    插件 manifest 非阻断检查结果。

    :param plugin_id: 插件 ID
    :param issues: manifest 检查问题项列表
    """

    plugin_id: str
    issues: list[PluginValidationIssue]

    @property
    def ok(self) -> bool:
        """
        判断 manifest 检查是否存在阻断错误。

        :return: 是否不存在 error 级问题
        """
        return not self.error_issues

    @property
    def error_issues(self) -> list[PluginValidationIssue]:
        """
        获取 error 级问题项。

        :return: error 级问题项列表
        """
        return [issue for issue in self.issues if issue.level == 'error']

    @property
    def warning_issues(self) -> list[PluginValidationIssue]:
        """
        获取 warning 级问题项。

        :return: warning 级问题项列表
        """
        return [issue for issue in self.issues if issue.level == 'warning']


class PluginManifestChecker:
    """
    插件 manifest 非阻断检查器。

    使用 Checker 模式承载不适合放入 Pydantic 强校验的提示类规则。
    """

    _node_version_cache: ClassVar[object | str | None] = UNRESOLVED_NODE_VERSION

    def __init__(
        self,
        *,
        backend_root: Path | None = None,
        frontend_root: Path | None = None,
        python_version: str | None = None,
        node_version: str | None = None,
    ) -> None:
        """
        初始化插件 manifest 非阻断检查器。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端项目根目录
        :param python_version: 当前 Python 版本
        :param node_version: 当前 Node.js 版本
        :return: None
        """
        self.backend_root = backend_root or Path(__file__).resolve().parents[3]
        self.frontend_root = frontend_root or Path(
            PluginRuntimeEnvironmentService(backend_root=self.backend_root).get_frontend_dir()
        )
        self.python_version = python_version or platform.python_version()
        self.node_version = node_version

    def check(self, manifest: PluginManifest) -> PluginManifestCheckResult:
        """
        检查插件 manifest 提示类问题。

        :param manifest: 插件 manifest
        :return: manifest 检查结果
        """
        issues = []
        issues.extend(self._check_secret_config_defaults(manifest))
        issues.extend(self._check_secret_config_type_alignment(manifest))
        issues.extend(self._check_unpinned_dependencies(manifest))
        issues.extend(self._check_resources_without_purge_hook(manifest))
        issues.extend(self._check_required_config_without_default(manifest))
        issues.extend(self._check_ineffective_config_constraints(manifest))
        issues.extend(self._check_permissions_without_plugin_prefix(manifest))
        issues.extend(self._check_frontend_menus_without_permissions(manifest))
        issues.extend(self._check_button_menus_without_permission(manifest))
        issues.extend(self._check_button_menu_structure(manifest))
        issues.extend(self._check_permission_button_parent(manifest))
        issues.extend(self._check_lifecycle_script_order(manifest))
        issues.extend(self._check_enabled_jobs_without_health_checker(manifest))
        issues.extend(self._check_unpaired_runtime_hooks(manifest))
        issues.extend(self._check_compatibility(manifest))

        return PluginManifestCheckResult(plugin_id=manifest.id, issues=issues)

    def _check_secret_config_defaults(self, manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查敏感配置默认值声明。

        :param manifest: 插件 manifest
        :return: 敏感配置默认值问题项列表
        """
        issues = []
        for config_item in manifest.config.items:
            if not config_item.secret or config_item.default in (None, ''):
                continue
            issues.append(
                PluginValidationIssue(
                    level='warning',
                    category='manifest',
                    kind='secret_config_default',
                    path=f'config.items.{config_item.key}.default',
                    message=f'敏感配置 {config_item.key} 声明了非空默认值',
                    suggestion='建议删除默认值，改为安装后在插件配置中录入',
                    ok=True,
                )
            )

        return issues

    @staticmethod
    def _check_secret_config_type_alignment(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查敏感配置类型和 secret 标记是否一致。

        :param manifest: 插件 manifest
        :return: 敏感配置类型一致性问题项列表
        """
        issues = []
        for config_item in manifest.config.items:
            if config_item.type == 'password' and not config_item.secret:
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='password_config_without_secret',
                        path=f'config.items.{config_item.key}.secret',
                        message=f'密码配置 {config_item.key} 未声明 secret=true',
                        suggestion='建议为 password 类型配置显式声明 secret=true，避免配置展示和导出时泄露敏感值',
                        ok=True,
                    )
                )
            if config_item.secret and config_item.type != 'password':
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='secret_config_non_password_type',
                        path=f'config.items.{config_item.key}.type',
                        message=f'敏感配置 {config_item.key} 的类型不是 password',
                        suggestion='建议将敏感配置类型设置为 password，便于前端输入控件、导出和审计统一脱敏处理',
                        ok=True,
                    )
                )

        return issues

    def _check_unpinned_dependencies(self, manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查未声明版本约束的依赖。

        :param manifest: 插件 manifest
        :return: 未声明版本约束问题项列表
        """
        issues = []
        for dependency_kind, requirements in (
            ('python', manifest.dependencies.python),
            ('npm', manifest.dependencies.npm),
            ('npmDev', manifest.dependencies.npm_dev),
        ):
            for index, requirement in enumerate(requirements):
                if dependency_kind == 'python':
                    parsed_python = PythonRequirementParser.parse(requirement)
                    name = parsed_python.name
                    has_version_constraint = bool(parsed_python.required_version)
                else:
                    parsed_requirement = DependencyRequirementParser.parse(requirement)
                    name = parsed_requirement.name
                    has_version_constraint = bool(parsed_requirement.required_version)
                if has_version_constraint:
                    continue
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='dependency_unpinned',
                        path=f'dependencies.{dependency_kind}.{index}',
                        message=f'{dependency_kind} 依赖 {name} 未声明版本约束',
                        suggestion='建议为插件依赖声明最小版本或兼容版本范围，降低环境漂移风险',
                        ok=True,
                    )
                )
        for dependency in manifest.dependencies.plugins:
            if dependency.version:
                continue
            issues.append(
                PluginValidationIssue(
                    level='warning',
                    category='manifest',
                    kind='plugin_dependency_unpinned',
                    path=f'dependencies.plugins.{dependency.id}.version',
                    message=f'插件依赖 {dependency.id} 未声明版本约束',
                    suggestion='建议声明依赖插件的最小版本或兼容版本范围',
                    ok=True,
                )
            )

        return issues

    @staticmethod
    def _check_resources_without_purge_hook(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查资源声明是否缺少物理清理钩子。

        :param manifest: 插件 manifest
        :return: 资源清理提示问题项列表
        """
        resources = manifest.resources
        resource_count = len(resources.static) + len(resources.uploads) + len(resources.temp)
        if resource_count == 0 or manifest.backend.hooks.on_purge:
            return []

        return [
            PluginValidationIssue(
                level='warning',
                category='manifest',
                kind='resources_without_purge_hook',
                path='resources',
                message='插件声明了资源清单，但未声明 onPurge 清理钩子',
                suggestion='如资源需要随插件物理清理，请通过 backend.hooks.onPurge 显式实现清理逻辑',
                ok=True,
            )
        ]

    @staticmethod
    def _check_required_config_without_default(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查必填配置是否缺少默认值。

        :param manifest: 插件 manifest
        :return: 必填配置默认值提示问题项列表
        """
        issues = []
        for config_item in manifest.config.items:
            if not config_item.required or config_item.default not in (None, ''):
                continue
            issues.append(
                PluginValidationIssue(
                    level='warning',
                    category='manifest',
                    kind='required_config_without_default',
                    path=f'config.items.{config_item.key}.default',
                    message=f'必填配置 {config_item.key} 未声明默认值',
                    suggestion='建议提供安全默认值，或在插件 README 中明确安装后必须配置该项',
                    ok=True,
                )
            )

        return issues

    @staticmethod
    def _check_ineffective_config_constraints(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查配置项声明了当前类型不会生效的增强约束。

        :param manifest: 插件 manifest
        :return: 无效配置增强约束问题项列表
        """
        issues = []
        for config_item in manifest.config.items:
            if config_item.type != 'number' and (
                config_item.min_value is not None or config_item.max_value is not None
            ):
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='ineffective_config_constraint',
                        path=f'config.items.{config_item.key}.min/max',
                        message=f'配置 {config_item.key} 不是 number 类型，min/max 约束不会生效',
                        suggestion='仅 number 类型配置支持 min/max；请删除该约束或将配置类型改为 number',
                        ok=True,
                    )
                )
            if config_item.type not in {'string', 'textarea', 'password'} and config_item.pattern:
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='ineffective_config_constraint',
                        path=f'config.items.{config_item.key}.pattern',
                        message=f'配置 {config_item.key} 不是文本类型，pattern 约束不会生效',
                        suggestion='仅 string、textarea、password 类型配置支持 pattern；请删除该约束或调整配置类型',
                        ok=True,
                    )
                )
            if config_item.type != 'select' and config_item.options:
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='ineffective_config_constraint',
                        path=f'config.items.{config_item.key}.options',
                        message=f'配置 {config_item.key} 不是 select 类型，options 声明不会生效',
                        suggestion='仅 select 类型配置支持 options；请删除 options 或将配置类型改为 select',
                        ok=True,
                    )
                )

        return issues

    @staticmethod
    def _check_permissions_without_plugin_prefix(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查权限标识是否使用插件 ID 前缀。

        :param manifest: 插件 manifest
        :return: 权限前缀提示问题项列表
        """
        expected_prefix = f'{manifest.id}:'
        permission_set = set(manifest.permission_codes) | PluginMenuTree.collect_permissions(manifest.frontend.menus)
        declared_permissions = {
            permission for permission in permission_set if not permission.startswith(expected_prefix)
        }
        return [
            PluginValidationIssue(
                level='warning',
                category='manifest',
                kind='permission_without_plugin_prefix',
                path=f'permissions.{permission}',
                message=f'权限标识 {permission} 未使用插件 ID 前缀',
                suggestion=f'建议使用 {expected_prefix}<resource>:<action> 格式，降低与平台或其他插件权限冲突的风险',
                ok=True,
            )
            for permission in sorted(declared_permissions)
        ]

    @staticmethod
    def _check_frontend_menus_without_permissions(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查前端菜单是否完全缺少权限声明。

        :param manifest: 插件 manifest
        :return: 前端菜单权限提示问题项列表
        """
        if not manifest.frontend.menus:
            return []
        if not any(menu.type != 'F' for menu in PluginMenuTree.flatten(manifest.frontend.menus)):
            return []
        if manifest.permission_codes or PluginMenuTree.collect_permissions(manifest.frontend.menus):
            return []

        return [
            PluginValidationIssue(
                level='warning',
                category='manifest',
                kind='frontend_menus_without_permissions',
                path='frontend.menus',
                message='插件声明了前端菜单，但没有声明任何权限标识',
                suggestion='建议至少为页面菜单声明 perms 并在顶层 permissions 中同步声明，便于角色授权和菜单可见性统一管理',
                ok=True,
            )
        ]

    @staticmethod
    def _check_button_menus_without_permission(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查按钮菜单是否声明权限标识。

        :param manifest: 插件 manifest
        :return: 按钮菜单权限提示问题项列表
        """
        issues = []
        for menu in PluginMenuTree.flatten(manifest.frontend.menus):
            if menu.type != 'F' or menu.perms:
                continue
            issues.append(
                PluginValidationIssue(
                    level='warning',
                    category='manifest',
                    kind='button_menu_without_permission',
                    path=f'frontend.menus.{menu.path}.perms',
                    message=f'按钮菜单 {menu.name} 未声明权限标识',
                    suggestion='建议为按钮菜单声明 perms，并在顶层 permissions 中同步声明，便于前端权限指令和后端权限校验统一控制',
                    ok=True,
                )
            )

        return issues

    @staticmethod
    def _check_button_menu_structure(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查按钮菜单结构是否混入路由菜单语义。

        :param manifest: 插件 manifest
        :return: 按钮菜单结构提示问题项列表
        """
        issues = []
        for menu in PluginMenuTree.flatten(manifest.frontend.menus):
            if menu.type != 'F':
                continue
            if menu.component:
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='button_menu_with_component',
                        path=f'frontend.menus.{menu.path}.component',
                        message=f'按钮菜单 {menu.name} 声明了 component',
                        suggestion='按钮菜单只用于权限动作，不参与路由渲染；建议将 component 留空',
                        ok=True,
                    )
                )
            if menu.children:
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='button_menu_with_children',
                        path=f'frontend.menus.{menu.path}.children',
                        message=f'按钮菜单 {menu.name} 声明了子菜单',
                        suggestion='按钮菜单不应承载子菜单；建议将子菜单移动到目录或页面菜单下',
                        ok=True,
                    )
                )

        return issues

    @staticmethod
    def _check_permission_button_parent(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查自动权限按钮是否存在可挂载的页面或目录菜单。

        :param manifest: 插件 manifest
        :return: 自动权限按钮父菜单提示问题项列表
        """
        menu_permissions = PluginMenuTree.collect_permissions(manifest.frontend.menus)
        auto_button_permissions = sorted(set(manifest.permission_codes) - menu_permissions)
        if not auto_button_permissions:
            return []
        has_parent_menu = any(menu.type != 'F' for menu in PluginMenuTree.flatten(manifest.frontend.menus))
        if has_parent_menu:
            return []

        return [
            PluginValidationIssue(
                level='warning',
                category='manifest',
                kind='permission_without_menu_parent',
                path=f'permissions.{permission}',
                message=f'权限标识 {permission} 未声明菜单承载，且插件没有可挂载按钮的页面或目录菜单',
                suggestion='如该权限需要分配给角色，建议声明页面/目录菜单，或显式声明按钮菜单承载该权限',
                ok=True,
            )
            for permission in auto_button_permissions
        ]

    @staticmethod
    def _check_lifecycle_script_order(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查 migration 和 seed 声明顺序是否稳定。

        :param manifest: 插件 manifest
        :return: 生命周期脚本顺序提示问题项列表
        """
        issues = []
        for field_name, script_paths in (
            ('migrations', manifest.backend.migrations),
            ('seeds', manifest.backend.seeds),
        ):
            sorted_paths = sorted(script_paths)
            if script_paths == sorted_paths:
                continue
            issues.append(
                PluginValidationIssue(
                    level='warning',
                    category='manifest',
                    kind='script_order_unsorted',
                    path=f'backend.{field_name}',
                    message=f'backend.{field_name} 未按文件名顺序声明',
                    suggestion='插件 migration 和 seed 会按 manifest 列表顺序执行；建议按文件名升序声明，降低执行顺序出错风险',
                    ok=True,
                )
            )

        return issues

    @staticmethod
    def _check_enabled_jobs_without_health_checker(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查默认启用任务是否缺少健康检查声明。

        :param manifest: 插件 manifest
        :return: 定时任务健康检查提示问题项列表
        """
        enabled_jobs = [job for job in manifest.backend.jobs if job.enabled]
        if not enabled_jobs or manifest.backend.health.checker:
            return []

        return [
            PluginValidationIssue(
                level='warning',
                category='manifest',
                kind='enabled_jobs_without_health_checker',
                path='backend.health.checker',
                message='插件声明了默认启用的定时任务，但未声明健康检查 callable',
                suggestion='建议为包含默认启用任务的插件声明 backend.health.checker，便于运维侧确认任务依赖状态',
                ok=True,
            )
        ]

    @staticmethod
    def _check_unpaired_runtime_hooks(manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查启动和关闭钩子是否成对声明。

        :param manifest: 插件 manifest
        :return: 生命周期钩子配对提示问题项列表
        """
        hooks = manifest.backend.hooks
        if bool(hooks.on_startup) == bool(hooks.on_shutdown):
            return []

        missing_hook = 'onShutdown' if hooks.on_startup else 'onStartup'
        declared_hook = 'onStartup' if hooks.on_startup else 'onShutdown'
        return [
            PluginValidationIssue(
                level='warning',
                category='manifest',
                kind='unpaired_runtime_hook',
                path=f'backend.hooks.{missing_hook}',
                message=f'插件声明了 {declared_hook}，但未声明 {missing_hook}',
                suggestion='建议启动和关闭钩子成对声明，确保运行时资源可以完整初始化和释放',
                ok=True,
            )
        ]

    def _check_compatibility(self, manifest: PluginManifest) -> list[PluginValidationIssue]:
        """
        检查插件平台兼容性声明。

        :param manifest: 插件 manifest
        :return: 平台兼容性问题项列表
        """
        compatibility = manifest.compatibility
        checks = [
            ('backendVersion', compatibility.backend_version, self._read_backend_version, 'backend'),
            ('frontendVersion', compatibility.frontend_version, self._read_frontend_version, 'frontend'),
            ('pythonVersion', compatibility.python_version, lambda: self.python_version, 'python'),
            ('nodeVersion', compatibility.node_version, self._resolve_node_version, 'node'),
        ]
        issues = []
        for field_name, constraint, version_loader, target_name in checks:
            if not constraint:
                continue
            current_version = version_loader()
            if current_version is None:
                issues.append(
                    PluginValidationIssue(
                        level='warning',
                        category='manifest',
                        kind='compatibility_unknown',
                        path=f'compatibility.{field_name}',
                        message=f'无法读取当前 {target_name} 版本，跳过兼容性判断',
                        suggestion='确认运行环境可读取版本信息后重新执行插件检查',
                        ok=True,
                    )
                )
                continue
            if self._version_satisfied(current_version, constraint):
                continue
            issues.append(
                PluginValidationIssue(
                    level='error',
                    category='manifest',
                    kind='compatibility_unsatisfied',
                    path=f'compatibility.{field_name}',
                    message=f'{target_name} 版本不满足插件兼容性声明：current={current_version} required={constraint}',
                    suggestion='升级平台运行环境或调整插件 compatibility 声明',
                    ok=False,
                )
            )

        current_database = DataBaseConfig.db_type
        if compatibility.databases and current_database not in compatibility.databases:
            issues.append(
                PluginValidationIssue(
                    level='error',
                    category='manifest',
                    kind='compatibility_unsatisfied',
                    path='compatibility.databases',
                    message=(
                        'database 类型不满足插件兼容性声明：'
                        f'current={current_database} required={", ".join(compatibility.databases)}'
                    ),
                    suggestion='切换到插件支持的数据库，或调整插件 compatibility.databases 声明',
                    ok=False,
                )
            )

        return issues

    def _read_backend_version(self) -> str | None:
        """
        读取后端项目版本。

        :return: 后端项目版本，读取失败时返回 None
        """
        return self._read_pyproject_version(self.backend_root / 'pyproject.toml')

    def _read_frontend_version(self) -> str | None:
        """
        读取前端项目版本。

        :return: 前端项目版本，读取失败时返回 None
        """
        package_json = self.frontend_root / 'package.json'
        try:
            payload = json.loads(package_json.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return None
        version = payload.get('version') if isinstance(payload, dict) else None

        return str(version) if version else None

    @staticmethod
    def _read_pyproject_version(pyproject_path: Path) -> str | None:
        """
        读取 pyproject.toml 中的项目版本。

        :param pyproject_path: pyproject.toml 路径
        :return: 项目版本，读取失败时返回 None
        """
        try:
            for line in pyproject_path.read_text(encoding='utf-8').splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith('version ='):
                    return stripped_line.split('=', maxsplit=1)[1].strip().strip('"\'')
        except OSError:
            return None

        return None

    def _resolve_node_version(self) -> str | None:
        """
        解析当前 Node.js 版本。

        :return: Node.js 版本，读取失败时返回 None
        """
        if self.node_version is not None:
            return self.node_version
        cached_node_version = self.__class__._node_version_cache
        if cached_node_version is not UNRESOLVED_NODE_VERSION:
            return cached_node_version if isinstance(cached_node_version, str) else None
        try:
            completed = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            self.__class__._node_version_cache = None
            return None
        if completed.returncode != 0:
            self.__class__._node_version_cache = None
            return None

        resolved_node_version = completed.stdout.strip().lstrip('v') or None
        self.__class__._node_version_cache = resolved_node_version
        return resolved_node_version

    @staticmethod
    def _version_satisfied(current_version: str, constraint: str) -> bool:
        """
        判断当前版本是否满足兼容性约束。

        :param current_version: 当前版本
        :param constraint: 兼容性约束
        :return: 是否满足
        """
        matched_constraint = COMPATIBILITY_CONSTRAINT_PATTERN.match(constraint)
        if not matched_constraint:
            return True
        operator, required_version = matched_constraint.groups()
        operator = operator or '=='

        return PluginVersionConstraintMatcher.is_satisfied(current_version, operator, required_version)
