from collections.abc import Callable
from pathlib import Path
from typing import Any

from plugins.core.frontend import select_frontend_root
from plugins.core.utils import validate_plugin_id_value

from .backend import PluginBackendScaffoldTemplateBuilder
from .frontend import FrontendFramework, PluginFrontendFrameworkResolver, PluginFrontendScaffoldTemplateBuilder
from .options import PluginScaffoldOptions, PluginScaffoldTemplateResolver
from .payload import PluginScaffoldPayloadBuilder, PluginScaffoldPlanPayload
from .v2 import PluginV2ScaffoldBuilder


class PluginScaffoldBuilder:
    """
    插件模板构建器。

    使用 Builder 模式生成后端与前端插件模板文件计划，并在确认无冲突后落地。
    """

    def __init__(
        self,
        backend_root: Path,
        frontend_root: Path,
        frontend_framework_resolver: Callable[[Path], str] | None = None,
    ) -> None:
        """
        初始化插件模板构建器。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端工程根目录或包含框架分类的聚合目录
        :param frontend_framework_resolver: 宿主框架解析函数，保留运行环境中选择的框架
        :return: None
        """
        self.backend_root = backend_root
        self.frontend_root = select_frontend_root(frontend_root)
        self.frontend_framework_resolver = frontend_framework_resolver

    def build_plan(
        self,
        plugin_id: str,
        *,
        template: str = PluginScaffoldTemplateResolver.DEFAULT_TEMPLATE,
        backend: bool,
        frontend: bool,
        migration: bool = True,
        seed: bool = True,
        job: bool = True,
        config: bool = True,
        test: bool = True,
        frontend_framework: str = PluginFrontendFrameworkResolver.AUTO,
    ) -> dict[str, Any]:
        """
        构建插件模板写入计划。

        :param plugin_id: 插件ID
        :param template: 插件模板名称
        :param backend: 是否创建后端插件模板
        :param frontend: 是否创建前端插件模板
        :param migration: 是否创建 migration 示例
        :param seed: 是否创建 seed 示例
        :param job: 是否创建定时任务示例
        :param config: 是否创建配置项示例
        :param test: 是否创建测试样例
        :param frontend_framework: 目标前端框架标识，auto 表示自动识别；源码模板仅支持 vue2、vue3
        :return: 插件模板写入计划
        """
        self._validate_plugin_id(plugin_id)
        frontend_root = select_frontend_root(self.frontend_root, frontend_framework)
        normalized_template = (template or PluginScaffoldTemplateResolver.DEFAULT_TEMPLATE).strip()
        if normalized_template in PluginScaffoldTemplateResolver.V2_TEMPLATES:
            return PluginV2ScaffoldBuilder(
                self.backend_root, frontend_root, frontend_framework_resolver=self.frontend_framework_resolver
            ).build_plan(
                plugin_id,
                template=normalized_template,
                backend=backend,
                frontend=frontend,
                test=test,
                frontend_framework=frontend_framework,
            )
        options = self._merge_options(
            PluginScaffoldTemplateResolver.resolve(template),
            backend=backend,
            frontend=frontend,
            migration=migration,
            seed=seed,
            job=job,
            config=config,
            test=test,
        )
        if not options.backend and not options.frontend:
            raise ValueError('backend 和 frontend 至少需要创建一个')

        files = []
        target_dirs = []
        effective_backend_test = options.test and options.backend
        effective_frontend_test = options.test and options.frontend
        resolved_frontend_framework = (
            self._resolve_frontend_framework(frontend_root, frontend_framework) if options.frontend else None
        )
        if options.backend:
            backend_plugin_root = self.backend_root / 'plugins' / plugin_id
            target_dirs.append(str(backend_plugin_root))
            if effective_backend_test:
                target_dirs.append(str(self.backend_root / 'tests' / 'plugins' / plugin_id))
            files.extend(self._build_backend_files(plugin_id, backend_plugin_root, options))
        if options.frontend:
            assert resolved_frontend_framework is not None
            frontend_plugin_root = frontend_root / 'plugins' / plugin_id
            target_dirs.append(str(frontend_plugin_root))
            if effective_frontend_test:
                target_dirs.append(str(frontend_root / 'tests' / 'plugins' / plugin_id))
            files.extend(
                self._build_frontend_files(
                    plugin_id,
                    frontend_plugin_root,
                    options,
                    frontend_framework=resolved_frontend_framework,
                )
            )

        conflicts = [target_dir for target_dir in target_dirs if Path(target_dir).exists()]

        return PluginScaffoldPlanPayload(
            template=template or PluginScaffoldTemplateResolver.DEFAULT_TEMPLATE,
            backend=options.backend,
            frontend=options.frontend,
            migration=options.migration,
            seed=options.seed,
            job=options.job,
            config=options.config,
            crud=options.crud,
            test=effective_backend_test or effective_frontend_test,
            backend_test=effective_backend_test,
            frontend_test=effective_frontend_test,
            frontend_framework=resolved_frontend_framework,
            target_dirs=target_dirs,
            files=files,
            conflicts=conflicts,
        ).to_payload()

    build_conflict_payload = staticmethod(PluginScaffoldPayloadBuilder.build_conflict_payload)
    build_success_payload = staticmethod(PluginScaffoldPayloadBuilder.build_success_payload)

    def _resolve_frontend_framework(self, frontend_root: Path, requested_framework: str) -> str:
        """
        优先使用命令显式框架，其次沿用宿主运行环境的框架选择。

        :param frontend_root: 已选中的前端工程目录
        :param requested_framework: 命令指定的框架标识
        :return: 已解析的前端框架标识
        """
        if (requested_framework or 'auto').strip().lower() == 'auto' and self.frontend_framework_resolver is not None:
            return self.frontend_framework_resolver(frontend_root)
        return PluginFrontendFrameworkResolver.resolve(frontend_root, requested_framework)

    @classmethod
    def _validate_plugin_id(cls, plugin_id: str) -> None:
        """
        校验插件模板 ID。

        :param plugin_id: 插件ID
        :return: None
        """
        validate_plugin_id_value(plugin_id)

    @staticmethod
    def _merge_options(
        base_options: PluginScaffoldOptions,
        *,
        backend: bool,
        frontend: bool,
        migration: bool,
        seed: bool,
        job: bool,
        config: bool,
        test: bool,
    ) -> PluginScaffoldOptions:
        """
        合并模板预设和命令行开关。

        :param base_options: 模板预设选项
        :param backend: 是否创建后端插件模板
        :param frontend: 是否创建前端插件模板
        :param migration: 是否创建 migration 示例
        :param seed: 是否创建 seed 示例
        :param job: 是否创建定时任务示例
        :param config: 是否创建配置项示例
        :param test: 是否创建测试样例
        :return: 合并后的插件模板生成选项
        """
        return PluginScaffoldOptions(
            backend=base_options.backend and backend,
            frontend=base_options.frontend and frontend,
            migration=base_options.migration and migration,
            seed=base_options.seed and seed,
            job=base_options.job and job,
            config=base_options.config and config,
            test=base_options.test and test,
            crud=base_options.crud,
        )

    def apply_plan(self, scaffold_plan: dict[str, Any]) -> None:
        """
        执行插件模板写入计划。

        :param scaffold_plan: 插件模板写入计划
        :return: None
        """
        for file_payload in scaffold_plan['files']:
            file_path = Path(file_payload['path'])
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(file_payload['content'], encoding='utf-8')

    def _build_backend_files(
        self,
        plugin_id: str,
        plugin_root: Path,
        options: PluginScaffoldOptions,
    ) -> list[tuple[Path, str]]:
        """
        构建后端插件模板文件。

        :param plugin_id: 插件ID
        :param plugin_root: 后端插件根目录
        :param options: 插件模板生成选项
        :return: 文件路径和内容列表
        """
        files = [
            (plugin_root / 'plugin.yaml', PluginBackendScaffoldTemplateBuilder.build_manifest(plugin_id, options)),
            (
                plugin_root / 'controller' / f'{plugin_id}_controller.py',
                PluginBackendScaffoldTemplateBuilder.build_crud_controller(plugin_id)
                if options.crud
                else PluginBackendScaffoldTemplateBuilder.build_controller(plugin_id),
            ),
            (
                plugin_root / 'service' / f'{plugin_id}_service.py',
                PluginBackendScaffoldTemplateBuilder.build_crud_service(plugin_id)
                if options.crud
                else PluginBackendScaffoldTemplateBuilder.build_service(plugin_id),
            ),
            (plugin_root / 'hooks.py', PluginBackendScaffoldTemplateBuilder.build_hooks(plugin_id)),
            (plugin_root / 'README.md', PluginBackendScaffoldTemplateBuilder.build_readme(plugin_id)),
        ]
        if options.job:
            files.append((plugin_root / 'jobs.py', PluginBackendScaffoldTemplateBuilder.build_jobs(plugin_id)))
        if options.migration:
            files.append(
                (
                    plugin_root / 'migrations' / '001_init.sql',
                    PluginBackendScaffoldTemplateBuilder.build_migration(plugin_id),
                )
            )
        if options.seed:
            files.append(
                (plugin_root / 'seeds' / '001_seed.sql', PluginBackendScaffoldTemplateBuilder.build_seed(plugin_id))
            )
        if options.test:
            files.append(
                (
                    self.backend_root / 'tests' / 'plugins' / plugin_id / 'test_ping.py',
                    PluginBackendScaffoldTemplateBuilder.build_crud_test(plugin_id)
                    if options.crud
                    else PluginBackendScaffoldTemplateBuilder.build_test(plugin_id),
                )
            )

        return files

    def _build_frontend_files(
        self,
        plugin_id: str,
        plugin_root: Path,
        options: PluginScaffoldOptions,
        *,
        frontend_framework: FrontendFramework,
    ) -> list[tuple[Path, str]]:
        """
        构建前端插件模板文件。

        :param plugin_id: 插件ID
        :param plugin_root: 前端插件根目录
        :param options: 插件模板生成选项
        :param frontend_framework: 已解析的前端框架标识
        :return: 文件路径和内容列表
        """
        files = [
            (
                plugin_root / 'api' / f'{plugin_id}.js',
                PluginFrontendScaffoldTemplateBuilder.build_crud_api(plugin_id)
                if options.crud
                else PluginFrontendScaffoldTemplateBuilder.build_api(plugin_id),
            ),
            (
                plugin_root / 'views' / 'index.vue',
                PluginFrontendScaffoldTemplateBuilder.build_crud_view(plugin_id, frontend_framework)
                if options.crud
                else PluginFrontendScaffoldTemplateBuilder.build_view(plugin_id, frontend_framework),
            ),
            (
                plugin_root / 'README.md',
                PluginFrontendScaffoldTemplateBuilder.build_readme(plugin_id, frontend_framework),
            ),
        ]
        if options.test:
            files.append(
                (
                    plugin_root.parents[1] / 'tests' / 'plugins' / plugin_id / 'pluginView.test.js',
                    PluginFrontendScaffoldTemplateBuilder.build_test(plugin_id, frontend_framework),
                )
            )

        return files
