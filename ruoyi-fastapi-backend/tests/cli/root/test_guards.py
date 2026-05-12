import importlib
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(BACKEND_DIR))
cli_guards = importlib.import_module('cli.guards')
cli_guards = importlib.reload(cli_guards)

DEFAULT_DANGEROUS_COMMAND_RULES = cli_guards.DEFAULT_DANGEROUS_COMMAND_RULES
DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY = cli_guards.DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY


def test_dangerous_command_rules_cover_expected_commands() -> None:
    """
    校验危险命令规则表已覆盖当前设计文档中约定的命令范围。

    :return: None
    """
    assert set(DEFAULT_DANGEROUS_COMMAND_RULES) == {
        'cache clear',
        'cache warmup',
        'db upgrade',
        'db init',
        'db downgrade',
        'db revision',
        'config set',
        'config sync-cache',
        'crypto rotate',
        'job run-once',
        'job pause',
        'job resume',
        'job sync',
        'gen import-table',
        'gen create-table',
        'gen export',
        'gen sync-db',
    }


def test_dangerous_command_rules_expose_risk_level_and_dry_run_metadata() -> None:
    """
    校验危险命令规则能够提供风险级别和 dry-run 能力元数据。

    :return: None
    """
    db_upgrade_rule = DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY.get_rule('db upgrade')
    cache_warmup_rule = DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY.get_rule('cache warmup')

    assert db_upgrade_rule is not None
    assert db_upgrade_rule.risk_level == 'high'
    assert db_upgrade_rule.supports_dry_run is True

    assert cache_warmup_rule is not None
    assert cache_warmup_rule.risk_level == 'normal'
    assert cache_warmup_rule.supports_dry_run is False


def test_require_dangerous_command_rule_rejects_unknown_command() -> None:
    """
    校验未注册的危险命令名称会被显式拒绝。

    :return: None
    """
    with pytest.raises(ValueError, match='危险命令未注册保护规则'):
        DEFAULT_DANGEROUS_COMMAND_RULE_REGISTRY.require_rule('unknown dangerous command')
