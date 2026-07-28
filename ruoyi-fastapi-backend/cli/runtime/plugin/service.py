from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from cli.exit_codes import RUNTIME_ERROR, SUCCESS

from .gateway import PluginRuntimeGateway
from .scaffold import PluginScaffoldBuilder
from .support import (
    PLUGIN_DEPENDENCY_ALLOWLIST_EXAMPLE_YAML,
    CliPluginRuntimeExceptionPayload,
    PluginDependencyAllowlistExamplePayloadBuilder,
    PluginDependencyLockfileTemplateBuilder,
    PluginDependencyLockPayloadBuilder,
    PluginTestPayloadBuilder,
    PluginTestPlanBuilder,
)

PYTEST_COMMAND_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class CliPluginRuntimeDependencies:
    """
    CLI 插件运行时依赖容器。
    """

    runtime_environment: object | None = None
    dependency_checker: object | None = None
    management_gateway: object | None = None
    model_gateway: object | None = None
    command_gateway: object | None = None
    lifecycle_lock: object | None = None


class CliPluginRuntimeService:
    """
    插件 CLI 运行时服务。

    该服务负责为 CLI 组装核心插件运行时，并只承载 CLI 专属开发命令能力，
    例如插件测试执行、插件模板创建和本地辅助文件生成。
    """

    def __init__(
        self,
        *,
        success_code: int = SUCCESS,
        runtime_error_code: int = RUNTIME_ERROR,
        runtime_environment: object | None = None,
        dependency_checker: object | None = None,
        management_gateway: object | None = None,
        model_gateway: object | None = None,
        command_gateway: object | None = None,
        lifecycle_lock: object | None = None,
        plugin_gateway: PluginRuntimeGateway | None = None,
    ) -> None:
        """
        初始化插件 CLI 运行时服务。

        :param success_code: CLI 成功退出码
        :param runtime_error_code: CLI 运行失败退出码
        :param runtime_environment: 插件运行时环境服务
        :param dependency_checker: 插件依赖检查器
        :param management_gateway: 插件管理运行时适配器
        :param model_gateway: 插件管理模型工厂网关
        :param command_gateway: 插件命令执行网关
        :param lifecycle_lock: 插件生命周期操作锁
        :param plugin_gateway: 插件 CLI 运行时网关
        :return: None
        """
        self.success_code = success_code
        self.runtime_error_code = runtime_error_code
        self.plugin_gateway = plugin_gateway or PluginRuntimeGateway()
        self.dependencies = CliPluginRuntimeDependencies(
            runtime_environment=runtime_environment,
            dependency_checker=dependency_checker,
            management_gateway=management_gateway,
            model_gateway=model_gateway,
            command_gateway=command_gateway,
            lifecycle_lock=lifecycle_lock,
        )
        self._core_runtime: Any | None = None

    @property
    def core_runtime(self) -> Any:
        """
        延迟获取插件核心运行时服务。

        :return: 插件核心运行时服务
        """
        if self._core_runtime is None:
            runtime_service_class = self.plugin_gateway.get_core_runtime_service_class()
            management_gateway = self._resolve_management_gateway()
            gateway_overrides_class = self.plugin_gateway.get_core_runtime_gateway_overrides_class()
            self._core_runtime = runtime_service_class(
                runtime_environment=self._resolve_runtime_environment(),
                dependency_checker=self.dependencies.dependency_checker,
                gateways=self._build_gateway_overrides(gateway_overrides_class, management_gateway),
                model_gateway=self._resolve_model_gateway(),
                command_gateway=self._resolve_command_gateway(),
                lifecycle_lock=self._resolve_lifecycle_lock(),
            )
        return self._core_runtime

    def _resolve_runtime_environment(self) -> object:
        """
        解析插件核心运行时环境服务。

        :return: 插件核心运行时环境服务
        """
        if self.dependencies.runtime_environment is not None:
            return self.dependencies.runtime_environment
        runtime_environment = self.plugin_gateway.get_core_runtime_environment()
        self.dependencies = replace(self.dependencies, runtime_environment=runtime_environment)
        return runtime_environment

    def _load_management_gateway(self) -> object:
        """
        解析插件管理运行时适配器。

        :return: 插件管理运行时适配器
        """
        management_gateway = self.plugin_gateway.get_management_runtime_gateway()
        self.dependencies = replace(
            self.dependencies,
            management_gateway=self.dependencies.management_gateway or management_gateway,
            model_gateway=self.dependencies.model_gateway or management_gateway,
            command_gateway=self.dependencies.command_gateway or management_gateway,
        )
        return management_gateway

    def _resolve_management_gateway(self) -> object:
        """
        解析插件管理运行时适配器。

        :return: 插件管理运行时适配器
        """
        if self.dependencies.management_gateway is None:
            self._load_management_gateway()
        return self.dependencies.management_gateway

    @staticmethod
    def _build_gateway_overrides(gateway_overrides_class: object, management_gateway: object) -> object:
        """
        构建插件核心运行时窄端口覆盖项。

        :param gateway_overrides_class: 插件核心运行时窄端口覆盖项类
        :param management_gateway: 插件管理运行时适配器
        :return: 插件核心运行时窄端口覆盖项
        """
        return gateway_overrides_class(
            config_gateway=management_gateway,
            audit_gateway=management_gateway,
            state_query_gateway=management_gateway,
            migration_history_gateway=management_gateway,
            purge_plan_gateway=management_gateway,
            lifecycle_state_gateway=management_gateway,
            lifecycle_uow_gateway=management_gateway,
            migration_execution_gateway=management_gateway,
        )

    def _resolve_model_gateway(self) -> object:
        """
        解析插件核心运行时模型工厂网关。

        :return: 插件核心运行时模型工厂网关
        """
        if self.dependencies.model_gateway is None:
            self._resolve_management_gateway()
        return self.dependencies.model_gateway

    def _resolve_command_gateway(self) -> object:
        """
        解析插件核心运行时命令执行网关。

        :return: 插件核心运行时命令执行网关
        """
        if self.dependencies.command_gateway is None:
            self._resolve_management_gateway()
        return self.dependencies.command_gateway

    def _resolve_lifecycle_lock(self) -> object:
        """
        解析插件核心生命周期操作锁。

        :return: 插件核心生命周期操作锁
        """
        if self.dependencies.lifecycle_lock is not None:
            return self.dependencies.lifecycle_lock
        lifecycle_lock = self.plugin_gateway.get_core_lifecycle_lock()
        self.dependencies = replace(self.dependencies, lifecycle_lock=lifecycle_lock)
        return lifecycle_lock

    def _build_exception_payload(self, message: str, exc: Exception) -> dict[str, object]:
        """
        构建 CLI 插件运行时异常负载。

        :param message: 异常场景提示
        :param exc: 异常对象
        :return: 异常负载
        """
        return CliPluginRuntimeExceptionPayload(
            self.plugin_gateway.build_exception_payload(message, exc),
            failure_code=self.runtime_error_code,
        ).to_payload()

    def lock_plugin_dependencies(
        self,
        plugin_id: str,
        *,
        output_path: str = '',
        offline_dir: str = '',
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """
        生成插件依赖锁文件模板。

        :param plugin_id: 插件ID
        :param output_path: 输出锁文件路径
        :param offline_dir: 离线制品根目录
        :param dry_run: 是否仅预演
        :param overwrite: 是否覆盖已有文件
        :return: 插件依赖锁文件模板负载
        """
        try:
            runtime_environment = self._resolve_runtime_environment()
            discovered_plugin = self._find_discovered_plugin(plugin_id)
            if discovered_plugin is None:
                return PluginDependencyLockPayloadBuilder.build_not_found_payload(plugin_id)

            backend_root = Path(runtime_environment.get_backend_dir())
            resolved_output_path = self._resolve_lockfile_output_path(
                backend_root,
                discovered_plugin.backend_path,
                output_path,
            )
            lockfile_template = PluginDependencyLockfileTemplateBuilder.build(
                discovered_plugin.manifest,
                offline_dir=offline_dir or None,
            )
            if resolved_output_path.exists() and not overwrite and not dry_run:
                return PluginDependencyLockPayloadBuilder.build_exists_payload(plugin_id, resolved_output_path)

            written = False
            overwritten = resolved_output_path.exists()
            if not dry_run:
                resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
                resolved_output_path.write_text(lockfile_template.to_yaml(), encoding='utf-8')
                written = True

            return PluginDependencyLockPayloadBuilder.build_success_payload(
                plugin_id,
                lockfile_template,
                resolved_output_path,
                dry_run=dry_run,
                written=written,
                overwritten=overwritten and written,
            )
        except Exception as exc:
            return self._build_exception_payload('生成插件依赖锁文件模板失败', exc)

    def _find_discovered_plugin(self, plugin_id: str) -> Any | None:
        """
        根据插件ID发现本地插件。

        :param plugin_id: 插件ID
        :return: 已发现插件
        """
        from plugins.core.discovery.scanner import PluginScanner  # noqa: PLC0415

        runtime_environment = self._resolve_runtime_environment()
        return next(
            (
                discovered_plugin
                for discovered_plugin in PluginScanner(runtime_environment.get_backend_plugins_dir()).discover()
                if discovered_plugin.manifest.id == plugin_id
            ),
            None,
        )

    @staticmethod
    def _resolve_lockfile_output_path(backend_root: Path, plugin_path: Path, output_path: str) -> Path:
        """
        解析锁文件输出路径。

        :param backend_root: 后端项目根目录
        :param plugin_path: 插件目录
        :param output_path: 用户指定输出路径
        :return: 输出路径
        """
        if not output_path:
            return plugin_path / 'plugin.lock.yaml'
        return CliPluginRuntimeService._resolve_backend_output_path(backend_root, output_path)

    def generate_plugin_dependency_allowlist_example(
        self,
        *,
        output_path: str = '',
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """
        生成插件依赖允许列表示例。

        :param output_path: 输出允许列表路径
        :param dry_run: 是否仅预演
        :param overwrite: 是否覆盖已有文件
        :return: 允许列表示例负载
        """
        try:
            runtime_environment = self._resolve_runtime_environment()
            backend_root = Path(runtime_environment.get_backend_dir())
            resolved_output_path = self._resolve_allowlist_example_output_path(backend_root, output_path)
            if resolved_output_path.exists() and not overwrite and not dry_run:
                return PluginDependencyAllowlistExamplePayloadBuilder.build_exists_payload(resolved_output_path)

            written = False
            overwritten = resolved_output_path.exists()
            if not dry_run:
                resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
                resolved_output_path.write_text(PLUGIN_DEPENDENCY_ALLOWLIST_EXAMPLE_YAML, encoding='utf-8')
                written = True

            return PluginDependencyAllowlistExamplePayloadBuilder.build_success_payload(
                resolved_output_path,
                allowlist_text=PLUGIN_DEPENDENCY_ALLOWLIST_EXAMPLE_YAML,
                dry_run=dry_run,
                written=written,
                overwritten=overwritten and written,
            )
        except Exception as exc:
            return self._build_exception_payload('生成插件依赖允许列表示例失败', exc)

    @staticmethod
    def _resolve_allowlist_example_output_path(backend_root: Path, output_path: str) -> Path:
        """
        解析允许列表示例输出路径。

        :param backend_root: 后端项目根目录
        :param output_path: 用户指定输出路径
        :return: 输出路径
        """
        if not output_path:
            return backend_root / 'config' / 'plugin_dependency_allowlist.yaml'
        return CliPluginRuntimeService._resolve_backend_output_path(backend_root, output_path)

    @staticmethod
    def _resolve_backend_output_path(backend_root: Path, output_path: str) -> Path:
        """
        解析 CLI 输出路径，并限制在后端项目目录内。

        :param backend_root: 后端项目根目录
        :param output_path: 用户指定输出路径
        :return: 规范化后的输出路径
        """
        raw_output_path = Path(output_path)
        resolved_backend_root = backend_root.resolve(strict=False)
        resolved_output_path = (
            raw_output_path if raw_output_path.is_absolute() else resolved_backend_root / raw_output_path
        ).resolve(strict=False)
        try:
            resolved_output_path.relative_to(resolved_backend_root)
        except ValueError as exc:
            raise ValueError(f'输出路径必须位于后端项目目录内：{output_path}') from exc
        return resolved_output_path

    def test_plugin(
        self,
        plugin_id: str,
        *,
        keyword: str = '',
        maxfail: int = 0,
        quiet: bool = False,
        frontend_build: bool = False,
    ) -> dict[str, object]:
        """
        执行插件测试样例。

        :param plugin_id: 插件ID
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: 最大失败数，0 表示不限制
        :param quiet: 是否启用简洁输出
        :param frontend_build: 是否执行前端构建验收
        :return: 插件测试执行结果负载
        """
        try:
            runtime_environment = self._resolve_runtime_environment()
            command_gateway = self._resolve_command_gateway()
            backend_root = Path(runtime_environment.get_backend_dir())
            frontend_root = Path(runtime_environment.get_frontend_dir())
            test_plan_builder = PluginTestPlanBuilder(
                backend_root=backend_root,
                frontend_root=frontend_root,
                python_executable=runtime_environment.get_python_executable(),
                timeout=PYTEST_COMMAND_TIMEOUT_SECONDS,
            )
            targets = test_plan_builder.build(
                plugin_id,
                keyword=keyword,
                maxfail=maxfail,
                quiet=quiet,
                frontend_build=frontend_build,
            )
            if not targets:
                return PluginTestPayloadBuilder.with_exit_code(
                    PluginTestPayloadBuilder.build_missing_payload(
                        plugin_id,
                        test_plan_builder.expected_paths(plugin_id),
                    ),
                    success_code=self.success_code,
                    failure_code=self.runtime_error_code,
                )

            results = []
            for target in targets:
                completed = command_gateway.run_command(
                    target.command,
                    str(target.workdir),
                    timeout=target.timeout,
                )
                results.append(PluginTestPayloadBuilder.build_result_item(target, completed))

            return PluginTestPayloadBuilder.with_exit_code(
                PluginTestPayloadBuilder.build_execution_payload(
                    plugin_id,
                    keyword=keyword,
                    maxfail=maxfail,
                    quiet=quiet,
                    frontend_build=frontend_build,
                    results=results,
                ),
                success_code=self.success_code,
                failure_code=self.runtime_error_code,
            )
        except Exception as exc:
            return self._build_exception_payload('插件测试执行失败', exc)

    def create_plugin(  # noqa: PLR0913
        self,
        plugin_id: str,
        *,
        template: str = 'full-stack',
        backend: bool = True,
        frontend: bool = True,
        migration: bool = True,
        seed: bool = True,
        job: bool = True,
        config: bool = True,
        test: bool = True,
        frontend_version: str = 'auto',
        dry_run: bool = False,
    ) -> dict[str, object]:
        """
        创建插件开发模板。

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
        :param dry_run: 是否仅预演
        :return: 插件创建结果负载
        """
        try:
            runtime_environment = self._resolve_runtime_environment()
            scaffold = PluginScaffoldBuilder(
                Path(runtime_environment.get_backend_dir()),
                frontend_root=Path(runtime_environment.get_frontend_dir()),
            )
            scaffold_plan = scaffold.build_plan(
                plugin_id,
                template=template,
                backend=backend,
                frontend=frontend,
                migration=migration,
                seed=seed,
                job=job,
                config=config,
                test=test,
                frontend_version=frontend_version,
            )
            if scaffold_plan['conflicts']:
                return PluginScaffoldBuilder.build_conflict_payload(
                    plugin_id,
                    scaffold_plan,
                    dry_run=dry_run,
                    failure_code=self.runtime_error_code,
                )
            if not dry_run:
                scaffold.apply_plan(scaffold_plan)

            return PluginScaffoldBuilder.build_success_payload(plugin_id, scaffold_plan, dry_run=dry_run)
        except Exception as exc:
            return self._build_exception_payload('创建插件模板失败', exc)


PLUGIN_RUNTIME = CliPluginRuntimeService()
