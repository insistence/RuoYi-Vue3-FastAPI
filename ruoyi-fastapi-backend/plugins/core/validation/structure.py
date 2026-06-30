import importlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.manifest.menu_tree import PluginMenuTree
from plugins.core.manifest.schema import PluginJobManifest, PluginManifest, PluginMenuManifest
from plugins.core.validation.result import PluginValidationIssue, PluginValidationLevelResolver, ValidationLevel
from utils.cron_util import CronUtil

MAX_PLUGIN_JOB_NAME_LENGTH = 64
SUPPORTED_SEED_SUFFIXES = {'.py', '.sql'}
SUPPORTED_MIGRATION_SUFFIXES = {'.py', '.sql'}


@dataclass(frozen=True)
class PluginStructureCheckItem:
    """
    插件结构检查项。
    """

    kind: str
    path: str
    ok: bool
    message: str
    suggestion: str = ''

    @property
    def level(self) -> ValidationLevel:
        """
        获取结构检查项等级。

        :return: 检查等级
        """
        return PluginValidationLevelResolver.from_ok(self.ok)

    def to_issue(self) -> PluginValidationIssue:
        """
        转换为统一校验问题项。

        :return: 统一校验问题项
        """
        return PluginValidationIssue(
            level=self.level,
            category='structure',
            kind=self.kind,
            path=self.path,
            message=self.message,
            suggestion=self.suggestion,
            ok=self.ok,
        )


@dataclass(frozen=True)
class PluginStructureCheckResult:
    """
    插件结构检查结果。
    """

    plugin_id: str
    items: list[PluginStructureCheckItem]

    @property
    def ok(self) -> bool:
        """
        判断结构检查是否整体通过。

        :return: 是否通过
        """
        return all(item.ok for item in self.items)

    @property
    def failed_items(self) -> list[PluginStructureCheckItem]:
        """
        获取失败检查项列表。

        :return: 失败检查项列表
        """
        return [item for item in self.items if not item.ok]

    @property
    def issues(self) -> list[PluginValidationIssue]:
        """
        获取统一校验问题项列表。

        :return: 统一校验问题项列表
        """
        return [item.to_issue() for item in self.items]


class PluginStructureChecker:
    """
    插件结构检查器。

    使用 Checker 模式集中验证 manifest 引用的后端目录、seed 文件和前端页面是否存在。
    """

    def __init__(self, backend_root: Path | str, frontend_root: Path | str | None = None) -> None:
        """
        初始化插件结构检查器。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端插件根目录，默认使用运行时环境解析出的 plugins 目录
        """
        self.backend_root = Path(backend_root)
        self.frontend_root = (
            Path(frontend_root)
            if frontend_root
            else Path(PluginRuntimeEnvironmentService(backend_root=self.backend_root).get_frontend_plugins_dir())
        )

    def check(self, discovered_plugin: DiscoveredPlugin) -> PluginStructureCheckResult:
        """
        检查插件结构。

        :param discovered_plugin: 已发现插件对象
        :return: 插件结构检查结果
        """
        manifest = discovered_plugin.manifest
        items = [
            self._check_dir('backend_root', discovered_plugin.backend_path),
            self._check_file('manifest', discovered_plugin.manifest_path),
        ]
        if manifest.backend.routers.auto_scan:
            items.append(self._check_dir('controller_dir', discovered_plugin.backend_path / 'controller'))

        entity_dir = discovered_plugin.backend_path / 'entity' / 'do'
        if entity_dir.exists():
            items.append(self._check_dir('entity_do_dir', entity_dir))

        items.extend(self._check_migration_files(discovered_plugin))
        items.extend(self._check_seed_files(discovered_plugin))
        items.extend(self._check_hooks(discovered_plugin))
        items.extend(self._check_jobs(discovered_plugin))
        items.extend(self._check_frontend(discovered_plugin))

        return PluginStructureCheckResult(plugin_id=manifest.id, items=items)

    def _check_hooks(self, discovered_plugin: DiscoveredPlugin) -> list[PluginStructureCheckItem]:
        """
        检查插件生命周期钩子声明。

        :param discovered_plugin: 已发现插件对象
        :return: 生命周期钩子检查项列表
        """
        items = []
        hooks = discovered_plugin.manifest.backend.hooks
        hook_mapping = {
            'on_install': hooks.on_install,
            'on_upgrade': hooks.on_upgrade,
            'on_startup': hooks.on_startup,
            'on_shutdown': hooks.on_shutdown,
            'on_purge': hooks.on_purge,
        }
        for hook_name, hook_path in hook_mapping.items():
            if not hook_path:
                continue
            items.append(self._check_hook_boundary(discovered_plugin.manifest.backend.module, hook_name, hook_path))
            items.append(self._check_hook_callable_importable(discovered_plugin, hook_name, hook_path))

        return items

    def _check_hook_callable_importable(
        self,
        discovered_plugin: DiscoveredPlugin,
        hook_name: str,
        hook_path: str,
    ) -> PluginStructureCheckItem:
        """
        检查生命周期钩子 callable 是否可以导入。

        :param discovered_plugin: 已发现插件对象
        :param hook_name: 生命周期钩子名称
        :param hook_path: 生命周期钩子声明
        :return: 结构检查项
        """
        try:
            module_path, callable_name = hook_path.split(':', maxsplit=1)
            module_name = self._resolve_hook_module_name(discovered_plugin.manifest.backend.module, module_path)
            module = self._import_plugin_module(discovered_plugin, module_name)
            target = getattr(module, callable_name)
            ok = callable(target)
        except Exception as exc:
            return PluginStructureCheckItem(
                kind='hook_callable',
                path=f'{hook_name}:{hook_path}',
                ok=False,
                message=f'生命周期钩子不可导入：{exc}',
            )

        return PluginStructureCheckItem(
            kind='hook_callable',
            path=f'{hook_name}:{hook_path}',
            ok=ok,
            message=f'生命周期钩子可调用：{hook_path}' if ok else f'生命周期钩子不是可调用对象：{hook_path}',
        )

    @staticmethod
    def _check_hook_boundary(backend_module: str, hook_name: str, hook_path: str) -> PluginStructureCheckItem:
        """
        检查生命周期钩子是否位于当前插件后端模块内。

        :param backend_module: 插件后端模块路径
        :param hook_name: 生命周期钩子名称
        :param hook_path: 生命周期钩子声明
        :return: 结构检查项
        """
        module_path = hook_path.split(':', maxsplit=1)[0]
        resolved_module_path = PluginStructureChecker._resolve_hook_module_name(backend_module, module_path)
        ok = resolved_module_path == backend_module or resolved_module_path.startswith(f'{backend_module}.')
        return PluginStructureCheckItem(
            kind='hook_boundary',
            path=f'{hook_name}:{hook_path}',
            ok=ok,
            message=f'生命周期钩子位于插件模块内：{hook_path}' if ok else f'生命周期钩子越界：{hook_path}',
        )

    @staticmethod
    def _resolve_hook_module_name(backend_module: str, module_path: str) -> str:
        """
        解析生命周期钩子模块名。

        :param backend_module: 插件后端模块路径
        :param module_path: manifest 中声明的钩子模块路径
        :return: 完整 Python 模块名
        """
        if module_path == backend_module or module_path.startswith(f'{backend_module}.'):
            return module_path
        if module_path.startswith('plugins.'):
            return module_path

        return f'{backend_module}.{module_path}'

    def _check_jobs(self, discovered_plugin: DiscoveredPlugin) -> list[PluginStructureCheckItem]:
        """
        检查插件定时任务声明。

        :param discovered_plugin: 已发现插件对象
        :return: 定时任务检查项列表
        """
        items = []
        manifest = discovered_plugin.manifest
        for job in manifest.backend.jobs:
            items.append(self._check_job_name_length(manifest.id, job))
            items.append(self._check_job_callable_boundary(manifest.backend.module, job))
            items.append(self._check_job_callable_importable(job))
            items.append(self._check_job_cron_expression(job))

        return items

    @staticmethod
    def _check_job_name_length(plugin_id: str, job: PluginJobManifest) -> PluginStructureCheckItem:
        """
        检查插件任务映射到系统任务表后的名称长度。

        :param plugin_id: 插件ID
        :param job: 插件定时任务声明
        :return: 结构检查项
        """
        job_name = f'{plugin_id}:{job.id}'
        ok = len(job_name) <= MAX_PLUGIN_JOB_NAME_LENGTH
        return PluginStructureCheckItem(
            kind='job_name',
            path=job_name,
            ok=ok,
            message=f'任务名称长度有效：{job_name}' if ok else f'任务名称超过 64 字符：{job_name}',
        )

    @staticmethod
    def _check_job_callable_boundary(
        backend_module: str,
        job: PluginJobManifest,
    ) -> PluginStructureCheckItem:
        """
        检查任务 callable 是否位于当前插件后端模块内。

        :param backend_module: 插件后端模块路径
        :param job: 插件定时任务声明
        :return: 结构检查项
        """
        ok = job.callable.startswith(f'{backend_module}.')
        return PluginStructureCheckItem(
            kind='job_callable_boundary',
            path=job.callable,
            ok=ok,
            message=f'任务 callable 位于插件模块内：{job.callable}' if ok else f'任务 callable 越界：{job.callable}',
        )

    def _check_job_callable_importable(self, job: PluginJobManifest) -> PluginStructureCheckItem:
        """
        检查任务 callable 是否可以导入。

        :param job: 插件定时任务声明
        :return: 结构检查项
        """
        try:
            module_path, callable_name = job.callable.rsplit('.', 1)
            module = self._import_job_module(module_path)
            target = getattr(module, callable_name)
            ok = callable(target)
        except Exception as exc:
            return PluginStructureCheckItem(
                kind='job_callable',
                path=job.callable,
                ok=False,
                message=f'任务 callable 不可导入：{exc}',
            )

        return PluginStructureCheckItem(
            kind='job_callable',
            path=job.callable,
            ok=ok,
            message=f'任务 callable 可调用：{job.callable}' if ok else f'任务 callable 不是可调用对象：{job.callable}',
        )

    def _import_job_module(self, module_path: str) -> object:
        """
        导入插件任务模块，优先从当前检查的后端根目录解析。

        :param module_path: Python 模块路径
        :return: 导入后的模块对象
        """
        module_file = self.backend_root / Path(*module_path.split('.')).with_suffix('.py')
        if module_file.is_file():
            module_name = f'_plugin_check_{module_path}'
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            if spec is None or spec.loader is None:
                raise ImportError(f'无法加载模块文件：{module_file}')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        backend_root_text = str(self.backend_root)
        if backend_root_text not in sys.path:
            sys.path.insert(0, backend_root_text)
        return importlib.import_module(module_path)

    def _import_plugin_module(self, discovered_plugin: DiscoveredPlugin, module_path: str) -> object:
        """
        导入插件内模块，优先从当前插件目录解析。

        :param discovered_plugin: 已发现插件对象
        :param module_path: Python 模块路径
        :return: 导入后的模块对象
        """
        backend_module = discovered_plugin.manifest.backend.module
        if module_path == backend_module:
            module_file = discovered_plugin.backend_path / '__init__.py'
        elif module_path.startswith(f'{backend_module}.'):
            relative_module = module_path.removeprefix(backend_module).lstrip('.')
            module_file = discovered_plugin.backend_path.joinpath(*relative_module.split('.')).with_suffix('.py')
        else:
            module_file = self.backend_root / Path(*module_path.split('.')).with_suffix('.py')

        if module_file.is_file():
            module_name = f'_plugin_check_{module_path}'
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            if spec is None or spec.loader is None:
                raise ImportError(f'无法加载模块文件：{module_file}')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        backend_root_text = str(self.backend_root)
        if backend_root_text not in sys.path:
            sys.path.insert(0, backend_root_text)
        return importlib.import_module(module_path)

    @staticmethod
    def _check_job_cron_expression(job: PluginJobManifest) -> PluginStructureCheckItem:
        """
        检查任务 cron 表达式。

        :param job: 插件定时任务声明
        :return: 结构检查项
        """
        ok = CronUtil.validate_cron_expression(job.cron_expression)
        return PluginStructureCheckItem(
            kind='job_cron',
            path=f'{job.id}:{job.cron_expression}',
            ok=ok,
            message=(
                f'任务 cron 表达式有效：{job.cron_expression}' if ok else f'任务 cron 表达式无效：{job.cron_expression}'
            ),
        )

    def _check_migration_files(self, discovered_plugin: DiscoveredPlugin) -> list[PluginStructureCheckItem]:
        """
        检查 migration 文件。

        :param discovered_plugin: 已发现插件对象
        :return: migration 检查项列表
        """
        items = []
        for migration_path in discovered_plugin.manifest.backend.migrations:
            items.append(
                self._check_plugin_relative_file('migration_file', discovered_plugin.backend_path, migration_path)
            )
            items.append(self._check_migration_type(migration_path))

        return items

    @staticmethod
    def _check_migration_type(migration_path: str) -> PluginStructureCheckItem:
        """
        检查 migration 文件类型。

        :param migration_path: migration 相对插件根目录路径
        :return: 结构检查项
        """
        ok = Path(migration_path).suffix in SUPPORTED_MIGRATION_SUFFIXES
        return PluginStructureCheckItem(
            kind='migration_type',
            path=migration_path,
            ok=ok,
            message=f'支持的 migration：{migration_path}' if ok else f'暂不支持的 migration 类型：{migration_path}',
        )

    def _check_seed_files(self, discovered_plugin: DiscoveredPlugin) -> list[PluginStructureCheckItem]:
        """
        检查 seed 文件。

        :param discovered_plugin: 已发现插件对象
        :return: seed 检查项列表
        """
        items = []
        for seed_path in discovered_plugin.manifest.backend.seeds:
            items.append(self._check_plugin_relative_file('seed_file', discovered_plugin.backend_path, seed_path))
            items.append(self._check_seed_type(seed_path))

        return items

    @staticmethod
    def _check_seed_type(seed_path: str) -> PluginStructureCheckItem:
        """
        检查 seed 文件类型。

        :param seed_path: seed 相对插件根目录路径
        :return: 结构检查项
        """
        ok = Path(seed_path).suffix in SUPPORTED_SEED_SUFFIXES
        return PluginStructureCheckItem(
            kind='seed_type',
            path=seed_path,
            ok=ok,
            message=f'支持的 seed：{seed_path}' if ok else f'暂不支持的 seed 类型：{seed_path}',
        )

    def _check_frontend(self, discovered_plugin: DiscoveredPlugin) -> list[PluginStructureCheckItem]:
        """
        检查前端插件目录和菜单组件。

        :param discovered_plugin: 已发现插件对象
        :return: 前端检查项列表
        """
        manifest = discovered_plugin.manifest
        plugin_view_menus = [
            menu
            for menu in PluginMenuTree.flatten(manifest.frontend.menus)
            if PluginMenuTree.is_plugin_component(menu.component)
        ]
        frontend_plugin_root = self.frontend_root / (manifest.frontend.plugin_id or manifest.id)
        if not plugin_view_menus:
            return []

        items = [self._check_dir('frontend_root', frontend_plugin_root)]
        items.append(self._check_dir('frontend_views_path', frontend_plugin_root / manifest.frontend.views_path))
        items.append(self._check_dir('frontend_api_path', frontend_plugin_root / manifest.frontend.api_path))
        items.extend(self._check_plugin_view(frontend_plugin_root, manifest, menu) for menu in plugin_view_menus)

        return items

    def _check_plugin_view(
        self,
        frontend_plugin_root: Path,
        manifest: PluginManifest,
        menu: PluginMenuManifest,
    ) -> PluginStructureCheckItem:
        """
        检查插件菜单组件对应的 Vue 页面。

        :param frontend_plugin_root: 前端插件根目录
        :param manifest: 插件清单
        :param menu: 菜单声明
        :return: 页面检查项
        """
        view_path = PluginMenuTree.resolve_plugin_view_path(manifest, menu.component)
        if view_path is None:
            return PluginStructureCheckItem(
                kind='frontend_view',
                path=menu.component,
                ok=False,
                message=f'插件组件路径格式错误：{menu.component}',
            )

        return self._check_file('frontend_view', frontend_plugin_root / view_path)

    @staticmethod
    def _check_dir(kind: str, path: Path) -> PluginStructureCheckItem:
        """
        检查目录是否存在。

        :param kind: 检查类型
        :param path: 目录路径
        :return: 结构检查项
        """
        return PluginStructureCheckItem(
            kind=kind,
            path=str(path),
            ok=path.is_dir(),
            message=f'目录存在：{path}' if path.is_dir() else f'目录不存在：{path}',
        )

    @staticmethod
    def _check_file(kind: str, path: Path) -> PluginStructureCheckItem:
        """
        检查文件是否存在。

        :param kind: 检查类型
        :param path: 文件路径
        :return: 结构检查项
        """
        return PluginStructureCheckItem(
            kind=kind,
            path=str(path),
            ok=path.is_file(),
            message=f'文件存在：{path}' if path.is_file() else f'文件不存在：{path}',
        )

    @classmethod
    def _check_plugin_relative_file(cls, kind: str, plugin_root: Path, relative_path: str) -> PluginStructureCheckItem:
        """
        检查插件相对路径文件是否存在且未越过插件根目录。

        :param kind: 检查类型
        :param plugin_root: 插件后端根目录
        :param relative_path: 相对插件根目录路径
        :return: 结构检查项
        """
        file_path = (plugin_root / relative_path).resolve()
        resolved_plugin_root = plugin_root.resolve()
        if resolved_plugin_root not in file_path.parents:
            return PluginStructureCheckItem(
                kind=kind,
                path=relative_path,
                ok=False,
                message=f'文件路径不能越过插件根目录：{relative_path}',
                suggestion='请使用插件目录内的相对路径',
            )

        return cls._check_file(kind, file_path)
