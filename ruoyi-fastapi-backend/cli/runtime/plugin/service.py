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
    state_gateway: object | None = None
    model_gateway: object | None = None
    command_gateway: object | None = None
    lifecycle_lock: object | None = None


class CliPluginRuntimeService:
    """
    插件 CLI 运行时服务。

    该服务继承共享插件运行时能力，并补充仅 CLI 使用的开发命令能力，
    例如插件测试执行和插件模板创建。
    """

    def __init__(
        self,
        *,
        success_code: int = SUCCESS,
        runtime_error_code: int = RUNTIME_ERROR,
        runtime_environment: object | None = None,
        dependency_checker: object | None = None,
        state_gateway: object | None = None,
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
        :param state_gateway: 插件管理状态网关
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
            state_gateway=state_gateway,
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
            self._core_runtime = runtime_service_class(
                runtime_environment=self._resolve_runtime_environment(),
                dependency_checker=self.dependencies.dependency_checker,
                state_gateway=self._resolve_state_gateway(),
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

    def _resolve_management_gateway(self) -> object:
        """
        解析插件管理运行时适配器。

        :return: 插件管理运行时适配器
        """
        management_gateway = self.plugin_gateway.get_management_runtime_gateway()
        self.dependencies = replace(
            self.dependencies,
            state_gateway=self.dependencies.state_gateway or management_gateway,
            model_gateway=self.dependencies.model_gateway or management_gateway,
            command_gateway=self.dependencies.command_gateway or management_gateway,
        )
        return management_gateway

    def _resolve_state_gateway(self) -> object:
        """
        解析插件核心运行时状态网关。

        :return: 插件核心运行时状态网关
        """
        if self.dependencies.state_gateway is None:
            self._resolve_management_gateway()
        return self.dependencies.state_gateway

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

    def _delegate(self, method_name: str, *args: object, **kwargs: object) -> Any:
        """
        调用插件核心运行时方法。

        :param method_name: 核心运行时方法名
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 核心运行时方法返回值
        """
        return getattr(self.core_runtime, method_name)(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """
        将未在 CLI runtime 定义的插件能力转发给核心运行时。

        :param name: 属性名
        :return: 核心运行时属性
        """
        if name.startswith('_') or '_core_runtime' not in self.__dict__:
            raise AttributeError(name)
        return getattr(self.core_runtime, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """
        设置 CLI runtime 属性，并在必要时同步给已创建的核心运行时。

        :param name: 属性名
        :param value: 属性值
        :return: None
        """
        object.__setattr__(self, name, value)
        if name.startswith('_') or name in {
            'success_code',
            'runtime_error_code',
            'plugin_gateway',
            'dependencies',
        }:
            return
        core_runtime = self.__dict__.get('_core_runtime')
        if core_runtime is not None:
            setattr(core_runtime, name, value)

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

    def list_plugins(self) -> dict[str, Any]:
        """
        查看本地插件列表。

        :return: 插件列表负载
        """
        return self._delegate('list_plugins')

    async def get_plugin_info_with_state(self, plugin_id: str) -> dict[str, Any]:
        """
        查看插件详情与管理状态。

        :param plugin_id: 插件ID
        :return: 插件详情负载
        """
        return await self._delegate('get_plugin_info_with_state', plugin_id)

    def check_plugin(self, plugin_id: str | None = None) -> dict[str, Any]:
        """
        检查插件状态。

        :param plugin_id: 插件ID
        :return: 插件检查负载
        """
        return self._delegate('check_plugin', plugin_id)

    def check_plugin_dependencies(self, plugin_id: str) -> dict[str, Any]:
        """
        检查插件依赖。

        :param plugin_id: 插件ID
        :return: 插件依赖检查负载
        """
        return self._delegate('check_plugin_dependencies', plugin_id)

    async def precheck_plugin_operation(self, plugin_id: str, operation: str) -> dict[str, Any]:
        """
        执行插件操作预检。

        :param plugin_id: 插件ID
        :param operation: 操作类型
        :return: 插件操作预检负载
        """
        return await self._delegate('precheck_plugin_operation', plugin_id, operation)

    async def health_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        执行插件健康检查。

        :param plugin_id: 插件ID
        :return: 插件健康检查负载
        """
        return await self._delegate('health_plugin', plugin_id)

    async def diagnose_plugin(self, plugin_id: str) -> dict[str, Any]:
        """
        生成插件诊断信息。

        :param plugin_id: 插件ID
        :return: 插件诊断负载
        """
        return await self._delegate('diagnose_plugin', plugin_id)

    def generate_plugin_docs(self, plugin_id: str) -> dict[str, Any]:
        """
        生成插件文档片段。

        :param plugin_id: 插件ID
        :return: 插件文档负载
        """
        return self._delegate('generate_plugin_docs', plugin_id)

    def plan_plugins(self, operation: str, plugin_ids: list[str] | None = None) -> dict[str, Any]:
        """
        生成插件批量操作计划。

        :param operation: 操作类型
        :param plugin_ids: 插件ID列表
        :return: 插件批量操作计划负载
        """
        return self._delegate('plan_plugins', operation, plugin_ids)

    async def batch_plugins(
        self,
        operation: str,
        plugin_ids: list[str] | None = None,
        *,
        dry_run: bool = False,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        """
        执行插件批量操作。

        :param operation: 操作类型
        :param plugin_ids: 插件ID列表
        :param dry_run: 是否仅预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: 插件批量操作负载
        """
        if '_execute_batch_plugin_item' in self.__dict__:
            self.core_runtime._execute_batch_plugin_item = self.__dict__['_execute_batch_plugin_item']
        return await self._delegate(
            'batch_plugins',
            operation,
            plugin_ids,
            dry_run=dry_run,
            continue_on_error=continue_on_error,
        )

    def install_plugin_dependencies(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        policy_config: object | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """
        安装插件依赖。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :param policy_config: 依赖安装策略配置
        :param confirmed: 是否已显式确认
        :return: 插件依赖安装负载
        """
        return self._delegate(
            'install_plugin_dependencies',
            plugin_id,
            dry_run=dry_run,
            policy_config=policy_config,
            confirmed=confirmed,
        )

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
        resolved_output_path = Path(output_path)
        if resolved_output_path.is_absolute():
            return resolved_output_path
        return backend_root / resolved_output_path

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
        resolved_output_path = Path(output_path)
        if resolved_output_path.is_absolute():
            return resolved_output_path
        return backend_root / resolved_output_path

    async def install_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        安装插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件安装负载
        """
        return await self._delegate('install_plugin', plugin_id, dry_run=dry_run)

    async def upgrade_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        升级插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件升级负载
        """
        return await self._delegate('upgrade_plugin', plugin_id, dry_run=dry_run)

    async def set_plugin_enabled(self, plugin_id: str, *, enabled: bool, dry_run: bool = False) -> dict[str, Any]:
        """
        设置插件启停状态。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param dry_run: 是否仅预演
        :return: 插件启停状态负载
        """
        return await self._delegate('set_plugin_enabled', plugin_id, enabled=enabled, dry_run=dry_run)

    async def uninstall_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        卸载插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件卸载负载
        """
        return await self._delegate('uninstall_plugin', plugin_id, dry_run=dry_run)

    async def purge_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        物理清理插件。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 插件物理清理负载
        """
        return await self._delegate('purge_plugin', plugin_id, dry_run=dry_run)

    async def list_plugin_migrations(self, plugin_id: str, status: str | None = None) -> dict[str, Any]:
        """
        查询插件 migration 历史。

        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: 插件 migration 历史负载
        """
        return await self._delegate('list_plugin_migrations', plugin_id, status)

    async def mark_plugin_migration_success(
        self,
        plugin_id: str,
        migration_path: str,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """
        人工标记插件 migration 为成功。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param note: 人工恢复备注
        :return: 插件 migration 状态标记负载
        """
        return await self._delegate('mark_plugin_migration_success', plugin_id, migration_path, note=note)

    async def mark_plugin_migration_failed(
        self,
        plugin_id: str,
        migration_path: str,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        """
        人工标记插件 migration 为失败。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param note: 人工恢复备注
        :return: 插件 migration 状态标记负载
        """
        return await self._delegate('mark_plugin_migration_failed', plugin_id, migration_path, note=note)

    async def get_plugin_config(self, plugin_id: str) -> dict[str, Any]:
        """
        读取插件配置。

        :param plugin_id: 插件ID
        :return: 插件配置负载
        """
        return await self._delegate('get_plugin_config', plugin_id)

    async def export_plugin_config(self, plugin_id: str, *, reveal_secret: bool = False) -> dict[str, Any]:
        """
        导出插件配置。

        :param plugin_id: 插件ID
        :param reveal_secret: 是否显示敏感值
        :return: 插件配置导出负载
        """
        return await self._delegate('export_plugin_config', plugin_id, reveal_secret=reveal_secret)

    async def import_plugin_config(self, plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """
        导入插件配置。

        :param plugin_id: 插件ID
        :param values: 配置键值
        :return: 插件配置导入负载
        """
        return await self._delegate('import_plugin_config', plugin_id, values)

    async def set_plugin_config(self, plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """
        更新插件配置。

        :param plugin_id: 插件ID
        :param values: 配置键值
        :return: 插件配置更新负载
        """
        return await self._delegate('set_plugin_config', plugin_id, values)

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

    def create_plugin(
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
