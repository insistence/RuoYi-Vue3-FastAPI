from types import SimpleNamespace

from plugins.core.state import PluginStateResolver, PluginStateSnapshot, PluginStateTransitionTable


def test_state_resolver_covers_lifecycle_states() -> None:
    """校验插件状态解析器覆盖全部生命周期状态。"""
    cases = [
        (PluginStateSnapshot(source_version='1.0.0', installed_version=None, enabled=True), 'discovered'),
        (PluginStateSnapshot(source_version='1.0.0', installed_version='1.0.0', enabled=False), 'installed'),
        (PluginStateSnapshot(source_version='1.1.0', installed_version='1.0.0', enabled=True), 'pending_upgrade'),
        (
            PluginStateSnapshot(
                source_version='1.1.0',
                installed_version='1.0.0',
                enabled=True,
                current_status='error',
            ),
            'error',
        ),
    ]

    assert [PluginStateResolver.resolve(snapshot) for snapshot, _expected in cases] == [
        expected for _snapshot, expected in cases
    ]


def test_state_resolver_enables_only_installed_healthy_database_plugins() -> None:
    """校验状态解析器只启用已安装且健康的数据库插件。"""
    cases = [
        (SimpleNamespace(enabled='0', status='installed', installed_version='1.0.0'), True),
        (SimpleNamespace(enabled='1', status='installed', installed_version='1.0.0'), False),
        (SimpleNamespace(enabled='0', status='error', installed_version='1.0.0'), False),
        (SimpleNamespace(enabled='0', status='discovered', installed_version=None), False),
    ]

    assert [PluginStateResolver.is_enabled(plugin) for plugin, _expected in cases] == [
        expected for _plugin, expected in cases
    ]


def test_database_enabled_state_respects_error_status() -> None:
    """校验数据库启用状态不会覆盖插件错误状态。"""
    cases = [
        (SimpleNamespace(enabled='0', status='installed'), True),
        (SimpleNamespace(enabled='0', status='error'), False),
    ]

    assert [PluginStateResolver.is_database_plugin_enabled(plugin) for plugin, _expected in cases] == [
        expected for _plugin, expected in cases
    ]


def test_state_transition_table_covers_supported_and_rejected_operations() -> None:
    """校验状态转换表覆盖支持与拒绝的操作。"""
    supported_cases = [
        ('discovered', 'install', 'installed'),
        ('discovered', 'disable', 'discovered'),
        ('installed', 'mark_error', 'error'),
        ('pending_upgrade', 'mark_error', 'error'),
    ]

    assert [
        PluginStateTransitionTable.resolve_target(source, operation) for source, operation, _expected in supported_cases
    ] == [expected for _source, _operation, expected in supported_cases]
    assert PluginStateTransitionTable.can_transition('discovered', 'upgrade') is False
    assert PluginStateTransitionTable.can_transition('error', 'enable') is False


def test_state_resolver_and_transition_table_remain_consistent() -> None:
    """校验状态解析器与转换表保持一致。"""
    cases = [
        (None, 'discover', PluginStateSnapshot(source_version='1.0.0', installed_version=None, enabled=True)),
        (
            'discovered',
            'install',
            PluginStateSnapshot(source_version='1.0.0', installed_version='1.0.0', enabled=True),
        ),
        (
            'installed',
            'upgrade_available',
            PluginStateSnapshot(source_version='1.1.0', installed_version='1.0.0', enabled=True),
        ),
    ]

    for source, operation, snapshot in cases:
        assert PluginStateResolver.resolve(snapshot) == PluginStateTransitionTable.resolve_target(source, operation)

    transitions = PluginStateTransitionTable.list_transitions()
    assert transitions
    assert all(transition.description for transition in transitions)
