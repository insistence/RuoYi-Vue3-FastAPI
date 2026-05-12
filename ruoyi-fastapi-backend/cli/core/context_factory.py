import logging
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from cli.context import CLI_CONTEXT_BUILDER, CliContext, CliContextBuilder
from cli.guards import (
    DEFAULT_DANGEROUS_COMMAND_GUARD,
    DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY,
    DangerousCommandGuardService,
    DangerousCommandRuleRegistry,
)
from cli.output import OutputRenderer


@dataclass
class CliRuntimeState:
    """
    CLI 运行期状态。

    :param logs_suppressed: 当前进程日志是否已切换为静默模式
    """

    logs_suppressed: bool = False
    sqlalchemy_logs_suppressed: bool = False

    def get_logger(self) -> Any:
        """
        获取 CLI 使用的日志对象。

        :return: 日志对象
        """
        return import_module('utils.log_util').logger

    def suppress_logs(self) -> None:
        """
        关闭 CLI 进程中的终端日志输出。

        :return: None
        """
        if self.logs_suppressed:
            return
        self.get_logger().remove()
        self.logs_suppressed = True

    def suppress_sqlalchemy_logs(self) -> None:
        """
        关闭 CLI 进程中的 SQLAlchemy 终端 SQL 日志输出。

        该逻辑同时处理两类来源：

        1. 将 `config.env.DataBaseConfig.db_echo` 强制关闭，避免后续新建 Engine 时
           继续打开 SQLAlchemy echo。
        2. 将已知 SQLAlchemy logger 级别提升到 WARNING，避免已有 logger 配置把
           `INFO sqlalchemy.engine.Engine ...` 继续打到标准输出。

        :return: None
        """
        if self.sqlalchemy_logs_suppressed:
            return
        env_module = import_module('config.env')
        database_config = getattr(env_module, 'DataBaseConfig', None)
        if database_config is not None and hasattr(database_config, 'db_echo'):
            database_config.db_echo = False
        for logger_name in (
            'sqlalchemy',
            'sqlalchemy.engine',
            'sqlalchemy.engine.Engine',
            'sqlalchemy.pool',
        ):
            logging.getLogger(logger_name).setLevel(logging.WARNING)
        self.sqlalchemy_logs_suppressed = True


@dataclass
class CliLogPolicy:
    """
    CLI 日志策略服务。

    该对象负责在上下文构建前应用统一的日志输出策略，
    将“是否静默日志”这一策略从上下文工厂主体中拆出。

    :param runtime_state: CLI 运行期状态对象
    """

    runtime_state: CliRuntimeState

    def prepare_regular_command(self) -> None:
        """
        为普通 CLI 命令应用默认日志策略。

        :return: None
        """
        self.runtime_state.suppress_logs()
        self.runtime_state.suppress_sqlalchemy_logs()


@dataclass
class DangerousCommandContextSupport:
    """
    危险命令上下文支持服务。

    该对象负责危险命令规则查询、保护执行与拒绝结果收口，
    让上下文工厂本体只保留装配职责。

    :param dangerous_command_rule_registry: 危险命令规则注册表
    :param dangerous_command_guard_service: 危险命令保护执行服务
    :param output_renderer: 输出渲染器
    """

    dangerous_command_rule_registry: DangerousCommandRuleRegistry
    dangerous_command_guard_service: DangerousCommandGuardService
    output_renderer: OutputRenderer

    def guard_context(self, ctx: CliContext, *, command_name: str) -> CliContext:
        """
        对危险命令上下文执行统一保护。

        :param ctx: 已构建的 CLI 上下文
        :param command_name: 命令唯一标识
        :return: 通过保护后的 CLI 上下文
        """
        rule = self.dangerous_command_rule_registry.require_rule(command_name)
        guard_result = self.dangerous_command_guard_service.guard(ctx, rule=rule)
        if guard_result is not None:
            self.output_renderer.complete_command(guard_result, ctx)
        return ctx


@dataclass
class CliContextFactory:
    """
    统一构建 CLI 命令上下文。

    :param runtime_state: CLI 运行期状态对象
    :param output_renderer: 输出渲染器
    :param cli_context_builder: CLI 上下文构建器
    :param dangerous_command_rule_registry: 危险命令规则注册表
    :param dangerous_command_guard_service: 危险命令保护执行服务
    """

    runtime_state: CliRuntimeState = field(default_factory=CliRuntimeState)
    output_renderer: OutputRenderer = field(default_factory=OutputRenderer)
    cli_context_builder: CliContextBuilder = field(default_factory=lambda: CLI_CONTEXT_BUILDER)
    dangerous_command_rule_registry: DangerousCommandRuleRegistry = field(
        default_factory=lambda: DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY
    )
    dangerous_command_guard_service: DangerousCommandGuardService = field(
        default_factory=lambda: DEFAULT_DANGEROUS_COMMAND_GUARD
    )
    _log_policy: CliLogPolicy | None = field(default=None, init=False, repr=False)
    _dangerous_command_support: DangerousCommandContextSupport | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def get_log_policy(self) -> CliLogPolicy:
        """
        获取当前上下文工厂使用的日志策略服务。

        :return: CLI 日志策略服务
        """
        if self._log_policy is None:
            self._log_policy = CliLogPolicy(runtime_state=self.runtime_state)
        return self._log_policy

    def get_dangerous_command_support(self) -> DangerousCommandContextSupport:
        """
        获取当前上下文工厂使用的危险命令上下文支持服务。

        :return: 危险命令上下文支持服务
        """
        if self._dangerous_command_support is None:
            self._dangerous_command_support = DangerousCommandContextSupport(
                dangerous_command_rule_registry=self.dangerous_command_rule_registry,
                dangerous_command_guard_service=self.dangerous_command_guard_service,
                output_renderer=self.output_renderer,
            )
        return self._dangerous_command_support

    def build_regular(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> CliContext:
        """
        构建普通命令上下文。

        :param env: 运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :return: CLI 上下文
        """
        self.get_log_policy().prepare_regular_command()
        return self.cli_context_builder.build(env, output, allow_prod, yes, dry_run)

    def build_readonly(
        self,
        env: str,
        output: str,
    ) -> CliContext:
        """
        构建只读命令上下文。

        :param env: 运行环境
        :param output: 输出格式
        :return: CLI 上下文
        """
        return self.build_regular(env, output, False, False, False)

    def build_dangerous(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        command_name: str,
    ) -> CliContext:
        """
        构建危险命令上下文并执行统一保护。

        :param env: 运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param command_name: 命令唯一标识
        :return: CLI 上下文
        """
        ctx = self.build_regular(env, output, allow_prod, yes, dry_run)
        return self.get_dangerous_command_support().guard_context(ctx, command_name=command_name)
