from dataclasses import dataclass
from typing import Literal

from cli.guards import DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY, DangerousCommandRuleRegistry

CommandRiskLevel = Literal['readonly', 'normal', 'high']


@dataclass(frozen=True)
class CommandRiskSpec:
    """
    CLI 命令风险元数据定义。

    :param command_name: 命令唯一标识
    :param risk_level: 风险级别
    :param supports_dry_run: 是否支持演练执行
    """

    command_name: str
    risk_level: CommandRiskLevel
    supports_dry_run: bool


@dataclass(frozen=True)
class CommandRiskSpecRegistry:
    """
    CLI 命令风险元数据注册表。

    该注册表负责从危险命令规则注册表派生风险元数据，供 TUI、文档、
    诊断提示等只读场景统一查询。

    :param specs: 按命令名索引的风险元数据表
    """

    specs: dict[str, CommandRiskSpec]

    def get_spec(self, command_name: str) -> CommandRiskSpec | None:
        """
        获取指定命令的风险元数据。

        :param command_name: 命令唯一标识
        :return: 风险元数据，不存在时返回 None
        """
        return self.specs.get(command_name)


class CommandRiskSpecRegistryBuilder:
    """
    CLI 命令风险元数据注册表构建器。

    该构建器负责基于危险命令规则注册表生成命令风险元数据注册表，
    避免模块导入阶段散落重复的字典推导逻辑。
    """

    @staticmethod
    def build(rule_registry: DangerousCommandRuleRegistry) -> CommandRiskSpecRegistry:
        """
        基于危险命令规则注册表构建风险元数据注册表。

        :param rule_registry: 危险命令规则注册表
        :return: 风险元数据注册表
        """
        return CommandRiskSpecRegistry(
            specs={
                command_name: CommandRiskSpec(
                    command_name=rule.command_name,
                    risk_level=rule.risk_level,
                    supports_dry_run=rule.supports_dry_run,
                )
                for command_name, rule in rule_registry.rules.items()
            }
        )


COMMAND_RISK_SPEC_REGISTRY = CommandRiskSpecRegistryBuilder.build(DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY)
