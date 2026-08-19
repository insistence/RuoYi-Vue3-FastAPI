import importlib
import json
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

import click
import typer

from cli.core import DEFAULT_CORE_SERVICES, CliContextFactory, CliExecutionService
from cli.exit_codes import ARGUMENT_ERROR, DEPENDENCY_ERROR, RUNTIME_ERROR, SUCCESS
from plugins.core.validation.dependency_policy import DependencyInstallPolicyConfig

from .exporter import PluginCommandFileAdapter
from .options import (
    PluginCreateCommandOptions,
    PluginDependencyAllowlistExampleCommandOptions,
    PluginDependencyInstallCommandOptions,
    PluginDependencyLockCommandOptions,
)
from .payload import PluginCommandPayloadAdapter
from .presenter import PluginCommandPresenter

if TYPE_CHECKING:
    from cli.runtime.plugin.service import CliPluginRuntimeService
    from plugins.core.runtime.service import PluginRuntimeService

PluginDependencyOutputCallback = Callable[[str, str], None]


class PluginCommandController:
    """
    插件命令控制器。
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: PluginCommandPresenter | None = None,
        plugin_runtime: 'CliPluginRuntimeService | None' = None,
    ) -> None:
        """
        初始化插件命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 插件命令文本渲染器
        :param plugin_runtime: 插件运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or PluginCommandPresenter()
        self._plugin_runtime = plugin_runtime

    @property
    def plugin_runtime(self) -> 'CliPluginRuntimeService':
        """
        延迟获取插件 CLI 运行时服务。

        :return: 插件 CLI 运行时服务
        """
        if self._plugin_runtime is None:
            self._plugin_runtime = importlib.import_module('cli.runtime.plugin').PLUGIN_RUNTIME
        return self._plugin_runtime

    @property
    def core_runtime(self) -> 'PluginRuntimeService':
        """
        获取插件核心运行时服务。

        :return: 插件核心运行时服务
        """
        return self.plugin_runtime.core_runtime

    def list_plugins(self, env: str, output: str) -> None:
        """
        查看插件列表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.core_runtime.list_plugins_with_state())
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_list_text,
            failure_exit_code=RUNTIME_ERROR,
        )

    def _complete_plugin_payload(
        self,
        ctx: object,
        payload: dict[str, object],
        *,
        text_builder: object,
        success_exit_code: int = SUCCESS,
        failure_exit_code: int = DEPENDENCY_ERROR,
    ) -> None:
        """
        按插件 payload ok 字段统一完成命令输出。

        :param ctx: CLI上下文
        :param payload: 插件操作负载
        :param text_builder: 文本构造器
        :param success_exit_code: 成功退出码
        :param failure_exit_code: 失败退出码
        :return: None
        """
        payload = PluginCommandPayloadAdapter.adapt(payload)
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=text_builder,
            default_exit_code=self._resolve_plugin_exit_code(
                payload,
                success_exit_code=success_exit_code,
                failure_exit_code=failure_exit_code,
            ),
        )

    @staticmethod
    def _resolve_plugin_exit_code(
        payload: dict[str, object],
        *,
        success_exit_code: int,
        failure_exit_code: int,
    ) -> int:
        """
        按插件 payload 形状解析 CLI 退出码。

        :param payload: 插件操作负载
        :param success_exit_code: 成功退出码
        :param failure_exit_code: 业务失败退出码
        :return: CLI 退出码
        """
        if bool(payload.get('ok', False)):
            return success_exit_code
        if payload.get('error'):
            return RUNTIME_ERROR

        return failure_exit_code

    def plugin_info(self, plugin_id: str, env: str, output: str) -> None:
        """
        查看插件详情。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.core_runtime.get_plugin_info_with_state(plugin_id))
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_info_text,
            failure_exit_code=RUNTIME_ERROR,
        )

    def check_plugin(self, plugin_id: str | None, env: str, output: str) -> None:
        """
        检查插件依赖状态。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.core_runtime.check_plugin(plugin_id)
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_check_text,
        )

    def check_plugin_dependencies(self, plugin_id: str, env: str, output: str) -> None:
        """
        检查插件依赖。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.core_runtime.check_plugin_dependencies(plugin_id)
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_dependency_text,
        )

    def precheck_plugin(self, operation: str, plugin_id: str, env: str, output: str) -> None:
        """
        执行插件操作预检。

        :param operation: 预检操作类型
        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.core_runtime.precheck_plugin_operation(plugin_id, operation))
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_precheck_text,
        )

    def health_plugin(self, plugin_id: str, env: str, output: str) -> None:
        """
        执行插件健康检查。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.core_runtime.health_plugin(plugin_id))
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_health_text,
        )

    def diagnose_plugin(self, plugin_id: str, env: str, output: str, *, output_file: str = '') -> None:
        """
        生成插件诊断包。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param output_file: 诊断包 JSON 导出文件路径
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.core_runtime.diagnose_plugin(plugin_id))
        if output_file.strip():
            payload = PluginCommandFileAdapter.write_json_file(
                payload,
                output_file,
                failure_message='插件诊断包导出失败',
            )
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_diagnose_text,
        )

    def generate_plugin_docs(self, plugin_id: str, env: str, output: str, *, output_file: str = '') -> None:
        """
        生成插件 Markdown 文档片段。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param output_file: Markdown 文档导出文件路径
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.core_runtime.generate_plugin_docs(plugin_id)
        if output_file.strip():
            payload = PluginCommandFileAdapter.write_markdown_file(
                payload,
                output_file,
                content_key='markdown',
                failure_message='插件文档导出失败',
            )
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_docs_text,
        )

    def test_plugin(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        keyword: str = '',
        maxfail: int = 0,
        quiet: bool = False,
        frontend_build: bool = False,
    ) -> None:
        """
        执行插件测试。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param keyword: pytest 关键字过滤表达式
        :param maxfail: 最大失败数
        :param quiet: 是否启用简洁输出
        :param frontend_build: 是否执行前端构建验收
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.plugin_runtime.test_plugin(
            plugin_id,
            keyword=keyword,
            maxfail=maxfail,
            quiet=quiet,
            frontend_build=frontend_build,
        )
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_test_text,
        )

    def plan_plugins(self, operation: str, plugin_ids: list[str], env: str, output: str) -> None:
        """
        生成插件批量操作拓扑计划。

        :param operation: 计划操作类型
        :param plugin_ids: 插件ID列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.core_runtime.plan_plugins(operation, plugin_ids or None)
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_plan_text,
        )

    def batch_plugins(
        self,
        operation: str,
        plugin_ids: list[str],
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """
        按拓扑顺序批量执行插件操作。

        :param operation: 批量操作类型
        :param plugin_ids: 插件ID列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :param continue_on_error: 失败后是否继续执行后续插件
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='plugin batch',
        )
        payload = self.execution_service.run_async(
            self.core_runtime.batch_plugins(
                operation,
                plugin_ids or None,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_batch_text,
        )

    def install_plugin_dependencies(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        options: PluginDependencyInstallCommandOptions,
    ) -> None:
        """
        安装插件依赖。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param options: 依赖安装命令选项
        :return: None
        """
        ctx = self.context_factory.build_regular(
            env,
            output,
            options.allow_prod,
            options.yes,
            options.dry_run,
        )
        policy_config = DependencyInstallPolicyConfig.from_cli_environment(
            env=env,
            mode=options.policy_mode,
            allow_prod=options.allow_prod,
            allow_unlisted=options.allow_unlisted,
            lockfile_path=options.lockfile or None,
            allowlist_path=options.allowlist or None,
            offline_dir=options.offline_dir or None,
            require_lockfile=options.require_lockfile,
        )
        core_runtime = self.core_runtime
        output_callback = self._build_dependency_install_output_callback(ctx)
        if self._should_interactive_confirm_dependency_install(ctx, options):
            preview_payload = core_runtime.install_plugin_dependencies_from_cli(
                plugin_id,
                dry_run=True,
                policy_config=policy_config,
                confirmed=True,
            )
            preview_payload['env'] = ctx.env
            if self._dependency_install_policy_blocked(preview_payload):
                payload = core_runtime.install_plugin_dependencies_from_cli(
                    plugin_id,
                    dry_run=False,
                    policy_config=policy_config,
                    confirmed=True,
                    output_callback=output_callback,
                )
                payload['env'] = ctx.env
                self._complete_plugin_payload(
                    ctx,
                    payload,
                    text_builder=self.presenter.build_dependency_install_text,
                )
                return
            typer.echo(self.presenter.build_dependency_install_text(preview_payload))
            if not self._confirm_dependency_install(ctx.env):
                payload = self._build_dependency_install_cancel_payload(plugin_id, ctx.env, preview_payload)
                self._complete_plugin_payload(
                    ctx,
                    payload,
                    text_builder=self.presenter.build_dependency_install_text,
                )
                return
            confirmed = True
        else:
            confirmed = options.yes

        payload = core_runtime.install_plugin_dependencies_from_cli(
            plugin_id,
            dry_run=options.dry_run,
            policy_config=policy_config,
            confirmed=confirmed,
            output_callback=output_callback,
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_dependency_install_text,
        )

    @staticmethod
    def _build_dependency_install_output_callback(ctx: object) -> PluginDependencyOutputCallback | None:
        """
        为文本输出模式构建依赖安装实时输出回调。

        :param ctx: CLI上下文
        :return: 实时输出回调；非文本模式返回 None
        """
        if getattr(ctx, 'output', 'text') != 'text':
            return None

        def output_callback(kind: str, text: str) -> None:
            if text:
                typer.echo(text, nl=False, err=kind == 'stderr')

        return output_callback

    def lock_plugin_dependencies(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        options: PluginDependencyLockCommandOptions,
    ) -> None:
        """
        生成插件依赖锁文件模板。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param options: 依赖锁文件命令选项
        :return: None
        """
        ctx = self.context_factory.build_regular(
            env,
            output,
            False,
            True,
            options.dry_run,
        )
        payload = self.plugin_runtime.lock_plugin_dependencies(
            plugin_id,
            output_path=options.output_path,
            offline_dir=options.offline_dir,
            dry_run=options.dry_run,
            overwrite=options.overwrite,
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_dependency_lock_text,
        )

    def generate_plugin_dependency_allowlist_example(
        self,
        env: str,
        output: str,
        *,
        options: PluginDependencyAllowlistExampleCommandOptions,
    ) -> None:
        """
        生成插件依赖允许列表示例。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param options: 允许列表示例命令选项
        :return: None
        """
        ctx = self.context_factory.build_regular(
            env,
            output,
            False,
            True,
            options.dry_run,
        )
        payload = self.plugin_runtime.generate_plugin_dependency_allowlist_example(
            output_path=options.output_path,
            dry_run=options.dry_run,
            overwrite=options.overwrite,
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_dependency_allowlist_example_text,
        )

    @staticmethod
    def _should_interactive_confirm_dependency_install(
        ctx: object,
        options: PluginDependencyInstallCommandOptions,
    ) -> bool:
        """
        判断插件依赖安装是否应进入 CLI 交互确认流程。

        :param ctx: CLI上下文
        :param options: 依赖安装命令选项
        :return: 是否进入交互确认
        """
        return (
            not options.yes and not options.dry_run and getattr(ctx, 'output', 'text') == 'text' and sys.stdin.isatty()
        )

    @staticmethod
    def _dependency_install_policy_blocked(payload: dict[str, object]) -> bool:
        """
        判断依赖安装预览中的策略是否已阻断真实安装。

        :param payload: 依赖安装预览负载
        :return: 是否被策略阻断
        """
        policy = payload.get('policy')
        return isinstance(policy, dict) and policy.get('allowed') is False

    @staticmethod
    def _confirm_dependency_install(env: str) -> bool:
        """
        询问用户是否执行插件依赖安装。

        :param env: 当前运行环境
        :return: 是否确认执行
        """
        try:
            return bool(typer.confirm(f'确认执行插件依赖安装吗？ 当前环境：{env}', default=False))
        except (click.Abort, EOFError, KeyboardInterrupt):
            return False

    @staticmethod
    def _build_dependency_install_cancel_payload(
        plugin_id: str,
        env: str,
        preview_payload: dict[str, object],
    ) -> dict[str, object]:
        """
        构建用户取消插件依赖安装的负载。

        :param plugin_id: 插件ID
        :param env: 当前运行环境
        :param preview_payload: 安装预览负载
        :return: 取消安装负载
        """
        return {
            'ok': False,
            'message': '已取消插件依赖安装',
            'pluginId': plugin_id,
            'env': env,
            'dryRun': False,
            'preview': preview_payload,
        }

    def create_plugin(
        self,
        plugin_id: str,
        env: str,
        output: str,
        options: PluginCreateCommandOptions,
    ) -> None:
        """
        创建插件开发模板。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param options: 插件创建命令选项
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        if options.backend_only and options.frontend_only:
            self.execution_service.complete_payload_with_text(
                ctx,
                {
                    'ok': False,
                    'message': '--backend-only 和 --frontend-only 不能同时使用',
                },
                text_builder=self.presenter.build_create_text,
                default_exit_code=ARGUMENT_ERROR,
            )
            return

        payload = self.plugin_runtime.create_plugin(
            plugin_id,
            template=options.template,
            backend=not options.frontend_only,
            frontend=not options.backend_only,
            migration=not options.no_migration,
            seed=not options.no_seed,
            job=not options.no_job,
            config=not options.no_config,
            test=not options.no_test,
            frontend_version=options.frontend_version,
            dry_run=options.dry_run,
        )
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_create_text,
            default_exit_code=SUCCESS,
        )

    def install_plugin(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        安装插件。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='plugin install',
        )
        payload = self.execution_service.run_async(self.core_runtime.install_plugin(plugin_id, dry_run=dry_run))
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_install_text,
        )

    def upgrade_plugin(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        升级插件。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='plugin upgrade',
        )
        payload = self.execution_service.run_async(self.core_runtime.upgrade_plugin(plugin_id, dry_run=dry_run))
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_upgrade_text,
        )

    def set_plugin_enabled(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        enabled: bool,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        更新插件启停状态。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param enabled: 是否启用
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :return: None
        """
        command_name = 'plugin enable' if enabled else 'plugin disable'
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name=command_name,
        )
        payload = self.execution_service.run_async(
            self.core_runtime.set_plugin_enabled(plugin_id, enabled=enabled, dry_run=dry_run)
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_enabled_text,
        )

    def uninstall_plugin(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        安全卸载插件。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='plugin uninstall',
        )
        payload = self.execution_service.run_async(self.core_runtime.uninstall_plugin(plugin_id, dry_run=dry_run))
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_enabled_text,
        )

    def purge_plugin(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        物理清理插件平台元数据。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='plugin purge',
        )
        payload = self.execution_service.run_async(self.core_runtime.purge_plugin(plugin_id, dry_run=dry_run))
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_purge_text,
        )

    def list_plugin_migrations(self, plugin_id: str, status: str | None, env: str, output: str) -> None:
        """
        查看插件 migration 历史。

        :param plugin_id: 插件ID
        :param status: 执行状态
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.core_runtime.list_plugin_migrations(plugin_id, status))
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_migration_list_text,
        )

    def mark_plugin_migration_success(
        self,
        plugin_id: str,
        migration_path: str,
        env: str,
        output: str,
        *,
        note: str,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        人工标记插件 migration 为成功。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param note: 人工恢复备注
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            False,
            command_name='plugin mark-success',
        )
        payload = self.execution_service.run_async(
            self.core_runtime.mark_plugin_migration_success(plugin_id, migration_path, note=note or None)
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_migration_mark_text,
        )

    def mark_plugin_migration_failed(
        self,
        plugin_id: str,
        migration_path: str,
        env: str,
        output: str,
        *,
        note: str,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        人工标记插件 migration 为失败。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param note: 人工恢复备注
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            False,
            command_name='plugin mark-failed',
        )
        payload = self.execution_service.run_async(
            self.core_runtime.mark_plugin_migration_failed(plugin_id, migration_path, note=note or None)
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_migration_mark_text,
        )

    def plugin_config(
        self,
        plugin_id: str,
        action: str,
        pairs: list[str],
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        reveal_secret: bool = False,
        output_file: str = '',
        input_file: str = '',
    ) -> None:
        """
        查看或设置插件配置。

        :param plugin_id: 插件ID
        :param action: 操作类型
        :param pairs: 配置键值列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param reveal_secret: 是否导出敏感配置明文
        :param output_file: 配置导出 JSON 文件路径
        :param input_file: 配置导入 JSON 文件路径
        :return: None
        """
        if action == 'get':
            self._get_plugin_config(plugin_id, env, output)
            return

        if action == 'export':
            self._export_plugin_config(
                plugin_id,
                env,
                output,
                allow_prod=allow_prod,
                yes=yes,
                reveal_secret=reveal_secret,
                output_file=output_file,
            )
            return

        if action == 'import':
            self._import_plugin_config(
                plugin_id,
                env,
                output,
                allow_prod=allow_prod,
                yes=yes,
                input_file=input_file,
            )
            return

        if action != 'set':
            ctx = self.context_factory.build_readonly(env, output)
            self.execution_service.complete_payload_with_text(
                ctx,
                {
                    'ok': False,
                    'message': '插件配置操作只支持 get、set、export 或 import',
                    'pluginId': plugin_id,
                },
                text_builder=self.presenter.build_config_text,
                default_exit_code=ARGUMENT_ERROR,
            )
            return

        self._set_plugin_config(
            plugin_id,
            pairs,
            env,
            output,
            allow_prod=allow_prod,
            yes=yes,
        )

    def _get_plugin_config(self, plugin_id: str, env: str, output: str) -> None:
        """
        读取插件配置。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.core_runtime.get_plugin_config(plugin_id))
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_config_text,
        )

    def _export_plugin_config(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        reveal_secret: bool,
        output_file: str,
    ) -> None:
        """
        导出插件配置。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param reveal_secret: 是否导出敏感配置明文
        :param output_file: 配置导出 JSON 文件路径
        :return: None
        """
        ctx = (
            self.context_factory.build_dangerous(
                env,
                output,
                allow_prod,
                yes,
                dry_run=True,
                command_name='plugin config export',
            )
            if reveal_secret
            else self.context_factory.build_readonly(env, output)
        )
        payload = self.execution_service.run_async(
            self.core_runtime.export_plugin_config(plugin_id, reveal_secret=reveal_secret)
        )
        if output_file.strip():
            payload = PluginCommandFileAdapter.write_json_file(
                payload,
                output_file,
                failure_message='插件配置导出失败',
            )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_config_text,
        )

    def _import_plugin_config(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
        input_file: str,
    ) -> None:
        """
        导入插件配置。

        :param plugin_id: 插件ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param input_file: 配置导入 JSON 文件路径
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run=False,
            command_name='plugin config import',
        )
        values_payload = PluginCommandFileAdapter.read_config_import_file(input_file)
        if not values_payload.get('ok', False):
            self.execution_service.complete_payload_with_text(
                ctx,
                {'pluginId': plugin_id, **values_payload},
                text_builder=self.presenter.build_config_text,
                default_exit_code=ARGUMENT_ERROR,
            )
            return
        payload = self.execution_service.run_async(
            self.core_runtime.import_plugin_config(plugin_id, values_payload.get('values', {}))
        )
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_config_text,
        )

    def _set_plugin_config(
        self,
        plugin_id: str,
        pairs: list[str],
        env: str,
        output: str,
        *,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        更新插件配置。

        :param plugin_id: 插件ID
        :param pairs: 配置键值列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run=False,
            command_name='plugin config set',
        )
        try:
            values = self._parse_config_pairs(pairs)
        except ValueError as exc:
            self.execution_service.complete_payload_with_text(
                ctx,
                {'ok': False, 'message': str(exc), 'pluginId': plugin_id},
                text_builder=self.presenter.build_config_text,
                default_exit_code=ARGUMENT_ERROR,
            )
            return
        payload = self.execution_service.run_async(self.core_runtime.set_plugin_config(plugin_id, values))
        payload['env'] = ctx.env
        self._complete_plugin_payload(
            ctx,
            payload,
            text_builder=self.presenter.build_config_text,
        )

    @staticmethod
    def _parse_config_pairs(pairs: list[str]) -> dict[str, str]:
        """
        解析配置键值参数。

        :param pairs: 配置键值参数列表
        :return: 配置键值字典
        """
        values = {}
        for pair in pairs:
            if '=' not in pair:
                raise ValueError(f'配置参数必须使用 key=value 格式：{pair}')
            key, value = pair.split('=', 1)
            try:
                values[key] = json.loads(value)
            except json.JSONDecodeError:
                values[key] = value
        return values
