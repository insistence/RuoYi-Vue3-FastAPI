from pathlib import Path
from typing import Any

from plugins.core.utils import validate_plugin_id_value

from .backend import PluginBackendScaffoldTemplateBuilder
from .frontend import FrontendVersion, PluginFrontendScaffoldTemplateBuilder, PluginFrontendVersionResolver
from .options import PluginScaffoldOptions, PluginScaffoldTemplateResolver
from .payload import PluginScaffoldPayloadBuilder, PluginScaffoldPlanPayload


class PluginScaffoldBuilder:
    """
    插件模板构建器。

    使用 Builder 模式生成后端与前端插件模板文件计划，并在确认无冲突后落地。
    """

    def __init__(self, backend_root: Path, frontend_root: Path) -> None:
        """
        初始化插件模板构建器。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端项目根目录
        """
        self.backend_root = backend_root
        self.frontend_root = frontend_root

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
        frontend_version: str = PluginFrontendVersionResolver.AUTO,
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
        :param frontend_version: 前端 Vue 版本，支持 auto、vue2、vue3
        :return: 插件模板写入计划
        """
        self._validate_plugin_id(plugin_id)
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
        resolved_frontend_version = (
            PluginFrontendVersionResolver.resolve(self.frontend_root, frontend_version) if options.frontend else None
        )
        if options.backend:
            backend_plugin_root = self.backend_root / 'plugins' / plugin_id
            target_dirs.append(str(backend_plugin_root))
            if effective_backend_test:
                target_dirs.append(str(self.backend_root / 'tests' / 'plugins' / plugin_id))
            files.extend(self._build_backend_files(plugin_id, backend_plugin_root, options))
        if options.frontend:
            assert resolved_frontend_version is not None
            frontend_plugin_root = self.frontend_root / 'plugins' / plugin_id
            target_dirs.append(str(frontend_plugin_root))
            if effective_frontend_test:
                target_dirs.append(str(self.frontend_root / 'tests' / 'plugins' / plugin_id))
            files.extend(
                self._build_frontend_files(
                    plugin_id,
                    frontend_plugin_root,
                    options,
                    frontend_version=resolved_frontend_version,
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
            frontend_version=resolved_frontend_version,
            target_dirs=target_dirs,
            files=files,
            conflicts=conflicts,
        ).to_payload()

    build_conflict_payload = staticmethod(PluginScaffoldPayloadBuilder.build_conflict_payload)
    build_success_payload = staticmethod(PluginScaffoldPayloadBuilder.build_success_payload)

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
        frontend_version: FrontendVersion,
    ) -> list[tuple[Path, str]]:
        """
        构建前端插件模板文件。

        :param plugin_id: 插件ID
        :param plugin_root: 前端插件根目录
        :param options: 插件模板生成选项
        :param frontend_version: 已解析的前端 Vue 版本
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
                PluginFrontendScaffoldTemplateBuilder.build_crud_view(plugin_id, frontend_version)
                if options.crud
                else PluginFrontendScaffoldTemplateBuilder.build_view(plugin_id, frontend_version),
            ),
            (
                plugin_root / 'README.md',
                PluginFrontendScaffoldTemplateBuilder.build_readme(plugin_id, frontend_version),
            ),
        ]
        if options.test:
            files.append(
                (
                    self.frontend_root / 'tests' / 'plugins' / plugin_id / 'pluginView.test.js',
                    PluginFrontendScaffoldTemplateBuilder.build_test(plugin_id, frontend_version),
                )
            )

        return files
