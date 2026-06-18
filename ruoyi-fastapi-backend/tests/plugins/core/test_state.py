import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.state import PluginStateResolver, PluginStateSnapshot, PluginStateTransitionTable  # noqa: E402


def test_state_resolver_returns_discovered_without_installed_version() -> None:
    """
    校验未安装且启用的插件会解析为 discovered。

    :return: None
    """
    status = PluginStateResolver.resolve(
        PluginStateSnapshot(
            source_version='1.0.0',
            installed_version=None,
            enabled=True,
        )
    )

    assert status == 'discovered'


def test_state_resolver_returns_disabled_when_plugin_is_not_enabled() -> None:
    """
    校验停用插件会解析为 disabled。

    :return: None
    """
    status = PluginStateResolver.resolve(
        PluginStateSnapshot(
            source_version='1.0.0',
            installed_version='1.0.0',
            enabled=False,
        )
    )

    assert status == 'disabled'


def test_state_resolver_returns_pending_upgrade_for_newer_source_version() -> None:
    """
    校验源码版本高于已安装版本时会解析为 pending_upgrade。

    :return: None
    """
    status = PluginStateResolver.resolve(
        PluginStateSnapshot(
            source_version='1.1.0',
            installed_version='1.0.0',
            enabled=True,
        )
    )

    assert status == 'pending_upgrade'


def test_state_resolver_keeps_error_status() -> None:
    """
    校验异常状态优先保留。

    :return: None
    """
    status = PluginStateResolver.resolve(
        PluginStateSnapshot(
            source_version='1.1.0',
            installed_version='1.0.0',
            enabled=True,
            current_status='error',
        )
    )

    assert status == 'error'


def test_state_resolver_prefers_database_enabled_value() -> None:
    """
    校验数据库启停值优先于 manifest 默认值。

    :return: None
    """
    database_plugin = type('DatabasePlugin', (), {'enabled': '1', 'status': 'installed'})()

    assert PluginStateResolver.is_enabled(True, database_plugin) is False


def test_state_resolver_disables_error_database_plugin() -> None:
    """
    校验异常状态插件不会被运行时视为启用。

    :return: None
    """
    database_plugin = type('DatabasePlugin', (), {'enabled': '0', 'status': 'error'})()

    assert PluginStateResolver.is_enabled(True, database_plugin) is False


def test_state_resolver_reports_database_plugin_enabled() -> None:
    """
    校验数据库插件启用状态可被统一解析。

    :return: None
    """
    database_plugin = type('DatabasePlugin', (), {'enabled': '0', 'status': 'installed'})()

    assert PluginStateResolver.is_database_plugin_enabled(database_plugin) is True


def test_state_resolver_reports_error_database_plugin_disabled() -> None:
    """
    校验异常数据库插件即使启停值为启用也会被视为不可用。

    :return: None
    """
    database_plugin = type('DatabasePlugin', (), {'enabled': '0', 'status': 'error'})()

    assert PluginStateResolver.is_database_plugin_enabled(database_plugin) is False


def test_state_transition_table_resolves_install_target() -> None:
    """
    校验状态流转表可解析首次安装后的目标状态。

    :return: None
    """
    assert PluginStateTransitionTable.resolve_target('discovered', 'install') == 'installed'
    assert PluginStateTransitionTable.resolve_target('discovered', 'install_disabled') == 'disabled'


def test_state_transition_table_allows_discovered_plugin_disable() -> None:
    """
    校验未安装但已发现的插件可被显式停用。

    :return: None
    """
    assert PluginStateTransitionTable.resolve_target('discovered', 'disable') == 'disabled'


def test_state_transition_table_resolves_failure_target() -> None:
    """
    校验状态流转表会将失败操作解析为 error。

    :return: None
    """
    assert PluginStateTransitionTable.resolve_target('installed', 'mark_error') == 'error'
    assert PluginStateTransitionTable.resolve_target('pending_upgrade', 'mark_error') == 'error'


def test_state_transition_table_rejects_invalid_transition() -> None:
    """
    校验状态流转表会拒绝不允许的状态操作。

    :return: None
    """
    assert PluginStateTransitionTable.can_transition('discovered', 'upgrade') is False


def test_state_resolver_matches_transition_table_for_representative_snapshots() -> None:
    """
    校验状态解析器与流转表在代表性状态上保持一致。

    :return: None
    """
    cases = [
        (
            None,
            'discover',
            PluginStateSnapshot(source_version='1.0.0', installed_version=None, enabled=True),
        ),
        (
            'discovered',
            'install',
            PluginStateSnapshot(source_version='1.0.0', installed_version='1.0.0', enabled=True),
        ),
        (
            'discovered',
            'install_disabled',
            PluginStateSnapshot(source_version='1.0.0', installed_version='1.0.0', enabled=False),
        ),
        (
            'installed',
            'disable',
            PluginStateSnapshot(source_version='1.0.0', installed_version='1.0.0', enabled=False),
        ),
        (
            'disabled',
            'enable',
            PluginStateSnapshot(source_version='1.0.0', installed_version='1.0.0', enabled=True),
        ),
        (
            'installed',
            'upgrade_available',
            PluginStateSnapshot(source_version='1.1.0', installed_version='1.0.0', enabled=True),
        ),
        (
            'disabled',
            'upgrade_available',
            PluginStateSnapshot(source_version='1.1.0', installed_version='1.0.0', enabled=False),
        ),
    ]

    for source, operation, snapshot in cases:
        assert PluginStateResolver.resolve(snapshot) == PluginStateTransitionTable.resolve_target(source, operation)


def test_state_transition_table_lists_described_transitions() -> None:
    """
    校验状态流转表暴露带说明的规则列表。

    :return: None
    """
    transitions = PluginStateTransitionTable.list_transitions()

    assert transitions
    assert all(transition.description for transition in transitions)
