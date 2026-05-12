import sys
from dataclasses import dataclass, field
from typing import Literal

import click
import typer

from cli.context import CliContext
from cli.exit_codes import GUARD_REJECTED
from cli.output import CommandResult

DangerousCommandRiskLevel = Literal['high', 'normal']


@dataclass(frozen=True)
class DangerousCommandRule:
    """
    危险命令保护规则。

    :param command_name: 命令唯一标识
    :param risk_level: 风险级别
    :param supports_dry_run: 是否支持演练执行
    """

    command_name: str
    risk_level: DangerousCommandRiskLevel
    supports_dry_run: bool


@dataclass(frozen=True)
class DangerousCommandRuleRegistry:
    """
    危险命令规则注册表。

    该注册表负责维护 CLI 内所有危险命令的风险元数据，并提供查询与
    强制获取能力，作为上下文工厂、风险元数据与测试的统一入口。

    :param rules: 按命令名索引的危险命令规则表
    """

    rules: dict[str, DangerousCommandRule]

    def get_rule(self, command_name: str) -> DangerousCommandRule | None:
        """
        获取指定命令的危险命令规则。

        :param command_name: 命令唯一标识
        :return: 命令规则，不存在时返回 None
        """
        return self.rules.get(command_name)

    def require_rule(self, command_name: str) -> DangerousCommandRule:
        """
        获取指定命令的危险命令规则，不存在时抛出异常。

        :param command_name: 命令唯一标识
        :return: 命令规则
        :raises ValueError: 命令未注册危险命令规则时抛出
        """
        rule = self.get_rule(command_name)
        if rule is None:
            raise ValueError(f'危险命令未注册保护规则：{command_name}')
        return rule


@dataclass(frozen=True)
class DangerousCommandResultBuilder:
    """
    危险命令结果构建器。

    该对象负责统一构建危险命令拒绝结果，避免保护服务内部继续拼装
    结构化负载细节。
    """

    @staticmethod
    def build_guard_reject_result(message: str, hint: str) -> CommandResult:
        """
        构建危险命令拒绝结果。

        :param message: 拒绝原因
        :param hint: 补充提示
        :return: 命令拒绝结果
        """
        return CommandResult(
            data={
                'ok': False,
                'message': message,
                'hint': hint,
            },
            exit_code=GUARD_REJECTED,
        )


@dataclass(frozen=True)
class DangerousCommandConfirmationService:
    """
    危险命令确认服务。

    该对象负责处理 TTY 检测、确认提示与交互取消异常收口。

    :param result_builder: 危险命令结果构建器
    """

    result_builder: DangerousCommandResultBuilder

    def confirm(self, ctx: CliContext, *, command_name: str) -> CommandResult | None:
        """
        执行危险命令交互确认。

        :param ctx: CLI 上下文
        :param command_name: 命令唯一标识
        :return: 拒绝结果或 None
        """
        if ctx.yes:
            return None

        if not sys.stdin.isatty():
            return self.result_builder.build_guard_reject_result(
                f'已取消危险命令执行：{command_name}',
                '当前命令需要交互确认；如需非交互执行，请传入 --yes',
            )

        try:
            confirmed = typer.confirm(
                f'确认执行危险命令 `{command_name}` 吗？ 当前环境：{ctx.env}{"（dry-run）" if ctx.dry_run else ""}',
                default=False,
            )
        except (click.Abort, EOFError, KeyboardInterrupt):
            return self.result_builder.build_guard_reject_result(
                f'已取消危险命令执行：{command_name}',
                '当前命令需要交互确认；如需非交互执行，请传入 --yes',
            )
        if confirmed:
            return None

        return self.result_builder.build_guard_reject_result(
            f'已取消危险命令执行：{command_name}',
            '如需跳过确认，请传入 --yes',
        )


@dataclass
class DangerousCommandGuardService:
    """
    危险命令保护执行服务。

    该服务负责根据命令规则和 CLI 上下文执行生产环境保护、交互确认
    与拒绝结果收口。

    :param rule_registry: 危险命令规则注册表
    :param result_builder: 危险命令结果构建器
    :param confirmation_service: 危险命令确认服务
    """

    rule_registry: DangerousCommandRuleRegistry
    result_builder: DangerousCommandResultBuilder = field(default_factory=DangerousCommandResultBuilder)
    confirmation_service: DangerousCommandConfirmationService = field(init=False)

    def __post_init__(self) -> None:
        """
        初始化危险命令保护服务依赖。

        :return: None
        """
        self.confirmation_service = DangerousCommandConfirmationService(self.result_builder)

    def guard(self, ctx: CliContext, *, rule: DangerousCommandRule) -> CommandResult | None:
        """
        执行危险命令保护与确认。

        :param ctx: CLI 上下文
        :param rule: 危险命令规则
        :return: 拒绝结果或 None
        """
        command_name = rule.command_name
        if ctx.env == 'prod' and not ctx.allow_prod:
            return self.result_builder.build_guard_reject_result(
                f'生产环境默认禁止直接执行危险命令：{command_name}',
                '如确认执行，请传入 --allow-prod；如需跳过确认，请同时传入 --yes',
            )

        return self.confirmation_service.confirm(ctx, command_name=command_name)


DEFAULT_DANGEROUS_COMMAND_RULES: dict[str, DangerousCommandRule] = {
    'cache clear': DangerousCommandRule(command_name='cache clear', risk_level='high', supports_dry_run=True),
    'cache warmup': DangerousCommandRule(command_name='cache warmup', risk_level='normal', supports_dry_run=False),
    'db upgrade': DangerousCommandRule(command_name='db upgrade', risk_level='high', supports_dry_run=True),
    'db init': DangerousCommandRule(command_name='db init', risk_level='high', supports_dry_run=True),
    'db downgrade': DangerousCommandRule(command_name='db downgrade', risk_level='high', supports_dry_run=True),
    'db revision': DangerousCommandRule(command_name='db revision', risk_level='high', supports_dry_run=True),
    'config set': DangerousCommandRule(command_name='config set', risk_level='high', supports_dry_run=True),
    'config sync-cache': DangerousCommandRule(
        command_name='config sync-cache',
        risk_level='normal',
        supports_dry_run=False,
    ),
    'crypto rotate': DangerousCommandRule(command_name='crypto rotate', risk_level='high', supports_dry_run=True),
    'job run-once': DangerousCommandRule(command_name='job run-once', risk_level='normal', supports_dry_run=False),
    'job pause': DangerousCommandRule(command_name='job pause', risk_level='normal', supports_dry_run=False),
    'job resume': DangerousCommandRule(command_name='job resume', risk_level='normal', supports_dry_run=False),
    'job sync': DangerousCommandRule(command_name='job sync', risk_level='normal', supports_dry_run=False),
    'gen import-table': DangerousCommandRule(command_name='gen import-table', risk_level='high', supports_dry_run=True),
    'gen create-table': DangerousCommandRule(command_name='gen create-table', risk_level='high', supports_dry_run=True),
    'gen export': DangerousCommandRule(command_name='gen export', risk_level='high', supports_dry_run=True),
    'gen sync-db': DangerousCommandRule(command_name='gen sync-db', risk_level='normal', supports_dry_run=False),
}

DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY = DangerousCommandRuleRegistry(rules=DEFAULT_DANGEROUS_COMMAND_RULES)
DEFAULT_DANGEROUS_COMMAND_GUARD = DangerousCommandGuardService(rule_registry=DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY)
